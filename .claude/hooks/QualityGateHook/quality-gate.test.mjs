import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdirSync, mkdtempSync, realpathSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { checkFiles, repoPath } from "./quality-gate.mjs";

test("checks the edited files and rejects paths outside the checkout", (t) => {
  const root = realpathSync(mkdtempSync(join(tmpdir(), "agent-quality-")));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  execFileSync("git", ["init", "-q", "--template="], { cwd: root });
  mkdirSync(join(root, "source folder"));
  const source = "source folder/check.mjs";
  writeFileSync(join(root, source), "export const value = 1;\n");
  execFileSync("git", ["add", "--", source], { cwd: root });
  assert.deepEqual(checkFiles(root, [source], {}), []);
  assert.equal(repoPath(root, import.meta.filename), null);
  writeFileSync(join(root, source), "export const value = ;  \n");
  writeFileSync(join(root, "package.json"), "{bad json}");
  const failures = checkFiles(root, [source, "package.json"], {});
  assert.equal(failures.length, 3);
  assert.match(failures.join("\n"), /Git patch whitespace/);
  assert.match(failures.join("\n"), /SyntaxError/);
  assert.match(failures.join("\n"), /Invalid JSON/);
});
