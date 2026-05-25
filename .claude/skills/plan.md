# /plan — BMAD-Aware Planning Skill

Use this skill before writing any code. Switches into Planner role.
Do not mix planning and coding in the same turn.

## Rules

- No code is written in this turn
- Output is a story definition, not an implementation
- Identify blast radius BEFORE deciding what to change

## Process

1. **Read memory** — Read AGENTS.md and docs/architecture.md first.
2. **Check impact** — Run `mcp__gitnexus__impact` on any symbol you plan to change.
3. **Confirm story** — Ensure a BMAD story exists in `_bmad-output/` before proceeding.
4. **Scope** — List exactly what files will change and why. One bullet per file.
5. **Acceptance criteria** — Write 3-5 measurable exit conditions.
6. **Hand off** — End with: "Ready for Developer role. Story: [story name]"

## When to Use

Before any feature work, refactor touching shared code, schema migration, or
when unsure what's safe to change.

## When NOT to Use

Pure docs edits, lint-only fixes, test-only changes with no behavior change.
