import { spawnSync } from "node:child_process";
import { appendFileSync, existsSync, mkdirSync, readFileSync, realpathSync, rmSync } from "node:fs";
import { isAbsolute, join, relative, resolve, sep } from "node:path";

const stateDir = join(import.meta.dirname, "state");
const config = join(import.meta.dirname, "checks.json");
const localState = /^\.claude\/(?:backups|reviews|tasks|worktrees|hooks\/[^/]+\/(?:state|logs))\//;

export function repoPath(root, file) {
  if (typeof file !== "string" || !file) return null;
  const resolved = resolve(root, file);
  if (!existsSync(resolved)) return null;
  const path = relative(realpathSync(root), realpathSync(resolved)).split(sep).join("/");
  if (!path || isAbsolute(path) || path === ".." || path.startsWith("../")) return null;
  if (path.split("/").some((part) => [".git", "node_modules", "settings.local.json"].includes(part) || /^\.env(?:\.|$)/.test(part))) return null;
  return localState.test(path) ? null : path;
}

function run(root, executable, args) {
  return spawnSync(executable, args, { cwd: root, encoding: "utf8", timeout: 15_000, windowsHide: true });
}

export function checkFiles(root, files, profile) {
  const failures = [];
  const paths = [...new Set(files.map((file) => repoPath(root, file)).filter(Boolean))];
  if (paths.length === 0) return failures;
  function requireSuccess(result, label) {
    if (result.status !== 0) {
      const detail = (result.stderr || result.stdout || result.error?.message || "check did not complete").trim();
      failures.push(label + "\n" + detail.split("\n").slice(-15).join("\n"));
    }
  }

  requireSuccess(
    run(root, "git", ["--no-optional-locks", "--literal-pathspecs", "diff", "--no-ext-diff", "--no-textconv", "--check", "--", ...paths]),
    "Git patch whitespace",
  );
  const python = [];
  const go = [];
  for (const file of paths) {
    if (/\.(?:mjs|cjs)$/.test(file)) requireSuccess(run(root, process.execPath, ["--check", "--", file]), file);
    if (/(?:^|\/)(?:package|global)\.json$/.test(file) || /^\.claude\/(?:settings|skills\/skill-rules|hooks\/QualityGateHook\/checks)\.json$/.test(file)) {
      try {
        JSON.parse(readFileSync(join(root, file), "utf8"));
      } catch {
        failures.push(file + "\nInvalid JSON");
      }
    }
    if (profile.python && file.endsWith(".py")) python.push(file);
    if (profile.go && file.endsWith(".go")) go.push(file);
  }
  if (python.length) {
    const args = ["-c", "import ast,sys,tokenize\nfor name in sys.argv[1:]:\n with tokenize.open(name) as f: ast.parse(f.read(), filename=name)", ...python];
    const result = run(root, "python3", args);
    requireSuccess(result.error?.code === "ENOENT" ? run(root, "python", args) : result, "Python syntax");
  }
  if (go.length) {
    const result = run(root, "gofmt", ["-l", "--", ...go]);
    requireSuccess(result, "gofmt");
    if (result.status === 0 && result.stdout.trim()) failures.push("Go formatting\n" + result.stdout.trim());
  }
  return failures;
}

function main() {
  const payload = JSON.parse(readFileSync(0, "utf8") || "{}");
  if (!/^[\w-]+$/.test(payload.session_id ?? "")) return 0;
  const root = realpathSync(process.env.CLAUDE_PROJECT_DIR || process.cwd());
  const state = join(stateDir, payload.session_id + ".jsonl");
  if (process.argv[2] === "record") {
    const file = repoPath(root, payload.tool_input?.file_path);
    if (file) {
      mkdirSync(stateDir, { recursive: true, mode: 0o700 });
      appendFileSync(state, JSON.stringify(file) + "\n", { mode: 0o600 });
    }
  } else if (process.argv[2] === "check") {
    if (payload.stop_hook_active) {
      rmSync(state, { force: true });
      return 0;
    }
    const edits = existsSync(state) ? readFileSync(state, "utf8").trimEnd().split("\n").filter(Boolean).map(JSON.parse) : [];
    rmSync(state, { force: true });
    if (edits.length === 0) return 0;
    const failures = checkFiles(root, edits, JSON.parse(readFileSync(config, "utf8")));
    if (failures.length) {
      console.error("Quality gate found issues in this turn's files. Fix in-scope failures and report any remaining checks.\n\n" + failures.join("\n\n"));
      return 2;
    }
  }
  return 0;
}

if (process.argv[1] && existsSync(process.argv[1]) && realpathSync(process.argv[1]) === import.meta.filename) {
  try {
    process.exitCode = main();
  } catch (error) {
    console.error("Quality gate could not complete: " + error.message);
    if (process.argv[2] === "check") process.exitCode = 2;
  }
}
