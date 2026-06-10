#!/usr/bin/env python3
from __future__ import annotations

import html
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

START_MARKER = "<!--START_SECTION:waka-ai-->"
END_MARKER = "<!--END_SECTION:waka-ai-->"
README_PATH = Path(os.environ.get("README_PATH", "README.md"))
SVG_PATH = Path(os.environ.get("AI_DASHBOARD_SVG_PATH", "assets/ai-native-dashboard.svg"))

DEFAULTS = {
    "AI_DASHBOARD_AI_CHANGES": "18.7K",
    "AI_DASHBOARD_HUMAN_CHANGES": "0",
    "AI_DASHBOARD_CHANGE_UNIT": "line changes",
    "AI_DASHBOARD_TOKENS": "939.8M",
    "AI_DASHBOARD_INPUT_TOKENS": "936.8M in",
    "AI_DASHBOARD_OUTPUT_TOKENS": "3M out",
    "AI_DASHBOARD_COST": "$2,628",
    "AI_DASHBOARD_COST_LABEL": "estimated agentic build budget",
    "AI_DASHBOARD_HUMAN_REVIEW_RATE": "35%",
    "AI_DASHBOARD_REVIEW_SESSIONS": "246 review sessions",
    "AI_DASHBOARD_PROMPTS": "234 prompts",
    "AI_DASHBOARD_PROMPT_DEPTH": "2.4K chars avg prompt",
    "AI_DASHBOARD_TOP_AGENT": "Claude + Codex",
    "AI_DASHBOARD_MODEL_MIX": "Claude 68% · Codex 32%",
    "AI_DASHBOARD_FOLLOW_UP_RATE": "0%",
    "AI_DASHBOARD_FOLLOW_UP_LABEL": "follow-up edit loops",
    "AI_DASHBOARD_REVIEW_LABEL": "review discipline",
    "AI_DASHBOARD_POSITIONING": "AI-native engineer: agents for throughput, human judgment for correctness.",
    "AI_DASHBOARD_SOURCE_LABEL": "agent telemetry",
}


def main() -> int:
    metrics = build_metrics()
    update_readme()
    write_svg(metrics)
    print("AI dashboard updated.")
    return 0


def build_metrics() -> dict[str, Any]:
    ai_changes = env_value("AI_DASHBOARD_AI_CHANGES")
    human_changes = env_value("AI_DASHBOARD_HUMAN_CHANGES")
    ai_share = env_value("AI_DASHBOARD_AI_SHARE", "")

    if ai_share:
        ai_percentage = clamp(parse_percentage(ai_share), 0, 100)
    else:
        ai_count = parse_count(ai_changes)
        human_count = parse_count(human_changes)
        total_count = ai_count + human_count
        ai_percentage = clamp(ai_count / total_count * 100, 0, 100) if total_count else 0

    return {
        "ai_changes": ai_changes,
        "human_changes": human_changes,
        "change_unit": env_value("AI_DASHBOARD_CHANGE_UNIT"),
        "ai_percentage": ai_percentage,
        "human_percentage": max(100 - ai_percentage, 0),
        "tokens": env_value("AI_DASHBOARD_TOKENS"),
        "input_tokens": env_value("AI_DASHBOARD_INPUT_TOKENS"),
        "output_tokens": env_value("AI_DASHBOARD_OUTPUT_TOKENS"),
        "cost": env_value("AI_DASHBOARD_COST"),
        "cost_label": env_value("AI_DASHBOARD_COST_LABEL"),
        "review_rate": env_value("AI_DASHBOARD_HUMAN_REVIEW_RATE"),
        "review_sessions": env_value("AI_DASHBOARD_REVIEW_SESSIONS"),
        "prompts": env_value("AI_DASHBOARD_PROMPTS"),
        "prompt_depth": env_value("AI_DASHBOARD_PROMPT_DEPTH"),
        "top_agent": env_value("AI_DASHBOARD_TOP_AGENT"),
        "model_mix": env_value("AI_DASHBOARD_MODEL_MIX"),
        "follow_up_rate": env_value("AI_DASHBOARD_FOLLOW_UP_RATE"),
        "follow_up_label": env_value("AI_DASHBOARD_FOLLOW_UP_LABEL"),
        "review_label": env_value("AI_DASHBOARD_REVIEW_LABEL"),
        "positioning": env_value("AI_DASHBOARD_POSITIONING"),
        "source_label": env_value("AI_DASHBOARD_SOURCE_LABEL"),
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }


def update_readme() -> None:
    readme = README_PATH.read_text(encoding="utf-8")
    if START_MARKER not in readme or END_MARKER not in readme:
        raise RuntimeError(
            f"README must contain both {START_MARKER} and {END_MARKER} markers."
        )

    section = "![AI-native engineering dashboard](assets/ai-native-dashboard.svg)"
    before, remainder = readme.split(START_MARKER, 1)
    _, after = remainder.split(END_MARKER, 1)
    updated = f"{before}{START_MARKER}\n{section}\n{END_MARKER}{after}"
    README_PATH.write_text(updated, encoding="utf-8")


def write_svg(metrics: dict[str, Any]) -> None:
    SVG_PATH.parent.mkdir(parents=True, exist_ok=True)
    SVG_PATH.write_text(render_svg(metrics), encoding="utf-8")


def render_svg(metrics: dict[str, Any]) -> str:
    ai_percentage = float(metrics["ai_percentage"])
    human_percentage = float(metrics["human_percentage"])
    ai_width = round(828 * ai_percentage / 100)
    human_width = round(828 * human_percentage / 100)
    review_width = round(260 * clamp(parse_percentage(metrics["review_rate"]), 0, 100) / 100)
    follow_up_width = round(260 * clamp(parse_percentage(metrics["follow_up_rate"]), 0, 100) / 100)
    ring_dash = round(565.49 * ai_percentage / 100, 2)
    ring_gap = round(565.49 - ring_dash, 2)
    ai_display = format_percentage(ai_percentage)
    human_display = format_percentage(human_percentage)
    review_parts = metrics["review_sessions"].split(" ", 1)
    review_count = review_parts[0]
    review_label = review_parts[1] if len(review_parts) > 1 else metrics["review_label"]

    return f'''<svg width="1200" height="700" viewBox="0 0 1200 700" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="title desc">
  <title id="title">AI-native engineering dashboard</title>
  <desc id="desc">Agentic engineering telemetry dashboard for Marko Mirić.</desc>
  <defs>
    <linearGradient id="blue" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#7AA2FF"/><stop offset="1" stop-color="#3D6DFF"/></linearGradient>
    <linearGradient id="green" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#69D391"/><stop offset="1" stop-color="#2EAD68"/></linearGradient>
    <linearGradient id="panelGlow" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#142033"/><stop offset="1" stop-color="#0E1520"/></linearGradient>
    <filter id="softShadow" x="-10%" y="-10%" width="120%" height="120%"><feDropShadow dx="0" dy="18" stdDeviation="18" flood-color="#020617" flood-opacity="0.35"/></filter>
  </defs>
  <style>
    .bg {{ fill: #090E16; }}
    .panel {{ fill: url(#panelGlow); stroke: #233044; stroke-width: 1; }}
    .panel2 {{ fill: #101722; stroke: #263449; stroke-width: 1; }}
    .eyebrow {{ fill: #8D98AA; font-family: 'Aptos Display', 'Segoe UI', sans-serif; font-weight: 800; letter-spacing: .04em; }}
    .text {{ fill: #E7EAF0; font-family: 'Aptos Display', 'Segoe UI', sans-serif; font-weight: 850; }}
    .muted {{ fill: #8F9AAB; font-family: 'Aptos', 'Segoe UI', sans-serif; font-weight: 700; }}
    .mono {{ fill: #A9B4C4; font-family: 'SFMono-Regular', 'Cascadia Mono', 'Consolas', monospace; font-weight: 700; }}
    .track {{ stroke: #202938; stroke-width: 6; stroke-linecap: round; }}
    .barBlue {{ stroke: url(#blue); stroke-width: 6; stroke-linecap: round; }}
    .barGreen {{ stroke: url(#green); stroke-width: 6; stroke-linecap: round; }}
    .chipBlue {{ fill: #13264D; }}
    .chipGreen {{ fill: #123525; }}
    .blue {{ fill: #5D8AFF; }}
    .green {{ fill: #55C083; }}
  </style>

  <rect class="bg" width="1200" height="700" rx="24"/>

  <g filter="url(#softShadow)">
    <rect class="panel" x="24" y="24" width="1152" height="258" rx="18"/>
    <circle cx="130" cy="153" r="76" stroke="#1F2937" stroke-width="18"/>
    <circle cx="130" cy="153" r="76" stroke="url(#blue)" stroke-width="18" stroke-linecap="round" stroke-dasharray="{ring_dash} {ring_gap}" transform="rotate(-90 130 153)"/>
    <text class="text" x="130" y="158" text-anchor="middle" font-size="46">{xml(ai_display)}</text>
    <text class="eyebrow" x="130" y="189" text-anchor="middle" font-size="13">AI-driven</text>

    <circle class="blue" cx="252" cy="91" r="4"/>
    <text class="eyebrow" x="267" y="96" font-size="13">AI</text>
    <text class="text" x="292" y="99" font-size="20">{xml(metrics['ai_changes'])}</text>
    <line class="track" x1="252" y1="123" x2="1080" y2="123"/>
    <line class="barBlue" x1="252" y1="123" x2="{252 + ai_width}" y2="123"/>
    <text class="muted" x="1110" y="128" text-anchor="end" font-size="15">{xml(ai_display)}</text>

    <circle class="green" cx="252" cy="164" r="4"/>
    <text class="eyebrow" x="267" y="169" font-size="13">Human edits</text>
    <text class="text" x="362" y="172" font-size="20">{xml(metrics['human_changes'])}</text>
    <line class="track" x1="252" y1="196" x2="1080" y2="196"/>
    <line class="barGreen" x1="252" y1="196" x2="{252 + human_width}" y2="196"/>
    <text class="muted" x="1110" y="201" text-anchor="end" font-size="15">{xml(human_display)}</text>

    <line x1="252" y1="226" x2="1080" y2="226" stroke="#1E2937"/>
    <text class="mono" x="252" y="250" font-size="12">&lt;/&gt; {xml(metrics['ai_changes'])} AI-authored {xml(metrics['change_unit'])}</text>
  </g>

  <g>
    <rect class="panel2" x="24" y="306" width="360" height="152" rx="16"/>
    <rect class="chipBlue" x="48" y="330" width="34" height="34" rx="8"/>
    <text class="blue" x="65" y="352" text-anchor="middle" font-size="18">↔</text>
    <text class="eyebrow" x="100" y="351" font-size="14">Tokens</text>
    <text class="text" x="48" y="398" font-size="36">{xml(metrics['tokens'])}</text>
    <line class="track" x1="48" y1="420" x2="340" y2="420"/>
    <line class="barBlue" x1="48" y1="420" x2="340" y2="420"/>
    <circle class="blue" cx="52" cy="443" r="4"/>
    <text class="muted" x="66" y="448" font-size="13">{xml(metrics['input_tokens'])}</text>
    <circle fill="#93C5FD" cx="178" cy="443" r="4"/>
    <text class="muted" x="192" y="448" font-size="13">{xml(metrics['output_tokens'])}</text>

    <rect class="panel2" x="420" y="306" width="360" height="152" rx="16"/>
    <rect class="chipBlue" x="444" y="330" width="34" height="34" rx="8"/>
    <text class="blue" x="461" y="352" text-anchor="middle" font-size="18">$</text>
    <text class="eyebrow" x="496" y="351" font-size="14">Model spend</text>
    <text class="text" x="444" y="402" font-size="38">{xml(metrics['cost'])}</text>
    <text class="muted" x="444" y="432" font-size="14">{xml(metrics['cost_label'])}</text>

    <rect class="panel2" x="816" y="306" width="360" height="152" rx="16"/>
    <rect class="chipGreen" x="840" y="330" width="34" height="34" rx="8"/>
    <text class="green" x="857" y="352" text-anchor="middle" font-size="16">◉</text>
    <text class="eyebrow" x="892" y="351" font-size="14">Human review</text>
    <text class="text" x="840" y="402" font-size="38">{xml(metrics['review_rate'])}</text>
    <line class="track" x1="840" y1="424" x2="1100" y2="424"/>
    <line class="barGreen" x1="840" y1="424" x2="{840 + review_width}" y2="424"/>
    <text class="text" x="840" y="450" font-size="14">{xml(review_count)}</text>
    <text class="muted" x="880" y="450" font-size="14">{xml(review_label)}</text>
  </g>

  <g>
    <rect class="panel2" x="24" y="482" width="270" height="126" rx="14"/>
    <text class="eyebrow" x="48" y="518" font-size="13">Prompt surface</text>
    <text class="text" x="48" y="554" font-size="28">{xml(metrics['prompts'])}</text>
    <text class="muted" x="48" y="582" font-size="13">{xml(metrics['prompt_depth'])}</text>

    <rect class="panel2" x="318" y="482" width="270" height="126" rx="14"/>
    <text class="eyebrow" x="342" y="518" font-size="13">Top agent stack</text>
    <text class="text" x="342" y="554" font-size="25">{xml(metrics['top_agent'])}</text>
    <text class="muted" x="342" y="582" font-size="13">{xml(metrics['model_mix'])}</text>

    <rect class="panel2" x="612" y="482" width="270" height="126" rx="14"/>
    <text class="eyebrow" x="636" y="518" font-size="13">Human follow-up</text>
    <text class="text" x="636" y="554" font-size="28">{xml(metrics['follow_up_rate'])}</text>
    <line class="track" x1="636" y1="574" x2="856" y2="574"/>
    <line class="barGreen" x1="636" y1="574" x2="{636 + follow_up_width}" y2="574"/>
    <text class="muted" x="636" y="596" font-size="13">{xml(metrics['follow_up_label'])}</text>

    <rect class="panel2" x="906" y="482" width="270" height="126" rx="14"/>
    <text class="eyebrow" x="930" y="518" font-size="13">Positioning</text>
    <text class="text" x="930" y="550" font-size="23">AI-native</text>
    <text class="muted" x="930" y="580" font-size="13">agents for throughput</text>
  </g>

  <text class="text" x="24" y="654" font-size="24">{xml(metrics['positioning'])}</text>
  <text class="mono" x="24" y="680" font-size="12">source: {xml(metrics['source_label'])} · updated: {xml(metrics['updated_at'])}</text>
</svg>
'''


def env_value(name: str, default: str | None = None) -> str:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return DEFAULTS[name] if default is None else default
    return value.strip()


def parse_count(value: str) -> float:
    normalized = value.strip().replace(",", "")
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*([KMB])?", normalized, re.IGNORECASE)
    if not match:
        return 0.0
    number = float(match.group(1))
    suffix = (match.group(2) or "").upper()
    multiplier = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}.get(suffix, 1)
    return number * multiplier


def parse_percentage(value: str) -> float:
    match = re.search(r"-?[0-9]+(?:\.[0-9]+)?", value)
    return float(match.group(0)) if match else 0.0


def format_percentage(value: float) -> str:
    value = clamp(value, 0, 100)
    if abs(value - round(value)) < 0.05:
        return f"{round(value)}%"
    return f"{value:.1f}%"


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def xml(value: Any) -> str:
    return html.escape(str(value), quote=True)


if __name__ == "__main__":
    raise SystemExit(main())
