# /ship — PR Creation Skill

Use this skill after /review passes. Creates the PR to dev.

## Pre-Conditions

- All quality gates pass
- /review checklist complete
- On a `feat/*` or `fix/*` branch (never `main` or `dev`)

## Process

1. Stage and commit any remaining changes:
   ```bash
   git add <specific files>   # never git add -A blindly
   git commit -m "type(scope): description

   Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
   ```

2. Push and create PR:
   ```bash
   git push -u origin <branch>
   gh pr create --base dev --title "type(scope): description" --body "..."
   ```

3. PR body must include: `## Summary` (3 bullets), `## Test plan` (checkboxes),
   coverage numbers, BMAD story link if applicable.
