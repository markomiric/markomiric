---
description: Prepare a project plan and its validation for operator approval
argument-hint: "<request> [Orchestration: <team or sequencing guidance>]"
disallowed-tools: EnterPlanMode
hooks:
  Stop:
    - hooks:
        - type: command
          command: >-
            node "$CLAUDE_PROJECT_DIR/.claude/hooks/Validators/validate-new-file.mjs"
            --directory "$CLAUDE_PROJECT_DIR/.claude/tasks"
            --extension .md
        - type: command
          command: >-
            node "$CLAUDE_PROJECT_DIR/.claude/hooks/Validators/validate-file-contains.mjs"
            --directory "$CLAUDE_PROJECT_DIR/.claude/tasks"
            --extension .md
            --contains "## Task Description"
            --contains "## Objective"
            --contains "## Relevant Files"
            --contains "## Step by Step Tasks"
            --contains "## Acceptance Criteria"
            --contains "## Team Orchestration"
            --contains "### Team Members"
            --contains "## Open Questions & Decisions"
            --contains "## Amendments"
            --contains "builds_on:"
---

# Team plan

Read `AGENTS.md` and `project-checks`. Plan the request in `$ARGUMENTS` using the current source and manifests. Write the plan under `.claude/tasks/`. Keep implementation outside this planning turn.

Use these sections as written:

# Plan: <task name>

## Task Description
## Objective
## Relevant Files
## Step by Step Tasks
## Acceptance Criteria
## Team Orchestration
### Team Members
## Open Questions & Decisions
## Amendments

Under Step by Step Tasks, write each task as `### N. Title` with a `- **Status**: [ ]` bullet, its scope, and a validation step. After approval the build lead updates status to `[wip]`, `[x]` after verification, or `[f]` with the failure.

Record `builds_on: none` or the prior plan that this one extends. Use real check commands and identify the required proof for each changed boundary. Name project roles only for genuinely independent work with bounded ownership. When the plan and account are approved for a Codex handoff, use `codex-review` on the saved plan and verify its findings. Present the plan and wait for implementation approval.
