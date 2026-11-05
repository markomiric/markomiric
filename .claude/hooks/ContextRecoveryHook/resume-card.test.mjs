import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdirSync, mkdtempSync, realpathSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { buildCard } from "./resume-card.mjs";

test("the resume card restores open plan tasks from the checkout", (t) => {
  const root = realpathSync(mkdtempSync(join(tmpdir(), "agent-resume-")));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  execFileSync("git", ["init", "-q", "--template="], { cwd: root });
  const tasks = join(root, ".claude", "tasks");
  mkdirSync(tasks, { recursive: true });
  writeFileSync(join(tasks, "change.md"), "# Plan: Change\n\n### 1. Complete\n- **Status**: [x]\n\n### 2. Verify\n- **Status**: [ ]\n");
  const card = buildCard(root);
  assert.match(card, /\.claude\/tasks\/change\.md \(1 remaining\)/);
  assert.match(card, /2\. Verify/);
  assert.doesNotMatch(card, /1\. Complete/);
});
