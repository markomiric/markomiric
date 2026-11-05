#!/usr/bin/env node

/**
 * Stop hook registered by /team-plan: blocks when a plan file written in a
 * turn that ran /team-plan is missing required content strings.
 *
 * Command-frontmatter hooks persist for the whole session, so the check is
 * scoped by the transcript: only a turn that ran /team-plan is judged, and
 * every plan file that turn wrote is checked (see team-plan-turn.mjs). A
 * turn that wrote no plan is left to validate-new-file.mjs.
 *
 * Exit codes:
 * - 0: not a /team-plan turn, a stop_hook_active retry, all sections present, or any error
 * - 2: a written plan misses required sections (reason on stderr)
 *
 * Usage:
 *   node validate-file-contains.mjs -d specs -e .md --contains "## Task Description" --contains "## Objective"
 *   (--max-age is accepted for compatibility and ignored)
 */

import { readFileSync } from "node:fs";
import { readHookInput, teamPlanFilesThisTurn } from "./team-plan-turn.mjs";

const DEFAULT_DIRECTORY = ".claude/tasks";
const DEFAULT_EXTENSION = ".md";

const MISSING_CONTENT_ERROR = (file, count, missingList) =>
  `VALIDATION FAILED: File '${file}' is missing ${count} required section(s).\n\n` +
  `MISSING SECTIONS:\n${missingList}\n\n` +
  `ACTION REQUIRED: Use the Edit tool to add the missing sections to '${file}'. ` +
  `Each section must appear exactly as shown above (case-sensitive). ` +
  `Do not stop until all required sections are present in the file.`;

function missingStrings(filepath, requiredStrings) {
  let content;
  try {
    content = readFileSync(filepath, "utf-8");
  } catch {
    return requiredStrings;
  }
  // A required heading must be its own line, so naming a section in prose does not count.
  const lines = new Set(content.split(/\r?\n/).map((line) => line.trimEnd()));
  return requiredStrings.filter((req) => (req.startsWith("#") ? !lines.has(req) : !content.includes(req)));
}

// Parse args manually since parseArgs doesn't support repeated flags well
function parseCustomArgs(argv) {
  const args = { directory: DEFAULT_DIRECTORY, extension: DEFAULT_EXTENSION, contains: [] };

  for (let i = 2; i < argv.length; i++) {
    const arg = argv[i];
    if ((arg === "-d" || arg === "--directory") && i + 1 < argv.length) {
      args.directory = argv[++i];
    } else if ((arg === "-e" || arg === "--extension") && i + 1 < argv.length) {
      args.extension = argv[++i];
    } else if (arg === "--max-age" && i + 1 < argv.length) {
      i++;
    } else if (arg === "--contains" && i + 1 < argv.length) {
      args.contains.push(argv[++i]);
    }
  }

  return args;
}

try {
  const input = readHookInput();
  if (input.stop_hook_active) process.exit(0);

  const args = parseCustomArgs(process.argv);
  const files = teamPlanFilesThisTurn(input.transcript_path, args.directory, args.extension) ?? [];

  const reasons = [];
  for (const file of files) {
    const missing = missingStrings(file, args.contains);
    if (missing.length > 0) {
      const missingList = missing.map((m) => `  - ${m}`).join("\n");
      reasons.push(MISSING_CONTENT_ERROR(file, missing.length, missingList));
    }
  }

  if (reasons.length > 0) {
    console.error(reasons.join("\n\n"));
    process.exit(2);
  }
  process.exit(0);
} catch {
  process.exit(0);
}
