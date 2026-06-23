"""Fetch and normalize AI subscription usage for Grok, Codex, and Claude."""

from __future__ import annotations

import json
import os
import re
import select
import shlex
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable, Iterable, Mapping, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class Provider(str, Enum):
    GROK = "grok"
    CODEX = "codex"
    CLAUDE = "claude"


class UsageStatus(str, Enum):
    OK = "ok"
    LOGIN_REQUIRED = "login_required"
    ERROR = "error"


STATUS_COLORS = {
    UsageStatus.OK: "green",
    UsageStatus.LOGIN_REQUIRED: "yellow",
    UsageStatus.ERROR: "red",
}


@dataclass(frozen=True)
class UsageLimit:
    name: str
    used_percent: float
    remaining_percent: float
    reset_at: Optional[datetime] = None


@dataclass
class UsageInfo:
    provider: Provider
    status: UsageStatus
    used_percent: Optional[float] = None
    remaining_percent: Optional[float] = None
    reset_at: Optional[datetime] = None
    message: str = ""
    limits: list[UsageLimit] = field(default_factory=list)

    @property
    def status_color(self) -> str:
        if self.status != UsageStatus.OK:
            return STATUS_COLORS[self.status]
        if self.remaining_percent is None:
            return "yellow"
        if self.remaining_percent >= 50:
            return "green"
        if self.remaining_percent >= 20:
            return "yellow"
        return "red"

    @property
    def display_label(self) -> str:
        if self.status == UsageStatus.LOGIN_REQUIRED:
            return self.message or "Sign in required"
        if self.status == UsageStatus.ERROR:
            return self.message or "Unavailable"
        if self.remaining_percent is not None:
            return f"{self.remaining_percent:.0f}% left"
        if self.used_percent is not None:
            return f"{self.used_percent:.0f}% used"
        return "Unknown"


def default_grok_auth_path(home: Path | None = None) -> Path:
    return (home or Path.home()) / ".grok" / "auth.json"


def default_codex_auth_path(home: Path | None = None) -> Path:
    return (home or Path.home()) / ".codex" / "auth.json"


def default_claude_desktop_config_path(home: Path | None = None) -> Path:
    return (
        (home or Path.home())
        / "Library/Application Support/Claude/config.json"
    )


def default_codex_binary_path() -> str:
    return "/Applications/Codex.app/Contents/Resources/codex"


def _login_path() -> str:
    home = Path.home()
    parts = [
        str(home / ".grok/bin"),
        str(home / ".local/bin"),
        "/opt/homebrew/bin",
        "/usr/local/bin",
        "/usr/bin",
        "/bin",
    ]
    current = os.environ.get("PATH", "")
    if current:
        parts.append(current)
    return ":".join(parts)


def _find_executable(
    name: str,
    *,
    extra_candidates: tuple[str, ...] = (),
) -> Optional[str]:
    found = shutil.which(name, path=_login_path())
    if found:
        return found
    for candidate in extra_candidates:
        if os.path.isfile(candidate):
            return candidate
    return None


def default_grok_binary_path() -> str:
    found = _find_executable(
        "grok",
        extra_candidates=(
            str(Path.home() / ".grok/bin/grok"),
            "/opt/homebrew/bin/grok",
            "/usr/local/bin/grok",
        ),
    )
    return found or str(Path.home() / ".grok/bin/grok")


def default_claude_binary_path() -> str:
    found = _find_executable(
        "claude",
        extra_candidates=(
            str(Path.home() / ".local/bin/claude"),
            "/opt/homebrew/bin/claude",
            "/usr/local/bin/claude",
        ),
    )
    return found or "/opt/homebrew/bin/claude"


def provider_install_hint(provider: Provider) -> str:
    if provider == Provider.GROK:
        return (
            "Grok CLI not found. Install the Grok app or CLI so "
            f"{default_grok_binary_path()} exists, then run: grok login"
        )
    if provider == Provider.CODEX:
        return (
            "Codex not found. Install Codex.app from OpenAI, then run: codex login"
        )
    if provider == Provider.CLAUDE:
        return (
            "Claude Code CLI not found. Install with:\n"
            "  npm install -g @anthropic-ai/claude-code\n"
            "Then run: claude auth login\n"
            "\n"
            "Or sign in with the Claude Desktop app (Usage Status reads that session)."
        )
    return "Provider CLI not found."


def provider_login_command(provider: Provider) -> list[str] | None:
    if provider == Provider.GROK:
        binary = default_grok_binary_path()
        if not os.path.isfile(binary):
            return None
        return [binary, "login"]
    if provider == Provider.CODEX:
        binary = default_codex_binary_path()
        if not os.path.isfile(binary):
            return None
        return [binary, "login"]
    if provider == Provider.CLAUDE:
        binary = default_claude_binary_path()
        if not os.path.isfile(binary):
            return None
        return [binary, "auth", "login"]
    return None


def _escape_applescript_string(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _launch_terminal_script(shell_command: str) -> bool:
    escaped = _escape_applescript_string(shell_command)
    script = (
        'tell application "Terminal" to activate\n'
        f'tell application "Terminal" to do script "{escaped}"'
    )
    result = subprocess.run(
        ["osascript", "-e", script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def launch_provider_login(
    provider: Provider,
    *,
    terminal_launcher: Callable[[str], bool] | None = None,
) -> tuple[bool, str]:
    launch = terminal_launcher or _launch_terminal_script
    command = provider_login_command(provider)
    if not command:
        hint = provider_install_hint(provider)
        launch(f"printf '%s\\n\\n' {shlex.quote(hint)}")
        return False, hint

    path_prefix = f"export PATH={shlex.quote(_login_path())}; "
    login_command = path_prefix + " ".join(shlex.quote(part) for part in command)
    if not launch(login_command):
        return False, "Could not open Terminal for sign-in."
    return True, ""


def parse_iso_datetime(value: object) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_epoch_seconds(value: object) -> Optional[datetime]:
    if value is None:
        return None
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    if seconds > 1_000_000_000_000:
        seconds /= 1000.0
    return datetime.fromtimestamp(seconds, tz=timezone.utc)


def format_reset_time(value: Optional[datetime], *, now: Optional[datetime] = None) -> str:
    if value is None:
        return "unknown"
    current = now or datetime.now(timezone.utc)
    delta = value - current
    seconds = int(delta.total_seconds())
    if seconds <= 0:
        return "now"
    if seconds < 3600:
        minutes = max(1, seconds // 60)
        return f"in {minutes}m"
    if seconds < 86400:
        hours = max(1, seconds // 3600)
        return f"in {hours}h"
    days = max(1, seconds // 86400)
    return f"in {days}d"


def _round_percent(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return round(value, 1)


def format_reset_clock(value: Optional[datetime]) -> str:
    if value is None:
        return ""
    local = value.astimezone()
    return local.strftime("%b %-d, %-I:%M %p")


def read_json_file(path: str | Path) -> object:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_grok_bearer_token(
    auth_path: str | Path | None = None,
    *,
    reader: Callable[[str | Path], object] | None = None,
) -> Optional[str]:
    path = Path(auth_path) if auth_path is not None else default_grok_auth_path()
    read = reader or read_json_file
    try:
        data = read(path)
    except (OSError, json.JSONDecodeError):
        return None

    if isinstance(data, dict):
        if "key" in data and isinstance(data.get("key"), str):
            return data["key"]
        for entry in data.values():
            if isinstance(entry, dict) and isinstance(entry.get("key"), str):
                return entry["key"]
    return None


def parse_grok_billing(payload: Mapping[str, object]) -> UsageInfo:
    config = payload.get("config")
    if not isinstance(config, Mapping):
        return UsageInfo(
            provider=Provider.GROK,
            status=UsageStatus.ERROR,
            message="Unexpected Grok billing response",
        )

    used = config.get("creditUsagePercent")
    try:
        used_percent = float(used)
    except (TypeError, ValueError):
        return UsageInfo(
            provider=Provider.GROK,
            status=UsageStatus.ERROR,
            message="Missing Grok credit usage",
        )

    remaining_percent = _round_percent(max(0.0, min(100.0, 100.0 - used_percent)))
    used_percent = _round_percent(used_percent)
    reset_at = parse_iso_datetime(config.get("billingPeriodEnd"))
    if reset_at is None:
        current_period = config.get("currentPeriod")
        if isinstance(current_period, Mapping):
            reset_at = parse_iso_datetime(current_period.get("end"))

    limits: list[UsageLimit] = []
    product_usage = config.get("productUsage")
    if isinstance(product_usage, list):
        product_labels = {
            "GrokBuild": "Build",
            "Api": "API",
        }
        for entry in product_usage:
            if not isinstance(entry, Mapping):
                continue
            product = str(entry.get("product") or "Product")
            try:
                product_used = float(entry.get("usagePercent"))
            except (TypeError, ValueError):
                continue
            limits.append(
                UsageLimit(
                    name=product_labels.get(product, product),
                    used_percent=_round_percent(product_used) or 0.0,
                    remaining_percent=_round_percent(
                        max(0.0, 100.0 - product_used)
                    )
                    or 0.0,
                    reset_at=reset_at,
                )
            )

    return UsageInfo(
        provider=Provider.GROK,
        status=UsageStatus.OK,
        used_percent=used_percent,
        remaining_percent=remaining_percent,
        reset_at=reset_at,
        limits=limits,
    )


def parse_claude_usage(payload: Mapping[str, object]) -> UsageInfo:
    rate_limits = payload.get("rate_limits")
    if not isinstance(rate_limits, Mapping):
        rate_limits = payload
    if not isinstance(rate_limits, Mapping):
        return UsageInfo(
            provider=Provider.CLAUDE,
            status=UsageStatus.ERROR,
            message="Unexpected Claude usage response",
        )

    limits: list[UsageLimit] = []
    for key, label in (
        ("five_hour", "5-hour"),
        ("seven_day", "7-day"),
        ("seven_day_opus", "7-day Opus"),
        ("seven_day_sonnet", "7-day Sonnet"),
    ):
        entry = rate_limits.get(key)
        if not isinstance(entry, Mapping):
            continue
        try:
            used_percent = float(entry.get("used_percentage"))
        except (TypeError, ValueError):
            utilization = entry.get("utilization")
            try:
                used_percent = float(utilization) * 100.0
            except (TypeError, ValueError):
                continue
        limits.append(
            UsageLimit(
                name=label,
                used_percent=_round_percent(used_percent) or 0.0,
                remaining_percent=_round_percent(max(0.0, 100.0 - used_percent)) or 0.0,
                reset_at=parse_epoch_seconds(entry.get("resets_at")),
            )
        )

    if not limits:
        return UsageInfo(
            provider=Provider.CLAUDE,
            status=UsageStatus.ERROR,
            message="No Claude rate limits in response",
        )

    primary = limits[0]
    for candidate in limits:
        if candidate.name == "5-hour":
            primary = candidate
            break

    return UsageInfo(
        provider=Provider.CLAUDE,
        status=UsageStatus.OK,
        used_percent=primary.used_percent,
        remaining_percent=primary.remaining_percent,
        reset_at=primary.reset_at,
        limits=limits,
    )


def _pick_codex_limit(entries: Iterable[Mapping[str, object]]) -> Optional[UsageLimit]:
    best: Optional[UsageLimit] = None
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue

        name = str(
            entry.get("limit_name")
            or entry.get("limitName")
            or entry.get("name")
            or "Codex"
        )
        reset_at = parse_epoch_seconds(
            entry.get("resets_at")
            or entry.get("reset_at")
            or entry.get("resetAt")
        )

        remaining_percent = entry.get("remaining_percent")
        if remaining_percent is None:
            remaining_percent = entry.get("remainingPercent")
        try:
            remaining = float(remaining_percent)
            used_percent = max(0.0, min(100.0, 100.0 - remaining))
            limit = UsageLimit(
                name=name,
                used_percent=used_percent,
                remaining_percent=max(0.0, min(100.0, remaining)),
                reset_at=reset_at,
            )
        except (TypeError, ValueError):
            used = entry.get("usedPercent")
            if used is None:
                used = entry.get("used_percent")
            try:
                used_percent = float(used)
            except (TypeError, ValueError):
                primary = entry.get("primary")
                if isinstance(primary, Mapping):
                    nested = _pick_codex_limit([primary])
                    if nested is not None:
                        nested = UsageLimit(
                            name=name,
                            used_percent=nested.used_percent,
                            remaining_percent=nested.remaining_percent,
                            reset_at=nested.reset_at or reset_at,
                        )
                        limit = nested
                    else:
                        continue
                else:
                    continue
            else:
                limit = UsageLimit(
                    name=name,
                    used_percent=used_percent,
                    remaining_percent=max(0.0, 100.0 - used_percent),
                    reset_at=reset_at,
                )

        if best is None or limit.remaining_percent < best.remaining_percent:
            best = limit
    return best


def parse_codex_rate_limits(payload: Mapping[str, object]) -> UsageInfo:
    candidates: list[Mapping[str, object]] = []

    def _collect_limits(value: object) -> None:
        if isinstance(value, list):
            candidates.extend(item for item in value if isinstance(item, Mapping))
            return
        if not isinstance(value, Mapping):
            return

        windows = (
            ("5-hour", value.get("primary")),
            ("weekly", value.get("secondary")),
        )
        if any(isinstance(window, Mapping) for _, window in windows):
            base_name = str(
                value.get("limitName") or value.get("limitId") or "Codex"
            )
            for label, window in windows:
                if not isinstance(window, Mapping):
                    continue
                candidates.append(
                    {
                        "name": f"{base_name} {label}",
                        "usedPercent": window.get("usedPercent"),
                        "resetAt": window.get("resetsAt"),
                    }
                )
            return

        candidates.append(value)

    for key in ("rateLimits", "rate_limits", "limits"):
        _collect_limits(payload.get(key))

    if not candidates:
        result = payload.get("result")
        if isinstance(result, Mapping):
            for key in ("rateLimits", "rate_limits", "limits"):
                _collect_limits(result.get(key))

    if not candidates and any(
        key in payload for key in ("remaining_percent", "usedPercent", "used_percent")
    ):
        candidates = [payload]

    primary = _pick_codex_limit(candidates)
    if primary is None:
        return UsageInfo(
            provider=Provider.CODEX,
            status=UsageStatus.ERROR,
            message="No Codex limits in response",
        )

    limits = []
    for entry in candidates:
        picked = _pick_codex_limit([entry])
        if picked is not None:
            limits.append(picked)

    return UsageInfo(
        provider=Provider.CODEX,
        status=UsageStatus.OK,
        used_percent=primary.used_percent,
        remaining_percent=primary.remaining_percent,
        reset_at=primary.reset_at,
        limits=limits or [primary],
    )


def http_get_json(
    url: str,
    *,
    headers: Optional[Mapping[str, str]] = None,
    opener: Callable[..., object] | None = None,
    timeout: float = 10.0,
) -> object:
    request = Request(url, headers=dict(headers or {}))
    open_fn = opener or urlopen
    with open_fn(request, timeout=timeout) as response:
        body = response.read().decode("utf-8")
    return json.loads(body)


def fetch_grok_usage(
    *,
    auth_path: str | Path | None = None,
    opener: Callable[..., object] | None = None,
) -> UsageInfo:
    token = load_grok_bearer_token(auth_path)
    if not token:
        return UsageInfo(
            provider=Provider.GROK,
            status=UsageStatus.LOGIN_REQUIRED,
            message="Run grok login",
        )

    url = "https://cli-chat-proxy.grok.com/v1/billing?format=credits"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        payload = http_get_json(url, headers=headers, opener=opener)
    except HTTPError as exc:
        if exc.code in {401, 403}:
            return UsageInfo(
                provider=Provider.GROK,
                status=UsageStatus.LOGIN_REQUIRED,
                message="Grok session expired",
            )
        return UsageInfo(
            provider=Provider.GROK,
            status=UsageStatus.ERROR,
            message=f"Grok billing HTTP {exc.code}",
        )
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        return UsageInfo(
            provider=Provider.GROK,
            status=UsageStatus.ERROR,
            message=f"Grok billing failed: {exc}",
        )

    if not isinstance(payload, Mapping):
        return UsageInfo(
            provider=Provider.GROK,
            status=UsageStatus.ERROR,
            message="Unexpected Grok billing payload",
        )
    if "error" in payload:
        return UsageInfo(
            provider=Provider.GROK,
            status=UsageStatus.LOGIN_REQUIRED,
            message="Grok login required",
        )
    return parse_grok_billing(payload)


def load_claude_code_access_token() -> Optional[str]:
    try:
        raw = subprocess.check_output(
            [
                "security",
                "find-generic-password",
                "-s",
                "Claude Code-credentials",
                "-w",
            ],
            text=True,
        ).strip()
        data = json.loads(raw)
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError):
        return None

    if not isinstance(data, Mapping):
        return None

    oauth = data.get("claudeAiOauth")
    if isinstance(oauth, Mapping):
        token = oauth.get("accessToken")
        if isinstance(token, str) and token.strip():
            return token.strip()
    return None


def load_claude_access_token(
    *,
    env: Mapping[str, str] | None = None,
    config_path: str | Path | None = None,
) -> Optional[str]:
    environment = env if env is not None else os.environ
    explicit = environment.get("CLAUDE_CODE_OAUTH_TOKEN")
    if explicit:
        return explicit

    cli_token = load_claude_code_access_token()
    if cli_token:
        return cli_token

    path = (
        Path(config_path)
        if config_path is not None
        else default_claude_desktop_config_path()
    )
    try:
        data = read_json_file(path)
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(data, Mapping):
        return None

    token_cache = data.get("oauth:tokenCache")
    if not isinstance(token_cache, str) or not token_cache.strip():
        return None

    decrypted = decrypt_electron_safe_storage(token_cache, service_name="Claude Safe Storage")
    if not decrypted:
        return None

    try:
        parsed = json.loads(decrypted)
    except json.JSONDecodeError:
        return None

    if isinstance(parsed, Mapping):
        for key in ("accessToken", "access_token", "token"):
            value = parsed.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def decrypt_electron_safe_storage(
    encrypted_b64: str,
    *,
    service_name: str,
    password_fetcher: Callable[[str], str] | None = None,
) -> Optional[str]:
    try:
        import base64
        import hashlib
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except ImportError:
        return None

    try:
        blob = base64.b64decode(encrypted_b64)
    except (ValueError, TypeError):
        return None

    if len(blob) < 35 or not blob.startswith(b"v10"):
        return None

    fetch = password_fetcher or _read_keychain_password
    try:
        password = fetch(service_name).encode()
    except (OSError, subprocess.CalledProcessError):
        return None

    salt = blob[3:19]
    iv = blob[19:35]
    ciphertext = blob[35:]
    key = hashlib.pbkdf2_hmac("sha1", password, salt, 1003, dklen=16)
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    decryptor = cipher.decryptor()
    plain_padded = decryptor.update(ciphertext) + decryptor.finalize()
    pad = plain_padded[-1]
    if pad < 1 or pad > 16 or plain_padded[-pad:] != bytes([pad]) * pad:
        return None
    return plain_padded[:-pad].decode("utf-8")


def _read_keychain_password(service_name: str) -> str:
    for account in (service_name.split()[0], "Claude", "Chromium"):
        try:
            return subprocess.check_output(
                [
                    "security",
                    "find-generic-password",
                    "-s",
                    service_name,
                    "-a",
                    account,
                    "-w",
                ],
                text=True,
            ).strip()
        except subprocess.CalledProcessError:
            continue
    return subprocess.check_output(
        ["security", "find-generic-password", "-s", service_name, "-w"],
        text=True,
    ).strip()


def fetch_claude_usage(
    *,
    token_loader: Callable[[], Optional[str]] | None = None,
    opener: Callable[..., object] | None = None,
) -> UsageInfo:
    loader = token_loader or load_claude_access_token
    token = loader()
    if not token:
        return UsageInfo(
            provider=Provider.CLAUDE,
            status=UsageStatus.LOGIN_REQUIRED,
            message="Run claude auth login or use Claude Desktop",
        )

    url = "https://api.anthropic.com/api/oauth/usage"
    headers = {
        "Authorization": f"Bearer {token}",
        "anthropic-beta": "oauth-2025-04-20",
        "User-Agent": "usage-status-tool/1.0",
    }
    try:
        payload = http_get_json(url, headers=headers, opener=opener)
    except HTTPError as exc:
        if exc.code in {401, 403}:
            return UsageInfo(
                provider=Provider.CLAUDE,
                status=UsageStatus.LOGIN_REQUIRED,
                message="Claude session expired",
            )
        return UsageInfo(
            provider=Provider.CLAUDE,
            status=UsageStatus.ERROR,
            message=f"Claude usage HTTP {exc.code}",
        )
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        return UsageInfo(
            provider=Provider.CLAUDE,
            status=UsageStatus.ERROR,
            message=f"Claude usage failed: {exc}",
        )

    if not isinstance(payload, Mapping):
        return UsageInfo(
            provider=Provider.CLAUDE,
            status=UsageStatus.ERROR,
            message="Unexpected Claude usage payload",
        )
    return parse_claude_usage(payload)


def load_codex_auth_mode(
    auth_path: str | Path | None = None,
    *,
    reader: Callable[[str | Path], object] | None = None,
) -> Optional[str]:
    path = Path(auth_path) if auth_path is not None else default_codex_auth_path()
    read = reader or read_json_file
    try:
        data = read(path)
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(data, Mapping):
        mode = data.get("auth_mode")
        if isinstance(mode, str):
            return mode
    return None


def _codex_app_server_exchange(
    method: str,
    *,
    codex_binary: str,
    timeout: float = 8.0,
) -> object:
    proc = subprocess.Popen(
        [codex_binary, "app-server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    assert proc.stdin is not None
    assert proc.stdout is not None

    def send(message: Mapping[str, object]) -> None:
        proc.stdin.write(json.dumps(message) + "\n")
        proc.stdin.flush()

    def read_response(request_id: int) -> Optional[Mapping[str, object]]:
        deadline = datetime.now(timezone.utc).timestamp() + timeout
        while datetime.now(timezone.utc).timestamp() < deadline:
            wait = max(0.1, deadline - datetime.now(timezone.utc).timestamp())
            ready, _, _ = select.select([proc.stdout], [], [], wait)
            if not ready:
                break
            line = proc.stdout.readline()
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, Mapping):
                continue
            if payload.get("id") == request_id:
                return payload
        return None

    send(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "clientInfo": {"name": "usage-status", "version": "1.0"},
                "capabilities": {},
            },
        }
    )
    read_response(1)
    send({"jsonrpc": "2.0", "method": "initialized", "params": {}})

    request_id = 2
    send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": {}})
    response = read_response(request_id)
    proc.terminate()
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()
    return response or {}


def fetch_codex_usage(
    *,
    auth_path: str | Path | None = None,
    codex_binary: str | None = None,
    app_server: Callable[[str], object] | None = None,
) -> UsageInfo:
    auth_mode = load_codex_auth_mode(auth_path)
    if auth_mode == "apikey":
        return UsageInfo(
            provider=Provider.CODEX,
            status=UsageStatus.LOGIN_REQUIRED,
            message="Sign in with ChatGPT in Codex",
        )

    binary = codex_binary or default_codex_binary_path()
    if not os.path.isfile(binary):
        return UsageInfo(
            provider=Provider.CODEX,
            status=UsageStatus.ERROR,
            message="Codex app not found",
        )

    exchange = app_server or (lambda method: _codex_app_server_exchange(method, codex_binary=binary))
    try:
        response = exchange("account/rateLimits/read")
    except OSError as exc:
        return UsageInfo(
            provider=Provider.CODEX,
            status=UsageStatus.ERROR,
            message=f"Codex app-server failed: {exc}",
        )

    if not isinstance(response, Mapping):
        return UsageInfo(
            provider=Provider.CODEX,
            status=UsageStatus.ERROR,
            message="Invalid Codex app-server response",
        )

    error = response.get("error")
    if isinstance(error, Mapping):
        message = str(error.get("message") or "Codex usage unavailable")
        if "chatgpt authentication required" in message.lower():
            return UsageInfo(
                provider=Provider.CODEX,
                status=UsageStatus.LOGIN_REQUIRED,
                message="Sign in with ChatGPT in Codex",
            )
        return UsageInfo(
            provider=Provider.CODEX,
            status=UsageStatus.ERROR,
            message=message,
        )

    result = response.get("result")
    if isinstance(result, Mapping):
        return parse_codex_rate_limits(result)
    return parse_codex_rate_limits(response)


def discover_usage(
    *,
    grok_fetcher: Callable[[], UsageInfo] = fetch_grok_usage,
    codex_fetcher: Callable[[], UsageInfo] = fetch_codex_usage,
    claude_fetcher: Callable[[], UsageInfo] = fetch_claude_usage,
) -> list[UsageInfo]:
    return [
        grok_fetcher(),
        codex_fetcher(),
        claude_fetcher(),
    ]


def _provider_title(provider: Provider) -> str:
    return {
        Provider.GROK: "SuperGrok",
        Provider.CODEX: "Codex",
        Provider.CLAUDE: "Claude",
    }[provider]


def format_usage_line(info: UsageInfo) -> str:
    reset = format_reset_time(info.reset_at)
    reset_clock = format_reset_clock(info.reset_at)
    limits = ";".join(
        f"{limit.name}:{limit.remaining_percent:.0f}%"
        for limit in info.limits
    )
    return (
        f"{info.provider.value}\t{info.status.value}\t{info.status_color}\t"
        f"{info.used_percent if info.used_percent is not None else ''}\t"
        f"{info.remaining_percent if info.remaining_percent is not None else ''}\t"
        f"{reset}\t{reset_clock}\t{info.message}\t{limits}"
    )


def format_usage_list(entries: Iterable[UsageInfo]) -> str:
    lines = [
        "provider\tstatus\tcolor\tused_percent\tremaining_percent\t"
        "reset_in\treset_at\tmessage\tlimits"
    ]
    lines.extend(format_usage_line(entry) for entry in entries)
    return "\n".join(lines) + "\n"


def format_usage_menu_title(info: UsageInfo) -> str:
    title = _provider_title(info.provider)
    if info.status != UsageStatus.OK:
        return f"{title}: {info.display_label}"
    reset = format_reset_time(info.reset_at)
    return f"{title}: {info.display_label} · resets {reset}"


def format_usage_detail(info: UsageInfo) -> str:
    if info.status != UsageStatus.OK:
        return info.display_label
    lines = [f"{info.display_label}"]
    if info.reset_at is not None:
        lines.append(f"Resets {format_reset_clock(info.reset_at)}")
    for limit in info.limits:
        lines.append(
            f"{limit.name}: {limit.remaining_percent:.0f}% left "
            f"({format_reset_time(limit.reset_at)})"
        )
    return "\n".join(lines)