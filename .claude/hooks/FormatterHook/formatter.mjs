#!/usr/bin/env node

/**
 * Framework Formatter Hook (PostToolUse)
 *
 * Runs after Write or Edit tool completes and formats the edited file with the
 * formatter the project actually uses:
 *
 * 1. Biome, when the project has biome.json/biome.jsonc and @biomejs/biome
 *    installed: `biome check --write` formats, applies safe lint fixes, and
 *    organizes imports, honoring the project's Biome config and ignores.
 *    Anything Biome cannot fix is reported back to Claude (exit 2) so it gets
 *    fixed in the same turn instead of surfacing later in CI.
 * 2. Prettier, when installed locally (silent, as before).
 * 3. Nothing otherwise.
 */

import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, extname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { repoPath } from "../QualityGateHook/quality-gate.mjs";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

/**
 * Project root for tool resolution. Claude Code sets CLAUDE_PROJECT_DIR to the
 * project root for every hook regardless of the process CWD; we prefer it so we
 * find the project's local node_modules even when the session's shell has moved
 * into a subdirectory (sub-agent worktree, monorepo subdir). Falls back to CWD.
 */
function projectRoot() {
  return process.env.CLAUDE_PROJECT_DIR || process.cwd();
}

// File extensions that Prettier can format
const PRETTIER_EXTENSIONS = [
  ".js",
  ".jsx",
  ".ts",
  ".tsx",
  ".json",
  ".md",
  ".mdx",
  ".css",
  ".scss",
  ".less",
  ".html",
  ".vue",
  ".svelte",
  ".yaml",
  ".yml",
];

const BIOME_CONFIGS = ["biome.json", "biome.jsonc"];
const TOOL_TIMEOUT_MS = 30000;
const FEEDBACK_LINES = 60;

function log(message) {
  const logDir = join(__dirname, "logs");
  mkdirSync(logDir, { recursive: true });

  const logFile = join(logDir, "formatter.log");
  const timestamp = new Date().toISOString();
  const logLine = `[${timestamp}] ${message}\n`;

  try {
    const existing = existsSync(logFile) ? readFileSync(logFile, "utf-8") : "";
    // Keep log file from growing too large (last 1000 lines)
    const lines = existing.split("\n").slice(-1000);
    writeFileSync(logFile, lines.join("\n") + logLine);
  } catch {
    // Fail silently
  }
}

/**
 * Resolve a CLI tool's executable entry point from the project's local
 * node_modules, reading the package's own declared "bin" field so we stay
 * version-agnostic. Returns an absolute path to a JS file runnable with Node,
 * or null when the tool is not installed locally.
 *
 * Why this shape: we invoke tools via `node <bin> <args>` with shell:false. No
 * shell ever parses the command, so the file path stays a literal argument and
 * a crafted filename cannot inject commands. Running the resolved JS through
 * node (a real executable) also sidesteps the Windows ".cmd shim cannot be
 * spawned without a shell" problem that breaks a naive spawn('npx', ...) port.
 */
function resolveLocalBin(packageName, binName) {
  try {
    const requireFromProject = createRequire(join(projectRoot(), "package.json"));
    const pkgJsonPath = requireFromProject.resolve(`${packageName}/package.json`);
    const pkg = JSON.parse(readFileSync(pkgJsonPath, "utf-8"));
    const bin = pkg.bin;
    const relativeEntry = typeof bin === "string" ? bin : bin && bin[binName];
    if (!relativeEntry) return null;
    return join(dirname(pkgJsonPath), relativeEntry);
  } catch {
    return null;
  }
}

function runTool(bin, args) {
  const result = spawnSync(process.execPath, [bin, ...args], {
    encoding: "utf-8",
    timeout: TOOL_TIMEOUT_MS,
    cwd: projectRoot(),
    shell: false,
  });
  const output = `${result.stdout ?? ""}${result.stderr ?? ""}`.trim();
  return { ok: result.status === 0, output: output || result.error?.message || "" };
}

/** Biome is the project's formatter when it is both configured and installed. */
function resolveBiome() {
  if (!BIOME_CONFIGS.some((name) => existsSync(join(projectRoot(), name)))) return null;
  return resolveLocalBin("@biomejs/biome", "biome");
}

function runBiome(bin, filePath) {
  // Repo-relative path keeps Biome's include/ignore globs and its messages readable.
  const target = relative(projectRoot(), filePath).split("\\").join("/");
  // DECISION: --files-ignore-unknown and --no-errors-on-unmatched let Biome
  // decide which files it handles (and which the config ignores) instead of
  // this hook duplicating Biome's extension list and ignore rules.
  return {
    target,
    ...runTool(bin, ["check", "--write", "--files-ignore-unknown=true", "--no-errors-on-unmatched", `./${target}`]),
  };
}

function tail(text) {
  return text.split("\n").slice(-FEEDBACK_LINES).join("\n");
}

function main() {
  let data;
  try {
    data = JSON.parse(readFileSync(0, "utf-8"));
  } catch (err) {
    log(`Error: unreadable hook input: ${err.message}`);
    return 0;
  }

  const toolName = data.tool_name || "";
  const file = repoPath(projectRoot(), data.tool_input?.file_path);
  if (!file) return 0;
  const filePath = join(projectRoot(), file);

  // Only process Write and Edit tools on files that still exist
  if ((toolName !== "Write" && toolName !== "Edit") || !filePath) return 0;
  if (!existsSync(filePath)) {
    log(`File not found: ${filePath}`);
    return 0;
  }

  const biome = resolveBiome();
  if (biome) {
    const result = runBiome(biome, filePath);
    // "Checked 0 files" means the config ignores this path or Biome has no handler for it.
    const skipped = result.ok && /\bChecked 0 files\b/.test(result.output);
    log(`Biome: ${skipped ? "skipped (ignored or unsupported)" : result.ok ? "clean" : "problems"} - ${result.target}`);
    if (result.ok) return 0;
    // Exit 2 is the only PostToolUse exit code whose stderr reaches Claude.
    console.error(
      `Biome fixed what it safely could in ${result.target}; fix the rest before continuing:\n${tail(result.output)}`
    );
    return 2;
  }

  const ext = extname(filePath).toLowerCase();
  if (!PRETTIER_EXTENSIONS.includes(ext)) return 0;
  const prettier = resolveLocalBin("prettier", "prettier");
  if (!prettier) {
    log(`Skipped ${filePath}: no Biome config and no local Prettier`);
    return 0;
  }
  const result = runTool(prettier, ["--write", filePath]);
  log(`Prettier: ${result.ok ? "success" : `failed - ${result.output}`}`);
  // Formatting stays silent to Claude on the Prettier path
  return 0;
}

try {
  process.exit(main());
} catch (err) {
  log(`Error: ${err.message}`);
  // Exit gracefully - don't break the workflow
  process.exit(0);
}
