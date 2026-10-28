import hashlib
import json
from typing import Any


def hash_payload(payload: dict[str, Any]) -> str:
    """Deterministic SHA-256 hash of a JSON payload.

    Keys are sorted and separators are minimized so the same logical document
    always produces the same hash regardless of insertion order.
    """
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()
