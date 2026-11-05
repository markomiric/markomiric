// Shared by the /team-plan Stop validators. Command-frontmatter hooks stay
// registered for the rest of the session, so the validators must judge only a
// turn that actually ran /team-plan, and only the plan files that turn wrote.
// The transcript is the ground truth for both.
import { existsSync, readFileSync, statSync } from "node:fs";
import { resolve, sep } from "node:path";

const MAX_TRANSCRIPT_BYTES = 50 * 1024 * 1024;
const WRITE_TOOLS = new Set(["Write", "Edit", "MultiEdit"]);
const TYPED_MARKER = "<command-name>/team-plan</command-name>";

export function readHookInput() {
  if (process.stdin.isTTY) return {};
  try {
    return JSON.parse(readFileSync(0, "utf-8"));
  } catch {
    return {};
  }
}

const norm = (p) => (process.platform === "win32" ? resolve(p).toLowerCase() : resolve(p));
const blocks = (entry) => {
  const content = (entry.message || entry).content;
  return Array.isArray(content) ? content.filter(Boolean) : [];
};

function parseEntries(transcriptPath) {
  const entries = [];
  for (const line of readFileSync(transcriptPath, "utf-8").split("\n")) {
    try {
      if (line) entries.push(JSON.parse(line));
    } catch {
      // skip a partial or corrupt line
    }
  }
  return entries;
}

// The turn opens at the last real user message: tool results, meta entries
// (expanded command or skill bodies), and a compaction summary written mid-turn
// do not start a new turn.
function isTurnStart(entry) {
  const isUser = entry.type === "user" || entry.message?.role === "user";
  return isUser && !entry.isMeta && !entry.isCompactSummary && !blocks(entry).some((b) => b.type === "tool_result");
}

function openingText(entry) {
  const content = (entry.message || entry).content;
  return typeof content === "string"
    ? content
    : blocks(entry)
        .map((b) => b.text ?? "")
        .join(" ");
}

// Returns null when the current turn did not run /team-plan (or on any error),
// otherwise the resolved paths of plan files written in the turn after
// /team-plan was invoked (earlier writes in the same turn are not its plan).
export function teamPlanFilesThisTurn(transcriptPath, directory, extension) {
  try {
    if (!transcriptPath || !existsSync(transcriptPath)) return null;
    if (statSync(transcriptPath).size > MAX_TRANSCRIPT_BYTES) return null;
    const entries = parseEntries(transcriptPath);
    const start = entries.findLastIndex(isTurnStart);
    if (start === -1) return null;

    const turn = entries.slice(start + 1).flatMap(blocks);
    const uses = turn.filter((b) => b.type === "tool_use");
    // A typed command's entry is the command markup itself; prose quoting the marker is not.
    const opening = openingText(entries[start]).trimStart();
    const typed = opening.startsWith("<command-") && opening.includes(TYPED_MARKER);
    const skillAt = uses.findIndex((b) => b.name === "Skill" && b.input?.skill === "team-plan");
    if (!typed && skillAt === -1) return null;

    const dir = norm(directory) + sep;
    const ext = extension.startsWith(".") ? extension : `.${extension}`;
    const extNorm = process.platform === "win32" ? ext.toLowerCase() : ext;
    const files = uses
      .slice(typed ? 0 : skillAt)
      .filter((b) => WRITE_TOOLS.has(b.name) && typeof b.input?.file_path === "string")
      .map((b) => b.input.file_path)
      .filter((p) => norm(p).startsWith(dir) && norm(p).endsWith(extNorm))
      .map((p) => resolve(p));
    return [...new Set(files)];
  } catch {
    return null;
  }
}
