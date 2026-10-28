"""Mounts the-state's FastAPI app as a sub-application.

the-state's own code (the_state/api/main.py and everything it imports —
core, models, routes, schemas, services, cli) uses flat, un-namespaced
imports because it was built to run as its own project root. Rather than
rewrite those imports to merge it into open-supply-chain's package layout
(a much larger, riskier change), this puts the_state/api/ on sys.path so
its existing code runs completely unmodified, and only the resulting
FastAPI app object crosses into open-supply-chain's process.

See the_state/README.md for the consolidation this is part of.
"""

from __future__ import annotations

import sys
from pathlib import Path

_THE_STATE_API_DIR = Path(__file__).parent / "api"
if str(_THE_STATE_API_DIR) not in sys.path:
    sys.path.insert(0, str(_THE_STATE_API_DIR))

from main import app as the_state_app  # noqa: E402

__all__ = ["the_state_app"]
