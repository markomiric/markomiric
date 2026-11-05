// Run: node --test .claude/hooks/Validators/validators.test.mjs
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { test } from "node:test";

const newFile = join(import.meta.dirname, "validate-new-file.mjs");
const contains = join(import.meta.dirname, "validate-file-contains.mjs");
const SECTIONS = ["## Task Description", "## Objective"];

function setup(entries) {
  const root = mkdtempSync(join(tmpdir(), "validators-"));
  const transcript = join(root, "session.jsonl");
  writeFileSync(transcript, entries.map((e) => JSON.stringify(e)).join("\n"));
  return { root, plans: join(root, "tasks"), transcript };
}

function run(script, plans, payload) {
  const args = [script, "--directory", plans, "--extension", ".md", "--max-age", "5"];
  if (script === contains) for (const s of SECTIONS) args.push("--contains", s);
  return spawnSync(process.execPath, args, { input: JSON.stringify(payload), encoding: "utf8" });
}

const user = (content) => ({ type: "user", message: { role: "user", content } });
const typed = user("<command-message>team-plan</command-message>\n<command-name>/team-plan</command-name>");
const meta = { ...user([{ type: "text", text: "# Team Plan" }]), isMeta: true };
const toolResult = user([{ type: "tool_result", tool_use_id: "t", content: "ok" }]);
const toolUse = (name, input) => ({
  type: "assistant",
  message: { role: "assistant", content: [{ type: "tool_use", id: "t", name, input }] },
});
const skill = toolUse("Skill", { skill: "team-plan", args: "x" });
const write = (file_path) => toolUse("Write", { file_path, content: "" });

function setupWithPlan(entriesFor, body) {
  const ctx = setup([]);
  mkdirSync(ctx.plans);
  const file = join(ctx.plans, "p.md");
  writeFileSync(file, body);
  writeFileSync(
    ctx.transcript,
    entriesFor(file)
      .map((e) => JSON.stringify(e))
      .join("\n")
  );
  return ctx;
}

test("typed /team-plan turn with an incomplete plan blocks and names the missing sections", () => {
  const { plans, transcript } = setupWithPlan((f) => [typed, meta, write(f), toolResult], "## Task Description\n");
  const result = run(contains, plans, { transcript_path: transcript, stop_hook_active: false });
  assert.equal(result.status, 2);
  assert.match(result.stderr, /- ## Objective/);
  assert.doesNotMatch(result.stderr, /- ## Task Description/);
});

test("Skill-invoked /team-plan turn with a complete plan passes silently", () => {
  const { plans, transcript } = setupWithPlan(
    (f) => [user("plan it"), skill, toolResult, meta, write(f), toolResult],
    SECTIONS.join("\n")
  );
  for (const script of [newFile, contains]) {
    const result = run(script, plans, { transcript_path: transcript });
    assert.equal(result.status, 0);
    assert.equal(result.stdout, "");
    assert.equal(result.stderr, "");
  }
});

test("task files written before a Skill-invoked /team-plan in the same turn are not judged", () => {
  let planFile;
  const { plans, transcript } = setupWithPlan((audit) => {
    planFile = join(dirname(audit), "new-plan.md");
    return [user("audit, then plan"), write(audit), toolResult, skill, toolResult, meta, write(planFile), toolResult];
  }, "# Audit\n");
  writeFileSync(planFile, SECTIONS.join("\n"));
  for (const script of [newFile, contains]) assert.equal(run(script, plans, { transcript_path: transcript }).status, 0);
});

test("a turn without /team-plan stays silent even when it writes an incomplete plan", () => {
  const { plans, transcript } = setupWithPlan((f) => [user("update the audit"), write(f), toolResult], "# Audit\n");
  for (const script of [newFile, contains]) {
    const result = run(script, plans, { transcript_path: transcript });
    assert.equal(result.status, 0);
    assert.equal(result.stderr, "");
  }
});

test("/team-plan in an earlier turn does not scope the current turn", () => {
  const { plans, transcript } = setupWithPlan(
    (f) => [typed, meta, write(f), toolResult, user("now fix the audit"), write(f), toolResult],
    "# Audit\n"
  );
  for (const script of [newFile, contains]) assert.equal(run(script, plans, { transcript_path: transcript }).status, 0);
});

test("a stop_hook_active retry never blocks", () => {
  const { plans, transcript } = setupWithPlan((f) => [typed, write(f), toolResult], "# nothing\n");
  for (const script of [newFile, contains]) {
    assert.equal(run(script, plans, { transcript_path: transcript, stop_hook_active: true }).status, 0);
  }
});

test("a /team-plan turn that wrote no plan file blocks the new-file validator", () => {
  const { plans, transcript } = setup([typed, meta, write(join(tmpdir(), "elsewhere.md")), toolResult]);
  const result = run(newFile, plans, { transcript_path: transcript });
  assert.equal(result.status, 2);
  assert.match(result.stderr, /No new file found/);
  assert.equal(run(contains, plans, { transcript_path: transcript }).status, 0);
});

test("a missing or unparseable transcript is a silent no-op", () => {
  const { root, plans } = setup([]);
  const broken = join(root, "broken.jsonl");
  writeFileSync(broken, "{not json");
  for (const script of [newFile, contains]) {
    for (const payload of [{}, { transcript_path: join(root, "missing.jsonl") }, { transcript_path: broken }]) {
      const result = run(script, plans, payload);
      assert.equal(result.status, 0);
      assert.equal(result.stderr, "");
    }
  }
});

test("a section named only in prose does not satisfy a required heading", () => {
  const body = "## Task Description\nThis plan still lacks `## Objective`.\n";
  const { plans, transcript } = setupWithPlan((f) => [typed, meta, write(f), toolResult], body);
  const result = run(contains, plans, { transcript_path: transcript, stop_hook_active: false });
  assert.equal(result.status, 2);
  assert.match(result.stderr, /- ## Objective/);
});

test("a compaction summary or prose quoting the /team-plan marker is not a /team-plan turn", () => {
  const marker = "<command-name>/team-plan</command-name>";
  const summary = { ...user(`Notes: a typed command contains \`${marker}\`.`), isCompactSummary: true };
  const quoted = user(`See \`${marker}\` in the notes.`);
  for (const entries of [
    [user("do the other fixes"), summary, toolResult],
    [quoted, toolResult],
  ]) {
    const { plans, transcript } = setup(entries);
    const result = run(newFile, plans, { transcript_path: transcript, stop_hook_active: false });
    assert.equal(result.status, 0, result.stderr);
  }
});

test("a typed command whose markup opens with command-name is detected", () => {
  const realTyped = user("<command-name>/team-plan</command-name>\n<command-message>team-plan</command-message>");
  const { plans, transcript } = setup([realTyped, meta, toolResult]);
  assert.equal(run(newFile, plans, { transcript_path: transcript, stop_hook_active: false }).status, 2);
});
