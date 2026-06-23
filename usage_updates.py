"""Check GitHub releases for newer Usage Status builds."""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from typing import Callable, Mapping, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

APP_VERSION = "1.0.2"
GITHUB_REPO = "yurii-lgtm/usage-status"
RELEASES_LATEST_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
USER_AGENT = f"usage-status/{APP_VERSION}"


@dataclass(frozen=True)
class UpdateCheckResult:
    current_version: str
    latest_version: Optional[str] = None
    update_available: bool = False
    release_url: str = ""
    download_url: str = ""
    error: str = ""


def normalize_version(version: str) -> tuple[int, ...]:
    text = version.strip().lstrip("vV")
    parts = re.split(r"[.+-]", text)
    numbers: list[int] = []
    for part in parts:
        if not part:
            continue
        match = re.match(r"(\d+)", part)
        if match is None:
            break
        numbers.append(int(match.group(1)))
    return tuple(numbers or (0,))


def is_newer_version(current: str, latest: str) -> bool:
    return normalize_version(latest) > normalize_version(current)


def current_app_version() -> str:
    if getattr(sys, "frozen", False):
        try:
            from Foundation import NSBundle

            info = NSBundle.mainBundle().infoDictionary() or {}
            short = info.get("CFBundleShortVersionString")
            if isinstance(short, str) and short.strip():
                return short.strip()
        except Exception:
            pass
    return APP_VERSION


def parse_latest_release(payload: Mapping[str, object]) -> tuple[str, str, str]:
    tag_name = payload.get("tag_name")
    html_url = payload.get("html_url")
    if not isinstance(tag_name, str) or not tag_name.strip():
        raise ValueError("Missing release tag")
    if not isinstance(html_url, str) or not html_url.strip():
        raise ValueError("Missing release URL")

    latest_version = tag_name.strip().lstrip("vV")
    release_url = html_url.strip()
    download_url = release_url

    assets = payload.get("assets")
    if isinstance(assets, list):
        for asset in assets:
            if not isinstance(asset, Mapping):
                continue
            name = asset.get("name")
            browser_url = asset.get("browser_download_url")
            if (
                isinstance(name, str)
                and name.endswith(".dmg")
                and isinstance(browser_url, str)
                and browser_url.strip()
            ):
                download_url = browser_url.strip()
                break

    return latest_version, release_url, download_url


def fetch_latest_release(
    *,
    opener: Callable[..., object] | None = None,
    url: str = RELEASES_LATEST_URL,
) -> Mapping[str, object]:
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
        },
    )
    open_url = opener or urlopen
    with open_url(request, timeout=12) as response:
        payload = json.load(response)
    if not isinstance(payload, Mapping):
        raise ValueError("Unexpected GitHub release payload")
    return payload


def check_for_updates(
    *,
    current_version: str | None = None,
    opener: Callable[..., object] | None = None,
) -> UpdateCheckResult:
    current = current_version or current_app_version()
    try:
        payload = fetch_latest_release(opener=opener)
        latest_version, release_url, download_url = parse_latest_release(payload)
    except HTTPError as exc:
        return UpdateCheckResult(
            current_version=current,
            error=f"Update check failed (HTTP {exc.code})",
        )
    except (URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        return UpdateCheckResult(
            current_version=current,
            error=f"Update check failed: {exc}",
        )

    return UpdateCheckResult(
        current_version=current,
        latest_version=latest_version,
        update_available=is_newer_version(current, latest_version),
        release_url=release_url,
        download_url=download_url,
    )