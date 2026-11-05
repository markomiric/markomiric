// Run: node --test .claude/hooks/ReportGateHook/report-gate.test.mjs
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

const gate = join(import.meta.dirname, "report-gate.mjs");

const user = (content, extra = {}) => ({ type: "user", message: { role: "user", content }, ...extra });
const assignment = (text) => user(`<teammate-message teammate_id="team-lead">\n${text}\n</teammate-message>`);
const work = {
  type: "assistant",
  message: { role: "assistant", content: [{ type: "tool_use", id: "w", name: "Edit", input: {} }] },
};
const toolResult = user([{ type: "tool_result", tool_use_id: "t", content: "ok" }]);
const sendMessage = {
  type: "assistant",
  message: {
    role: "assistant",
    content: [{ type: "tool_use", id: "t", name: "SendMessage", input: { to: "team-lead" } }],
  },
};
const hookFeedback = user(
  "TeammateIdle hook feedback:\n[node report-gate.mjs]: Deliver your completion report to the lead via SendMessage",
  { isMeta: true }
);
// What the lead's session transcript holds when a teammate reports: the report is a user-role entry.
const incomingReport = user(
  'Another Claude session sent a message:\n<teammate-message teammate_id="builder">done</teammate-message>'
);

/** Lays out <root>/<session>.jsonl (lead) and <root>/<session>/subagents/agent-<id>.jsonl (teammate). */
function setup({ lead, teammate }) {
  const root = mkdtempSync(join(tmpdir(), "report-gate-"));
  const session = "s1";
  const leadPath = join(root, `${session}.jsonl`);
  writeFileSync(leadPath, lead.map((e) => JSON.stringify(e)).join("\n"));
  if (teammate) {
    mkdirSync(join(root, session, "subagents"), { recursive: true });
    writeFileSync(
      join(root, session, "subagents", "agent-a1.jsonl"),
      teammate.map((e) => JSON.stringify(e)).join("\n")
    );
  }
  const payload = { session_id: session, agent_id: "a1", transcript_path: leadPath };
  return { payload, state: join(root, "state.json") };
}

function run({ payload, state }) {
  return spawnSync(process.execPath, [gate], {
    input: JSON.stringify(payload),
    encoding: "utf8",
    env: {
      ...process.env,
      CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS: "1",
      REPORT_GATE_FLUSH_DELAY_MS: "0",
      REPORT_GATE_STATE_PATH: state,
    },
  });
}

test("a delivered report passes even though the lead transcript shows it as a new user entry", () => {
  const ctx = setup({ lead: [incomingReport], teammate: [assignment("Task 2"), sendMessage, toolResult] });
  assert.equal(run(ctx).status, 0);
});

test("own isMeta feedback is not an assignment, so a report before it still counts", () => {
  const ctx = setup({ lead: [], teammate: [assignment("Task 2"), sendMessage, toolResult, hookFeedback] });
  assert.equal(run(ctx).status, 0);
});

test("a missing report gets at most two pushbacks per assignment, then re-arms on a new one", () => {
  const ctx = setup({ lead: [], teammate: [assignment("Task 3"), work, toolResult] });
  assert.equal(run(ctx).status, 2);
  assert.equal(run(ctx).status, 2);
  assert.equal(run(ctx).status, 0);
  assert.equal(run(ctx).status, 0);

  const next = setup({
    lead: [],
    teammate: [assignment("Task 3"), sendMessage, assignment("Task 4"), work, toolResult],
  });
  assert.equal(run({ ...next, state: ctx.state }).status, 2);
});

test("a release or FYI answered without tool calls owes no report", () => {
  const ack = { type: "assistant", message: { role: "assistant", content: [{ type: "text", text: "Acknowledged." }] } };
  const ctx = setup({
    lead: [],
    teammate: [assignment("Task 2"), sendMessage, toolResult, assignment("You are released."), ack],
  });
  assert.equal(run(ctx).status, 0);
});

test("stays silent when the teammate transcript cannot be found", () => {
  const ctx = setup({ lead: [incomingReport] });
  assert.equal(run(ctx).status, 0);
});
