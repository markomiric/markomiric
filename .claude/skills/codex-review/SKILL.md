---
name: codex-review
description: Use Codex as an independent read-only reviewer after the project's checks, on an authorized saved plan, or when the user asks for Codex review or a second opinion.
---

# Codex review

Read `AGENTS.md` and the project review rules. Run once for a substantive code change after the relevant local checks pass, or for a saved plan that needs review before approval. Use the Codex account and source scope authorized for this project. If authorization or Codex is unavailable, report the review as skipped with the reason.

Run from the root of the intended Git worktree. Use Git, Node.js 22.13 or newer, and a signed-in Codex CLI on PATH. Runner v1 was tested with Codex CLI 0.166.0. Set `CODEX_BIN` to the native executable if Claude cannot find it. On Windows, the runner also checks the desktop CLI cache when available.

| Target | Command |
| --- | --- |
| One commit | `node .claude/skills/codex-review/scripts/codex-review.mjs diff --commit <sha>` |
| Branch changes | `node .claude/skills/codex-review/scripts/codex-review.mjs diff --base <ref>` |
| Isolated uncommitted change | `node .claude/skills/codex-review/scripts/codex-review.mjs diff --uncommitted` |
| Saved plan | `node .claude/skills/codex-review/scripts/codex-review.mjs plan <repo-relative-plan.md>` |
| Focused review | `node .claude/skills/codex-review/scripts/codex-review.mjs ask "<scope and question>"` |

For a branch review, use a clean worktree at the branch tip. Use `--uncommitted` only when every staged, unstaged, and untracked change is in scope. On a mixed worktree, pass the precise file list and question to `ask`, within the approved review scope. Keep sensitive files and operational data out of the review worktree.

Use the configured model. Set `--model <id>` or `--effort <low|medium|high|xhigh|max>` when the review needs an explicit override. Diff and focused reviews default to high effort. Plan reviews use the configured effort.

Start the command in the background if Claude supports it, then wait for the result. A successful run prints `report:` with the path under the ignored `.claude/reviews/` directory. Each run has a separate local report. The runner uses Codex in read-only mode without escalation, disables configured integrations for the review, passes focused prompts on stdin, and discards raw CLI output. If it prints `skipped:` or `FAILED:`, report that outcome.

Read the report and check each material finding against the source and the user's scope. Return findings by severity with file and line evidence. Mark them verified, disputed, or unverified. Apply fixes only within the user's authorization.
