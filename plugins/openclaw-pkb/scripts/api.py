#!/usr/bin/env python3
"""
PKB 知识库 HTTP 客户端（与 openclaw-nextcloud 的 api 相互独立）。

模块分层（阅读顺序）：
  1) 文件顶部：超时常量、环境加载、FileSaaS 配置解析（与 PKB_API_KEY 不同套凭证）；
  2) normalize_nextcloud_path：与 nextcloud 插件同语义，保证 PKB 资源名与网盘路径一致；
  3) PKBAPI：
       - 会话/问答 ask（SSE）；
       - 资源上传 upload_resource：FileSaaS 拿 file_key → PKB 登记 file_saas；
       - sync_file：删旧索引再 upload，供桥「更新」语义；
       - delete / list / wait_resource_indexed：维护与流水线等待。

被谁调用：openclaw_bridge.py（插件）、main.py（CLI）、get_api()（依赖 config.py）。
"""

from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

import requests

# (connect_timeout, read_timeout) 秒
_HTTP_TIMEOUT = (15, 120)
_HTTP_STREAM_TIMEOUT = (20, 300)
_FILESAAS_UPLOAD_TIMEOUT = (15, 600)
_PKB_RESOURCE_POST_TIMEOUT = (15, 120)


def _ensure_env_loaded() -> None:
    """加载插件根目录 .env，使 FILESAAS_* 等在子进程中可用。"""
    from config import PKBConfig

    PKBConfig._load_from_env_file()


def _apply_filesaas_from_plugin_config_json() -> None:
    """
    若 FILESAAS_* 仍未设置，从插件根目录 config.json 的 fileSaaS 块写入 os.environ。

    与仓库内 config.json 字段对齐：appId、appSecret、tenantId（或 tenant）、uploadServer（或 server）。
    已存在的环境变量不被覆盖（便于 .env / 系统环境优先）。
    """
    cfg_path = Path(__file__).resolve().parent.parent / "config.json"
    if not cfg_path.is_file():
        return
    try:
        raw = json.loads(cfg_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return
    fs = raw.get("fileSaaS") or raw.get("file_saas")
    if not isinstance(fs, dict):
        return
    tenant = fs.get("tenant") or fs.get("tenantId")
    server = fs.get("server") or fs.get("uploadServer")
    pairs = [
        ("FILESAAS_APP_ID", fs.get("appId")),
        ("FILESAAS_APP_SECRET", fs.get("appSecret")),
        ("FILESAAS_TENANT", tenant),
        ("FILESAAS_SERVER", server),
    ]
    for key, val in pairs:
        if val is None or val == "":
            continue
        s = str(val).strip()
        if not s:
            continue
        if not os.environ.get(key):
            os.environ[key] = s


def _filesaas_settings() -> tuple[str, str, str, str]:
    """
    FileSaaS 与 PKB API（PKB_BASE_URL / PKB_API_KEY）是两套凭证，见 upload_resource 注释。

    优先级：已设置的环境变量 > 插件目录 .env > 插件目录 config.json 的 fileSaaS。
    """
    _ensure_env_loaded()
    _apply_filesaas_from_plugin_config_json()
    app_id = os.getenv("FILESAAS_APP_ID", "tct-pkb-api").strip()
    secret = os.getenv("FILESAAS_APP_SECRET", "").strip()
    tenant = os.getenv("FILESAAS_TENANT", "tct-pkb").strip()
    server = os.getenv("FILESAAS_SERVER", "").strip()
    if not secret:
        raise ValueError(
            "缺少 FileSaaS 配置：需要 FILESAAS_APP_SECRET。"
            "可在 openclaw-pkb/.env、插件根目录 config.json 的 fileSaaS.appSecret，"
            "或 OpenClaw 的 plugins.entries.pkb.config.fileSaaS.appSecret 中设置。"
        )
    if not server:
        raise ValueError(
            "缺少 FileSaaS 配置：需要 FILESAAS_SERVER（上传服务主机名，不含 https://）。"
            "可在 .env、config.json 的 fileSaaS.uploadServer，或 pkb.config.fileSaaS.server 中设置。"
        )
    return app_id, secret, tenant, server


def normalize_nextcloud_path(path: str) -> str:
    """
    尝试修复「UTF-8 字节被误当成 Latin-1 解码」导致的乱码路径（按路径段 / 分段处理）。

    已是正常 UTF-8（含中文）的路径保持不变：含超出 Latin-1 的字符时 encode 会失败并退回原文。
    若乱码中部分字节被替换为 '_' 等字符，原始 UTF-8 已损坏，则无法自动恢复。
    """
    if not path:
        return path

    had_leading = path.startswith("/")
    raw = path.lstrip("/")
    if not raw:
        return path

    def _has_cjk(s: str) -> bool:
        for ch in s:
            o = ord(ch)
            if 0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF:
                return True
        return False

    def _recover_segment(seg: str) -> str:
        if not seg or seg.isascii():
            return seg
        try:
            recovered = seg.encode("latin-1").decode("utf-8")
        except (UnicodeDecodeError, UnicodeEncodeError):
            return seg
        if recovered == seg:
            return seg
        if _has_cjk(recovered) and not _has_cjk(seg):
            return recovered
        return seg

    out = "/".join(_recover_segment(p) for p in raw.split("/"))
    if had_leading:
        return "/" + out
    return out


class PKBAPI:
    """
    PKB 后端会话：默认请求头带 Bearer(api_key) 与 X-PROVIDER-USER-ID(user_id)。

    provider_resource_id：问答溯源用，内嵌 base64(JSON) 保存 path + Nextcloud 公开 url（若有）。
    """

    def __init__(self, base_url: str, api_key: str, user_id: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.user_id = user_id
        self.session = requests.Session()
        # 勿在 Session 层写死 Content-Type：GET（如 list_resources）带 application/json
        # 时，部分网关会返回 400；POST 使用 requests.post(..., json=...) 会自动带 JSON 类型。
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "X-PROVIDER-USER-ID": user_id,
        })
    
    def create_chat_session(self) -> str:
        """创建问答会话"""
        url = f"{self.base_url}/api/v1/tct-knowledge-base/chat-sessions"
        data = {"title": None}
        
        response = self.session.post(url, json=data, timeout=_HTTP_TIMEOUT)
        response.raise_for_status()
        
        session_id = response.json()["data"]["id"]
        return session_id
    
    def _normalize_resource_name(self, resource_name: str) -> str:
        return normalize_nextcloud_path(resource_name).lstrip("/")

    def _build_provider_resource_id(self, resource_name: str, source_url: str = "") -> str:
        meta = {
            "resource_name": self._normalize_resource_name(resource_name),
            "path": self._normalize_resource_name(resource_name),
            "url": source_url or "",
        }
        encoded = base64.urlsafe_b64encode(
            json.dumps(meta, ensure_ascii=False).encode("utf-8")
        ).decode("ascii")
        return f"{self.user_id}:ocmeta:{encoded}"

    @staticmethod
    def _parse_provider_resource_id(provider_resource_id: str) -> Dict[str, str]:
        if not provider_resource_id:
            return {"path": "", "url": ""}

        parts = provider_resource_id.split(":", 2)
        if len(parts) == 3 and parts[1] == "ocmeta":
            try:
                padding = "=" * (-len(parts[2]) % 4)
                decoded = base64.urlsafe_b64decode(parts[2] + padding).decode("utf-8")
                data = json.loads(decoded)
                return {
                    "path": normalize_nextcloud_path(data.get("path", "")).lstrip("/"),
                    "url": data.get("url", "") or "",
                }
            except Exception:
                return {"path": "", "url": ""}

        # 兼容旧格式：user_id:path
        if ":" in provider_resource_id:
            _, path = provider_resource_id.split(":", 1)
            return {
                "path": normalize_nextcloud_path(path).lstrip("/"),
                "url": "",
            }

        return {"path": "", "url": ""}

    def _iter_all_resources(self, size: int = 30):
        page = 1
        while True:
            result = self.list_resources(page=page, size=size)
            for item in result.get("resources", []):
                yield item
            if page >= result.get("pages", 1):
                break
            page += 1

    def _find_resource_matches(self, resource_name: str) -> list[Dict[str, Any]]:
        normalized_name = self._normalize_resource_name(resource_name)
        exact_matches: list[Dict[str, Any]] = []
        fuzzy_matches: list[Dict[str, Any]] = []

        for item in self._iter_all_resources():
            name = self._normalize_resource_name(item.get("name", ""))
            if name == normalized_name:
                exact_matches.append(item)
            elif normalized_name and normalized_name in name:
                fuzzy_matches.append(item)

        return exact_matches or fuzzy_matches

    def ask(self, question: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        提问并获取答案
        
        返回格式:
        {
            "answer": "回答内容",
            "sources": [{"name": "文件名", "url": "链接"}]
        }
        """
        if session_id is None:
            session_id = self.create_chat_session()
        
        url = f"{self.base_url}/api/v1/tct-knowledge-base/chat-sessions/{session_id}/messages/stream"
        data = {"message": question}
        
        # 收集所有响应
        response_text = ""
        citations = []
        
        # 使用流式请求
        response = self.session.post(url, json=data, stream=True, timeout=_HTTP_STREAM_TIMEOUT)
        response.raise_for_status()
        
        for line in response.iter_lines():
            if line:
                line = line.decode('utf-8')
                if line.startswith('data: '):
                    json_str = line[6:]
                    try:
                        event_data = json.loads(json_str)
                        event = event_data.get("data", {}).get("event", "")
                        
                        if event == "content":
                            text = event_data.get("data", {}).get("text", "")
                            response_text += text
                        elif event == "citations":
                            citations = event_data.get("data", {}).get("citations", [])
                    except:
                        pass
        
        # 处理 citations，生成链接
        sources = []
        for cit in citations:
            name = cit.get("resource_name", "Unknown")
            pid = cit.get("provider_resource_id", "")
            parsed = self._parse_provider_resource_id(pid)
            sources.append({
                "name": name,
                "path": parsed.get("path", ""),
                "url": parsed.get("url", ""),
            })
        
        return {
            "answer": response_text,
            "sources": sources,
            "session_id": session_id
        }
    
    def upload_resource(self, file_path: str, resource_name: str, source_url: str = "") -> bool:
        """
        上传文件到知识库：两段链路，与 PKB 登录凭证无关。

        1) 字节流 POST 到 FileSaaS（HMAC 签名，FILESAAS_*），得到 file_key；
        2) 再 POST PKB API（Bearer PKB_API_KEY），payload 内携带 file_saas.file_key。

        因此仅有 PKB_BASE_URL / PKB_API_KEY / PKB_USER_ID 无法完成第 1 步，必须另有 FileSaaS 配置。
        """
        import hmac
        import hashlib
        import base64
        import uuid
        import time
        import mimetypes

        resource_name = self._normalize_resource_name(resource_name)

        fs_app_id, fs_secret, fs_tenant, fs_server = _filesaas_settings()

        # 1. 上传到 FileSaaS
        timestamp = str(int(time.time()))
        nonce = str(uuid.uuid4()).replace("-", "")[:32]
        method = "POST"
        upload_path = f"/upload/{fs_tenant}"

        canonical_headers = (
            f"xtcl-algorithm:tcl2-hmac-sha256;xtcl-app:file-saas;xtcl-appid:{fs_app_id};"
            f"xtcl-nonce:{nonce};xtcl-timestamp:{timestamp};"
        )

        canonical_request = f"{method}\n{upload_path}\n\n{canonical_headers}\n"

        signature = base64.b64encode(
            hmac.new(fs_secret.encode(), canonical_request.encode(), hashlib.sha256).digest()
        ).decode()

        url = f"https://{fs_server}{upload_path}"
        headers = {
            "xtcl-timestamp": timestamp,
            "xtcl-app": "file-saas",
            "xtcl-nonce": nonce,
            "xtcl-appid": fs_app_id,
            "xtcl-algorithm": "tcl2-hmac-sha256",
            "xtcl-signature": signature,
        }

        mime_type, _ = mimetypes.guess_type(file_path)
        mime_type = mime_type or "application/octet-stream"
        upload_name = os.path.basename(resource_name) or resource_name

        with open(file_path, "rb") as f:
            files = {"file": (upload_name, f, mime_type)}
            response = requests.post(
                url, files=files, headers=headers, timeout=_FILESAAS_UPLOAD_TIMEOUT
            )

        if response.status_code != 200:
            raise Exception(f"FileSaaS 上传失败: {response.status_code} - {response.text[:500]}")

        data = response.json()
        file_key = data.get("data", {}).get("fileKey", "")

        if not file_key:
            raise Exception("FileSaaS 未返回 file_key")

        # 2. 创建 PKB 资源
        ext = resource_name.split(".")[-1].lower()
        is_image = ext in ["jpg", "jpeg", "png", "gif", "webp"]
        provider_resource_id = self._build_provider_resource_id(resource_name, source_url)

        if is_image:
            api_url = f"{self.base_url}/api/v1/tct-knowledge-base/resources/images"
            payload = {
                "provider_resource_id": provider_resource_id,
                "name": resource_name,
                "file_saas": {"file_key": file_key, "tenant_id": fs_tenant},
                "user_language": "zh-CN",
            }
        else:
            api_url = f"{self.base_url}/api/v1/tct-knowledge-base/resources/files"
            if ext == "pdf":
                resource_type = "pdf"
            elif ext in ["md", "markdown"]:
                resource_type = "markdown"
            else:
                resource_type = "text"

            payload = {
                "provider_resource_id": provider_resource_id,
                "name": resource_name,
                "file_resource_type": resource_type,
                "file_saas": {"file_key": file_key, "tenant_id": fs_tenant},
                "user_language": "zh-CN",
            }

        response = requests.post(
            api_url,
            json=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "X-PROVIDER-USER-ID": self.user_id,
                "Content-Type": "application/json",
            },
            timeout=_PKB_RESOURCE_POST_TIMEOUT,
        )

        if response.status_code not in (200, 201):
            if response.status_code == 400:
                try:
                    error = response.json()
                except Exception:
                    error = {}
                if error.get("code") == 1204:
                    # 资源已存在（例如与 sync 竞态）；视为成功，完整更新应使用 sync_file
                    return True
            raise Exception(f"PKB 创建失败: {response.status_code} - {response.text}")

        return True
    
    def delete_resource(self, resource_name: str) -> bool:
        """删除知识库中的资源"""
        resource_ids = [item["id"] for item in self._find_resource_matches(resource_name) if item.get("id")]
        if not resource_ids:
            raise Exception(f"资源不存在: {resource_name}")
        
        # 删除资源 - 使用 POST 带 resource_ids
        url = f"{self.base_url}/api/v1/tct-knowledge-base/resources"
        response = self.session.delete(
            url, json={"resource_ids": resource_ids}, timeout=_HTTP_TIMEOUT
        )

        if response.status_code not in (200, 204):
            raise Exception(f"删除失败: {response.status_code} - {response.text}")
        
        return True
    
    def sync_file(self, file_path: str, remote_path: str, source_url: str = "") -> bool:
        """
        同步文件到知识库（支持更新）
        如果资源已存在，先删除再重新创建
        """
        # 检查资源是否已存在
        resource_name = self._normalize_resource_name(remote_path)

        for r in self._find_resource_matches(resource_name):
            if self._normalize_resource_name(r["name"]) == resource_name:
                # 资源已存在，先删除
                print(f"  Resource exists, deleting first...")
                try:
                    self.delete_resource(resource_name)
                except Exception as e:
                    print(f"  Delete warning: {e}")
                break
        
        # 上传新文件
        return self.upload_resource(file_path, resource_name, source_url=source_url)

    def wait_resource_indexed(
        self,
        resource_name: str,
        timeout_seconds: int = 60,
        interval_seconds: int = 2,
    ) -> Dict[str, Any]:
        """轮询直到资源出现在列表中。"""
        normalized_name = self._normalize_resource_name(resource_name)
        started_at = time.monotonic()

        while True:
            matches = self._find_resource_matches(normalized_name)
            for item in matches:
                if self._normalize_resource_name(item.get("name", "")) == normalized_name:
                    status = str(item.get("status", "") or "").lower()
                    status_ready = status in {"", "completed", "complete", "ready", "done", "success", "indexed"}
                    if not status_ready:
                        continue
                    return {
                        "success": True,
                        "indexed": True,
                        "resource_name": normalized_name,
                        "elapsed_seconds": round(time.monotonic() - started_at, 2),
                        "resource": item,
                    }

            if time.monotonic() - started_at >= timeout_seconds:
                return {
                    "success": False,
                    "indexed": False,
                    "resource_name": normalized_name,
                    "elapsed_seconds": round(time.monotonic() - started_at, 2),
                }

            time.sleep(max(interval_seconds, 1))
    
    def list_resources(self, page: int = 1, size: int = 20) -> Dict[str, Any]:
        """
        列出知识库中的所有资源
        
        返回格式:
        {
            "resources": [
                {
                    "id": "resource_xxx",
                    "name": "文件名",
                    "type": "pdf/text/image",
                    "summary": "摘要",
                    "created_at": timestamp
                }
            ],
            "total": 24,
            "page": 1,
            "pages": 5
        }
        """
        url = f"{self.base_url}/api/v1/tct-knowledge-base/resources"
        params = {"page": page, "size": size}
        
        response = self.session.get(url, params=params, timeout=_HTTP_TIMEOUT)
        if not response.ok:
            body = (response.text or "")[:2000]
            raise Exception(
                f"PKB list_resources 失败: HTTP {response.status_code} url={url} params={params} body={body}"
            )

        data = response.json()
        
        resources = []
        for item in data.get("data", {}).get("items", []):
            resources.append({
                "id": item.get("id", ""),
                "name": item.get("name", ""),
                "type": item.get("resource_type", ""),
                "status": item.get("status", ""),
                "summary": item.get("summary", "")[:200] if item.get("summary") else "",
                "description": item.get("image_description", "")[:200] if item.get("image_description") else "",
                "created_at": item.get("created_at", 0)
            })
        
        return {
            "resources": resources,
            "total": data.get("data", {}).get("total", 0),
            "page": data.get("data", {}).get("page", 1),
            "pages": data.get("data", {}).get("pages", 1)
        }


def get_api() -> "PKBAPI":
    """获取 API 实例"""
    # 延迟导入，避免循环依赖
    import sys
    from pathlib import Path
    script_dir = Path(__file__).parent
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))
    
    from config import get_config
    config = get_config()
    return PKBAPI(config.base_url, config.api_key, config.user_id)
