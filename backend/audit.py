"""Append-only audit trail at output/audit_trail.json.

The file is a JSON array. Each call to `append` reads the array, adds one
entry and writes it back atomically - it is NEVER wiped between runs.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.config import AUDIT_TEXT_LIMIT, AUDIT_TRAIL

_LOCK = threading.Lock()


def _clip(value: Any) -> Any:
    if isinstance(value, str) and len(value) > AUDIT_TEXT_LIMIT:
        return value[:AUDIT_TEXT_LIMIT] + f"... [truncated {len(value) - AUDIT_TEXT_LIMIT} chars]"
    return value


def _jsonable(value: Any) -> Any:
    try:
        json.dumps(value)
        return _clip(value) if isinstance(value, str) else value
    except TypeError:
        return _clip(str(value))


class AuditTrail:
    def __init__(self, path: Path = AUDIT_TRAIL):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]\n")

    def append(self, entry: dict) -> str:
        step_id = entry.get("step_id") or uuid.uuid4().hex[:12]
        record = {
            "step_id": step_id,
            "logged_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            **{k: _jsonable(v) for k, v in entry.items() if k != "step_id"},
        }
        with _LOCK:
            try:
                data = json.loads(self.path.read_text() or "[]")
                if not isinstance(data, list):
                    data = [data]
            except json.JSONDecodeError:
                # Never destroy history: keep the unreadable file aside.
                self.path.rename(self.path.with_suffix(f".corrupt-{uuid.uuid4().hex[:6]}.json"))
                data = []
            data.append(record)
            fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2, default=str)
                f.write("\n")
            os.replace(tmp, self.path)
        return step_id
