"""Static artifact renderer - operational decision infrastructure.

Decision-first, grounded, honest about coverage. The page answers one
question - "can this operation execute here, right now?" - from real
pulled records and a fixed deterministic mapping. No marketing narrative,
no implied data we do not actually connect. Fully usable with no
JavaScript; JS only recomputes the decision label when the operator
changes inputs (the same fixed rules, mirrored).
"""

from __future__ import annotations

import json
from html import escape

from services.nyc_living_artifact_service import NycLivingArtifactResult

_DECISION_LABEL = {
    "proceed": "PROCEED",
    "proceed_with_caution": "PROCEED WITH CAUTION",
    "hold": "HOLD",
    "escalate": "ESCALATE / REVIEW",
}
# Mirrors state_products.location_state.decision (fallback when an older
# snapshot has no precomputed decision).
_BASE = {
    "normal": "proceed",
    "elevated": "proceed_with_caution",
    "watch": "hold",
    "disrupted": "hold",
    "critical": "escalate",
}
_ACTION = {
    "proceed": "Dispatch as planned. Monitor for street-closure changes.",
    "proceed_with_caution": (
        "Dispatch with added monitoring; brief the crew on active closures and events in the area."
    ),
    "hold": (
        "Hold dispatch; reassess after the next refresh, or choose an "
        "alternate area or time window."
    ),
    "escalate": "Escalate to a human decision-maker before any dispatch.",
}
_AUTOMATION = {
    "proceed": "low_risk_only",
    "proceed_with_caution": "supervised_only",
    "hold": "no",
    "escalate": "no",
}


def _css_token(s: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in s.lower())


def _decision(snapshot: NycLivingArtifactResult) -> dict:
    d = dict(snapshot.decision or {})
    if d.get("decision"):
        return d
    state = (snapshot.operational_state or "normal").lower()
    dec = _BASE.get(state, "proceed")
    return {
        "decision": dec,
        "disruption_score": round(max(0.0, min(1.0, snapshot.risk_score)) * 100),
        "operational_state": state,
        "confidence": (
            "high"
            if snapshot.confidence >= 0.66
            else "medium"
            if snapshot.confidence >= 0.33
            else "low"
        ),
        "reason": (
            "No high-severity disruption was detected in the connected "
            "public records for the selected window."
            if dec == "proceed"
            else "Disruption signals are present in the connected public "
            "records for the selected window."
        ),
        "action": _ACTION[dec],
        "safe_for_automation": _AUTOMATION[dec],
        "operation_type": "field_dispatch",
        "time_window": snapshot.time_window,
        "risk_tolerance": "normal",
    }


def render_nyc_static_artifact(
    snapshot: NycLivingArtifactResult,
    *,
    latest_json_href: str = "./latest.json",
) -> str:
    d = _decision(snapshot)
    return (
        _HEAD
        + _STYLE
        + "<body>"
        + _topbar(latest_json_href)
        + _hero(snapshot, d)
        + _operation_panel(snapshot, d)
        + _decision_basis(snapshot)
        + _evidence(snapshot)
        + _how_calculated(snapshot)
        + _agent_api(snapshot, d)
        + _audit(snapshot)
        + _use_cases()
        + _footer(snapshot)
        + _script(latest_json_href, _embed(snapshot), d)
        + "</body></html>"
    )


def _embed(snapshot: NycLivingArtifactResult) -> str:
    return snapshot.model_dump_json().replace("</", "<\\/")


_HEAD = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>The State - operational reality check</title>
<meta name="description"
  content="The pre-action check for the physical world. Grounded,
  deterministic, source-backed.">
<meta name="robots" content="index,follow">
"""

_STYLE = """<style>
:root{--bg:#0a0b0d;--ink:#f3f5f7;--mut:#8a929e;--line:#1e232b;
 --card:#0f1318;--acc:#6c8cff;--ok:#46c98a;--warn:#e6bb45;
 --hold:#ec8a45;--stop:#e0533f;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
 font:16px/1.6 ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif;
 -webkit-font-smoothing:antialiased}
a{color:var(--acc);text-decoration:none}a:hover{text-decoration:underline}
.wrap{max-width:880px;margin:0 auto;padding:0 22px}
.bar{display:flex;justify-content:space-between;align-items:center;
 padding:16px 22px;max-width:880px;margin:0 auto;border-bottom:1px solid var(--line)}
.brand{font-weight:700;letter-spacing:.14em;font-size:.84rem}
.brand small{display:block;color:var(--mut);font-weight:500;
 letter-spacing:0;font-size:.72rem}
.bar a{color:var(--mut);font-size:.82rem;margin-left:16px}
section{padding:38px 0;border-top:1px solid var(--line)}
section:first-of-type{border-top:0;padding-top:34px}
.eyebrow{color:var(--mut);font-size:.72rem;letter-spacing:.16em;
 text-transform:uppercase;margin:0 0 10px}
h1{font-size:clamp(1.5rem,3.6vw,2.1rem);line-height:1.18;margin:0 0 18px;
 font-weight:750;letter-spacing:-.01em}
h2{font-size:1.04rem;text-transform:uppercase;letter-spacing:.06em;
 color:var(--mut);margin:0 0 16px;font-weight:700}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;
 padding:22px}
.dwrap{display:flex;flex-wrap:wrap;gap:14px;align-items:center;
 margin:0 0 16px}
.badge{font-weight:800;letter-spacing:.05em;font-size:1.15rem;
 padding:9px 18px;border-radius:8px;color:#08120c}
.d-proceed{background:var(--ok)}
.d-proceed_with_caution{background:var(--warn)}
.d-hold{background:var(--hold);color:#fff}
.d-escalate{background:var(--stop);color:#fff}
.kv{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
 gap:1px;background:var(--line);border:1px solid var(--line);
 border-radius:10px;overflow:hidden;margin:14px 0 0}
.kv div{background:var(--card);padding:13px 15px}
.kv .l{color:var(--mut);font-size:.7rem;text-transform:uppercase;
 letter-spacing:.07em;margin-bottom:4px}
.kv .v{font-weight:700;font-variant-numeric:tabular-nums}
.line{padding:11px 0;border-bottom:1px solid var(--line);font-size:.94rem;
 display:flex;justify-content:space-between;gap:14px}
.line:last-child{border-bottom:0}
.line .l{color:var(--mut)}
.ok{color:var(--ok)}.no{color:var(--mut)}
.tag{color:var(--acc);font-weight:700;font-variant-numeric:tabular-nums}
.warnbox{margin:16px 0 0;padding:12px 15px;border:1px solid var(--line);
 border-left:3px solid var(--warn);border-radius:8px;color:var(--mut);
 font-size:.88rem;background:rgba(230,187,69,.05)}
.panel{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));
 gap:12px;margin:0 0 6px}
.panel label{display:block;color:var(--mut);font-size:.72rem;
 text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px}
.panel select,.panel input{width:100%;background:var(--bg);
 border:1px solid var(--line);color:var(--ink);border-radius:9px;
 padding:11px 13px;font:inherit}
table{width:100%;border-collapse:collapse;font-size:.9rem}
td,th{text-align:left;padding:9px 10px;border-bottom:1px solid var(--line)}
th{color:var(--mut);font-size:.72rem;text-transform:uppercase;
 letter-spacing:.05em;font-weight:650}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
pre{background:#070809;border:1px solid var(--line);border-radius:10px;
 padding:15px;overflow:auto;color:#d7dde7;font:12.5px/1.6 ui-monospace,
 SFMono-Regular,Menlo,monospace;margin:0 0 12px}
.codehdr{display:flex;justify-content:space-between;color:var(--mut);
 font-size:.74rem;margin:0 0 6px}
details{border-top:1px solid var(--line);padding:14px 0}
summary{cursor:pointer;font-weight:650;list-style:none}
summary::-webkit-details-marker{display:none}
summary::after{content:" +";color:var(--mut)}
details[open] summary::after{content:" \\2212"}
.dd{padding-top:12px;color:var(--mut);font-size:.9rem}
.dd code{color:var(--acc);word-break:break-all}
.sub{color:var(--mut);font-size:.92rem;margin:0 0 16px}
.uc{display:grid;gap:10px}
.uc div{padding:14px 16px;background:var(--card);
 border:1px solid var(--line);border-radius:10px;font-size:.93rem}
.uc b{color:var(--ink)}
footer{padding:34px 0 56px;border-top:1px solid var(--line);
 color:var(--mut);font-size:.85rem}
</style>
"""


def _topbar(href: str) -> str:
    return f"""
<div class="bar">
  <span class="brand">THE STATE
    <small>The pre-action check for the physical world</small></span>
  <span><a href="#basis">Decision basis</a>
    <a href="#api">Agent API</a>
    <a href="{escape(href)}">latest.json</a></span>
</div>
"""


def _hero(snapshot: NycLivingArtifactResult, d: dict) -> str:
    dec = str(d["decision"])
    return f"""
<section><div class="wrap">
  <p class="eyebrow">Operational reality check</p>
  <h1>Can I send a field crew in {escape(snapshot.place)} right now?</h1>
  <div class="card">
    <div class="dwrap">
      <span class="badge d-{_css_token(dec)}" id="decBadge">
        {escape(_DECISION_LABEL.get(dec, dec.upper()))}</span>
      <span class="l" style="color:var(--mut)">level
        <b style="color:var(--ink)" id="lvl">
        {escape(str(d["operational_state"]).upper())}</b></span>
    </div>
    <p id="reason">{escape(str(d["reason"]))}</p>
    <p><b>Action:</b> <span id="action">{escape(str(d["action"]))}</span></p>
    <div class="kv">
      <div><div class="l">Disruption score</div>
        <div class="v" id="score">{int(d["disruption_score"])}/100</div></div>
      <div><div class="l">Confidence</div>
        <div class="v">{escape(str(d["confidence"]).title())}</div></div>
      <div><div class="l">Safe for automation</div>
        <div class="v" id="auto">
        {escape(str(d["safe_for_automation"]).replace("_", " "))}</div></div>
      <div><div class="l">Data window</div>
        <div class="v">{escape(snapshot.time_window)}</div></div>
      <div><div class="l">Last updated</div>
        <div class="v">{escape(snapshot.generated_at.strftime("%Y-%m-%d %H:%M UTC"))}</div></div>
    </div>
    <div class="warnbox">Coverage: this decision uses only currently
       connected public records (NYC). Sources not connected are excluded,
       not assumed safe - see the decision basis below.</div>
  </div>
</div></section>
"""


def _operation_panel(snapshot: NycLivingArtifactResult, d: dict) -> str:
    return f"""
<section><div class="wrap">
  <h2>Operation</h2>
  <p class="sub">The decision is a fixed mapping over the live state.
     Changing operation or risk tolerance re-derives it with the same
     rules; the data window is fixed to what was pulled.</p>
  <div class="panel">
    <div><label>Location</label>
      <input id="opLoc" value="{escape(snapshot.place)}" disabled></div>
    <div><label>Operation type</label>
      <select id="opType">
        <option value="field_dispatch">Send field crew</option>
        <option value="crew_routing">Route a crew</option>
        <option value="site_visit">Site visit</option>
        <option value="delivery">Delivery</option>
      </select></div>
    <div><label>Time window</label>
      <select id="opWin">
        <option value="next_4_hours">Next 4 hours</option>
        <option value="next_24_hours">Next 24 hours</option>
      </select></div>
    <div><label>Risk tolerance</label>
      <select id="opTol">
        <option value="low">Low (risk-averse)</option>
        <option value="normal" selected>Normal</option>
        <option value="high">High</option>
      </select></div>
  </div>
</div></section>
"""


def _decision_basis(snapshot: NycLivingArtifactResult) -> str:
    cov = snapshot.coverage or {}
    connected = list(cov.get("included") or [])
    if not connected:
        connected = [r.dataset for r in snapshot.datasets]
    excluded = list(cov.get("excluded") or [])
    on = "".join(
        f'<div class="line"><span class="l">{escape(str(s))}</span>'
        f'<span class="ok">connected</span></div>'
        for s in connected
    )
    off = "".join(
        f'<div class="line"><span class="l">{escape(str(s))}</span>'
        f'<span class="no">not included in this decision</span></div>'
        for s in excluded
    )
    return f"""
<section id="basis"><div class="wrap">
  <h2>Decision basis</h2>
  <p class="sub">Exactly what this decision is - and is not - built on.
     Transparency is part of the product.</p>
  <div class="card">{on}{off}</div>
</div></section>
"""


def _evidence(snapshot: NycLivingArtifactResult) -> str:
    ds = (
        "".join(
            f"<tr><td>{escape(r.dataset)}</td><td class='n'>{r.collected}</td></tr>"
            for r in snapshot.datasets
        )
        or "<tr><td>No records in this window</td><td class='n'>0</td></tr>"
    )
    sig = (
        "".join(
            f"<tr><td>{escape(str(s.get('title') or s.get('signal_type', '')))}</td>"
            f"<td>{escape(str(s.get('source', '') or '-'))}</td>"
            f"<td><code>{escape(str(s.get('signal_id', '')))}</code></td></tr>"
            for s in snapshot.active_signals
        )
        or "<tr><td colspan='3'>No active signals - the all-clear is the answer.</td></tr>"
    )
    return f"""
<section><div class="wrap">
  <h2>Evidence used for this decision</h2>
  <p class="sub">The public records pulled for this place and window, and
     the signals that moved the score.</p>
  <table><tr><th>Connected source</th><th class="n">Records pulled</th></tr>
    {ds}</table>
  <table style="margin-top:16px">
    <tr><th>Signal</th><th>Source</th><th>Record id</th></tr>{sig}</table>
</div></section>
"""


def _how_calculated(snapshot: NycLivingArtifactResult) -> str:
    rows = (
        "".join(
            f"<tr><td>{escape(str(x.get('label', '-')))}</td>"
            f"<td class='n tag'>+{round(float(x.get('weight', 0)) * 100)}</td></tr>"
            for x in snapshot.drivers
        )
        or "<tr><td>Nothing pushed the score up</td><td class='n'>0</td></tr>"
    )
    actions = "".join(
        f"<li>{escape(str(a.get('action', '')))}</li>" for a in snapshot.recommended_actions
    )
    return f"""
<section><div class="wrap">
  <h2>How the decision was calculated</h2>
  <p class="sub">Fixed scoring rules over the connected records. Same
     inputs, same number, every time. No AI moves this.</p>
  <table><tr><th>Driver</th><th class="n">Adds to score</th></tr>
    {rows}
    <tr><td><b>Operational disruption score</b></td>
      <td class="n"><b>{round(max(0.0, min(1.0, snapshot.risk_score)) * 100)}</b></td></tr>
  </table>
  <details><summary>Operator actions for this state</summary>
    <div class="dd"><ul>{actions or "<li>Continue normal operations.</li>"}
    </ul></div></details>
</div></section>
"""


def _agent_api(snapshot: NycLivingArtifactResult, d: dict) -> str:
    req = {
        "location": snapshot.place,
        "operation_type": d.get("operation_type", "field_dispatch"),
        "time_window": d.get("time_window", "next_4_hours"),
        "risk_tolerance": d.get("risk_tolerance", "normal"),
    }
    cov = snapshot.coverage or {}
    resp = {
        "decision": d["decision"],
        "score": int(d["disruption_score"]),
        "level": d["operational_state"],
        "confidence": d["confidence"],
        "coverage_level": cov.get("level", "limited"),
        "safe_for_automation": d["safe_for_automation"],
        "action": d["action"],
        "included_sources": cov.get("included") or [r.dataset for r in snapshot.datasets],
        "excluded_sources": cov.get("excluded") or [],
        "coverage_warning": cov.get("warning", ""),
    }
    rj = json.dumps(req, indent=2)
    sj = json.dumps(resp, indent=2)
    return f"""
<section id="api"><div class="wrap">
  <h2>The call an agent makes before acting</h2>
  <p class="sub">Real endpoint. The response below is the actual decision
     for this place and window - not a mock.</p>
  <div class="codehdr"><span>POST /decisions/check</span></div>
  <pre>{escape(rj)}</pre>
  <div class="codehdr"><span>200 OK</span></div>
  <pre>{escape(sj)}</pre>
</div></section>
"""


def _audit(snapshot: NycLivingArtifactResult) -> str:
    return f"""
<section><div class="wrap">
  <h2>Audit &amp; replay</h2>
  <p class="sub">Every decision is backed by an immutable, citable brief
     and the archived records behind it.</p>
  <div class="line"><span class="l">Brief</span>
    <a href="{escape(snapshot.brief_url)}">
    {escape(str(snapshot.brief_id))}</a></div>
  <div class="line"><span class="l">Content credential (SHA-256)</span>
    <code class="tag">{escape(snapshot.content_hash or "(pending first run)")}</code></div>
  <div class="line"><span class="l">Independent verification</span>
    <span>re-hash the brief body; if one character changed it would not
    match</span></div>
  <p class="sub" style="margin-top:14px">{snapshot.signals_seen} records
     seen &middot; {snapshot.signals_inserted} new &middot; archived before
     interpretation, so any decision can be replayed from source.</p>
</div></section>
"""


def _use_cases() -> str:
    return """
<section><div class="wrap">
  <h2>Who runs this check</h2>
  <div class="uc">
    <div><b>Dispatch / field ops</b> - run the check before sending a
       crew or truck so you do not roll into a closed corridor that was
       public hours ago.</div>
    <div><b>Risk / claims / audit</b> - keep a permanent, source-backed
       record of the conditions a decision was made under.</div>
    <div><b>Agents / automations</b> - one call your agent makes before it
       dispatches, routes, books, or acts in the physical world.</div>
  </div>
</div></section>
"""


def _footer(snapshot: NycLivingArtifactResult) -> str:
    return f"""
<footer><div class="wrap">
  New York is live. Other geographies can use the same decision format as
  coverage expands. Generated
  {escape(snapshot.generated_at.strftime("%Y-%m-%d %H:%M UTC"))} &middot;
  deterministic &middot; source-backed &middot; replayable.
</div></footer>
"""


def _script(href: str, embedded: str, d: dict) -> str:
    cfg = json.dumps(
        {
            "state": d["operational_state"],
            "score": int(d["disruption_score"]),
            "tol0": d.get("risk_tolerance", "normal"),
        }
    )
    body = """
<script id="snapshot" type="application/json">__JSON__</script>
<script>
(function(){
 "use strict";
 var C=__CFG__;
 var LADDER=["proceed","proceed_with_caution","hold","escalate"];
 var BASE={normal:0,elevated:1,watch:2,disrupted:2,critical:3};
 var LABEL={proceed:"PROCEED",
  proceed_with_caution:"PROCEED WITH CAUTION",hold:"HOLD",
  escalate:"ESCALATE / REVIEW"};
 var ACT={proceed:"Dispatch as planned. Monitor for street-closure changes.",
  proceed_with_caution:"Dispatch with added monitoring; brief the crew on "+
   "active closures and events in the area.",
  hold:"Hold dispatch; reassess after the next refresh, or choose an "+
   "alternate area or time window.",
  escalate:"Escalate to a human decision-maker before any dispatch."};
 var AUTO={proceed:"low risk only",
  proceed_with_caution:"supervised only",hold:"no",escalate:"no"};
 function recompute(){
  var tol=(document.getElementById("opTol")||{}).value||"normal";
  var shift=tol==="low"?1:(tol==="high"?-1:0);
  var base=BASE[C.state]!==undefined?BASE[C.state]:0;
  var floor=(C.state==="watch"||C.state==="disrupted")&&shift<0?2:0;
  var i=Math.max(floor,Math.min(LADDER.length-1,base+shift));
  var dec=LADDER[i];
  var b=document.getElementById("decBadge");
  if(b){b.textContent=LABEL[dec];b.className="badge d-"+dec;}
  var a=document.getElementById("action");if(a)a.textContent=ACT[dec];
  var au=document.getElementById("auto");if(au)au.textContent=AUTO[dec];
 }
 ["opTol","opType","opWin"].forEach(function(id){
  var el=document.getElementById(id);
  if(el)el.addEventListener("change",recompute);
 });
})();
</script>
"""
    return body.replace("__JSON__", embedded).replace("__CFG__", cfg)
