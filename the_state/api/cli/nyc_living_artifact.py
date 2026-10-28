from __future__ import annotations

import argparse
import asyncio
import os
import shlex
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import cast

from core.db import AsyncSessionLocal
from ingestion.nyc import NYC_DATASETS, NycDatasetName, NycOpenDataCollector, SocrataClient
from services.ai_roi_demo_service import (
    AiRoiDemoResult,
    AssistantCommandRoiClient,
    MissingAiConfiguration,
    RoiAssumptions,
    build_ai_roi_demo,
)
from services.nyc_living_artifact_service import NycLivingArtifactResult, NycLivingArtifactService
from services.nyc_static_artifact_renderer import render_nyc_static_artifact


def main() -> None:
    args = _parse_args()
    result = asyncio.run(_run(args))
    if args.write_docs:
        write_docs_snapshot(
            result,
            docs_output_dir=args.docs_output_dir,
            site_base_url=args.site_base_url,
        )
    if args.ai_demo:
        demo = asyncio.run(_run_ai_demo(result, args))
        write_ai_demo(demo, demo_output_dir=args.demo_output_dir)
    print(result.model_dump_json(indent=2))


async def _run(args: argparse.Namespace):
    since = datetime.now(timezone.utc) - timedelta(hours=args.hours)
    async with SocrataClient(
        api_key_id=os.getenv("API_KEY_ID"),
        api_key_secret=os.getenv("API_KEY_SECRET"),
        app_token=os.getenv("SOCRATA_APP_TOKEN"),
    ) as socrata:
        collector = NycOpenDataCollector(socrata)
        async with AsyncSessionLocal() as db:
            service = NycLivingArtifactService(db, collector)
            return await service.run(
                place=args.place,
                watchlist_name=args.watchlist_name,
                time_window=args.time_window,
                since=since,
                dataset_names=args.dataset,
                limit_per_dataset=args.limit_per_dataset,
                brief_base_url=args.brief_base_url,
            )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch recent NYC Open Data signals, persist them, evaluate a "
            "watchlist, and generate a shareable brief."
        )
    )
    parser.add_argument("--place", default="New York, NY")
    parser.add_argument("--watchlist-name", default="NYC Living Watchlist")
    parser.add_argument("--time-window", default="24h")
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--limit-per-dataset", type=int, default=100)
    parser.add_argument("--brief-base-url", default="http://localhost:8000")
    parser.add_argument(
        "--write-docs",
        action="store_true",
        help="Write docs/state/nyc/latest.json and docs/state/nyc/index.html.",
    )
    parser.add_argument(
        "--docs-output-dir",
        type=Path,
        default=Path("docs/state/nyc"),
        help="Directory for generated static NYC artifact files.",
    )
    parser.add_argument(
        "--site-base-url",
        default="https://forest-builds.github.io/the-state",
        help="Public base URL used for static links.",
    )
    parser.add_argument(
        "--ai-demo",
        action="store_true",
        help="Run a live assistant synthesis step and write ROI demo artifacts.",
    )
    parser.add_argument(
        "--ai-provider",
        choices=["auto", "claude", "codex", "command", "none"],
        default="auto",
        help="Assistant provider for --ai-demo. Auto prefers Claude Code, then Codex.",
    )
    parser.add_argument(
        "--ai-command",
        help="Custom assistant command for --ai-provider command. The prompt is passed on stdin.",
    )
    parser.add_argument(
        "--ai-model",
        help="Optional model name passed through to claude or codex providers.",
    )
    parser.add_argument(
        "--require-ai",
        action="store_true",
        help="Fail if --ai-demo cannot run a real assistant command.",
    )
    parser.add_argument(
        "--demo-output-dir",
        type=Path,
        default=Path("docs/demo"),
        help="Directory for generated AI ROI demo artifacts.",
    )
    parser.add_argument(
        "--roi-minutes-saved-per-signal",
        type=float,
        default=5.0,
        help="ROI assumption: analyst triage minutes saved per signal.",
    )
    parser.add_argument(
        "--roi-analyst-hourly-cost-usd",
        type=float,
        default=75.0,
        help="ROI assumption: fully loaded hourly analyst cost.",
    )
    parser.add_argument(
        "--roi-runs-per-month",
        type=int,
        default=30,
        help="ROI assumption: monthly watchlist evaluations.",
    )
    parser.add_argument(
        "--dataset",
        action="append",
        choices=sorted(NYC_DATASETS),
        help="Dataset to collect. Repeat for multiple. Defaults to all NYC starter datasets.",
    )
    parsed = parser.parse_args()
    parsed.dataset = _datasets_or_default(parsed.dataset)
    return parsed


def _datasets_or_default(values: list[str] | None) -> list[NycDatasetName]:
    if values is None:
        return cast(list[NycDatasetName], list(NYC_DATASETS))
    return [cast(NycDatasetName, value) for value in values]


def write_docs_snapshot(
    result: NycLivingArtifactResult,
    *,
    docs_output_dir: Path,
    site_base_url: str,
) -> None:
    docs_output_dir.mkdir(parents=True, exist_ok=True)
    latest_json = docs_output_dir / "latest.json"
    latest_json.write_text(result.model_dump_json(indent=2), encoding="utf-8")

    latest_json_url = f"{site_base_url.rstrip('/')}/state/nyc/latest.json"
    index_html = docs_output_dir / "index.html"
    index_html.write_text(
        render_nyc_static_artifact(result, latest_json_href=latest_json_url),
        encoding="utf-8",
    )


async def _run_ai_demo(
    result: NycLivingArtifactResult,
    args: argparse.Namespace,
) -> AiRoiDemoResult:
    assumptions = RoiAssumptions(
        minutes_saved_per_signal=args.roi_minutes_saved_per_signal,
        analyst_hourly_cost_usd=args.roi_analyst_hourly_cost_usd,
        runs_per_month=args.roi_runs_per_month,
    )
    return await build_ai_roi_demo(
        snapshot=result,
        assumptions=assumptions,
        client=_assistant_client(args),
        require_ai=args.require_ai,
    )


def _assistant_client(args: argparse.Namespace) -> AssistantCommandRoiClient | None:
    provider = args.ai_provider
    if provider == "none":
        return None
    if provider == "command":
        if not args.ai_command:
            if args.require_ai:
                raise MissingAiConfiguration("--ai-command is required for --ai-provider command.")
            return None
        return AssistantCommandRoiClient(
            provider="command",
            command=shlex.split(args.ai_command),
        )
    if provider == "auto":
        if shutil.which("claude"):
            provider = "claude"
        elif shutil.which("codex"):
            provider = "codex"
        else:
            return None
    if provider == "claude":
        if not shutil.which("claude"):
            return None
        command = [
            "claude",
            "-p",
            "--output-format",
            "text",
            "--permission-mode",
            "dontAsk",
            "--tools",
            "",
            "--max-budget-usd",
            "1",
        ]
        if args.ai_model:
            command.extend(["--model", args.ai_model])
        return AssistantCommandRoiClient(provider="claude-code", command=command)
    if provider == "codex":
        if not shutil.which("codex"):
            return None
        command = [
            "codex",
            "exec",
            "--sandbox",
            "read-only",
            "--ask-for-approval",
            "never",
            "--ephemeral",
        ]
        if args.ai_model:
            command.extend(["--model", args.ai_model])
        command.append("-")
        return AssistantCommandRoiClient(provider="codex", command=command)
    return None


def write_ai_demo(
    demo: AiRoiDemoResult,
    *,
    demo_output_dir: Path,
) -> None:
    demo_output_dir.mkdir(parents=True, exist_ok=True)
    (demo_output_dir / "latest-ai-roi.json").write_text(
        demo.model_dump_json(indent=2),
        encoding="utf-8",
    )
    (demo_output_dir / "latest-ai-roi.md").write_text(
        demo.narrative_markdown,
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
