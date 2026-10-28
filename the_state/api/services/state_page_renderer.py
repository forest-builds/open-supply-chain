from __future__ import annotations

import json
from html import escape

from state_products.location_state.schema import LocationState


def render_location_state_page(state: LocationState) -> str:
    """Render a shareable living state page from deterministic LocationState."""

    api_payload = escape(json.dumps(state.model_dump(mode="json"), indent=2))
    status = state.operational_state.value.upper()
    risk_percent = round(state.risk_score * 100)
    confidence_percent = round(state.confidence * 100)

    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{escape(state.place)} State - The State</title>
    <style>
      :root {{
        --ink: #12201f;
        --muted: #5e6763;
        --line: #d8d4ca;
        --paper: #fbfaf6;
        --soft: #f1eee7;
        --panel: #ffffff;
        --green: #2e6f73;
        --amber: #f6c35b;
        --red: #b94e48;
      }}
      * {{ box-sizing: border-box; }}
      body {{
        margin: 0;
        background: var(--paper);
        color: var(--ink);
        font-family:
          Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
          "Segoe UI", sans-serif;
        letter-spacing: 0;
      }}
      header {{
        display: flex;
        justify-content: space-between;
        gap: 24px;
        padding: 24px clamp(18px, 4vw, 56px);
        border-bottom: 1px solid var(--line);
        background: rgba(251, 250, 246, 0.94);
      }}
      .brand {{ display: flex; align-items: center; gap: 10px; font-weight: 800; }}
      .mark {{
        width: 28px;
        height: 28px;
        border: 2px solid var(--ink);
        border-radius: 8px;
        background: var(--amber);
      }}
      main {{ padding: clamp(28px, 5vw, 72px) clamp(18px, 4vw, 56px); }}
      .hero {{
        display: grid;
        grid-template-columns: minmax(0, 1.1fr) minmax(320px, 0.9fr);
        gap: 20px;
        align-items: start;
      }}
      .eyebrow {{
        margin: 0 0 14px;
        color: var(--green);
        font-size: 13px;
        font-weight: 850;
        text-transform: uppercase;
      }}
      h1 {{
        margin: 0 0 18px;
        font-size: clamp(42px, 7vw, 84px);
        line-height: 0.96;
        letter-spacing: 0;
      }}
      h2 {{ margin: 0 0 14px; font-size: 24px; }}
      p {{ line-height: 1.55; }}
      .lede {{ max-width: 720px; color: var(--muted); font-size: 20px; }}
      .panel {{
        border: 1px solid var(--line);
        border-radius: 8px;
        background: var(--panel);
        padding: 20px;
      }}
      .panel + .panel {{ margin-top: 14px; }}
      .status {{
        display: inline-flex;
        align-items: center;
        min-height: 42px;
        padding: 0 14px;
        border: 1px solid #d79f31;
        border-radius: 8px;
        background: #fff2ce;
        color: #5d4205;
        font-weight: 900;
      }}
      .metrics {{
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 10px;
        margin-top: 24px;
      }}
      .metric {{
        min-height: 92px;
        padding: 14px;
        border: 1px solid var(--line);
        border-radius: 8px;
        background: #fffdfa;
      }}
      .metric span {{
        display: block;
        color: var(--muted);
        font-size: 12px;
        font-weight: 800;
        text-transform: uppercase;
      }}
      .metric strong {{ display: block; margin-top: 10px; font-size: 30px; }}
      .visual {{
        display: block;
        width: 100%;
        min-height: 220px;
        border: 1px solid var(--line);
        border-radius: 8px;
        background: var(--soft);
      }}
      .list {{ display: grid; gap: 10px; margin: 14px 0 0; padding: 0; list-style: none; }}
      .list li {{
        padding: 13px;
        border: 1px solid var(--line);
        border-radius: 8px;
        background: #fffdfa;
      }}
      .grid {{
        display: grid;
        grid-template-columns: minmax(0, 1fr) minmax(300px, 0.7fr);
        gap: 14px;
        margin-top: 18px;
      }}
      .button {{
        display: inline-flex;
        align-items: center;
        min-height: 40px;
        padding: 0 14px;
        border: 1px solid var(--ink);
        border-radius: 8px;
        background: var(--ink);
        color: #fff;
        font-weight: 800;
      }}
      pre {{
        margin: 0;
        padding: 18px;
        overflow: auto;
        border-radius: 8px;
        background: #101918;
        color: #eef7f0;
        font-size: 13px;
        line-height: 1.5;
      }}
      @media (max-width: 900px) {{
        .hero, .grid {{ grid-template-columns: 1fr; }}
        .metrics {{ grid-template-columns: 1fr; }}
      }}
    </style>
  </head>
  <body>
    <header>
      <div class="brand"><span class="mark"></span><span>The State</span></div>
      <span class="status">{status}</span>
    </header>
    <main>
      <section class="hero">
        <div>
          <p class="eyebrow">LocationState</p>
          <h1>{escape(state.place)}</h1>
          <p class="lede">{escape(state.summary)}</p>
          <div class="metrics">
            <div class="metric"><span>Risk score</span><strong>{risk_percent}%</strong></div>
            <div class="metric"><span>Confidence</span><strong>{confidence_percent}%</strong></div>
            <div class="metric">
              <span>Window</span><strong>{escape(state.time_window)}</strong>
            </div>
          </div>
        </div>
        <svg class="visual" viewBox="0 0 640 360" role="img" aria-label="Operational state field">
          <rect width="640" height="360" fill="#f1eee7"></rect>
          <path
            d="M0 229C77 197 123 207 178 179
               C247 144 290 72 369 79
               C463 88 475 189 577 169
               C603 164 623 152 640 138V360H0V229Z"
            fill="#e7f1ec"
          ></path>
          <path
            d="M135 226C187 201 243 202 284 176C331 147 365 117 437 131"
            stroke="#2e6f73"
            stroke-width="4"
            stroke-linecap="round"
          ></path>
          <path
            d="M203 146C251 155 276 171 312 173C359 177 389 158 440 164"
            stroke="#b94e48"
            stroke-width="3"
            stroke-linecap="round"
          ></path>
          <circle cx="316" cy="173" r="42" fill="#12201f"></circle>
          <circle cx="316" cy="173" r="31" fill="#f6c35b"></circle>
          <circle cx="316" cy="173" r="14" fill="#12201f"></circle>
        </svg>
      </section>

      <section class="grid" aria-label="State details">
        <div>
          <article class="panel">
            <h2>What changed</h2>
            <ul class="list">{_recent_changes_html(state)}</ul>
          </article>
          <article class="panel">
            <h2>Recommended actions</h2>
            <ul class="list">{_recommendations_html(state)}</ul>
          </article>
        </div>
        <aside>
          <article class="panel">
            <h2>Why it matters</h2>
            <p>{escape(_why_it_matters(state))}</p>
          </article>
          <article class="panel">
            <h2>Evidence</h2>
            <ul class="list">{_provenance_html(state)}</ul>
          </article>
          <article class="panel">
            <h2>Watch</h2>
            <p>Watch button placeholder. This becomes POST /watchlists next.</p>
            <span class="button">Watch this location</span>
          </article>
        </aside>
      </section>

      <section class="panel" style="margin-top: 14px;">
        <h2>API example</h2>
        <pre>{api_payload}</pre>
      </section>
    </main>
  </body>
</html>"""


def _recent_changes_html(state: LocationState) -> str:
    if not state.recent_changes:
        return "<li>No recent changes in the requested window.</li>"
    return "".join(
        "<li>"
        f"{escape(change.description)}"
        f"<br><small>{escape(change.occurred_at.isoformat())}</small>"
        "</li>"
        for change in state.recent_changes
    )


def _recommendations_html(state: LocationState) -> str:
    if not state.recommended_actions:
        return "<li>No action recommended.</li>"
    return "".join(f"<li>{escape(item.action)}</li>" for item in state.recommended_actions)


def _provenance_html(state: LocationState) -> str:
    if not state.provenance:
        return "<li>No active provenance records in this window.</li>"
    return "".join(
        "<li>"
        f"{escape(item.source)}"
        "<br><small>"
        f"signal {escape(str(item.signal_id))}, "
        f"contribution {item.contribution:.2f}"
        "</small>"
        "</li>"
        for item in state.provenance
    )


def _why_it_matters(state: LocationState) -> str:
    if state.operational_state.value in {"normal", "elevated"}:
        return (
            "The location is operating within a low-risk band. Continue monitoring for escalation."
        )
    if state.operational_state.value == "watch":
        return (
            "A watch state means the location is still operational, but the "
            "probability of delay or degraded service is high enough to change planning behavior."
        )
    if state.operational_state.value == "disrupted":
        return (
            "A disrupted state means operations should adapt now rather than wait for escalation."
        )
    return "A critical state means the location needs immediate attention and escalation."
