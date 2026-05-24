# AGENTS.md

Any AI agent working in this repo should read this before touching code.

---

## Project Identity

**open-supply-chain** — Open supply-chain intelligence infrastructure for mapping how goods, risks, organizations, facilities, ports, and routes interact.

---

## Agent Roles (Cognitive Gearing)

Switch roles explicitly. Never plan and code in the same turn.

- **Planner** — Read docs/, confirm a story exists before any code. Use `/plan`.
- **Architect** — Read `docs/architecture.md`, run GitNexus impact before schema changes.
- **Developer** — Smallest possible diff. No speculative abstraction.
- **Reviewer** — Run quality gates. Confirm coverage ≥ 90%. Use `/review`.
- **Shipper** — Open PR to `dev` branch. Never push to `main` directly. Use `/ship`.

---

## Memory Architecture

| Source | Purpose | Scope |
|---|---|---|
| `CLAUDE.md` | Project rules, commands, quality gates | Persistent, checked in |
| `AGENTS.md` | Agent operating manual (this file) | Persistent, checked in |
| `docs/architecture.md` | System design decisions | Persistent, checked in |
| `_bmad-output/` | PRD, stories, sprint state | Gitignored, session-scoped |
| `docs/obsidian/` | Product thinking, PARA vault | Persistent, checked in |

---

## What Agents Love (Discovery Master Principles)

See: https://github.com/forest-builds/archetype/blob/main/docs/discovery-master.md

1. **Relevant context, not full context** — Use GitNexus to load only what you need.
2. **Stable cache structure** — CLAUDE.md + AGENTS.md stay at top; dynamic content grows below.
3. **Clear role separation** — One cognitive mode per turn. Never plan and code together.
4. **Memory over re-derivation** — Read this file first. Don't re-explore documented things.
5. **Measurable stories** — Every task needs acceptance criteria before implementation starts.

---

## BMAD Workflow

Install once: `npx bmad-method@latest install` (interactive — run in terminal, needs TTY).

| Command | Purpose |
|---------|---------|
| `/bmad-help` | Contextual guidance for current project state |
| `/bmad-prd` | Create or update the Product Requirements Document |
| `/bmad-sprint-planning` | Plan sprint with stories |
| `/bmad-create-story` | Define a story with acceptance criteria |
| `/bmad-dev-story` | Implement a story (developer role) |
| `/bmad-code-review` | Review against acceptance criteria |

Output artifacts go to `_bmad-output/` (gitignored).

---

## Custom Skills

| Skill | When to Use |
|-------|-------------|
| `/discover` | Map a project's needs to tool/stack recommendations |
| `/plan` | Before any code — load context, check impact, confirm story |
| `/review` | After implementation — run quality gates, write PR summary |
| `/ship` | After /review — create PR to dev branch |

---

## Quality Gates

Every PR must pass all quality checks before merging.
Add your project's specific commands here (e.g. `make check`, `npm test`).

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **open-supply-chain** (180 symbols, 241 relationships, 6 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/open-supply-chain/context` | Codebase overview, check index freshness |
| `gitnexus://repo/open-supply-chain/clusters` | All functional areas |
| `gitnexus://repo/open-supply-chain/processes` | All execution flows |
| `gitnexus://repo/open-supply-chain/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
