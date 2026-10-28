from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Protocol

from pydantic import BaseModel, Field

from services.nyc_living_artifact_service import NycLivingArtifactResult


class RoiAssumptions(BaseModel):
    minutes_saved_per_signal: float = Field(default=5.0, ge=0.0)
    analyst_hourly_cost_usd: float = Field(default=75.0, ge=0.0)
    runs_per_month: int = Field(default=30, ge=0)


class RoiEstimate(BaseModel):
    signals_triaged: int
    active_signals: int
    estimated_minutes_saved_per_run: float
    estimated_hours_saved_per_run: float
    estimated_labor_value_per_run_usd: float
    estimated_labor_value_per_month_usd: float
    assumptions: RoiAssumptions


class AiRoiDemoResult(BaseModel):
    generated_at: datetime
    ai_generated: bool
    provider: str
    command: list[str]
    narrative_markdown: str
    roi_estimate: RoiEstimate
    source_snapshot: dict[str, Any]


class AiRoiNarrativeClient(Protocol):
    provider: str
    command: list[str]

    async def generate(
        self,
        *,
        snapshot: NycLivingArtifactResult,
        roi_estimate: RoiEstimate,
    ) -> str: ...


class MissingAiConfiguration(RuntimeError):
    pass


class AssistantCommandRoiClient:
    def __init__(
        self,
        *,
        provider: str,
        command: list[str],
        timeout_seconds: float = 120.0,
    ) -> None:
        self.provider = provider
        self.command = command
        self.timeout_seconds = timeout_seconds

    async def generate(
        self,
        *,
        snapshot: NycLivingArtifactResult,
        roi_estimate: RoiEstimate,
    ) -> str:
        prompt = build_roi_demo_prompt(snapshot=snapshot, roi_estimate=roi_estimate)
        process = await asyncio.create_subprocess_exec(
            *self.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(prompt.encode("utf-8")),
                timeout=self.timeout_seconds,
            )
        except TimeoutError as exc:
            process.kill()
            await process.wait()
            raise RuntimeError(
                f"{self.provider} did not finish within {self.timeout_seconds:.0f}s"
            ) from exc

        if process.returncode != 0:
            raise RuntimeError(
                f"{self.provider} exited with {process.returncode}: "
                f"{stderr.decode('utf-8', errors='replace').strip()}"
            )

        narrative = stdout.decode("utf-8", errors="replace").strip()
        if not narrative:
            raise RuntimeError(f"{self.provider} returned an empty narrative")
        return narrative


async def build_ai_roi_demo(
    *,
    snapshot: NycLivingArtifactResult,
    assumptions: RoiAssumptions,
    client: AiRoiNarrativeClient | None,
    require_ai: bool = False,
) -> AiRoiDemoResult:
    roi_estimate = estimate_roi(snapshot=snapshot, assumptions=assumptions)
    source_snapshot = compact_snapshot(snapshot)

    if client is None:
        if require_ai:
            raise MissingAiConfiguration(
                "No assistant command is available. Install/authenticate Claude Code "
                "or Codex, or pass --ai-command."
            )
        return AiRoiDemoResult(
            generated_at=datetime.now(timezone.utc),
            ai_generated=False,
            provider="none",
            command=[],
            narrative_markdown=(
                "AI synthesis was not run. Rerun with --ai-provider claude, "
                "--ai-provider codex, or --ai-command for the real AI demo."
            ),
            roi_estimate=roi_estimate,
            source_snapshot=source_snapshot,
        )

    narrative = await client.generate(snapshot=snapshot, roi_estimate=roi_estimate)
    return AiRoiDemoResult(
        generated_at=datetime.now(timezone.utc),
        ai_generated=True,
        provider=client.provider,
        command=client.command,
        narrative_markdown=narrative,
        roi_estimate=roi_estimate,
        source_snapshot=source_snapshot,
    )


def estimate_roi(
    *,
    snapshot: NycLivingArtifactResult,
    assumptions: RoiAssumptions,
) -> RoiEstimate:
    minutes = round(snapshot.signals_seen * assumptions.minutes_saved_per_signal, 2)
    raw_hours = minutes / 60
    hours = round(raw_hours, 2)
    per_run = round(raw_hours * assumptions.analyst_hourly_cost_usd, 2)
    monthly = round(per_run * assumptions.runs_per_month, 2)
    return RoiEstimate(
        signals_triaged=snapshot.signals_seen,
        active_signals=snapshot.active_signal_count,
        estimated_minutes_saved_per_run=minutes,
        estimated_hours_saved_per_run=hours,
        estimated_labor_value_per_run_usd=per_run,
        estimated_labor_value_per_month_usd=monthly,
        assumptions=assumptions,
    )


def compact_snapshot(snapshot: NycLivingArtifactResult) -> dict[str, Any]:
    return {
        "place": snapshot.place,
        "time_window": snapshot.time_window,
        "generated_at": snapshot.generated_at.isoformat(),
        "since": snapshot.since.isoformat(),
        "datasets": [run.model_dump(mode="json") for run in snapshot.datasets],
        "signals_seen": snapshot.signals_seen,
        "signals_inserted": snapshot.signals_inserted,
        "signals_skipped": snapshot.signals_skipped,
        "operational_state": snapshot.operational_state,
        "risk_score": snapshot.risk_score,
        "active_signal_count": snapshot.active_signal_count,
        "summary": snapshot.summary,
        "what_changed": snapshot.what_changed,
        "why_it_matters": snapshot.why_it_matters,
        "drivers": snapshot.drivers[:5],
        "active_signals": snapshot.active_signals[:8],
        "recommended_actions": snapshot.recommended_actions,
        "evidence": snapshot.evidence[:8],
        "confidence": snapshot.confidence,
        "brief_url": snapshot.brief_url,
    }


def build_roi_demo_prompt(
    *,
    snapshot: NycLivingArtifactResult,
    roi_estimate: RoiEstimate,
) -> str:
    return f"""
You are generating a live ROI demo brief for The State.

Use only the provided JSON. Do not invent datasets, customers, incidents,
avoided losses, dollar amounts, or operational outcomes. The deterministic
LocationState is the source of truth. Your job is to explain what ran, what the
current state means, and how the ROI estimate was calculated.

Use exact numeric fields from the JSON. Do not recompute operational counts.
In particular, active_signal_count and signals_skipped are different concepts:
active_signal_count is the number of scored active signals; signals_skipped is
the number of raw records skipped by ingestion because they were already seen.
Never describe skipped records as "below threshold" unless the JSON says that.
Do not claim the pipeline ran "in seconds" or make any runtime claim unless a
runtime field is present in the JSON.
If brief_url starts with http://localhost, call it a local API brief URL, not a
public or stable URL.

Return concise Markdown with these sections:
- Live run
- State readout
- ROI case
- Why this is valuable
- Proof points

Clearly label ROI as assumption-based.
Keep it under 350 words.

JSON:
{
        json.dumps(
            {
                "snapshot": compact_snapshot(snapshot),
                "roi_estimate": roi_estimate.model_dump(mode="json"),
            },
            indent=2,
            default=str,
        )
    }
""".strip()
