#!/usr/bin/env python3
from __future__ import annotations

import base64
import html
import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

START_MARKER = "<!--START_SECTION:waka-ai-->"
END_MARKER = "<!--END_SECTION:waka-ai-->"
README_PATH = Path(os.environ.get("README_PATH", "README.md"))
SVG_PATH = Path(os.environ.get("AI_DASHBOARD_SVG_PATH", "assets/ai-native-dashboard.svg"))
WAKATIME_RANGE = os.environ.get("WAKATIME_RANGE", "last_7_days")
WAKATIME_BASE_URL = os.environ.get(
    "WAKATIME_BASE_URL",
    "https://wakatime.com/api/v1/users/current",
)

DEFAULTS = {
    "AI_DASHBOARD_AI_CHANGES": "18.7K",
    "AI_DASHBOARD_HUMAN_CHANGES": "0",
    "AI_DASHBOARD_CHANGE_UNIT": "line changes",
    "AI_DASHBOARD_TOKENS": "939.8M",
    "AI_DASHBOARD_INPUT_TOKENS": "936.8M in",
    "AI_DASHBOARD_OUTPUT_TOKENS": "3M out",
    "AI_DASHBOARD_COST": "$2,628",
    "AI_DASHBOARD_COST_LABEL": "estimated agentic build budget",
    "AI_DASHBOARD_PROMPTS": "234 prompts",
    "AI_DASHBOARD_PROMPT_DEPTH": "2.4K chars avg prompt",
    "AI_DASHBOARD_TOP_AGENT": "Claude + Codex",
    "AI_DASHBOARD_MODEL_MIX": "Claude 68% · Codex 32%",
    "AI_DASHBOARD_REVIEW_POSTURE": "Human-led",
    "AI_DASHBOARD_REVIEW_POSTURE_LABEL": "architecture, debugging, release decisions",
    "AI_DASHBOARD_SESSIONS": "246 AI sessions",
    "AI_DASHBOARD_POSITIONING": "AI-native engineer: agents for throughput, human judgment for correctness.",
    "AI_DASHBOARD_SOURCE_LABEL": "configured rolling telemetry",
}

AI_FIELD_NAMES = (
    "ai_additions",
    "ai_deletions",
    "ai_line_changes_total",
    "ai_agent_line_changes",
    "ai_agent_costs",
    "ai_agent_breakdown",
    "ai_agent_total_cost",
    "ai_input_tokens",
    "ai_output_tokens",
    "ai_prompt_length_avg",
    "ai_prompt_events_total",
    "ai_sessions",
)


def main() -> int:
    metrics = build_metrics()
    update_readme()
    write_svg(metrics)
    print("AI dashboard updated.")
    return 0


def build_metrics() -> dict[str, Any]:
    api_key = os.environ.get("WAKATIME_API_KEY", "").strip()
    if not api_key:
        return build_fallback_metrics()

    stats = fetch_wakatime_stats(api_key)
    if not has_wakatime_ai_fields(stats):
        metrics = build_fallback_metrics()
        metrics["source_label"] = "configured fallback; WakaTime AI fields unavailable"
        return metrics

    return build_wakatime_metrics(stats)


def fetch_wakatime_stats(api_key: str) -> dict[str, Any]:
    url = f"{WAKATIME_BASE_URL.rstrip('/')}/stats/{WAKATIME_RANGE}"
    auth_values = (
        base64.b64encode(api_key.encode("utf-8")).decode("ascii"),
        base64.b64encode(f"{api_key}:".encode("utf-8")).decode("ascii"),
    )
    last_error: Exception | None = None

    for auth_value in auth_values:
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "Authorization": f"Basic {auth_value}",
                "User-Agent": "markomiric-profile-readme/1.0",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            last_error = error
            if error.code in {401, 403}:
                continue
            raise RuntimeError(f"WakaTime API request failed with HTTP {error.code}.") from error
        except urllib.error.URLError as error:
            raise RuntimeError(f"WakaTime API request failed: {error.reason}") from error

        data = payload.get("data")
        if not isinstance(data, dict):
            raise RuntimeError("WakaTime API response did not contain a data object.")
        return data

    raise RuntimeError("WakaTime API authentication failed.") from last_error


def has_wakatime_ai_fields(stats: dict[str, Any]) -> bool:
    return any(field in stats for field in AI_FIELD_NAMES)


def build_fallback_metrics() -> dict[str, Any]:
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
        "review_posture": env_value("AI_DASHBOARD_REVIEW_POSTURE"),
        "review_posture_label": env_value("AI_DASHBOARD_REVIEW_POSTURE_LABEL"),
        "sessions": env_value("AI_DASHBOARD_SESSIONS"),
        "prompts": env_value("AI_DASHBOARD_PROMPTS"),
        "prompt_depth": env_value("AI_DASHBOARD_PROMPT_DEPTH"),
        "top_agent": env_value("AI_DASHBOARD_TOP_AGENT"),
        "model_mix": env_value("AI_DASHBOARD_MODEL_MIX"),
        "positioning": env_value("AI_DASHBOARD_POSITIONING"),
        "source_label": env_value("AI_DASHBOARD_SOURCE_LABEL"),
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }


def build_wakatime_metrics(stats: dict[str, Any]) -> dict[str, Any]:
    ai_lines = first_positive_number(
        stats.get("ai_line_changes_total"),
        number(stats.get("ai_additions")) + number(stats.get("ai_deletions")),
        sum_agent_lines(stats.get("ai_agent_breakdown")),
        sum_mapping(stats.get("ai_agent_line_changes")),
    )
    human_lines = number(stats.get("human_additions")) + number(stats.get("human_deletions"))
    total_lines = ai_lines + human_lines
    ai_percentage = clamp(ai_lines / total_lines * 100, 0, 100) if total_lines else 0

    input_tokens = number(stats.get("ai_input_tokens"))
    output_tokens = number(stats.get("ai_output_tokens"))
    total_tokens = input_tokens + output_tokens
    prompt_count = number(stats.get("ai_prompt_events_total"))
    prompt_length = number(stats.get("ai_prompt_length_avg_per_session")) or number(
        stats.get("ai_prompt_length_avg")
    )
    sessions = number(stats.get("ai_sessions"))
    cost = number(stats.get("ai_agent_total_cost")) or sum_mapping(stats.get("ai_agent_costs"))
    agents = normalize_agent_breakdown(stats)

    return {
        "ai_changes": format_compact(ai_lines),
        "human_changes": format_compact(human_lines),
        "change_unit": "line changes",
        "ai_percentage": ai_percentage,
        "human_percentage": max(100 - ai_percentage, 0),
        "tokens": format_compact(total_tokens),
        "input_tokens": f"{format_compact(input_tokens)} in",
        "output_tokens": f"{format_compact(output_tokens)} out",
        "cost": format_currency(cost),
        "cost_label": "estimated WakaTime GenAI cost",
        "review_posture": env_value("AI_DASHBOARD_REVIEW_POSTURE"),
        "review_posture_label": env_value("AI_DASHBOARD_REVIEW_POSTURE_LABEL"),
        "sessions": f"{format_compact(sessions)} AI sessions",
        "prompts": f"{format_compact(prompt_count)} prompts",
        "prompt_depth": f"{format_compact(prompt_length)} chars avg prompt",
        "top_agent": top_agent_label(agents),
        "model_mix": agent_mix_label(agents),
        "positioning": env_value("AI_DASHBOARD_POSITIONING"),
        "source_label": f"WakaTime AI telemetry · {display_range(WAKATIME_RANGE)}",
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }


def normalize_agent_breakdown(stats: dict[str, Any]) -> list[dict[str, float | str]]:
    raw_breakdown = stats.get("ai_agent_breakdown")
    agents: list[dict[str, float | str]] = []

    if isinstance(raw_breakdown, list):
        for item in raw_breakdown:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            agents.append(
                {
                    "name": name.strip(),
                    "lines": number(item.get("lines")),
                    "cost": number(item.get("cost")),
                }
            )

    if agents:
        return sorted(agents, key=lambda agent: float(agent["lines"]), reverse=True)

    line_changes = stats.get("ai_agent_line_changes")
    costs = stats.get("ai_agent_costs") if isinstance(stats.get("ai_agent_costs"), dict) else {}
    if isinstance(line_changes, dict):
        for name, lines in line_changes.items():
            agents.append(
                {
                    "name": str(name),
                    "lines": number(lines),
                    "cost": number(costs.get(name)) if isinstance(costs, dict) else 0,
                }
            )

    return sorted(agents, key=lambda agent: float(agent["lines"]), reverse=True)


def top_agent_label(agents: list[dict[str, float | str]]) -> str:
    if not agents:
        return "No agent signal yet"
    names = [str(agent["name"]) for agent in agents[:2]]
    return " + ".join(names)


def agent_mix_label(agents: list[dict[str, float | str]]) -> str:
    if not agents:
        return "Waiting for WakaTime agent breakdown"

    total_lines = sum(float(agent["lines"]) for agent in agents)
    if total_lines <= 0:
        return "Agent detected; no line mix yet"

    return " · ".join(
        f"{agent['name']} {round(float(agent['lines']) / total_lines * 100)}%"
        for agent in agents[:3]
    )


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
    ai_width = round(828 * ai_percentage / 100)
    ring_dash = round(565.49 * ai_percentage / 100, 2)
    ring_gap = round(565.49 - ring_dash, 2)
    ai_display = format_percentage(ai_percentage)
    session_parts = str(metrics["sessions"]).split(" ", 1)
    session_count = session_parts[0]
    session_label = session_parts[1] if len(session_parts) > 1 else "AI sessions"

    return f'''<svg width="2400" height="1400" viewBox="0 0 1200 700" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="title desc" preserveAspectRatio="xMidYMid meet" text-rendering="geometricPrecision" shape-rendering="geometricPrecision">
  <title id="title">AI-native engineering dashboard</title>
  <desc id="desc">Agentic engineering telemetry dashboard for Marko Miric.</desc>
  <defs>
    <linearGradient id="blue" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#7AA2FF"/><stop offset="1" stop-color="#3D6DFF"/></linearGradient>
    <linearGradient id="green" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#69D391"/><stop offset="1" stop-color="#2EAD68"/></linearGradient>
    <linearGradient id="panelGlow" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#142033"/><stop offset="1" stop-color="#0E1520"/></linearGradient>
    <filter id="softShadow" x="-10%" y="-10%" width="120%" height="120%"><feDropShadow dx="0" dy="18" stdDeviation="18" flood-color="#020617" flood-opacity="0.35"/></filter>
  </defs>
  <style>
    .bg {{ fill: #090E16; }}
    text {{ dominant-baseline: auto; }}
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

  <g>
    <rect class="panel" x="24" y="24" width="1152" height="258" rx="18"/>
    <circle cx="130" cy="153" r="76" stroke="#1F2937" stroke-width="18"/>
    <circle cx="130" cy="153" r="76" stroke="url(#blue)" stroke-width="18" stroke-linecap="round" stroke-dasharray="{ring_dash} {ring_gap}" transform="rotate(-90 130 153)"/>
    <text class="text" x="130" y="158" text-anchor="middle" font-size="46">{xml(ai_display)}</text>
    <text class="eyebrow" x="130" y="189" text-anchor="middle" font-size="13">AI-driven</text>

    <circle class="blue" cx="252" cy="91" r="4"/>
    <text class="eyebrow" x="267" y="96" font-size="13">AI-authored</text>
    <text class="text" x="292" y="99" font-size="20">{xml(metrics['ai_changes'])}</text>
    <line class="track" x1="252" y1="123" x2="1080" y2="123"/>
    <line class="barBlue" x1="252" y1="123" x2="{252 + ai_width}" y2="123"/>
    <text class="muted" x="1110" y="128" text-anchor="end" font-size="15">{xml(ai_display)}</text>

    <circle class="green" cx="252" cy="164" r="4"/>
    <text class="eyebrow" x="267" y="169" font-size="13">Review posture</text>
    <text class="text" x="388" y="172" font-size="20">{xml(metrics['review_posture'])}</text>
    <line class="track" x1="252" y1="196" x2="1080" y2="196"/>
    <line class="barGreen" x1="252" y1="196" x2="1080" y2="196"/>
    <text class="muted" x="1110" y="201" text-anchor="end" font-size="15">human-owned</text>

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
    <text class="eyebrow" x="496" y="351" font-size="14">Agent cost</text>
    <text class="text" x="444" y="402" font-size="38">{xml(metrics['cost'])}</text>
    <text class="muted" x="444" y="432" font-size="14">{xml(metrics['cost_label'])}</text>

    <rect class="panel2" x="816" y="306" width="360" height="152" rx="16"/>
    <rect class="chipGreen" x="840" y="330" width="34" height="34" rx="8"/>
    <text class="green" x="857" y="352" text-anchor="middle" font-size="16">◉</text>
    <text class="eyebrow" x="892" y="351" font-size="14">Review posture</text>
    <text class="text" x="840" y="402" font-size="38">{xml(metrics['review_posture'])}</text>
    <line class="track" x1="840" y1="424" x2="1100" y2="424"/>
    <line class="barGreen" x1="840" y1="424" x2="1100" y2="424"/>
    <text class="muted" x="840" y="450" font-size="14">{xml(metrics['review_posture_label'])}</text>
  </g>

  <g>
    <rect class="panel2" x="24" y="482" width="270" height="126" rx="14"/>
    <text class="eyebrow" x="48" y="518" font-size="13">AI sessions</text>
    <text class="text" x="48" y="554" font-size="28">{xml(session_count)}</text>
    <text class="muted" x="48" y="582" font-size="13">{xml(session_label)}</text>

    <rect class="panel2" x="318" y="482" width="270" height="126" rx="14"/>
    <text class="eyebrow" x="342" y="518" font-size="13">Prompt surface</text>
    <text class="text" x="342" y="554" font-size="28">{xml(metrics['prompts'])}</text>
    <text class="muted" x="342" y="582" font-size="13">{xml(metrics['prompt_depth'])}</text>

    <rect class="panel2" x="612" y="482" width="270" height="126" rx="14"/>
    <text class="eyebrow" x="636" y="518" font-size="13">Top agent stack</text>
    <text class="text" x="636" y="554" font-size="25">{xml(metrics['top_agent'])}</text>
    <text class="muted" x="636" y="582" font-size="13">{xml(metrics['model_mix'])}</text>

    <rect class="panel2" x="906" y="482" width="270" height="126" rx="14"/>
    <text class="eyebrow" x="930" y="518" font-size="13">Positioning</text>
    <text class="text" x="930" y="550" font-size="23">AI-native</text>
    <text class="muted" x="930" y="580" font-size="13">agents for throughput</text>
  </g>

  <text class="text" x="24" y="654" font-size="24">{xml(metrics['positioning'])}</text>
  <text class="mono" x="24" y="680" font-size="12">source: {xml(metrics['source_label'])} · refreshed daily at 06:00 UTC · updated: {xml(metrics['updated_at'])}</text>
</svg>
'''



def display_range(value: str) -> str:
    return value.replace("_", " ").title()

def env_value(name: str, default: str | None = None) -> str:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return DEFAULTS[name] if default is None else default
    return value.strip()


def number(value: Any) -> float:
    if isinstance(value, bool) or value is None:
        return 0.0
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", ""))
        except ValueError:
            return parse_count(value)
    return 0.0


def first_positive_number(*values: Any) -> float:
    for value in values:
        numeric = number(value)
        if numeric > 0:
            return numeric
    return 0.0


def sum_mapping(value: Any) -> float:
    if not isinstance(value, dict):
        return 0.0
    return sum(number(item) for item in value.values())


def sum_agent_lines(value: Any) -> float:
    if not isinstance(value, list):
        return 0.0
    return sum(number(item.get("lines")) for item in value if isinstance(item, dict))


def parse_count(value: str) -> float:
    normalized = value.strip().replace(",", "")
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*([KMB])?", normalized, re.IGNORECASE)
    if not match:
        return 0.0
    amount = float(match.group(1))
    suffix = (match.group(2) or "").upper()
    multiplier = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}.get(suffix, 1)
    return amount * multiplier


def parse_percentage(value: Any) -> float:
    match = re.search(r"-?[0-9]+(?:\.[0-9]+)?", str(value))
    return float(match.group(0)) if match else 0.0


def format_compact(value: float) -> str:
    value = max(0.0, float(value))
    if value >= 1_000_000_000:
        return trim_decimal(value / 1_000_000_000) + "B"
    if value >= 1_000_000:
        return trim_decimal(value / 1_000_000) + "M"
    if value >= 1_000:
        return trim_decimal(value / 1_000) + "K"
    return str(round(value))


def trim_decimal(value: float) -> str:
    formatted = f"{value:.1f}"
    return formatted[:-2] if formatted.endswith(".0") else formatted


def format_currency(value: float) -> str:
    if value >= 1000:
        return f"${value:,.0f}"
    if value >= 100:
        return f"${value:,.0f}"
    return f"${value:,.2f}"


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
