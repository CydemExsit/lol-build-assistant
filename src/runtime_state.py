from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_STATUS_PATH = Path("data/runtime/status.json")
_LOCK = threading.Lock()


def read_status(path: str | Path = DEFAULT_STATUS_PATH) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return {
            "state": "offline",
            "message": "背景服務尚未啟動",
            "compliance_mode": "static_pregame_v1",
        }
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {
            "state": "error",
            "message": "無法讀取背景服務狀態",
            "compliance_mode": "static_pregame_v1",
        }
    return payload if isinstance(payload, dict) else {}


def write_status(
    updates: dict[str, Any],
    path: str | Path = DEFAULT_STATUS_PATH,
) -> dict[str, Any]:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        current = read_status(target)
        current.update(updates)
        current["updated_at"] = datetime.now(timezone.utc).astimezone().isoformat()
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(target)
    return current
