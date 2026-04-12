#!/usr/bin/env python3
"""
OpenClaw PKB 插件桥接层：从 argv 读取 JSON，向 stdout 输出单行 JSON。
"""

from __future__ import annotations

import json
import sys
import tempfile
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

script_dir = Path(__file__).resolve().parent
if str(script_dir) not in sys.path:
    sys.path.insert(0, str(script_dir))

from api import PKBAPI  # noqa: E402


def _run_with_prints_to_stderr(fn):
    buf = StringIO()
    with redirect_stdout(buf):
        out = fn()
    extra = buf.getvalue()
    if extra:
        print(extra, end="", file=sys.stderr)
    return out


def _require_str(payload: dict, key: str) -> str:
    value = str(payload.get(key, "") or "").strip()
    if not value:
        raise ValueError(f"{key} is required")
    return value


def main() -> int:
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "error": "missing JSON payload"}))
        return 1

    try:
        payload = json.loads(sys.argv[1])
    except json.JSONDecodeError as e:
        print(json.dumps({"ok": False, "error": f"invalid JSON: {e}"}))
        return 1

    try:
        action = _require_str(payload, "action")
        base_url = _require_str(payload, "baseUrl")
        api_key = _require_str(payload, "apiKey")
        user_id = _require_str(payload, "userId")
        api = PKBAPI(base_url, api_key, user_id)

        if action == "ask":
            question = _require_str(payload, "question")
            session_id = str(payload.get("sessionId", "") or "").strip() or None
            result = _run_with_prints_to_stderr(lambda: api.ask(question, session_id=session_id))
            print(json.dumps({"ok": True, "result": result}))
            return 0

        if action == "upload_file":
            local_path = _require_str(payload, "localPath")
            resource_name = _require_str(payload, "resourceName")
            source_url = str(payload.get("sourceUrl", "") or "")
            _run_with_prints_to_stderr(
                lambda: api.upload_resource(local_path, resource_name, source_url=source_url)
            )
            print(
                json.dumps(
                    {
                        "ok": True,
                        "result": {
                            "success": True,
                            "resourceName": resource_name,
                            "sourceUrl": source_url,
                        },
                    }
                )
            )
            return 0

        if action == "upload_text":
            text = str(payload.get("text", ""))
            resource_name = _require_str(payload, "resourceName")
            source_url = str(payload.get("sourceUrl", "") or "")
            suffix = str(payload.get("suffix", "") or "") or Path(resource_name).suffix
            temp_path = None
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix or ".txt", mode="w", encoding="utf-8") as fp:
                    fp.write(text)
                    temp_path = fp.name
                _run_with_prints_to_stderr(
                    lambda: api.upload_resource(temp_path, resource_name, source_url=source_url)
                )
            finally:
                if temp_path:
                    Path(temp_path).unlink(missing_ok=True)
            print(
                json.dumps(
                    {
                        "ok": True,
                        "result": {
                            "success": True,
                            "resourceName": resource_name,
                            "sourceUrl": source_url,
                        },
                    }
                )
            )
            return 0

        if action == "delete_resource":
            resource_name = _require_str(payload, "resourceName")
            _run_with_prints_to_stderr(lambda: api.delete_resource(resource_name))
            print(json.dumps({"ok": True, "result": {"success": True, "resourceName": resource_name}}))
            return 0

        if action == "list_resources":
            page = int(payload.get("page", 1) or 1)
            size = int(payload.get("size", 20) or 20)
            result = _run_with_prints_to_stderr(lambda: api.list_resources(page=page, size=size))
            print(json.dumps({"ok": True, "result": result}))
            return 0

        if action == "wait_resource":
            resource_name = _require_str(payload, "resourceName")
            timeout_seconds = int(payload.get("timeoutSeconds", 60) or 60)
            interval_seconds = int(payload.get("intervalSeconds", 2) or 2)
            result = _run_with_prints_to_stderr(
                lambda: api.wait_resource_indexed(
                    resource_name,
                    timeout_seconds=timeout_seconds,
                    interval_seconds=interval_seconds,
                )
            )
            print(json.dumps({"ok": True, "result": result}))
            return 0

        print(json.dumps({"ok": False, "error": f"unknown action: {action}"}))
        return 1

    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
