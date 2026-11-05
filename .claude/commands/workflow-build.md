---
description: Run an explicitly requested workflow for an approved plan
argument-hint: "<approved plan>"
---

# workflow-build

Start only when the user invokes this command for the approved plan in `$ARGUMENTS`. Read `AGENTS.md` and `project-checks` first.

State the phases, roles, maximum concurrency, and expected work. Use the native Workflow capability only when it is available and its cost and scope are authorized. Give each phase bounded inputs and checks. If Workflow is unavailable, report that and use the already authorized build route.

The lead reviews the final diff, runs the applicable checks, and follows the scoped Codex handoff in `.claude/commands/build.md`.
