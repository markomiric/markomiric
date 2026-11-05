import { spawnSync } from "node:child_process";
import { existsSync, lstatSync, readFileSync, readdirSync, realpathSync } from "node:fs";
import { join } from "node:path";

export function buildCard(root) {
  const git = (...args) => spawnSync("git", ["--no-optional-locks", ...args], {
    cwd: root,
    encoding: "utf8",
    timeout: 5_000,
    windowsHide: true,
  }).stdout?.trimEnd() ?? "";
  const head = git("rev-parse", "--short", "HEAD");
  const branch = git("branch", "--show-current");
  const changes = git("status", "--porcelain", "-z").split("\0").filter(Boolean);
  const card = [
    "Session context restored.",
    `- Git: ${branch || "(detached)"} at ${head || "(unborn)"}, ${changes.length} status entries.`,
  ];

  const tasks = join(root, ".claude", "tasks");
  if (existsSync(tasks) && lstatSync(tasks).isDirectory() && realpathSync(tasks) === tasks) {
    const plans = readdirSync(tasks, { withFileTypes: true })
      .filter((entry) => entry.isFile() && entry.name.endsWith(".md"))
      .map((entry) => ({ name: entry.name, stat: lstatSync(join(tasks, entry.name)) }))
      .sort((a, b) => b.stat.mtimeMs - a.stat.mtimeMs);
    let listed = 0;
    for (const plan of plans) {
      if (listed === 5) break;
      if (plan.stat.size > 256_000) continue; // shortcut: read normal task plans, revisit the limit if larger plans are needed.
      const text = readFileSync(join(tasks, plan.name), "utf8");
      const pending = text.split(/^### /m).slice(1).filter((section) => /^- \*\*Status\*\*: \[(?: |wip|f)\]/m.test(section));
      if (!pending.length) continue;
      card.push(`- Open plan: .claude/tasks/${plan.name} (${pending.length} remaining)`);
      for (const section of pending.slice(0, 8)) card.push(`  - ${section.split(/\r?\n/, 1)[0]}`);
      listed++;
    }
  }
  return card.join("\n").slice(0, 6_000);
}

if (process.argv[1] && existsSync(process.argv[1]) && realpathSync(process.argv[1]) === import.meta.filename) {
  try {
    process.stdout.write(buildCard(realpathSync(process.env.CLAUDE_PROJECT_DIR || process.cwd())) + "\n");
  } catch {
    // A missing or unreadable checkout should not prevent resume.
  }
}
