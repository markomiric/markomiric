#!/usr/bin/env node
// Advisory skill surfacing on UserPromptSubmit: word-boundary keyword matching,
// relevance scoring by distinct trigger hits, capped output, softened voice.
// It recommends; the lead decides what to load. Agent recommendations were
// removed 2026-07-29 (operator decision): they never changed a routing
// decision and pushed toward over-delegation.
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const MAX_RECOMMENDATIONS = 3;
const PRIORITY_WEIGHT = { critical: 3, high: 2, medium: 1, low: 0 };

function escapeRegex(str) {
  return str.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function wordBoundaryMatch(prompt, keyword) {
  return new RegExp(`\\b${escapeRegex(keyword.toLowerCase())}\\b`, "i").test(prompt);
}

async function main() {
  try {
    const input = readFileSync(0, "utf-8");
    const data = JSON.parse(input);
    const prompt = (data.prompt || "").toLowerCase();
    if (!prompt) return;
    const sessionId = data.session_id;

    // This file is in .claude/hooks/SkillActivationHook/, so project root is 3 levels up
    const __filename = fileURLToPath(import.meta.url);
    const __dirname = dirname(__filename);
    const projectDir = join(__dirname, "..", "..", "..");
    const skillRulesPath = join(projectDir, ".claude", "skills", "skill-rules.json");
    const skillRules = JSON.parse(readFileSync(skillRulesPath, "utf-8"));

    // Session state: a skill is surfaced at most once per session
    const stateFilePath = join(__dirname, "recommendation-log.json");
    let state = {};
    if (existsSync(stateFilePath)) {
      try {
        state = JSON.parse(readFileSync(stateFilePath, "utf-8"));
      } catch {
        state = {};
      }
    }
    const sevenDaysAgo = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString();
    for (const [sid, sessionData] of Object.entries(state)) {
      if (sessionData.lastUpdated && sessionData.lastUpdated < sevenDaysAgo) {
        delete state[sid];
      }
    }
    const alreadyRecommended = state[sessionId]?.skills || [];

    // Score each skill by count of distinct matched triggers
    const matched = [];
    for (const [skillName, config] of Object.entries(skillRules.skills)) {
      const triggers = config.promptTriggers;
      if (!triggers || alreadyRecommended.includes(skillName)) continue;

      const keywordHits = [];
      for (const kw of triggers.keywords || []) {
        if (wordBoundaryMatch(prompt, kw)) keywordHits.push(kw);
      }
      let intentHits = 0;
      for (const pattern of triggers.intentPatterns || []) {
        try {
          if (new RegExp(pattern, "i").test(prompt)) intentHits++;
        } catch {
          // invalid pattern in rules file; skip it
        }
      }
      const score = keywordHits.length + intentHits;
      if (score > 0) {
        matched.push({ name: skillName, score, keywordHits, intentHits, priority: config.priority });
      }
    }

    if (!matched.length) {
      process.exit(0);
    }

    matched.sort(
      (a, b) => b.score - a.score || (PRIORITY_WEIGHT[b.priority] || 0) - (PRIORITY_WEIGHT[a.priority] || 0)
    );
    const top = matched.slice(0, MAX_RECOMMENDATIONS);

    let output = "Possibly relevant skills (load what genuinely applies, skip the rest):\n";
    for (const s of top) {
      const parts = s.keywordHits.slice(0, 3);
      if (s.intentHits) parts.push(`${s.intentHits} intent match${s.intentHits > 1 ? "es" : ""}`);
      output += `  → ${s.name} (matched: ${parts.join(", ")})\n`;
    }
    console.log(output);

    state[sessionId] = {
      skills: [...alreadyRecommended, ...top.map((s) => s.name)],
      lastUpdated: new Date().toISOString(),
    };
    writeFileSync(stateFilePath, JSON.stringify(state, null, 2), "utf-8");
    process.exit(0);
  } catch (err) {
    console.error("Error in skill-activation-prompt hook:", err);
    process.exit(1);
  }
}

main().catch((err) => {
  console.error("Uncaught error:", err);
  process.exit(1);
});
