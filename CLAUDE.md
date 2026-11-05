@AGENTS.md

## Codex second review

For an authorized account and review scope, use `codex-review` once after the relevant project checks pass for a substantive change, before approval of a saved plan, and when the user requests a second opinion. Focus on profile content, generated usage statistics, and scheduled workflow changes. Treat telemetry credentials and running the hosted updater as separate approvals. Report skipped or failed reviews separately from local checks.

## Project workflows

Read `AGENTS.md` before planning, changing, or reviewing code. Load `project-checks` to select the project's validation. Use `/team-plan` to prepare a plan, `/build` for an approved implementation, and `/team-build` when its approved scope includes delegated work. `/workflow-build` requires explicit invocation and an approved scope.

Use `session-management` on resume, `sub-agent-invocation` for approved delegation, and `git-commits` for an authorized commit. Project agents live in `.claude/agents/`. Use their declared scope and keep reviews report-only. The local hooks suggest skills, format supported edits, check changed files, and show task context on resume. Run the complete relevant project checks before a Codex review.
