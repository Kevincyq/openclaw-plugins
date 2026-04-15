#!/usr/bin/env python3
"""
Nextcloud 插件桥接层（被 index.ts spawn）

约定同 pkb：argv[1] 为 JSON；stdout 单行 JSON；失败时 exit 1 且 stdout 含 {"ok":false,"error":...}。

action 与 TS 侧 basePayload 第二个参数对应：
  upload | download | write_text | list | share | delete

底层：NextcloudAPI（api.py）→ WebDAV（/remote.php/dav/files/用户/路径）与 OCS 分享 API。
remotePath 使用 Unicode 未编码串，由 api 内 quote 再拼 URL。
"""

from __future__ import annotations

import json
import sys
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

script_dir = Path(__file__).resolve().parent
if str(script_dir) not in sys.path:
    sys.path.insert(0, str(script_dir))

from api import NextcloudAPI  # noqa: E402


def _run_with_prints_to_stderr(fn):
    """将 api 内 print 转到 stderr，保证 stdout 仅一行 JSON。"""
    buf = StringIO()
    with redirect_stdout(buf):
        out = fn()
    extra = buf.getvalue()
    if extra:
        print(extra, end="", file=sys.stderr)
    return out


def main() -> int:
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "error": "missing JSON payload"}))
        return 1
    try:
        payload = json.loads(sys.argv[1])
    except json.JSONDecodeError as e:
        print(json.dumps({"ok": False, "error": f"invalid JSON: {e}"}))
        return 1

    action = payload.get("action")
    base_url = payload.get("baseUrl", "").strip()
    username = payload.get("username", "").strip()
    app_password = payload.get("appPassword", "").strip()

    if not base_url or not username or not app_password:
        print(json.dumps({"ok": False, "error": "baseUrl, username, appPassword are required"}))
        return 1

    api = NextcloudAPI(base_url, username, app_password)

    try:
        # ---- WebDAV 文件体 / 文本 ----
        if action == "upload":
            local_path = payload.get("localPath", "")
            remote_path = payload.get("remotePath", "")
            result = _run_with_prints_to_stderr(lambda: api.upload_file(local_path, remote_path))
            print(json.dumps({"ok": True, "result": result}))
            return 0

        if action == "download":
            remote_path = payload.get("remotePath", "")
            local_path = payload.get("localPath", "")
            _run_with_prints_to_stderr(lambda: api.download_file(remote_path, local_path))
            print(json.dumps({"ok": True, "result": {"localPath": local_path}}))
            return 0

        if action == "write_text":
            remote_path = payload.get("remotePath", "")
            text = str(payload.get("text", ""))
            result = _run_with_prints_to_stderr(lambda: api.write_text_file(remote_path, text))
            print(json.dumps({"ok": True, "result": result}))
            return 0

        # ---- PROPFIND 列目录；OCS 分享（公开链接）----
        if action == "list":
            path = payload.get("path") or "/"
            files = api.list_files(path)
            print(json.dumps({"ok": True, "result": {"path": path, "files": files}}))
            return 0

        if action == "share":
            remote_path = payload.get("remotePath", "")
            existing = api.get_share_link(remote_path)
            url = existing or api.create_share_link(remote_path)
            print(json.dumps({"ok": True, "result": {"url": url}}))
            return 0

        # ---- DELETE 删云端文件 ----
        if action == "delete":
            remote_path = payload.get("remotePath", "")
            result = _run_with_prints_to_stderr(lambda: api.delete_file(remote_path))
            print(json.dumps({"ok": True, "result": result}))
            return 0

        print(json.dumps({"ok": False, "error": f"unknown action: {action}"}))
        return 1
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
