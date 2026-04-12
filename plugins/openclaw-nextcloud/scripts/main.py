#!/usr/bin/env python3
"""
Nextcloud 文件管理 CLI
用法:
    python main.py <command> [args]
    
Commands:
    upload <local_path> <remote_path>  上传文件
    download <remote_path> <local_path>  下载文件
    list [path]                       列出文件
    share <remote_path>                创建分享链接
    delete <remote_path>               删除文件
"""

import sys
import os
import re
import shlex
import json
import argparse
import subprocess
from pathlib import Path

# 直接导入同目录的模块
script_dir = Path(__file__).parent
if str(script_dir) not in sys.path:
    sys.path.insert(0, str(script_dir))

from config import get_config
from api import NextcloudAPI, normalize_nextcloud_path


def get_api():
    """获取 API 实例"""
    config = get_config()
    return NextcloudAPI(config.base_url, config.username, config.app_password)


def _looks_mojibake(name: str) -> bool:
    if not name:
        return False
    indicators = ['Ã', 'Â', 'å', 'ä', 'æ', 'ç', 'é', 'ï', 'ð', '�']
    score = sum(name.count(ch) for ch in indicators)
    return score >= 2 or ('_' in name and any(ch in name for ch in indicators))


_UUID_SUFFIX_RE = re.compile(r'---[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}(?=\.[^.]+$)')


def _sanitize_filename(name: str, ext: str) -> str:
    name = (name or '').replace('\n', ' ').replace('\r', ' ').strip()
    name = re.sub(r'\s+', ' ', name)
    name = re.sub(r'[\\/:*?"<>|]+', '_', name)
    name = name.strip(' ._-')
    if not name:
        name = 'document'
    if ext and not name.lower().endswith(ext.lower()):
        name = f'{name}{ext}'
    return name


def _pick_title_from_text(text: str) -> str | None:
    if not text:
        return None
    lines = [re.sub(r'\s+', ' ', line).strip(' #-*_\t') for line in text.splitlines()]
    lines = [line for line in lines if line and len(line) >= 4]
    for line in lines[:30]:
        if _looks_mojibake(line):
            continue
        if not re.search(r'[\u4e00-\u9fffA-Za-z]', line):
            continue
        if re.fullmatch(r'[\W_]+', line):
            continue
        return line[:80]
    return None



def _extract_text_title(local_path: str) -> str | None:
    try:
        with open(local_path, 'r', encoding='utf-8') as f:
            text = f.read(8000)
            title = _pick_title_from_text(text)
            if title:
                return title
    except Exception:
        pass

    try:
        with open(local_path, 'r', encoding='utf-8-sig') as f:
            text = f.read(8000)
            title = _pick_title_from_text(text)
            if title:
                return title
    except Exception:
        pass

    return None



def _extract_pdf_title(local_path: str) -> str | None:
    # 1) PyMuPDF: 本地最快最稳
    try:
        import fitz
        doc = fitz.open(local_path)
        if doc.page_count > 0:
            text = doc.load_page(0).get_text('text')
            title = _pick_title_from_text(text)
            if title:
                return title
    except Exception:
        pass

    # 2) pdftotext: 作为本地兜底
    try:
        cmd = ['pdftotext', '-f', '1', '-l', '1', '-layout', local_path, '-']
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        if res.returncode == 0 and res.stdout.strip():
            title = _pick_title_from_text(res.stdout)
            if title:
                return title
    except Exception:
        pass

    # 3) doc-parse: 远端能力最后兜底
    try:
        cmd = ['miaoda-studio-cli', 'doc-parse', '--file', local_path, '--output', 'json']
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
        if res.returncode != 0 or not res.stdout.strip():
            return None
        data = json.loads(res.stdout)
        text = ''
        if isinstance(data, dict):
            if isinstance(data.get('content'), str):
                text = data.get('content', '')
            elif isinstance(data.get('text'), str):
                text = data.get('text', '')
            elif isinstance(data.get('markdown'), str):
                text = data.get('markdown', '')
            elif isinstance(data.get('data'), dict):
                nested = data['data']
                text = nested.get('content') or nested.get('text') or nested.get('markdown') or ''
        return _pick_title_from_text(text)
    except Exception:
        return None



def _derive_better_name(local_path: str, requested_remote_path: str) -> str:
    requested_name = os.path.basename(requested_remote_path)
    normalized_name = normalize_nextcloud_path(requested_name)
    local_name = os.path.basename(local_path)
    ext = os.path.splitext(requested_name)[1] or os.path.splitext(local_name)[1]

    if normalized_name != requested_name and not _looks_mojibake(normalized_name):
        return _sanitize_filename(normalized_name, ext)

    candidate = normalized_name
    if _looks_mojibake(candidate):
        ext_lower = ext.lower()
        better_title = None
        if ext_lower == '.pdf':
            better_title = _extract_pdf_title(local_path)
        elif ext_lower in ['.txt', '.md', '.markdown']:
            better_title = _extract_text_title(local_path)

        if better_title:
            return _sanitize_filename(better_title, ext)

        candidate = _UUID_SUFFIX_RE.sub('', candidate)
        candidate = candidate.strip(' _-')

    if not candidate or _looks_mojibake(candidate):
        candidate = f'upload-{Path(local_path).stem}'

    return _sanitize_filename(candidate, ext)



def cmd_upload(args):
    """上传文件"""
    api = get_api()

    remote_path = args.remote_path
    dir_part = os.path.dirname(remote_path)
    better_name = _derive_better_name(args.local_path, remote_path)
    if better_name != os.path.basename(remote_path):
        remote_path = f"{dir_part}/{better_name}" if dir_part else better_name
        print(f"ℹ 文件名已规范化: {os.path.basename(args.remote_path)} -> {better_name}")

    result = api.upload_file(args.local_path, remote_path)
    print(result.get("message", f"✓ Nextcloud 上传成功: {remote_path}"))

    return 0


def cmd_download(args):
    """下载文件"""
    api = get_api()
    api.download_file(args.remote_path, args.local_path)
    print(f"✓ 下载成功: {args.local_path}")
    return 0


def cmd_list(args):
    """列出文件"""
    api = get_api()
    files = api.list_files(args.path or "/")
    
    if not files:
        print("(空目录)")
        return 0
    
    # 按类型排序（目录在前）
    files.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
    
    for f in files:
        if f["is_dir"]:
            print(f"📁 {f['name']}/")
        else:
            size_str = format_size(f["size"])
            print(f"📄 {f['name']} ({size_str})")
    
    return 0


def cmd_share(args):
    """创建分享链接"""
    api = get_api()
    
    # 先检查是否已有分享链接
    existing = api.get_share_link(args.remote_path)
    if existing:
        print(existing)
        return 0
    
    url = api.create_share_link(args.remote_path)
    print(url)
    return 0


def cmd_delete(args):
    """删除文件"""
    api = get_api()
    remote_path = args.remote_path

    result = api.delete_file(remote_path)
    print(result.get("message", f"✓ 已删除: {remote_path}"))

    return 0


def format_size(size: int) -> str:
    """格式化文件大小"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"


def main():
    parser = argparse.ArgumentParser(description="Nextcloud 文件管理工具")
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    # upload
    p_upload = subparsers.add_parser("upload", help="上传文件")
    p_upload.add_argument("local_path", help="本地文件路径")
    p_upload.add_argument("remote_path", help="远程文件路径")
    p_upload.set_defaults(func=cmd_upload)
    
    # download
    p_download = subparsers.add_parser("download", help="下载文件")
    p_download.add_argument("remote_path", help="远程文件路径")
    p_download.add_argument("local_path", help="本地保存路径")
    p_download.set_defaults(func=cmd_download)
    
    # list
    p_list = subparsers.add_parser("list", help="列出文件")
    p_list.add_argument("path", nargs="?", default="/", help="目录路径")
    p_list.set_defaults(func=cmd_list)
    
    # share
    p_share = subparsers.add_parser("share", help="创建分享链接")
    p_share.add_argument("remote_path", help="远程文件路径")
    p_share.set_defaults(func=cmd_share)
    
    # delete
    p_delete = subparsers.add_parser("delete", help="删除文件")
    p_delete.add_argument("remote_path", help="远程文件路径")
    p_delete.set_defaults(func=cmd_delete)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    try:
        return args.func(args)
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
