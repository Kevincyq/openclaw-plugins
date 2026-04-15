#!/usr/bin/env python3
"""
PKB 命令行工具（不经过 OpenClaw Node 插件）

与插件的关系：共用 api.PKBAPI / config.PKBConfig；适合本机调试、手动 sync/ask。
插件入口请看 openclaw_bridge.py + 上级 index.ts。

用法:
    python -m scripts.main <command> [args]
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote

# 添加脚本目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from api import get_api, normalize_nextcloud_path
from config import get_config


def _normalize_resource_name(name: str) -> str:
    normalized = normalize_nextcloud_path(name).lstrip("/")
    if "/" not in normalized:
        return f"PKB/{normalized}"
    return normalized


def cmd_ask(args):
    """问答"""
    api = get_api()
    result = api.ask(args.question, session_id=getattr(args, "session_id", None))

    print("=" * 50)
    print("ANSWER")
    print("=" * 50)
    print(result["answer"] or "抱歉，没有找到相关信息")
    print()

    print("=" * 50)
    print("SOURCES")
    print("=" * 50)

    if not result["sources"]:
        print("(无来源)")
        return 0

    config = get_config()
    for i, src in enumerate(result["sources"], 1):
        name = src["name"]
        source_url = src.get("url", "") or ""
        nc_path = src.get("path", "")

        if not source_url and nc_path and config.nextcloud_username and config.nextcloud_app_password:
            try:
                source_url = get_share_link(config, nc_path)
                if not source_url:
                    source_url = create_share_link(config, nc_path)
            except Exception as e:
                print(f"   ⚠️ 生成分享链接失败：{e}")

        print(f"{i}. [{name}]")
        if source_url:
            print(f"   {source_url}")
        elif nc_path:
            print(f"   {nc_path}")

    return 0


def get_share_link(config, path):
    """获取已存在的分享链接"""
    import requests
    import xml.etree.ElementTree as ET

    url = f"{config.nextcloud_base_url}/ocs/v2.php/apps/files_sharing/api/v1/shares?path={quote(path)}&share_type=3"
    response = requests.get(
        url,
        auth=(config.nextcloud_username, config.nextcloud_app_password),
        headers={"OCS-APIREQUEST": "true"},
    )

    if response.status_code != 200:
        return None

    root = ET.fromstring(response.content)
    ns = {"ocs": "http://api.nextcloud.org"}
    url_elem = root.find(".//ocs:url", ns)
    if url_elem is not None:
        return url_elem.text
    return None


def create_share_link(config, path):
    """创建分享链接"""
    import requests
    import xml.etree.ElementTree as ET

    url = f"{config.nextcloud_base_url}/ocs/v2.php/apps/files_sharing/api/v1/shares"
    data = {"path": path, "shareType": 3}

    response = requests.post(
        url,
        json=data,
        auth=(config.nextcloud_username, config.nextcloud_app_password),
        headers={"OCS-APIREQUEST": "true"},
    )
    response.raise_for_status()

    root = ET.fromstring(response.content)
    for elem in root.iter():
        if elem.tag == "url":
            return elem.text

    raise Exception("创建分享链接失败")


def cmd_sync(args):
    """同步 Nextcloud 到知识库"""
    import requests
    import xml.etree.ElementTree as ET

    config = get_config()
    nc_path = normalize_nextcloud_path(args.nc_path or "/PKB")
    rel_dir = nc_path.lstrip("/")
    dav_prefix = f"{config.nextcloud_base_url}/remote.php/dav/files/{config.nextcloud_username}"

    nc_url = f"{dav_prefix}/{quote(rel_dir)}"
    response = requests.request(
        "PROPFIND",
        nc_url,
        auth=(config.nextcloud_username, config.nextcloud_app_password),
        headers={"Depth": "1"},
    )
    response.raise_for_status()

    root = ET.fromstring(response.content)
    ns = {"d": "DAV:"}

    files = []
    for resp in root.findall(".//d:response", ns):
        href = resp.find("d:href", ns)
        if href is None:
            continue

        file_path = href.text.replace(f"/remote.php/dav/files/{config.nextcloud_username}/", "")
        file_path = normalize_nextcloud_path(file_path).lstrip("/")
        if not file_path or file_path.rstrip("/") == rel_dir.rstrip("/"):
            continue

        resource_type = resp.find(".//d:resourcetype/d:collection", ns)
        if resource_type is not None:
            continue

        files.append({"path": file_path, "name": os.path.basename(file_path)})

    print(f"Found {len(files)} files to sync")
    api = get_api()

    for item in files:
        print(f"Processing: {item['name']}...", end=" ", flush=True)
        temp_path = None
        try:
            rel = normalize_nextcloud_path(item["path"]).lstrip("/")
            download_url = f"{dav_prefix}/{quote(rel)}"
            response = requests.get(
                download_url,
                auth=(config.nextcloud_username, config.nextcloud_app_password),
            )
            response.raise_for_status()

            share_url = get_share_link(config, rel)
            if not share_url:
                share_url = create_share_link(config, rel)

            suffix = Path(item["name"]).suffix
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as fp:
                fp.write(response.content)
                temp_path = fp.name

            api.sync_file(temp_path, rel, source_url=share_url)
            print("✓")
        except Exception as e:
            print(f"❌ {e}")
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

    print("Sync completed!")
    return 0


def cmd_upload(args):
    """上传文件到知识库"""
    api = get_api()
    file_name = os.path.basename(args.file_path)
    resource_name = _normalize_resource_name(getattr(args, "name", None) or file_name)
    api.upload_resource(args.file_path, resource_name, source_url=getattr(args, "source_url", "") or "")
    print(f"✓ 上传成功：{resource_name}")
    return 0


def cmd_delete(args):
    """删除知识库资源"""
    api = get_api()
    resource_name = _normalize_resource_name(args.resource_name)
    api.delete_resource(resource_name)
    print(f"✓ 已删除知识库资源：{resource_name}")
    return 0


def cmd_list(args):
    """列出知识库资源"""
    api = get_api()
    result = api.list_resources(page=args.page or 1, size=args.size or 30)

    print(f"=== PKB 知识库资源 (共 {result['total']} 个) ===")
    print()

    type_icons = {"pdf": "📄", "text": "📝", "image": "🖼️", "markdown": "📝"}
    for item in result["resources"]:
        icon = type_icons.get(item["type"], "📁")
        print(f"{icon} {item['name']}")

    return 0


def cmd_wait(args):
    """轮询等待资源完成索引"""
    api = get_api()
    resource_name = _normalize_resource_name(args.resource_name)
    result = api.wait_resource_indexed(
        resource_name,
        timeout_seconds=args.timeout,
        interval_seconds=args.interval,
    )
    if result["success"]:
        print(f"✓ 已完成索引：{resource_name} ({result['elapsed_seconds']}s)")
        return 0
    print(f"✗ 等待超时：{resource_name} ({result['elapsed_seconds']}s)")
    return 1


def main():
    parser = argparse.ArgumentParser(description="PKB 知识库管理工具")
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    p_ask = subparsers.add_parser("ask", help="问答")
    p_ask.add_argument("question", help="问题")
    p_ask.add_argument("--session-id", help="复用会话 ID")
    p_ask.set_defaults(func=cmd_ask)

    p_sync = subparsers.add_parser("sync", help="同步 Nextcloud 到知识库")
    p_sync.add_argument("nc_path", nargs="?", default="/PKB", help="Nextcloud 目录路径")
    p_sync.set_defaults(func=cmd_sync)

    p_list = subparsers.add_parser("list", help="列出知识库资源")
    p_list.add_argument("--page", type=int, default=1, help="页码")
    p_list.add_argument("--size", type=int, default=30, help="每页数量")
    p_list.set_defaults(func=cmd_list)

    p_upload = subparsers.add_parser("upload", help="上传文件")
    p_upload.add_argument("file_path", help="本地文件路径")
    p_upload.add_argument("--name", help="资源名称（可选，默认使用文件名）")
    p_upload.add_argument("--source-url", help="Nextcloud 公共链接，用于问答溯源")
    p_upload.set_defaults(func=cmd_upload)

    p_delete = subparsers.add_parser("delete", help="删除知识库资源")
    p_delete.add_argument("resource_name", help="资源名称（支持精确或包含匹配）")
    p_delete.set_defaults(func=cmd_delete)

    p_wait = subparsers.add_parser("wait", help="等待资源完成索引")
    p_wait.add_argument("resource_name", help="资源名称")
    p_wait.add_argument("--timeout", type=int, default=60, help="超时时间（秒）")
    p_wait.add_argument("--interval", type=int, default=2, help="轮询间隔（秒）")
    p_wait.set_defaults(func=cmd_wait)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 1

    try:
        return args.func(args)
    except Exception as e:
        print(f"错误：{e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
