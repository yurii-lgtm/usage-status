"""Persist which AI usage providers appear in the menu bar."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from usage_logic import Provider

PROVIDER_ORDER = (Provider.GROK, Provider.CODEX, Provider.CLAUDE)


def default_settings_path(home: Path | None = None) -> Path:
    root = (home or Path.home()) / "Library/Application Support/com.bot.usage-status"
    return root / "settings.json"


def normalize_enabled_providers(values: object) -> set[Provider]:
    if not isinstance(values, list):
        return set(PROVIDER_ORDER)

    enabled: set[Provider] = set()
    for raw in values:
        try:
            enabled.add(Provider(str(raw)))
        except ValueError:
            continue
    return enabled


def load_display_preferences(
    path: str | Path | None = None,
    *,
    reader: Callable[[], str] | None = None,
) -> set[Provider]:
    settings_path = Path(path) if path is not None else default_settings_path()
    read = reader or settings_path.read_text
    try:
        payload = json.loads(read())
    except (OSError, json.JSONDecodeError):
        return set(PROVIDER_ORDER)

    if not isinstance(payload, dict):
        return set(PROVIDER_ORDER)
    return normalize_enabled_providers(payload.get("enabled_providers"))


def save_display_preferences(
    enabled: set[Provider],
    path: str | Path | None = None,
    *,
    writer: Callable[[str], None] | None = None,
) -> None:
    settings_path = Path(path) if path is not None else default_settings_path()
    ordered = [provider.value for provider in PROVIDER_ORDER if provider in enabled]
    payload = {"enabled_providers": ordered}
    text = json.dumps(payload, indent=2) + "\n"

    if writer is not None:
        writer(text)
        return

    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(text, encoding="utf-8")