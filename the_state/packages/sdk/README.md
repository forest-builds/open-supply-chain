# The State — Python SDK

Ground-truth operational state for any place, in ten lines of Python.

## Install

```bash
uv add the-state-sdk
```

## Quickstart

```python
import asyncio
from the_state_sdk import TheStateClient

async def main():
    async with TheStateClient(api_key="sk-...") as client:
        state = await client.get_state("New York, NY")
        print(state.operational_state, state.risk_score, state.confidence)

asyncio.run(main())
```

Synchronous callers:

```python
from the_state_sdk import TheStateSyncClient

with TheStateSyncClient(api_key="sk-...") as client:
    state = client.get_state("Brooklyn, NYC")
    print(state.operational_state)
```

## Auth

Pass `api_key` to the client; it is sent as `Authorization: Bearer <key>`.
Point at a different deployment with `base_url=` (default
`https://api.thestate.io`).

## Common patterns

Pre-dispatch check (gate an action on real-world state):

```python
state = await client.get_state("Midtown, NYC", time_window="6h")
if state.operational_state in {"disrupted", "critical"}:
    hold_dispatch(reason=state.summary)
```

Watchlist setup (track many places at once):

```python
wl = await client.create_watchlist(
    "Morning ops",
    places=["Brooklyn, NYC", "Manhattan, NYC", "Queens, NYC"],
)
```

Brief logging (close the feedback flywheel):

```python
brief = await client.get_brief(brief_id)
# ... operator acts on it, later learns it was a false alarm:
await client.log_feedback(brief_id, false_positive=True)
# or, when the disruption was real:
await client.log_feedback(brief_id, outcome="disruption_confirmed")
```

Feedback feeds the deterministic scoring calibration — confirmed disruptions
compound a signal's weight, false positives decay it.

## Errors

| Exception | When |
|-----------|------|
| `NotFoundError` | HTTP 404 (unknown brief, etc.) |
| `RateLimitError` | HTTP 429 |
| `TheStateError` | Base class; any other non-success response |
