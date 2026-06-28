"""Lightweight structured observability for offline and WebArena exploration."""
from __future__ import annotations

import json
import os
import re
import time
from collections import Counter
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


_LEVELS = {"debug": 10, "info": 20, "summary": 25, "warning": 30, "error": 40}
_SENSITIVE_KEY = re.compile(
    r"password|passwd|secret|token|api[_-]?key|credential|authorization|cookie",
    re.IGNORECASE,
)


def _redact_url(value: str) -> str:
    if not re.match(r"^https?://", value, re.IGNORECASE):
        return value
    try:
        parts = urlsplit(value)
        query = [
            (key, "<redacted>" if _SENSITIVE_KEY.search(key) else item)
            for key, item in parse_qsl(parts.query, keep_blank_values=True)
        ]
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))
    except Exception:
        return value


def redact(value: Any, key: str = "") -> Any:
    """Recursively redact credentials and sensitive URL query values."""
    if key and _SENSITIVE_KEY.search(key):
        return "<redacted>"
    if isinstance(value, dict):
        return {str(k): redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return _redact_url(value)
    return value


class ExploreEventLogger:
    """Append-only JSONL event sink with stable correlation metadata."""

    def __init__(
        self,
        out_dir: str,
        *,
        run_id: str | None = None,
        level: str = "info",
        resume: bool = False,
    ) -> None:
        if level not in _LEVELS:
            raise ValueError(f"unknown event log level: {level}")
        os.makedirs(out_dir, exist_ok=True)
        self.run_id = run_id or os.path.basename(os.path.abspath(out_dir)) or "run"
        self.level = level
        self.started_at = time.time()
        self.session_id = f"{self.run_id}-{int(self.started_at * 1000)}-{os.getpid()}"
        self.sequence = 0
        self.counts: Counter[str] = Counter()
        mode = "a" if resume else "w"
        self.path = os.path.join(out_dir, "events.jsonl")
        self._file = open(self.path, mode, encoding="utf-8", buffering=1)

    def emit(
        self,
        component: str,
        event: str,
        *,
        level: str = "info",
        node_id: int | None = None,
        task_id: str | None = None,
        episode_id: int | None = None,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        if level not in _LEVELS:
            raise ValueError(f"unknown event level: {level}")
        if _LEVELS[level] < _LEVELS[self.level]:
            return None
        now = time.time()
        self.sequence += 1
        record = {
            "timestamp": datetime.fromtimestamp(now, timezone.utc).isoformat(
                timespec="milliseconds"
            ).replace("+00:00", "Z"),
            "elapsed_ms": round((now - self.started_at) * 1000),
            "sequence": self.sequence,
            "run_id": self.run_id,
            "session_id": self.session_id,
            "component": component,
            "event": event,
            "level": level,
            "node_id": node_id,
            "task_id": task_id,
            "episode_id": episode_id,
            "data": redact(data or {}),
        }
        self._file.write(json.dumps(record, sort_keys=True) + "\n")
        self.counts[f"{component}.{event}"] += 1
        return record

    def flush(self) -> None:
        self._file.flush()

    def close(self) -> None:
        if not self._file.closed:
            self._file.flush()
            self._file.close()
