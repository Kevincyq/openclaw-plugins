#!/usr/bin/env python3
"""
Nextcloud 网盘 API（WebDAV + OCS 分享）

路径模型：remote.php/dav/files/{username}/{quote(utf8_path)}，与 openclaw-pkb 里资源名对齐时请用
同一套 normalize_nextcloud_path（本文件与 pkb 各有一份副本，语义保持一致）。

主要方法：upload(PUT)、download(GET)、write_text(PUT)、delete(DELETE)、list(PROPFIND)、
share/create_share_link(OCS POST)、get_share_link(OCS GET)。
"""

import os
import requests
from typing import Optional, List, Dict, Tuple
from urllib.parse import quote, unquote
import xml.etree.ElementTree as ET

# (connect, read) 秒；大文件上传放宽读超时
_NC_HTTP_TIMEOUT = (15, 120)
_NC_UPLOAD_TIMEOUT = (15, 600)


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


class NextcloudAPI:
    """
    使用应用专用密码（app_password）做 HTTP Basic，访问用户文件空间。
    OCS-APIREQUEST 头为 Nextcloud 对分享等接口的常规要求。
    """

    def __init__(self, base_url: str, username: str, app_password: str):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.app_password = app_password
        self.session = requests.Session()
        self.session.auth = (username, app_password)
        self.session.headers.update({
            "OCS-APIREQUEST": "true"
        })
    
    def _dav_url(self, path: str) -> str:
        """构建 WebDAV URL"""
        path = normalize_nextcloud_path(path).lstrip("/")
        return f"{self.base_url}/remote.php/dav/files/{self.username}/{quote(path)}"
    
    def list_files(self, path: str = "/") -> List[Dict[str, str]]:
        """列出目录下的文件"""
        path = normalize_nextcloud_path(path)
        url = self._dav_url(path)
        response = self.session.request(
            "PROPFIND",
            url,
            headers={"Depth": "1"},
            timeout=_NC_HTTP_TIMEOUT,
        )
        response.raise_for_status()
        
        files = []
        root = ET.fromstring(response.content)
        ns = {'d': 'DAV:'}
        
        for resp in root.findall('.//d:response', ns):
            href = resp.find('d:href', ns)
            if href is None:
                continue
            
            file_path = href.text.replace(f"/remote.php/dav/files/{self.username}/", "")
            file_path = unquote(file_path)
            compare_path = path.lstrip("/")
            if file_path.rstrip('/') == compare_path.rstrip('/') or not file_path:
                continue
            
            # 获取文件信息
            resource_type = resp.find('.//d:resourcetype/d:collection', ns)
            is_dir = resource_type is not None
            
            content_length = resp.find('.//d:getcontentlength', ns)
            size = int(content_length.text) if content_length is not None else 0
            
            files.append({
                "name": os.path.basename(file_path),
                "path": file_path,
                "size": size,
                "is_dir": is_dir
            })
        
        return files
    
    def upload_file(self, local_path: str, remote_path: str) -> Dict:
        """
        上传文件
        """
        remote_path = normalize_nextcloud_path(remote_path)
        url = self._dav_url(remote_path)
        file_name = os.path.basename(remote_path.lstrip("/"))
        
        with open(local_path, "rb") as f:
            response = self.session.put(url, data=f, timeout=_NC_UPLOAD_TIMEOUT)
        
        if response.status_code not in (201, 204):
            raise Exception(f"上传失败: {response.status_code} - {response.text}")
        
        result = {
            "success": True,
            "remote_path": remote_path,
            "file_name": file_name,
            "message": f"✅ 文件已上传至 Nextcloud: {file_name}"
        }
        return result
    
    def download_file(self, remote_path: str, local_path: str) -> bool:
        """下载文件"""
        remote_path = normalize_nextcloud_path(remote_path)
        url = self._dav_url(remote_path)
        response = self.session.get(url, timeout=_NC_UPLOAD_TIMEOUT)
        response.raise_for_status()

        with open(local_path, "wb") as f:
            f.write(response.content)
        return True

    def write_text_file(self, remote_path: str, text: str) -> Dict:
        """直接在 Nextcloud 创建或覆盖文本文件。"""
        remote_path = normalize_nextcloud_path(remote_path)
        url = self._dav_url(remote_path)
        file_name = os.path.basename(remote_path.lstrip("/"))

        response = self.session.put(url, data=text.encode("utf-8"), timeout=_NC_HTTP_TIMEOUT)
        if response.status_code not in (201, 204):
            raise Exception(f"写入失败: {response.status_code} - {response.text}")

        result = {
            "success": True,
            "remote_path": remote_path,
            "file_name": file_name,
            "message": f"✅ 文本文件已写入 Nextcloud: {file_name}",
        }
        return result

    def delete_file(self, remote_path: str) -> Dict:
        """
        删除文件
        """
        remote_path = normalize_nextcloud_path(remote_path)
        url = self._dav_url(remote_path)
        file_name = os.path.basename(remote_path.lstrip("/"))
        
        response = self.session.delete(url, timeout=_NC_HTTP_TIMEOUT)
        response.raise_for_status()
        
        result = {
            "success": True,
            "remote_path": remote_path,
            "file_name": file_name,
            "message": f"✅ 文件已从 Nextcloud 删除: {file_name}"
        }
        return result
    
    def create_share_link(self, path: str) -> str:
        """创建分享链接"""
        path = normalize_nextcloud_path(path)
        url = f"{self.base_url}/ocs/v2.php/apps/files_sharing/api/v1/shares"
        data = {
            "path": path,
            "shareType": 3  # 公开链接
        }
        
        response = self.session.post(url, json=data, timeout=_NC_HTTP_TIMEOUT)
        response.raise_for_status()
        
        # 解析返回的分享链接 - 不使用命名空间
        root = ET.fromstring(response.content)
        url_elem = root.find('.//url')
        
        if url_elem is None:
            raise Exception("创建分享链接失败")
        
        return url_elem.text
    
    def get_share_link(self, path: str) -> Optional[str]:
        """获取已存在的分享链接"""
        path = normalize_nextcloud_path(path)
        url = f"{self.base_url}/ocs/v2.php/apps/files_sharing/api/v1/shares?path={quote(path)}&share_type=3"
        response = self.session.get(url, timeout=_NC_HTTP_TIMEOUT)

        if response.status_code != 200:
            return None

        root = ET.fromstring(response.content)
        url_elem = root.find(".//url")

        if url_elem is not None:
            return url_elem.text
        return None


def get_api() -> NextcloudAPI:
    """获取 API 实例（CLI / 同目录脚本使用；与顶层 import 兼容）"""
    from config import get_config

    config = get_config()
    return NextcloudAPI(config.base_url, config.username, config.app_password)
