"""Session debug logging (NDJSON). Remove after debug session."""
import json
import time
from pathlib import Path

_LOG = Path(__file__).resolve().parent / "debug-dd4a47.log"


def agent_log(
    hypothesis_id: str,
    location: str,
    message: str,
    data: dict | None = None,
    run_id: str = "pre-fix",
) -> None:
    payload = {
        "sessionId": "dd4a47",
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data or {},
        "timestamp": int(time.time() * 1000),
        "runId": run_id,
    }
    try:
        with _LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except OSError:
        pass
