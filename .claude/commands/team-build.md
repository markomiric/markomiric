---
description: Implement an approved plan with scoped project agents
argument-hint: "<approved plan>"
---

# team-build

Read `AGENTS.md`, `project-checks`, and the approved plan named in `$ARGUMENTS`. The lead owns the integration and final checks.

- Give each independent assignment one writer, a bounded file scope, and an acceptance check. Select the named local agent from `.claude/agents/`. Sequence assignments that share a contract or file.
- Follow `sub-agent-invocation`. Use the available native Agent tool only within the approved plan. If agent teams are active, give teammates an explicit delivery step and use their reported output as evidence to inspect.
- Integrate the results and follow the validation, Codex handoff, and reporting steps in `.claude/commands/build.md`.
