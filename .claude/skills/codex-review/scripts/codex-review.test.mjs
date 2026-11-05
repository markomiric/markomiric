import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import {
  mkdirSync,
  mkdtempSync,
  readdirSync,
  readFileSync,
  realpathSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { test } from "node:test";
import { planRun, runReview } from "./codex-review.mjs";

test("a base branch with slashes gives a filename-safe label and passes the branch through unchanged", () => {
  const run = planRun(["diff", "--base", "feat/runner-github-issues"]);
  assert.equal(run.label, "base-feat-runner-github-issues");
  assert.ok(run.codexArgs.includes("feat/runner-github-issues"));
});

test("plain base, commit, and uncommitted labels are unchanged", () => {
  assert.equal(planRun(["diff", "--base", "main"]).label, "base-main");
  assert.equal(planRun(["diff", "--commit", "0123456789abcdef"]).label, "commit-01234567");
  assert.equal(planRun(["diff", "--uncommitted"]).label, "uncommitted");
});

test("diff requires exactly one explicit target", () => {
  assert.throws(() => planRun(["diff"]), /exactly one target/);
  assert.throws(() => planRun(["diff", "--base", "main", "--uncommitted"]), /exactly one target/);
  assert.throws(() => planRun(["diff", "--commit", "--base", "main"]), /needs a value/);
});

function fixture(t) {
  const root = realpathSync(mkdtempSync(join(tmpdir(), "codex-review-test-")));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  execFileSync("git", ["init", "-q", "--template="], { cwd: root });
  writeFileSync(join(root, ".gitignore"), "/.claude/reviews/\n");
  return root;
}

test("reviews the caller's worktree and creates a distinct private report for each run", (t) => {
  const root = fixture(t);
  const cwd = join(root, "nested directory");
  mkdirSync(cwd);
  const execute = (_codex, args, options) => {
    assert.equal(options.cwd, root);
    if (args[0] === "mcp") {
      assert.deepEqual(args.slice(0, 3), ["mcp", "list", "--json"]);
      assert.deepEqual(options.stdio, ["ignore", "pipe", "ignore"]);
      return { status: 0, stdout: '[{"name":"test-agent","enabled":true},{"name":"disabled","enabled":false}]' };
    }
    assert.deepEqual(args.slice(0, 3), ["exec", "review", "--uncommitted"]);
    for (const setting of [
      'sandbox_mode="read-only"',
      'approval_policy="never"',
      "mcp_servers.test-agent.enabled=false",
      "--ephemeral",
    ])
      assert.ok(args.includes(setting));
    assert.ok(!args.includes("mcp_servers.disabled.enabled=false"));
    assert.deepEqual(options.stdio, ["ignore", "ignore", "ignore"]);
    writeFileSync(args.at(-1), "No findings.\n");
    return { status: 0 };
  };
  const review = () => runReview(["diff", "--uncommitted"], { cwd, codex: "fake-codex", execute });
  const first = review();
  assert.notEqual(first, review());
  assert.match(readFileSync(first, "utf8"), /codex-review v1[\s\S]+No findings/);
  assert.deepEqual(readdirSync(dirname(first)), ["review.md"]);
  if (process.platform !== "win32") {
    assert.equal(statSync(dirname(first)).mode & 0o077, 0);
    assert.equal(statSync(first).mode & 0o077, 0);
  }
});

test("focused prompts go over stdin and failed reviews leave no partial report", (t) => {
  const cwd = fixture(t);
  const execute = (_codex, args, options) => {
    if (args[0] === "mcp") return { status: 0, stdout: "[]" };
    assert.equal(args.at(-1), "-");
    assert.ok(!args.join(" ").includes("synthetic focus"));
    assert.match(options.input, /synthetic focus/);
    assert.deepEqual(options.stdio, ["pipe", "ignore", "ignore"]);
    writeFileSync(args.at(-2), "Partial output.\n");
    return { status: 1 };
  };
  assert.throws(
    () => runReview(["ask", "synthetic focus"], { cwd, codex: "fake-codex", execute }),
    /Codex exited with 1/
  );
  assert.throws(
    () =>
      runReview(["diff", "--uncommitted"], {
        cwd,
        codex: "fake-codex",
        execute: (_codex, args) => {
          assert.equal(args[0], "mcp");
          return { status: 0, stdout: "malformed list" };
        },
      }),
    /Could not verify the configured MCP servers/
  );
  assert.deepEqual(readdirSync(join(cwd, ".claude", "reviews")), []);
});

test("rejects invalid refs, out-of-worktree plans and non-ignored reports before launching Codex", (t) => {
  const cwd = fixture(t);
  const options = { cwd, codex: "fake-codex", execute: () => assert.fail("Codex should not start") };
  assert.throws(() => runReview(["diff", "--commit", "missing"], options), /resolve to a commit/);
  assert.throws(() => runReview(["plan", import.meta.filename], options), /inside the review worktree/);
  writeFileSync(join(cwd, ".gitignore"), "");
  assert.throws(() => runReview(["diff", "--uncommitted"], options), /Git must ignore/);
  assert.equal(runReview(["diff", "--uncommitted"], { ...options, codex: null }), null);
});
