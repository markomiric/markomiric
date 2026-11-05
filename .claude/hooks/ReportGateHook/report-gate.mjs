#!/usr/bin/env node
// TeammateIdle gate (teams mode only). In agent-teams mode a teammate's plain
// final message never reaches the lead; only SendMessage does. On idle, this
// hook checks the teammate's transcript for a SendMessage after the last real
// assignment and, if none exists, keeps the teammate working (exit 2) with
// instructions to deliver the report. Inert when agent teams are off.
//
// Loop safety, field-tested 2026-07-29 and 2026-10-09:
// - The hook input's `transcript_path` is the LEAD's session transcript, where
//   each incoming teammate report is a user-role entry. Judging that file made
//   every delivered report look missing and drove repeat confirmations. The
//   gate reads the teammate's own transcript (`agent_transcript_path`, else
//   `<session>/subagents/agent-<agent_id>.jsonl` beside the session file) and
//   stays silent when it cannot find one.
// - Meta entries (this hook's own feedback arrives prefixed and `isMeta`, as do
//   system notices) are not assignments, so a pushback never resets the marker
//   past an already-delivered report.
// - The transcript file can lag the teammate's latest turn, so a short delay
//   precedes the read.
// - Only a turn that made tool calls after the latest lead message owes a
//   report; a release or FYI answered in plain text is left alone.
// - Pushbacks are budgeted per assignment: after MAX_PUSHBACKS the gate stays
//   silent for that assignment, and a new assignment re-arms it.
import { existsSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { basename, dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const MAX_PUSHBACKS = 2;
const MAX_TRANSCRIPT_BYTES = 50 * 1024 * 1024;
const FLUSH_DELAY_MS = Number(process.env.REPORT_GATE_FLUSH_DELAY_MS ?? 750);
const FEEDBACK =
  "Deliver your completion report to the lead via SendMessage before going idle: status first, then what changed, evidence, and anything not done. If a permission denial blocked you, report it as the first line. If you already sent it after your latest assignment, end your turn without sending anything else.";

function resolveTeammateTranscript(data) {
  if (data.agent_transcript_path) return data.agent_transcript_path;
  const sessionPath = data.transcript_path;
  if (!sessionPath) return null;
  if (basename(sessionPath).startsWith("agent-")) return sessionPath;
  if (!data.agent_id || !data.session_id) return null;
  return join(dirname(sessionPath), data.session_id, "subagents", `agent-${data.agent_id}.jsonl`);
}

/**
 * Reads a teammate transcript and returns { reported, assignment }: whether a
 * SendMessage follows the last real assignment, and that assignment's line
 * index. Parsed defensively: on anything unexpected, reported is true so the
 * gate never traps an agent by mistake.
 */
function readReportState(transcriptPath) {
  const silent = { reported: true, assignment: -1 };
  try {
    if (!transcriptPath || !existsSync(transcriptPath)) return silent;
    if (statSync(transcriptPath).size > MAX_TRANSCRIPT_BYTES) return silent;
    const lines = readFileSync(transcriptPath, "utf-8").split("\n").filter(Boolean);
    let lastAssignment = -1;
    let lastSendMessage = -1;
    let lastToolUse = -1;
    for (let i = 0; i < lines.length; i++) {
      let entry;
      try {
        entry = JSON.parse(lines[i]);
      } catch {
        continue;
      }
      const msg = entry.message || entry;
      const content = Array.isArray(msg.content) ? msg.content : [];
      if (entry.type === "user" || msg.role === "user") {
        const isToolResult = content.some((b) => b && b.type === "tool_result");
        if (!isToolResult && !entry.isMeta && !entry.isCompactSummary) lastAssignment = i;
      } else if (entry.type === "assistant" || msg.role === "assistant") {
        const toolUses = content.filter((b) => b && b.type === "tool_use");
        if (toolUses.length > 0) lastToolUse = i;
        if (toolUses.some((b) => b.name === "SendMessage")) lastSendMessage = i;
      }
    }
    // A turn with no tool calls since the latest message (a release, an FYI)
    // did no work, so there is nothing to report.
    const workedSinceAssignment = lastToolUse > lastAssignment;
    return { reported: lastSendMessage > lastAssignment || !workedSinceAssignment, assignment: lastAssignment };
  } catch {
    return silent;
  }
}

async function main() {
  if (process.env.CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS !== "1") process.exit(0);

  let data = {};
  try {
    data = JSON.parse(readFileSync(0, "utf-8"));
  } catch {
    process.exit(0);
  }
  const agentKey = data.agent_id || data.agent_type || "unknown";

  const statePath =
    process.env.REPORT_GATE_STATE_PATH || join(dirname(fileURLToPath(import.meta.url)), "pushback-state.json");
  let state = {};
  if (existsSync(statePath)) {
    try {
      state = JSON.parse(readFileSync(statePath, "utf-8"));
    } catch {
      state = {};
    }
  }
  const key = `${data.session_id || "s"}:${agentKey}`;

  // Let the transcript writer catch up before reading (observed lag between
  // the teammate's SendMessage turn and its appearance in the file).
  await new Promise((r) => setTimeout(r, FLUSH_DELAY_MS));

  const { reported, assignment } = readReportState(resolveTeammateTranscript(data));
  if (reported) {
    if (state[key] !== undefined) {
      delete state[key];
      writeFileSync(statePath, JSON.stringify(state));
    }
    process.exit(0);
  }

  const entry = state[key]?.assignment === assignment ? state[key] : { assignment, pushbacks: 0 };
  if (entry.pushbacks >= MAX_PUSHBACKS) {
    if (!entry.exhausted) {
      state[key] = { ...entry, exhausted: true };
      writeFileSync(statePath, JSON.stringify(state));
      console.log(`ReportGateHook: ${agentKey} idled without a delivered report after ${MAX_PUSHBACKS} pushbacks`);
    }
    process.exit(0);
  }
  state[key] = { assignment, pushbacks: entry.pushbacks + 1 };
  writeFileSync(statePath, JSON.stringify(state));
  console.error(FEEDBACK);
  process.exit(2);
}

main();
