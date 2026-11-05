#!/usr/bin/env node
import { execFileSync, spawnSync } from "node:child_process";
import {
  existsSync,
  lstatSync,
  mkdirSync,
  mkdtempSync,
  readdirSync,
  readFileSync,
  realpathSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { homedir } from "node:os";
import { delimiter, isAbsolute, join, relative, resolve, sep } from "node:path";

const VERSION = "1";
const WITHOUT_INTEGRATIONS = ["apps", "browser_use", "computer_use", "hooks", "in_app_browser", "plugins"].flatMap(
  (feature) => ["--disable", feature]
);

const GROUNDING = [
  "<grounding_rules>Base every claim on files and git output you actually read; cite file:line.",
  "Label inferences as inferences. Invent nothing. AGENTS.md describes this repository's contracts.</grounding_rules>",
  "<constraints>Read-only review. Do not edit files, stage, commit, or run package installs or builds.</constraints>",
].join(" ");

const PLAN_CONTRACT =
  "<output_contract>1) one-line verdict: ship, revise, or hold. 2) Findings ordered by severity " +
  "(blocker, major, minor), each with plan section, file:line evidence, and a concrete fix. " +
  "3) Missing steps or verification gates. 4) The single biggest risk. At most 10 findings; one " +
  "defensible finding beats several weak ones.</output_contract>";

const ASK_CONTRACT =
  "<output_contract>Findings ordered by severity with file:line evidence and a concrete fix, then " +
  "the single biggest risk. Say plainly when you found nothing material.</output_contract>";

const DEFAULT_EFFORT = { diff: "high", ask: "high", plan: null };

/** Builds the invocation without launching Codex. @internal */
export function planRun(argv) {
  const [mode, ...rest] = argv;
  const opts = { model: null, effort: null, base: null, commit: null, title: null };
  let uncommitted = false;
  const positional = [];
  for (let i = 0; i < rest.length; i++) {
    const flag = rest[i];
    if (flag === "--uncommitted") {
      uncommitted = true;
      continue;
    }
    const key = {
      "--model": "model",
      "--effort": "effort",
      "--base": "base",
      "--commit": "commit",
      "--title": "title",
    };
    if (Object.hasOwn(key, flag)) {
      const value = rest[i + 1];
      if (!value || value.startsWith("--")) throw new Error(`${flag} needs a value`);
      opts[key[flag]] = rest[++i];
    } else positional.push(flag);
  }

  // Per-run settings keep the review independent of the client's editing permissions and integrations.
  const common = [
    "--ephemeral",
    "-c",
    'sandbox_mode="read-only"',
    "-c",
    'approval_policy="never"',
    "-c",
    'web_search="disabled"',
    "-c",
    'shell_environment_policy.inherit="core"',
    "-c",
    "notify=[]",
    ...WITHOUT_INTEGRATIONS,
  ];
  // Preserve the kit's Windows sandbox, which does not require administrator provisioning.
  if (process.platform === "win32") common.push("-c", 'windows.sandbox="unelevated"');
  if (opts.model) common.push("-m", opts.model);
  // DECISION: routine diff/ask reviews default to high (duration scales with effort: high took
  // 86 s on a small commit, max about 7 min); plan audits keep the configured effort, where depth paid off.
  const effort = opts.effort ?? DEFAULT_EFFORT[mode];
  if (effort && !["low", "medium", "high", "xhigh", "max"].includes(effort))
    throw new Error("effort must be low, medium, high, xhigh, or max");
  const settings = { model: opts.model ?? "configured default", effort: effort ?? "configured default" };
  if (effort) common.push("-c", `model_reasoning_effort="${effort}"`);

  if (mode === "diff") {
    if ([opts.base, opts.commit, uncommitted].filter(Boolean).length !== 1)
      throw new Error("choose exactly one target: --commit <sha>, --base <ref>, or --uncommitted");
    if (positional.length)
      throw new Error("diff takes no free-text focus; codex review rejects a custom prompt with a target");
    const target = opts.commit ? ["--commit", opts.commit] : opts.base ? ["--base", opts.base] : ["--uncommitted"];
    const title = opts.title ? ["--title", opts.title] : [];
    const [kind, ref] = target;
    const label = ref
      ? `${kind.slice(2)}-${ref.replace(/[^\w.-]+/g, "-").slice(0, opts.commit ? 8 : 60)}`
      : "uncommitted";
    return { mode, label, ref, ...settings, codexArgs: ["exec", "review", ...target, ...title, ...common] };
  }
  if (opts.base || opts.commit || opts.title || uncommitted)
    throw new Error("diff target options apply only to diff reviews");
  const codexArgs = ["exec", "-s", "read-only", ...common, "--color", "never"];
  if (mode === "plan") {
    const [planFile, ...focus] = positional;
    if (!planFile) throw new Error("plan needs a plan file path");
    const prompt =
      `<task>Audit the implementation plan in ${planFile} against the actual codebase before it is built: ` +
      "risky or false assumptions, missing steps, wrong file targets, downstream breakage, sequencing and " +
      "dependency errors, missing verification gates, and, for UI work, state changes that move or drop keyboard " +
      "focus (a control disabled, hidden, or removed while focused) or change silently for screen readers." +
      `${focus.length ? ` Focus: ${focus.join(" ")}.` : ""}</task> ` +
      `${GROUNDING} ${PLAN_CONTRACT}`;
    return { mode, label: "plan", planFile, prompt, ...settings, codexArgs };
  }
  if (mode === "ask") {
    if (!positional.length) throw new Error("ask needs a prompt");
    const prompt = `<task>${positional.join(" ")}</task> ${GROUNDING} ${ASK_CONTRACT}`;
    return { mode, label: "ask", prompt, ...settings, codexArgs };
  }
  throw new Error("mode must be diff, plan, or ask");
}

/** Finds a runnable Codex: CODEX_BIN, codex(.exe) on PATH, then the desktop app's newest bundled CLI. */
function resolveCodex() {
  if (process.env.CODEX_BIN) return process.env.CODEX_BIN;
  const exe = process.platform === "win32" ? "codex.exe" : "codex";
  for (const dir of (process.env.PATH ?? "").split(delimiter)) {
    if (isAbsolute(dir) && statSync(join(dir, exe), { throwIfNoEntry: false })?.isFile()) return join(dir, exe);
  }
  if (process.platform !== "win32" || !process.env.LOCALAPPDATA) return null;
  const appBin = join(process.env.LOCALAPPDATA, "OpenAI", "Codex", "bin");
  if (existsSync(appBin)) {
    const found = readdirSync(appBin)
      .map((dir) => join(appBin, dir, exe))
      .filter((file) => statSync(file, { throwIfNoEntry: false })?.isFile())
      .sort((a, b) => statSync(b).mtimeMs - statSync(a).mtimeMs);
    if (found[0]) return found[0];
  }
  return null;
}

/**
 * Windows: Codex's sandbox cannot start Store-packaged executables (CreateProcessAsUserW is
 * denied for the WindowsApps aliases), and Codex picks the first `pwsh` on PATH. Put the MSI
 * PowerShell first and drop the alias folders so sandboxed commands get a launchable shell.
 */
function codexEnv() {
  if (process.platform !== "win32") return process.env;
  const msiPwsh = join(process.env.ProgramFiles ?? "C:\\Program Files", "PowerShell", "7");
  const pathKey = Object.keys(process.env).find((key) => key.toUpperCase() === "PATH") ?? "PATH";
  const kept = (process.env[pathKey] ?? "").split(delimiter).filter((dir) => dir && !/\\WindowsApps\\?$/i.test(dir));
  const preferred = existsSync(join(msiPwsh, "pwsh.exe")) ? [msiPwsh] : [];
  return {
    ...process.env,
    CODEX_HOME: process.env.CODEX_HOME || join(homedir(), ".codex"),
    [pathKey]: [...preferred, ...kept].join(delimiter),
  };
}

function git(cwd, ...args) {
  return execFileSync("git", args, { cwd, encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trimEnd();
}

function disableMcp(codex, execute, cwd, env) {
  const result = execute(codex, ["mcp", "list", "--json", ...WITHOUT_INTEGRATIONS], {
    cwd,
    env,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "ignore"],
    windowsHide: true,
  });
  try {
    if (result.error || result.status !== 0) throw new Error();
    // Codex merges an empty table with inherited servers, so disable the active entries individually.
    const servers = JSON.parse(result.stdout);
    if (!Array.isArray(servers)) throw new Error();
    const flags = [];
    for (const { name, enabled } of servers) {
      if (typeof enabled !== "boolean") throw new Error();
      if (!enabled) continue;
      if (typeof name !== "string" || !/^[\w-]+$/.test(name)) throw new Error();
      flags.push("-c", `mcp_servers.${name}.enabled=false`);
    }
    return flags;
  } catch {
    throw new Error("Could not verify the configured MCP servers. Check the installed Codex CLI.");
  }
}

/** Runs one review and returns the private report path, or null when Codex is unavailable. @internal */
export function runReview(argv, { cwd = process.cwd(), codex = resolveCodex(), execute = spawnSync } = {}) {
  const run = planRun(argv);
  if (!codex) return null;

  let root;
  try {
    root = realpathSync(git(cwd, "rev-parse", "--show-toplevel"));
  } catch {
    throw new Error("Start the review from the intended Git worktree.");
  }
  if (run.ref) {
    try {
      git(root, "rev-parse", "--verify", "--end-of-options", `${run.ref}^{commit}`);
    } catch {
      throw new Error("The review target must resolve to a commit in this worktree.");
    }
  }
  if (run.planFile) {
    const plan = statSync(resolve(root, run.planFile), { throwIfNoEntry: false })?.isFile()
      ? realpathSync(resolve(root, run.planFile))
      : null;
    const path = plan && relative(root, plan);
    if (!path || path === ".." || path.startsWith(`..${sep}`) || isAbsolute(path))
      throw new Error("Choose an existing plan file inside the review worktree.");
  }

  const claudeDir = join(root, ".claude");
  const reviewsDir = join(claudeDir, "reviews");
  if ([claudeDir, reviewsDir].some((dir) => lstatSync(dir, { throwIfNoEntry: false })?.isSymbolicLink()))
    throw new Error("Use a local .claude/reviews directory inside the worktree.");
  mkdirSync(reviewsDir, { recursive: true, mode: 0o700 });
  const stamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
  const folder = mkdtempSync(join(reviewsDir, `${stamp}-${run.label}-`));
  const report = join(folder, "review.md");
  try {
    try {
      git(root, "check-ignore", "-q", "--", report);
    } catch {
      throw new Error("Git must ignore the review report before it can be written.");
    }
    const env = codexEnv();
    const args = [...run.codexArgs, ...disableMcp(codex, execute, root, env), "-o", report];
    if (run.prompt) args.push("-");
    writeFileSync(report, "", { flag: "wx", mode: 0o600 });
    const started = Date.now();
    const result = execute(codex, args, {
      cwd: root,
      env,
      input: run.prompt,
      stdio: [run.prompt ? "pipe" : "ignore", "ignore", "ignore"],
      windowsHide: true,
    });
    if (result.error || result.status !== 0) {
      const reason = result.error?.code ?? result.signal ?? result.status;
      throw new Error(`Codex exited with ${reason}. Check the installed CLI and sign-in.`);
    }
    const markdown = readFileSync(report, "utf8");
    if (!markdown.trim()) throw new Error("Codex did not produce a review.");
    const seconds = Math.round((Date.now() - started) / 1000);
    const header = `<!-- codex-review v${VERSION} ${run.label} | model: ${run.model} | effort: ${run.effort} | ${seconds}s -->\n\n`;
    writeFileSync(report, header + markdown);
    return report;
  } catch (error) {
    rmSync(folder, { recursive: true, force: true });
    throw error;
  }
}

if (resolve(process.argv[1] ?? "") === resolve(import.meta.filename)) {
  try {
    const report = runReview(process.argv.slice(2));
    console.log(report ? `report: ${report}` : "skipped: Codex CLI unavailable (install it or set CODEX_BIN).");
  } catch (error) {
    console.error(`FAILED: ${error.message}`);
    process.exitCode = 1;
  }
}
