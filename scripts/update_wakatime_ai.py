#!/usr/bin/env python3
from __future__ import annotations

import base64
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
WAKATIME_RANGE = os.environ.get("WAKATIME_RANGE", "last_7_days")
WAKATIME_BASE_URL = os.environ.get(
    "WAKATIME_BASE_URL",
    "https://wakatime.com/api/v1/users/current",
)

DEFAULTS = {
    "AI_DASHBOARD_AI_CHANGES": "7.5K",
    "AI_DASHBOARD_TOKENS": "488.2M",
    "AI_DASHBOARD_INPUT_TOKENS": "486.7M in",
    "AI_DASHBOARD_OUTPUT_TOKENS": "1.6M out",
    "AI_DASHBOARD_TOP_AGENT": "Claude + Codex",
    "AI_DASHBOARD_MODEL_MIX": "Claude 63% · Codex 37%",
    "AI_DASHBOARD_SOURCE_LABEL": "configured rolling telemetry",
}

AI_FIELD_NAMES = (
    "ai_additions",
    "ai_deletions",
    "ai_line_changes_total",
    "ai_agent_line_changes",
    "ai_agent_breakdown",
    "ai_input_tokens",
    "ai_output_tokens",
)


def main() -> int:
    metrics = build_metrics()
    update_readme(render_section(metrics))
    print("AI telemetry section updated.")
    return 0


def build_metrics() -> dict[str, str]:
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


def build_fallback_metrics() -> dict[str, str]:
    return {
        "ai_changes": env_value("AI_DASHBOARD_AI_CHANGES"),
        "tokens": env_value("AI_DASHBOARD_TOKENS"),
        "token_split": f"{env_value('AI_DASHBOARD_INPUT_TOKENS')} · {env_value('AI_DASHBOARD_OUTPUT_TOKENS')}",
        "top_agent": env_value("AI_DASHBOARD_TOP_AGENT"),
        "model_mix": env_value("AI_DASHBOARD_MODEL_MIX"),
        "source_label": env_value("AI_DASHBOARD_SOURCE_LABEL"),
        "updated_at": utc_timestamp(),
    }


def build_wakatime_metrics(stats: dict[str, Any]) -> dict[str, str]:
    ai_lines = first_positive_number(
        stats.get("ai_line_changes_total"),
        number(stats.get("ai_additions")) + number(stats.get("ai_deletions")),
        sum_agent_lines(stats.get("ai_agent_breakdown")),
        sum_mapping(stats.get("ai_agent_line_changes")),
    )
    input_tokens = number(stats.get("ai_input_tokens"))
    output_tokens = number(stats.get("ai_output_tokens"))
    agents = normalize_agent_breakdown(stats)

    return {
        "ai_changes": format_compact(ai_lines),
        "tokens": format_compact(input_tokens + output_tokens),
        "token_split": f"{format_compact(input_tokens)} in · {format_compact(output_tokens)} out",
        "top_agent": top_agent_label(agents),
        "model_mix": agent_mix_label(agents),
        "source_label": f"WakaTime AI telemetry · {display_range(WAKATIME_RANGE)}",
        "updated_at": utc_timestamp(),
    }


def render_section(metrics: dict[str, str]) -> str:
    return "\n".join(
        [
            "**Rolling AI engineering telemetry**",
            "",
            "| Signal | Value | Context |",
            "| --- | ---: | --- |",
            f"| AI-authored changes | **{cell(metrics['ai_changes'])}** | Agent-generated line changes |",
            f"| Tokens processed | **{cell(metrics['tokens'])}** | {cell(metrics['token_split'])} |",
            f"| Agent stack | **{cell(metrics['top_agent'])}** | {cell(metrics['model_mix'])} |",
            "",
            f"<sub>Source: {cell(metrics['source_label'])} · refreshed daily at 06:00 UTC · updated: {cell(metrics['updated_at'])}</sub>",
        ]
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


def normalize_agent_breakdown(stats: dict[str, Any]) -> list[dict[str, float | str]]:
    raw_breakdown = stats.get("ai_agent_breakdown")
    agents: list[dict[str, float | str]] = []

    if isinstance(raw_breakdown, list):
        for item in raw_breakdown:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if isinstance(name, str) and name.strip():
                agents.append(
                    {
                        "name": name.strip(),
                        "lines": number(item.get("lines")),
                    }
                )

    if agents:
        return sorted(agents, key=lambda agent: float(agent["lines"]), reverse=True)

    line_changes = stats.get("ai_agent_line_changes")
    if isinstance(line_changes, dict):
        for name, lines in line_changes.items():
            agents.append({"name": str(name), "lines": number(lines)})

    return sorted(agents, key=lambda agent: float(agent["lines"]), reverse=True)


def top_agent_label(agents: list[dict[str, float | str]]) -> str:
    if not agents:
        return "No agent signal yet"
    return " + ".join(str(agent["name"]) for agent in agents[:2])


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


def display_range(value: str) -> str:
    return value.replace("_", " ").title()


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def cell(value: Any) -> str:
    return str(value).replace("\n", " ").replace("|", "\\|")


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


if __name__ == "__main__":
    raise SystemExit(main())
