---
name: project-checks
description: "Select and run local validation for the public profile and telemetry updater when checking a change, approving a plan, or preparing a review."
---

# Project checks

Read `AGENTS.md` and the affected package or feature before selecting checks.

Run `git diff --check` and inspect the rendered profile. Check updater changes with Python syntax and synthetic input. Running the hosted updater requires separate approval.

Report the exact checks and results. Keep source, browser, native, hosted, and provider evidence separate. Use the local or synthetic fixtures allowed by the project.
