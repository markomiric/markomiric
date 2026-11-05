---
description: Implement an approved project plan and run its verification
argument-hint: "<approved plan>"
---

# build

Read `AGENTS.md`, `project-checks`, and the approved plan named in `$ARGUMENTS`. Confirm the approved scope and applicable checks.

1. Load `session-management` for the approved plan. Record Git status and keep existing changes separate. Work only in the approved files and boundaries.
2. Implement the plan directly or use the named project roles when delegation is authorized. Preserve the project contracts and run the focused checks in the plan.
3. After the checks pass, follow `codex-review` once for the authorized target and account. Inspect each finding before applying an in-scope fix.
4. Report the diff scope, exact checks, and any skipped review or unverified behavior.
