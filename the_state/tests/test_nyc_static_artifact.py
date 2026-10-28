from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timezone

from cli import nyc_living_artifact
from services.ai_roi_demo_service import RoiAssumptions, estimate_roi
from services.nyc_living_artifact_service import NycDatasetRun, NycLivingArtifactResult
from services.nyc_static_artifact_renderer import render_nyc_static_artifact


def test_render_nyc_static_artifact_uses_snapshot_data() -> None:
    snapshot = _snapshot()

    html = render_nyc_static_artifact(snapshot)

    assert "New York, NY" in html
    assert "ELEVATED" in html
    assert "311" in html
    assert "HEAT/HOT WATER" in html
    assert "Check staffing buffers" in html
    assert "sample-signal" in html
    assert "latest.json" in html
    assert "sample living state page" not in html


def test_cli_write_docs_writes_latest_json_and_index_html(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    snapshot = _snapshot()
    output_dir = tmp_path / "nyc"

    async def fake_run(args):
        assert args.write_docs is True
        return snapshot

    monkeypatch.setattr(nyc_living_artifact, "_run", fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "the-state-nyc-artifact",
            "--write-docs",
            "--docs-output-dir",
            str(output_dir),
            "--site-base-url",
            "https://example.com/the-state",
        ],
    )

    nyc_living_artifact.main()

    latest = output_dir / "latest.json"
    index = output_dir / "index.html"
    assert latest.exists()
    assert index.exists()
    assert json.loads(latest.read_text(encoding="utf-8"))["place"] == "New York, NY"
    assert "https://example.com/the-state/state/nyc/latest.json" in index.read_text(
        encoding="utf-8"
    )
    assert json.loads(capsys.readouterr().out)["brief_id"] == str(snapshot.brief_id)


def test_cli_ai_demo_writes_roi_artifacts_without_assistant(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    snapshot = _snapshot()
    output_dir = tmp_path / "demo"

    async def fake_run(args):
        assert args.ai_demo is True
        return snapshot

    monkeypatch.setattr(nyc_living_artifact, "_run", fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "the-state-nyc-artifact",
            "--ai-demo",
            "--ai-provider",
            "none",
            "--demo-output-dir",
            str(output_dir),
            "--roi-minutes-saved-per-signal",
            "6",
            "--roi-analyst-hourly-cost-usd",
            "90",
            "--roi-runs-per-month",
            "20",
        ],
    )

    nyc_living_artifact.main()

    latest = output_dir / "latest-ai-roi.json"
    narrative = output_dir / "latest-ai-roi.md"
    assert latest.exists()
    assert narrative.exists()
    body = json.loads(latest.read_text(encoding="utf-8"))
    assert body["ai_generated"] is False
    assert body["roi_estimate"]["estimated_labor_value_per_month_usd"] == 360.0
    assert "AI synthesis was not run" in narrative.read_text(encoding="utf-8")
    assert json.loads(capsys.readouterr().out)["brief_id"] == str(snapshot.brief_id)


def test_estimate_roi_uses_live_signal_counts_and_explicit_assumptions() -> None:
    estimate = estimate_roi(
        snapshot=_snapshot(),
        assumptions=RoiAssumptions(
            minutes_saved_per_signal=6,
            analyst_hourly_cost_usd=90,
            runs_per_month=20,
        ),
    )

    assert estimate.signals_triaged == 2
    assert estimate.active_signals == 2
    assert estimate.estimated_minutes_saved_per_run == 12
    assert estimate.estimated_hours_saved_per_run == 0.2
    assert estimate.estimated_labor_value_per_run_usd == 18
    assert estimate.estimated_labor_value_per_month_usd == 360


def test_estimate_roi_uses_unrounded_hours_for_dollars() -> None:
    estimate = estimate_roi(
        snapshot=_snapshot_with_signals_seen(10),
        assumptions=RoiAssumptions(
            minutes_saved_per_signal=5,
            analyst_hourly_cost_usd=75,
            runs_per_month=30,
        ),
    )

    assert estimate.estimated_minutes_saved_per_run == 50
    assert estimate.estimated_hours_saved_per_run == 0.83
    assert estimate.estimated_labor_value_per_run_usd == 62.5
    assert estimate.estimated_labor_value_per_month_usd == 1875


def _snapshot_with_signals_seen(signals_seen: int) -> NycLivingArtifactResult:
    snapshot = _snapshot()
    return snapshot.model_copy(update={"signals_seen": signals_seen})


def _snapshot() -> NycLivingArtifactResult:
    return NycLivingArtifactResult(
        place="New York, NY",
        time_window="24h",
        generated_at=datetime(2026, 5, 12, 15, 30, tzinfo=timezone.utc),
        since=datetime(2026, 5, 11, 15, 30, tzinfo=timezone.utc),
        datasets=[NycDatasetRun(dataset="311", collected=2)],
        signals_seen=2,
        signals_inserted=2,
        signals_skipped=0,
        watchlist_id=uuid.UUID("11111111-1111-4111-8111-111111111111"),
        evaluation_result_id=uuid.UUID("22222222-2222-4222-8222-222222222222"),
        brief_id=uuid.UUID("33333333-3333-4333-8333-333333333333"),
        brief_url="https://example.com/briefs/33333333-3333-4333-8333-333333333333",
        operational_state="elevated",
        risk_score=0.37,
        active_signal_count=2,
        summary="New York, NY is elevated with risk score 0.37 and confidence 80%.",
        what_changed="This is the first stored evaluation for the watched location.",
        why_it_matters="Conditions deserve closer monitoring before they affect operations.",
        drivers=[
            {
                "label": "HEAT/HOT WATER",
                "weight": 0.37,
                "signal_ids": ["sample-signal"],
            }
        ],
        active_signals=[
            {
                "signal_id": "sample-signal",
                "signal_type": "nyc_311_complaint",
                "source": "nyc_open_data:311",
                "severity": "medium",
                "title": "Heat complaint",
                "occurred_at": "2026-05-12T12:00:00Z",
                "contribution": 0.37,
            }
        ],
        recent_changes=[],
        recommended_actions=[
            {
                "action": "Check staffing buffers",
                "rationale": "Elevated civic stress can create delays.",
            }
        ],
        evidence=[
            {
                "signal_id": "sample-signal",
                "source": "nyc_open_data:311",
                "raw_record_id": None,
                "contribution": 0.37,
                "observed_at": "2026-05-12T12:00:00Z",
            }
        ],
        confidence=0.8,
        provenance=[
            {
                "signal_id": "sample-signal",
                "source": "nyc_open_data:311",
                "raw_record_id": None,
                "contribution": 0.37,
                "observed_at": "2026-05-12T12:00:00Z",
            }
        ],
    )
