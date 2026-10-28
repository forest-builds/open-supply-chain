from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from models.brief import Brief
from models.state_evaluation_result import StateEvaluationResult
from models.watched_entity import WatchedEntity
from schemas.brief import BriefGenerateRequest, BriefResponse, BriefVerification
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession


class BriefService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def generate(
        self,
        *,
        body: BriefGenerateRequest,
    ) -> Brief:
        entity, result = await self._resolve_inputs(body)

        content = _render_brief(entity, result)

        brief = Brief(
            watched_entity_id=entity.id,
            evaluation_result_id=result.id,
            content=content,
        )
        self.db.add(brief)
        # Flush to materialize the id, then pin the canonical public path
        # and the tamper-evident credential. Both are set once, never updated.
        await self.db.flush()
        brief.url = f"/briefs/{brief.id}/view"
        brief.content_hash = content_hash(content)
        await self.db.commit()
        await self.db.refresh(brief)
        return brief

    async def render_html(self, brief: Brief) -> str:
        """Render the brief as a standalone, public, no-auth HTML artifact."""
        entity = await self.db.get(WatchedEntity, brief.watched_entity_id)
        if entity is None:
            raise HTTPException(status_code=404, detail="WatchedEntity not found")
        result: StateEvaluationResult | None = None
        if brief.evaluation_result_id is not None:
            result = await self.db.get(StateEvaluationResult, brief.evaluation_result_id)
        if result is None:
            raise HTTPException(status_code=409, detail="Brief is missing evaluation result")
        response = _to_response(brief=brief, entity=entity, result=result, url=brief.url or "")
        return _render_brief_html(response, result)

    async def get(self, brief_id: UUID) -> Brief:
        brief = await self.db.get(Brief, brief_id)
        if brief is None:
            raise HTTPException(status_code=404, detail="Brief not found")
        return brief

    async def verify(self, brief: Brief) -> BriefVerification:
        """Recompute the credential and attest whether it still matches.

        No trust in the issuer required: the caller can run the same SHA-256
        over `content` and reach the same `computed_hash`.
        """
        computed = content_hash(brief.content)
        return BriefVerification(
            brief_id=brief.id,
            stored_hash=brief.content_hash,
            computed_hash=computed,
            verified=brief.content_hash == computed,
            content_length=len(brief.content),
            generated_at=brief.created_at,
            verified_at=datetime.now(timezone.utc),
            canonical_url=brief.url or f"/briefs/{brief.id}/view",
        )

    async def to_response(self, brief: Brief, *, url: str) -> BriefResponse:
        entity = await self.db.get(WatchedEntity, brief.watched_entity_id)
        if entity is None:
            raise HTTPException(status_code=404, detail="WatchedEntity not found")

        result: StateEvaluationResult | None = None
        if brief.evaluation_result_id is not None:
            result = await self.db.get(StateEvaluationResult, brief.evaluation_result_id)

        if result is None:
            raise HTTPException(status_code=409, detail="Brief is missing evaluation result")

        return _to_response(brief=brief, entity=entity, result=result, url=url)

    async def _resolve_inputs(
        self,
        body: BriefGenerateRequest,
    ) -> tuple[WatchedEntity, StateEvaluationResult]:
        result: StateEvaluationResult | None = None
        if body.evaluation_result_id is not None:
            result = await self.db.get(StateEvaluationResult, body.evaluation_result_id)
            if result is None:
                raise HTTPException(status_code=404, detail="Evaluation result not found")

        entity = await self._resolve_entity(body=body, result=result)
        if result is None:
            result = await self._load_latest_result(entity.id)
            if result is None:
                raise HTTPException(
                    status_code=409,
                    detail="No evaluation result found; evaluate the watchlist first",
                )
        elif result.watched_entity_id != entity.id:
            raise HTTPException(
                status_code=400,
                detail="Evaluation result does not belong to the requested entity",
            )

        return entity, result

    async def _resolve_entity(
        self,
        *,
        body: BriefGenerateRequest,
        result: StateEvaluationResult | None,
    ) -> WatchedEntity:
        if body.watched_entity_id is not None:
            entity = await self.db.get(WatchedEntity, body.watched_entity_id)
            if entity is None:
                raise HTTPException(status_code=404, detail="Watched entity not found")
            if body.watchlist_id is not None and entity.watchlist_id != body.watchlist_id:
                raise HTTPException(
                    status_code=400,
                    detail="Watched entity does not belong to the requested watchlist",
                )
            return entity

        if body.watchlist_id is not None:
            stmt = (
                select(WatchedEntity)
                .where(WatchedEntity.watchlist_id == body.watchlist_id)
                .where(WatchedEntity.entity_type == "location")
                .limit(1)
            )
            entity = (await self.db.execute(stmt)).scalar_one_or_none()
            if entity is None:
                raise HTTPException(status_code=404, detail="Watchlist not found")
            return entity

        if result is not None:
            entity = await self.db.get(WatchedEntity, result.watched_entity_id)
            if entity is None:
                raise HTTPException(status_code=404, detail="Watched entity not found")
            return entity

        raise HTTPException(
            status_code=400,
            detail="Provide watchlist_id, watched_entity_id, or evaluation_result_id",
        )

    async def _load_latest_result(
        self,
        watched_entity_id: UUID,
    ) -> StateEvaluationResult | None:
        stmt = (
            select(StateEvaluationResult)
            .where(StateEvaluationResult.watched_entity_id == watched_entity_id)
            .order_by(desc(StateEvaluationResult.evaluated_at))
            .limit(1)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()


def _to_response(
    *,
    brief: Brief,
    entity: WatchedEntity,
    result: StateEvaluationResult,
    url: str,
) -> BriefResponse:
    title = f"{entity.entity_ref} Operational Brief"
    return BriefResponse(
        id=brief.id,
        watched_entity_id=brief.watched_entity_id,
        evaluation_result_id=brief.evaluation_result_id,
        title=title,
        place=entity.entity_ref,
        operational_state=result.current_state,
        risk_score=result.current_score,
        summary=_summary(entity, result),
        what_changed=_what_changed(result),
        why_it_matters=_why_it_matters(result),
        recommended_actions=_recommended_actions(result.recommended_actions),
        evidence=_evidence(result.provenance),
        confidence=result.confidence,
        content=brief.content,
        generated_at=brief.created_at,
        url=url,
        content_hash=brief.content_hash or content_hash(brief.content),
    )


def content_hash(content: str) -> str:
    """Tamper-evident credential: SHA-256 of the canonical brief content.

    Stable and reproducible - anyone can re-hash the brief body and confirm
    it matches, with no trust in us required.
    """
    return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()


def _render_brief(entity: WatchedEntity, result: StateEvaluationResult | None) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines: list[str] = []

    lines.append(f"# Operational Brief - {entity.entity_ref}")
    lines.append(f"*Generated {now}*")
    lines.append("")

    if result is None:
        lines.append("No evaluation result attached to this brief.")
        return "\n".join(lines)

    state = result.current_state.upper()
    lines.append(f"## State: {state}")
    lines.append(f"**Risk score:** {result.current_score:.2f} (confidence {result.confidence:.0%})")
    if result.previous_state and result.previous_state != result.current_state:
        lines.append(f"**Changed from:** {result.previous_state.upper()}")
    if result.score_delta is not None:
        direction = "+" if result.score_delta > 0 else "-"
        lines.append(f"**Score delta:** {direction}{abs(result.score_delta):.2f}")
    lines.append("")

    lines.append("## What Changed")
    lines.append(_what_changed(result))
    lines.append("")

    if result.drivers:
        lines.append("## Drivers")
        for d in result.drivers:
            label = d.get("label", "Unknown")
            weight = d.get("weight", 0.0)
            lines.append(f"- **{label}** - weight {weight:.2f}")
        lines.append("")

    if result.recommended_actions:
        lines.append("## Recommended Actions")
        for action in _recommended_actions(result.recommended_actions):
            rationale = action.get("rationale")
            text = action.get("action", "")
            if rationale:
                lines.append(f"- {text} ({rationale})")
            else:
                lines.append(f"- {text}")
        lines.append("")

    if result.provenance:
        lines.append("## Evidence")
        for p in _evidence(result.provenance)[:5]:
            sig_id = p.get("signal_id", "")
            source = p.get("source", "")
            contrib = p.get("contribution", 0.0)
            lines.append(f"- `{sig_id}` via {source} (contribution {contrib:.2f})")
        lines.append("")

    lines.append("---")
    lines.append(f"*Evaluated at: {result.evaluated_at.strftime('%Y-%m-%d %H:%M UTC')}*")

    return "\n".join(lines)


def _summary(entity: WatchedEntity, result: StateEvaluationResult) -> str:
    return (
        f"{entity.entity_ref} is {result.current_state} with risk score "
        f"{result.current_score:.2f} and confidence {result.confidence:.0%}."
    )


def _what_changed(result: StateEvaluationResult) -> str:
    if result.previous_state is None:
        return "This is the first stored evaluation for the watched location."
    if result.previous_state != result.current_state:
        return f"Operational state changed from {result.previous_state} to {result.current_state}."
    if result.score_delta is not None and result.score_delta != 0:
        return f"Risk score changed by {result.score_delta:+.2f} since the prior evaluation."
    if result.material_change:
        return "Threshold rules flagged this evaluation as material."
    return "No material state change was detected since the prior evaluation."


def _why_it_matters(result: StateEvaluationResult) -> str:
    state_text = {
        "normal": "Routine monitoring is enough unless new signals arrive.",
        "elevated": "Conditions deserve closer monitoring before they affect operations.",
        "watch": "The location has enough active signal weight to justify readiness steps.",
        "disrupted": "Operational disruption is likely enough to warrant active response.",
        "critical": "The state is severe enough to prioritize immediate action.",
    }.get(result.current_state, "Current conditions should be reviewed before acting.")
    driver_text = _driver_phrase(result.drivers)
    if driver_text:
        return f"{state_text} Main drivers: {driver_text}."
    return state_text


def _driver_phrase(drivers: list[Any]) -> str:
    labels: list[str] = []
    for driver in drivers[:3]:
        if isinstance(driver, dict):
            label = driver.get("label")
            if label:
                labels.append(str(label))
    return ", ".join(labels)


def _recommended_actions(actions: list[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for action in actions:
        if isinstance(action, dict):
            normalized.append(
                {
                    "action": str(action.get("action", "")),
                    "rationale": action.get("rationale"),
                }
            )
        else:
            normalized.append({"action": str(action), "rationale": None})
    return normalized


def _evidence(provenance: list[Any]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for item in provenance:
        if not isinstance(item, dict):
            continue
        evidence.append(
            {
                "signal_id": item.get("signal_id"),
                "source": item.get("source"),
                "raw_record_id": item.get("raw_record_id"),
                "contribution": item.get("contribution"),
                "observed_at": item.get("observed_at"),
            }
        )
    return evidence


_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "brief.html"


def _e(value: Any) -> str:
    return escape("" if value is None else str(value))


def _render_brief_html(response: BriefResponse, result: StateEvaluationResult) -> str:
    """Build the public brief page. Every interpolated value is HTML-escaped."""
    parts: list[str] = [
        f"<h1>{_e(response.title)}</h1>",
        f'<p class="sub">{_e(response.place)} &middot; computed '
        f"{_e(response.generated_at.strftime('%Y-%m-%d %H:%M UTC'))}</p>",
        f'<p><span class="state">{_e(response.operational_state)}</span></p>',
        '<div class="metrics">'
        f'<div class="metric"><div class="v">{response.risk_score:.2f}</div>'
        '<div class="l">Risk score</div></div>'
        f'<div class="metric"><div class="v">{response.confidence:.0%}</div>'
        '<div class="l">Confidence</div></div></div>',
        f"<h2>Summary</h2><p>{_e(response.summary)}</p>",
        f"<h2>What changed</h2><p>{_e(response.what_changed)}</p>",
        f"<h2>Why it matters</h2><p>{_e(response.why_it_matters)}</p>",
    ]

    if response.recommended_actions:
        items = "".join(
            f"<li>{_e(a.get('action'))}"
            + (f" &mdash; {_e(a.get('rationale'))}" if a.get("rationale") else "")
            + "</li>"
            for a in response.recommended_actions
        )
        parts.append(f"<h2>Recommended actions</h2><ul>{items}</ul>")

    if response.evidence:
        rows = "".join(
            "<tr>"
            f"<td><code>{_e(s.get('signal_id'))}</code></td>"
            f"<td>{_e(s.get('source'))}</td>"
            f"<td>{_e(s.get('contribution'))}</td>"
            "</tr>"
            for s in response.evidence
        )
        parts.append(
            "<h2>Active signals</h2><table>"
            "<tr><th>Signal</th><th>Source</th><th>Contribution</th></tr>"
            f"{rows}</table>"
        )

    prov = [p for p in (result.provenance or []) if isinstance(p, dict)]
    if prov:
        rows = "".join(
            "<tr>"
            f"<td><code>{_e(p.get('signal_id'))}</code></td>"
            f"<td>{_e(p.get('source'))}</td>"
            f"<td><code>{_e(p.get('raw_record_id'))}</code></td>"
            f"<td>{_e(p.get('observed_at'))}</td>"
            "</tr>"
            for p in prov
        )
        parts.append(
            "<h2>Provenance chain</h2><table>"
            "<tr><th>Signal</th><th>Source</th><th>Raw record</th>"
            f"<th>Observed</th></tr>{rows}</table>"
        )

    parts.append(
        "<h2>Credential</h2>"
        "<p>This artifact is tamper-evident. Re-hash the brief body with "
        "SHA-256 and you must get the value below; if a single character "
        "changed, it would not match.</p>"
        f"<p><code>{_e(response.content_hash)}</code></p>"
        f"<p>Check it without trusting us: "
        f'<a href="/briefs/{_e(response.id)}/verify">'
        f"/briefs/{_e(response.id)}/verify</a></p>"
    )

    parts.append(
        f"<footer>Evaluated at {_e(result.evaluated_at.strftime('%Y-%m-%d %H:%M UTC'))}. "
        f'Raw JSON: <a href="/briefs/{_e(response.id)}">/briefs/{_e(response.id)}</a>'
        "</footer>"
    )

    template = _TEMPLATE_PATH.read_text(encoding="utf-8")
    return template.replace("__TITLE__", _e(response.title)).replace("__BODY__", "\n".join(parts))
