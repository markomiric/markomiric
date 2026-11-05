#!/usr/bin/env node

/**
 * Stop hook registered by /team-plan: blocks when a turn that ran /team-plan
 * wrote no plan file in the specified directory.
 *
 * Command-frontmatter hooks persist for the whole session, so the check is
 * scoped by the transcript: only a turn that ran /team-plan is judged, and only
 * by the files that turn wrote (see team-plan-turn.mjs).
 *
 * Exit codes:
 * - 0: not a /team-plan turn, a stop_hook_active retry, a plan was written, or any error
 * - 2: /team-plan turn wrote no plan file (reason on stderr)
 *
 * Usage:
 *   node validate-new-file.mjs --directory specs --extension .md
 *   (--max-age is accepted for compatibility and ignored)
 */

import { parseArgs } from "node:util";
import { readHookInput, teamPlanFilesThisTurn } from "./team-plan-turn.mjs";

const DEFAULT_DIRECTORY = ".claude/tasks";
const DEFAULT_EXTENSION = ".md";

const NO_FILE_ERROR = (pattern, directory) =>
  `VALIDATION FAILED: No new file found matching ${pattern}.\n\n` +
  `ACTION REQUIRED: Use the Write tool to create a new file in the ${directory}/ directory. ` +
  `The file must match the expected pattern (${pattern}). ` +
  `Do not stop until the file has been created.`;

try {
  const input = readHookInput();
  if (input.stop_hook_active) process.exit(0);

  const { values } = parseArgs({
    options: {
      directory: { type: "string", short: "d", default: DEFAULT_DIRECTORY },
      extension: { type: "string", short: "e", default: DEFAULT_EXTENSION },
      "max-age": { type: "string" },
    },
    strict: false,
  });

  const directory = values.directory || DEFAULT_DIRECTORY;
  const extension = values.extension || DEFAULT_EXTENSION;
  const files = teamPlanFilesThisTurn(input.transcript_path, directory, extension);

  if (files && files.length === 0) {
    console.error(NO_FILE_ERROR(`${directory}/*${extension}`, directory));
    process.exit(2);
  }
  process.exit(0);
} catch {
  process.exit(0);
}
