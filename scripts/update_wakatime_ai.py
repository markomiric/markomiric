#!/usr/bin/env python3
from __future__ import annotations

import base64
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
    section = render_section(stats)
    update_readme(section)
    print("README WakaTime section updated.")
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


def render_section(stats: dict[str, Any]) -> str:
    total_seconds = to_seconds(stats.get("total_seconds"))
    human_total = stats.get("human_readable_total") or format_duration(total_seconds)
    best = best_ai_match(stats)
    updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        "<!-- Updated automatically by scripts/update_wakatime_ai.py -->",
        f"- WakaTime range: `{WAKATIME_RANGE.replace('_', ' ')}`",
        f"- Total tracked: **{human_total}**",
    ]

    if best["seconds"] > 0 and total_seconds > 0:
        percentage = best["seconds"] / total_seconds * 100
        lines.append(
            "- AI/tooling signal: "
            f"**{format_duration(best['seconds'])}** ({percentage:.1f}%) "
            f"from WakaTime `{best['dimension']}` entries matched by keyword"
        )
        lines.append(f"- Matching signals: {format_matches(best['matches'])}")
    else:
        lines.append("- AI/tooling signal: no keyword-matched WakaTime entries in this range")
        lines.append(f"- Matching keywords: `{', '.join(AI_KEYWORDS)}`")

    lines.append(f"- Last updated: {updated_at}")
    return "\n".join(lines)


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


def format_matches(matches: list[tuple[str, float]]) -> str:
    if not matches:
        return "none"
    top_matches = matches[:5]
    return ", ".join(
        f"`{name}` ({format_duration(seconds)})" for name, seconds in top_matches
    )


def update_readme(section: str) -> None:
    readme = README_PATH.read_text(encoding="utf-8")
    if START_MARKER not in readme or END_MARKER not in readme:
        raise RuntimeError(
            f"README must contain both {START_MARKER} and {END_MARKER} markers."
        )

    before, remainder = readme.split(START_MARKER, 1)
    _, after = remainder.split(END_MARKER, 1)
    updated = f"{before}{START_MARKER}\n{section}\n{END_MARKER}{after}"
    README_PATH.write_text(updated, encoding="utf-8")


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
        return f"{hours} hrs {minutes} mins"
    if hours:
        return f"{hours} hrs"
    if minutes == 1:
        return "1 min"
    return f"{minutes} mins"


if __name__ == "__main__":
    raise SystemExit(main())
