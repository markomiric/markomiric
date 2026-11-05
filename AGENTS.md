# Profile repository agent guide

This repository owns the public GitHub profile and the scheduled usage-statistics updater. Preserve the updater's generated region and confirm the owning workflow before editing it.

Keep the task scoped to the user request. Preserve unrelated changes and use local or synthetic data in checks. Follow the machine's shared agent contract when it is installed.

## Verification

Run `git diff --check` and inspect the rendered Markdown for profile changes. For changes to the updater, check the Python source and its workflow using local or synthetic input.

## Review workflow verification

For changes to the portable Codex review runner, run `node --test .claude/skills/codex-review/scripts/codex-review.test.mjs`. The fixture needs Git and Node.js and runs locally.

## Project agent checks

Use the repository's `project-checks` skill when selecting verification or handing off a reviewed change. For changes to agent hooks, skills, or commands, run `node --test ".claude/hooks/*/*.test.mjs" ".claude/skills/codex-review/scripts/*.test.mjs"` from the repository root. The local Stop hook checks edited paths. Use the project checks for full behavior verification.
