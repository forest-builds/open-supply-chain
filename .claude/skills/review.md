# /review — Pre-PR Review Skill

Use this skill after finishing implementation, before opening a PR.
Switches into Reviewer role.

## Process

1. **Run quality gates** — All checks must pass before continuing.
   If anything fails, return to Developer role and fix first.

2. **Check coverage** — Must not drop below the project threshold.
   Include numbers in the PR body.

3. **Blast radius check** — Run `mcp__gitnexus__detect_changes`.
   Flag anything unexpected.

4. **Write diff summary** — One paragraph: what problem is solved, what files
   changed and why, how to verify. This becomes the PR body.

## PR Checklist

- [ ] Branch is up to date with `dev`
- [ ] All quality gates pass
- [ ] Coverage did not drop
- [ ] No commented-out code
- [ ] No TODO stubs in production paths
- [ ] PR title: `type(scope): description`

## PR Title Types

`feat` · `fix` · `refactor` · `test` · `docs` · `chore`
