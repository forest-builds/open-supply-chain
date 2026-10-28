# Contributing a City

The State scales geographically by adding **city normalizers**. A normalizer
turns one city's open-data records into the platform-wide `NormalizedSignal`
shape. Nothing downstream (scoring, state, briefs, watchlists) changes — that
is the whole point of this seam.

This guide takes you from zero to a working city in **five steps**. A
developer unfamiliar with the codebase should be able to add a city following
only this document. NYC (`ingestion/nyc/`) is the reference implementation;
read it alongside this guide.

## The contract

Your city package must satisfy `ingestion.base.NormalizerProtocol`:

```python
from typing import Any, Protocol, runtime_checkable
from ingestion.base import NormalizedSignal

@runtime_checkable
class NormalizerProtocol(Protocol):
    def normalize_record(
        self, dataset_name: str, record: dict[str, Any]
    ) -> NormalizedSignal: ...
```

`dataset_name` selects which of your city's datasets the raw `record` came
from; you return exactly one `NormalizedSignal`.

### Required `NormalizedSignal` fields

| Field | Required | Notes |
|-------|----------|-------|
| `source_name` | yes | Stable slug for the dataset, e.g. `chicago-311` |
| `source_type` | yes (set it) | e.g. `chicago_open_data`. The default is the NYC value — always set yours explicitly |
| `external_id` | yes | The source's own record id; used for dedup |
| `record_type` | yes | Your dataset key, e.g. `chicago_311` |
| `payload` | yes | The raw source record, unmodified (provenance) |
| `signal_type` | yes | One of the platform signal types (see below) |
| `title` | yes | Short human-readable summary |
| `summary` | no | Longer description if available |
| `severity` | recommended | Drives scoring weight; see severity calibration |
| `occurred_at` | recommended | When the event happened (source timestamp) |
| `observed_at` | yes | When you fetched it (UTC) |
| `location` | recommended | `{"state", "borough"/"community_area", "zip", "nta", "lat", "lon"}` |
| `attributes` | no | Anything else useful for filtering |

**Platform signal types** (reuse these — do not invent new ones without a
core change): `weather_alert`, `declaration`, `civic_complaint`,
`street_closure`, `public_event`, `housing_violation`.

## Five steps to add a city

1. **Create the package.** `ingestion/<city>/` with `__init__.py`,
   `datasets.py`, `normalizers.py`, `collector.py`. Mirror `ingestion/nyc/`.

2. **Declare datasets.** In `datasets.py`, map each dataset key to its source
   config (endpoint/dataset id, date field, ordering). Mirror
   `nyc/datasets.py` / `NycDatasetConfig`.

3. **Write one normalizer per dataset.** Each is a pure function
   `(record: dict) -> NormalizedSignal`. Register them in a `NORMALIZERS`
   dict and expose a `normalize_record(dataset_name, record)` dispatcher,
   exactly like `nyc/normalizers.py`. Wrap them in a
   `class <City>Normalizer:` with a `normalize_record` method so the package
   satisfies `NormalizerProtocol` (see `NycNormalizer`).

4. **Normalize geography.** Map the city's sub-location unit into
   `location`. NYC uses `borough`; Chicago should use `community_area`.
   Always include `state` so the place resolver can filter. Keep ZIP/NTA-style
   keys where available — they power borough/ZIP `sub_locations`.

5. **Register & test.** Wire the city into the top-level collector under its
   city key (e.g. `"chicago"`). Add `tests/test_<city>_ingestion.py` with
   **mock records** and **expected `NormalizedSignal` output** for every
   normalizer. Assert `isinstance(<city>_normalizer, NormalizerProtocol)`.

## Severity calibration

Severity is not universal. Do **not** copy NYC's severity thresholds — signal
volumes differ per city (e.g. Chicago 311 volume differs from NYC). Calibrate
severity bands against the city's own volumes, and be conservative with
public-safety-derived severity. The feedback loop
(`scoring_calibration_service`) will refine weights over time, but start
sane.

## Test structure

Mirror `tests/test_nyc_ingestion.py`:

- One test per normalizer: feed a representative mock `record`, assert each
  meaningful `NormalizedSignal` field.
- A protocol test: `assert isinstance(<city>_normalizer, NormalizerProtocol)`.
- Collector test with a mocked HTTP transport (no live network).
