"""NDJSON debug logging for agent sessions (do not log secrets)."""

from __future__ import annotations

import json
import time
from typing import Any

_SESSION = "dd4a47"


def agent_log(
    *,
    location: str,
    message: str,
    data: dict[str, Any] | None = None,
    hypothesis_id: str = "",
    run_id: str = "pre-fix",
) -> None:
    try:
        from services.updater import project_root

        path = project_root() / "debug-dd4a47.log"
        payload = {
            "sessionId": _SESSION,
            "timestamp": int(time.time() * 1000),
            "location": location,
            "message": message,
            "data": data or {},
            "hypothesisId": hypothesis_id,
            "runId": run_id,
        }
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass
