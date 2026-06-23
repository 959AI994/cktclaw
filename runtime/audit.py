"""
Audit trail — append-only JSONL of security-relevant actions.

Each event is one JSON object per line (SIEM-friendly) written to the active
run's ``events.jsonl``. Secrets are redacted and raw argument payloads are
reduced to a SHA-256 digest so design content / filenames never persist.

Emission is best-effort: a no-op when there is no active run, and never raises
into the calling action.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .run_context import get_current_run

# Keys whose values must never be written verbatim.
_SECRET_KEY = re.compile(r"(authorization|api[_-]?key|token|secret|bearer|password)", re.IGNORECASE)
# Bearer/sk- style values embedded in free text.
_SECRET_VALUE = re.compile(r"(Bearer\s+\S+|sk-[A-Za-z0-9_\-]{8,})", re.IGNORECASE)

_REDACTED = "[REDACTED]"


def redact(obj: Any) -> Any:
    """Recursively redact secret-looking keys and values."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if isinstance(k, str) and _SECRET_KEY.search(k):
                out[k] = _REDACTED
            else:
                out[k] = redact(v)
        return out
    if isinstance(obj, (list, tuple)):
        return [redact(v) for v in obj]
    if isinstance(obj, str):
        return _SECRET_VALUE.sub(_REDACTED, obj)
    return obj


def _digest(args: Any) -> str:
    try:
        payload = json.dumps(args, ensure_ascii=False, sort_keys=True, default=str)
    except Exception:
        payload = str(args)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def audit_event(
    *,
    kind: str,
    capability: str = "",
    status: str = "ok",
    args: Optional[Any] = None,
    extra: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
    tokens: Optional[int] = None,
    cost: Optional[float] = None,
) -> None:
    """Append one audit event to the active run's events.jsonl (best-effort)."""
    run = get_current_run()
    if run is None:
        return

    event: Dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "run_id": run.run_id,
        "user": run.user,
        "kind": kind,
        "capability": capability,
        "status": status,
    }
    if args is not None:
        event["args_digest"] = _digest(args)
    if extra:
        event["extra"] = redact(extra)
    if error is not None:
        event["error"] = redact(str(error))
    if tokens is not None:
        event["tokens"] = tokens
    if cost is not None:
        event["cost"] = cost

    try:
        line = json.dumps(redact(event), ensure_ascii=False)
        path = run.events_path
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass
