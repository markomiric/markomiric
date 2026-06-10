#!/usr/bin/env python3
from __future__ import annotations

import base64
import html
import json
import os
import re
import sys
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
AI_KEYWORDS = tuple(
    keyword.strip().casefold()
    for keyword in os.environ.get(
        "WAKATIME_AI_KEYWORDS",
        "cursor,copilot,github copilot,claude,claude code,codex,chatgpt,openai,"
        "windsurf,continue,tabnine,cody,sourcegraph cody,aider,roo,gemini,kiro,ai",
    ).split(",")
    if keyword.strip()
)
DIMENSIONS = (
    "categories",
    "editors",
    "projects",
    "dependencies",
    "languages",
    "branches",
    "entities",
    "machines",
)


def main() -> int:
    api_key = os.environ.get("WAKATIME_API_KEY")
    if not api_key:
        print("WAKATIME_API_KEY is not set.", file=sys.stderr)
        return 1

    stats = fetch_wakatime_stats(api_key)
    metrics = build_metrics(stats)
    update_readme()
    write_svg(metrics)
    print("README dashboard updated.")
    return 0


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


def build_metrics(stats: dict[str, Any]) -> dict[str, Any]:
    total_seconds = to_seconds(stats.get("total_seconds"))
    human_total = stats.get("human_readable_total") or format_duration(total_seconds)
    ai_match = best_ai_match(stats)
    ai_seconds = min(ai_match["seconds"], total_seconds) if total_seconds > 0 else 0.0
    ai_percentage = min(ai_seconds / total_seconds * 100, 100.0) if total_seconds > 0 else 0.0
    non_ai_percentage = max(100.0 - ai_percentage, 0.0)
    ai_index = round(ai_percentage)
    top_languages = top_named_values(stats.get("languages"), 3)
    top_projects = top_named_values(stats.get("projects"), 2)
    updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    return {
        "ai_index": ai_index,
        "ai_percentage": ai_percentage,
        "non_ai_percentage": non_ai_percentage,
        "ai_seconds": ai_seconds,
        "human_total": human_total,
        "matched_dimension": ai_match["dimension"],
        "matched_signals": ai_match["matches"],
        "top_languages": top_languages,
        "top_projects": top_projects,
        "updated_at": updated_at,
    }


def best_ai_match(stats: dict[str, Any]) -> dict[str, Any]:
    best: dict[str, Any] = {"dimension": "none", "seconds": 0.0, "matches": []}

    for dimension in DIMENSIONS:
        values = stats.get(dimension)
        if not isinstance(values, list):
            continue

        matches: list[tuple[str, float]] = []
        for item in values:
            if not isinstance(item, dict):
                continue

            name = item_name(item)
            if not name or not is_ai_signal(name):
                continue

            seconds = to_seconds(item.get("total_seconds") or item.get("seconds"))
            if seconds <= 0:
                continue

            matches.append((name, seconds))

        matched_seconds = sum(seconds for _, seconds in matches)
        if matched_seconds > best["seconds"]:
            best = {
                "dimension": dimension,
                "seconds": matched_seconds,
                "matches": sorted(matches, key=lambda match: match[1], reverse=True),
            }

    return best


def top_named_values(values: Any, limit: int) -> list[tuple[str, float]]:
    if not isinstance(values, list):
        return []

    named_values: list[tuple[str, float]] = []
    for item in values:
        if not isinstance(item, dict):
            continue
        name = item_name(item)
        seconds = to_seconds(item.get("total_seconds") or item.get("seconds"))
        if name and seconds > 0:
            named_values.append((name, seconds))

    return sorted(named_values, key=lambda item: item[1], reverse=True)[:limit]


def item_name(item: dict[str, Any]) -> str:
    for key in ("name", "key", "value", "text"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def is_ai_signal(name: str) -> bool:
    normalized = name.casefold()
    for keyword in AI_KEYWORDS:
        if keyword == "ai":
            if re.search(r"(^|[^a-z0-9])ai([^a-z0-9]|$)", normalized):
                return True
            continue
        if keyword in normalized:
            return True
    return False


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
    ai_index = int(metrics["ai_index"])
    ai_percentage = float(metrics["ai_percentage"])
    human_percentage = float(metrics["non_ai_percentage"])
    ai_width = round(700 * ai_percentage / 100)
    human_width = round(700 * human_percentage / 100)
    ring_dash = round(565.49 * ai_percentage / 100, 2)
    ring_gap = round(565.49 - ring_dash, 2)
    signal = format_signal(metrics)
    stack = format_stack(metrics["top_languages"])
    projects = format_stack(metrics["top_projects"])
    updated = xml(metrics["updated_at"])

    return f'''<svg width="1200" height="620" viewBox="0 0 1200 620" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="title desc">
  <title id="title">AI-native engineering dashboard</title>
  <desc id="desc">WakaTime-powered AI-assisted engineering profile metrics for Marko Mirić.</desc>
  <defs>
    <linearGradient id="blue" x1="0" y1="0" x2="1" y2="1">
      <stop stop-color="#7AA2FF"/>
      <stop offset="1" stop-color="#3D6DFF"/>
    </linearGradient>
    <linearGradient id="green" x1="0" y1="0" x2="1" y2="1">
      <stop stop-color="#70E0A2"/>
      <stop offset="1" stop-color="#35B779"/>
    </linearGradient>
    <filter id="softShadow" x="-10%" y="-10%" width="120%" height="120%">
      <feDropShadow dx="0" dy="18" stdDeviation="18" flood-color="#020617" flood-opacity="0.35"/>
    </filter>
  </defs>
  <style>
    .bg {{ fill: #0B111B; }}
    .panel {{ fill: #101722; stroke: #253244; stroke-width: 1; }}
    .muted {{ fill: #94A3B8; font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif; font-weight: 700; }}
    .text {{ fill: #E5E7EB; font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif; font-weight: 800; }}
    .small {{ fill: #7C8799; font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif; font-weight: 700; }}
    .mono {{ fill: #AAB4C5; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-weight: 700; }}
    .blue {{ fill: #5B87FF; }}
    .green {{ fill: #4FC083; }}
    .track {{ stroke: #202938; stroke-width: 5; stroke-linecap: round; }}
    .barBlue {{ stroke: url(#blue); stroke-width: 5; stroke-linecap: round; }}
    .barGreen {{ stroke: url(#green); stroke-width: 5; stroke-linecap: round; }}
  </style>

  <rect class="bg" width="1200" height="620" rx="24"/>

  <g filter="url(#softShadow)">
    <rect class="panel" x="24" y="24" width="1152" height="248" rx="18"/>
    <circle cx="135" cy="148" r="76" stroke="#202938" stroke-width="18"/>
    <circle cx="135" cy="148" r="76" stroke="url(#blue)" stroke-width="18" stroke-linecap="round" stroke-dasharray="{ring_dash} {ring_gap}" transform="rotate(-90 135 148)"/>
    <text class="text" x="135" y="154" text-anchor="middle" font-size="46">{ai_index}%</text>
    <text class="muted" x="135" y="184" text-anchor="middle" font-size="13">AI-native index</text>

    <text class="muted" x="260" y="75" font-size="14">AI-assisted signal</text>
    <text class="text" x="260" y="104" font-size="26">{format_percentage(ai_percentage)}</text>
    <text class="text" x="372" y="104" font-size="22">{xml(signal)}</text>
    <line class="track" x1="260" y1="128" x2="960" y2="128"/>
    <line class="barBlue" x1="260" y1="128" x2="{260 + ai_width}" y2="128"/>
    <text class="muted" x="1010" y="133" font-size="15">{format_percentage(ai_percentage)}</text>

    <text class="muted" x="260" y="170" font-size="14">Human-owned judgment</text>
    <text class="text" x="260" y="199" font-size="26">Architecture · review · production calls</text>
    <line class="track" x1="260" y1="224" x2="960" y2="224"/>
    <line class="barGreen" x1="260" y1="224" x2="{260 + human_width}" y2="224"/>
    <text class="muted" x="1010" y="229" font-size="15">{format_percentage(human_percentage)}</text>
  </g>

  <g>
    <rect class="panel" x="24" y="294" width="270" height="136" rx="16"/>
    <text class="muted" x="48" y="336" font-size="14">Operating mode</text>
    <text class="text" x="48" y="374" font-size="28">Agent-first</text>
    <text class="small" x="48" y="404" font-size="13">Implementation accelerated by AI agents</text>

    <rect class="panel" x="318" y="294" width="270" height="136" rx="16"/>
    <text class="muted" x="342" y="336" font-size="14">Control layer</text>
    <text class="text" x="342" y="374" font-size="28">Human-led</text>
    <text class="small" x="342" y="404" font-size="13">Architecture, debugging, review, release</text>

    <rect class="panel" x="612" y="294" width="270" height="136" rx="16"/>
    <text class="muted" x="636" y="336" font-size="14">Primary stack signal</text>
    <text class="text" x="636" y="374" font-size="24">{xml(stack)}</text>
    <text class="small" x="636" y="404" font-size="13">WakaTime language mix</text>

    <rect class="panel" x="906" y="294" width="270" height="136" rx="16"/>
    <text class="muted" x="930" y="336" font-size="14">Focus surface</text>
    <text class="text" x="930" y="374" font-size="24">{xml(projects)}</text>
    <text class="small" x="930" y="404" font-size="13">Recent project signal</text>
  </g>

  <g>
    <rect class="panel" x="24" y="452" width="1152" height="120" rx="16"/>
    <text class="muted" x="48" y="493" font-size="14">Positioning</text>
    <text class="text" x="48" y="529" font-size="26">AI-native software engineer: agents for throughput, human judgment for correctness.</text>
    <text class="mono" x="48" y="555" font-size="12">WakaTime window: {xml(display_range(WAKATIME_RANGE))} · tracked signal: {xml(metrics['human_total'])} · updated: {updated}</text>
  </g>
</svg>
'''


def format_signal(metrics: dict[str, Any]) -> str:
    matches = metrics["matched_signals"]
    if not matches:
        return "No keyword match yet"
    name, seconds = matches[0]
    shown_seconds = min(seconds, metrics["ai_seconds"])
    return f"{name} · {format_duration(shown_seconds)}"


def format_stack(values: list[tuple[str, float]]) -> str:
    if not values:
        return "No signal yet"
    names = [name for name, _ in values[:2]]
    return " + ".join(names)


def display_range(value: str) -> str:
    return value.replace("_", " ").title()


def format_percentage(percentage: float) -> str:
    if percentage >= 99.95:
        return "100%"
    if percentage <= 0.05:
        return "0%"
    return f"{percentage:.1f}%"


def to_seconds(value: Any) -> float:
    if isinstance(value, bool) or value is None:
        return 0.0
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


def format_duration(seconds: float) -> str:
    total_minutes = max(0, round(seconds / 60))
    hours, minutes = divmod(total_minutes, 60)

    if hours and minutes:
        return f"{hours}h {minutes}m"
    if hours:
        return f"{hours}h"
    if minutes == 1:
        return "1m"
    return f"{minutes}m"


def xml(value: Any) -> str:
    return html.escape(str(value), quote=True)


if __name__ == "__main__":
    raise SystemExit(main())
