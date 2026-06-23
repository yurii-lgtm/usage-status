"""Unit tests for AI usage fetch and formatting logic."""

from __future__ import annotations

import io
import json
import sys
import unittest
from datetime import datetime, timezone
from unittest import mock

from usage_logic import (
    Provider,
    UsageInfo,
    UsageStatus,
    discover_usage,
    fetch_claude_usage,
    fetch_codex_usage,
    fetch_grok_usage,
    format_reset_time,
    format_usage_list,
    format_usage_menu_title,
    launch_provider_login,
    load_grok_bearer_token,
    parse_claude_usage,
    parse_codex_rate_limits,
    parse_grok_billing,
    provider_login_command,
)


class GrokParsingTests(unittest.TestCase):
    def test_parse_grok_billing(self):
        payload = {
            "config": {
                "creditUsagePercent": 72.06,
                "billingPeriodEnd": "2026-07-01T00:00:00+00:00",
                "productUsage": [
                    {"product": "GrokBuild", "usagePercent": 60.965},
                    {"product": "Api", "usagePercent": 9.84},
                ],
            }
        }
        info = parse_grok_billing(payload)
        self.assertEqual(info.provider, Provider.GROK)
        self.assertEqual(info.status, UsageStatus.OK)
        self.assertAlmostEqual(info.used_percent, 72.1)
        self.assertAlmostEqual(info.remaining_percent, 27.9)
        self.assertEqual(len(info.limits), 2)
        build = next(limit for limit in info.limits if limit.name == "Build")
        self.assertAlmostEqual(build.used_percent, 61.0)

    def test_load_grok_bearer_token_from_dict_entry(self):
        auth = {
            "https://auth.x.ai::client": {
                "key": "token-abc",
            }
        }
        token = load_grok_bearer_token(
            reader=lambda _path: auth,
        )
        self.assertEqual(token, "token-abc")


class ClaudeParsingTests(unittest.TestCase):
    def test_parse_claude_usage_prefers_five_hour_window(self):
        payload = {
            "rate_limits": {
                "five_hour": {
                    "used_percentage": 42.0,
                    "resets_at": 1_700_000_000,
                },
                "seven_day": {
                    "used_percentage": 10.0,
                    "resets_at": 1_700_100_000,
                },
            }
        }
        info = parse_claude_usage(payload)
        self.assertEqual(info.provider, Provider.CLAUDE)
        self.assertEqual(info.status, UsageStatus.OK)
        self.assertAlmostEqual(info.used_percent, 42.0)
        self.assertAlmostEqual(info.remaining_percent, 58.0)
        self.assertEqual(len(info.limits), 2)


class CodexParsingTests(unittest.TestCase):
    def test_parse_codex_rate_limits(self):
        payload = {
            "rateLimits": [
                {
                    "limit_name": "default",
                    "remaining_percent": 35.0,
                    "resets_at": 1_700_000_000,
                }
            ]
        }
        info = parse_codex_rate_limits(payload)
        self.assertEqual(info.provider, Provider.CODEX)
        self.assertEqual(info.status, UsageStatus.OK)
        self.assertAlmostEqual(info.remaining_percent, 35.0)
        self.assertAlmostEqual(info.used_percent, 65.0)


class FetcherTests(unittest.TestCase):
    def test_fetch_grok_usage_requires_login_without_token(self):
        info = fetch_grok_usage(
            auth_path="/missing/auth.json",
            opener=mock.Mock(),
        )
        self.assertEqual(info.status, UsageStatus.LOGIN_REQUIRED)

    def test_fetch_grok_usage_parses_live_payload(self):
        payload = {
            "config": {
                "creditUsagePercent": 10.0,
                "billingPeriodEnd": "2026-07-01T00:00:00+00:00",
                "productUsage": [],
            }
        }

        def fake_opener(request, timeout=10.0):
            body = json.dumps(payload).encode("utf-8")

            class Response:
                def read(self):
                    return body

                def __enter__(self):
                    return self

                def __exit__(self, *_args):
                    return False

            return Response()

        with mock.patch(
            "usage_logic.load_grok_bearer_token",
            return_value="token",
        ):
            info = fetch_grok_usage(opener=fake_opener)
        self.assertEqual(info.status, UsageStatus.OK)
        self.assertAlmostEqual(info.remaining_percent, 90.0)

    def test_fetch_codex_usage_api_key_mode(self):
        info = fetch_codex_usage(
            auth_path="/tmp/auth.json",
            app_server=mock.Mock(),
        )
        with mock.patch("usage_logic.load_codex_auth_mode", return_value="apikey"):
            info = fetch_codex_usage(app_server=mock.Mock())
        self.assertEqual(info.status, UsageStatus.LOGIN_REQUIRED)
        self.assertIn("ChatGPT", info.message)

    def test_fetch_claude_usage_without_token(self):
        info = fetch_claude_usage(token_loader=lambda: None, opener=mock.Mock())
        self.assertEqual(info.status, UsageStatus.LOGIN_REQUIRED)

    def test_discover_usage_calls_all_providers(self):
        entries = discover_usage(
            grok_fetcher=lambda: UsageInfo(Provider.GROK, UsageStatus.OK, remaining_percent=50),
            codex_fetcher=lambda: UsageInfo(Provider.CODEX, UsageStatus.LOGIN_REQUIRED, message="login"),
            claude_fetcher=lambda: UsageInfo(Provider.CLAUDE, UsageStatus.ERROR, message="err"),
        )
        self.assertEqual([entry.provider for entry in entries], [
            Provider.GROK,
            Provider.CODEX,
            Provider.CLAUDE,
        ])


class FormattingTests(unittest.TestCase):
    def test_format_reset_time(self):
        now = datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc)
        reset = datetime(2026, 6, 23, 13, 30, tzinfo=timezone.utc)
        self.assertEqual(format_reset_time(reset, now=now), "in 1h")

    def test_format_usage_menu_title(self):
        info = UsageInfo(
            Provider.GROK,
            UsageStatus.OK,
            remaining_percent=28.0,
            reset_at=datetime(2026, 7, 1, 0, 0, tzinfo=timezone.utc),
        )
        title = format_usage_menu_title(info)
        self.assertIn("Grok", title)
        self.assertIn("28% left", title)

    def test_format_usage_list(self):
        entries = [
            UsageInfo(Provider.GROK, UsageStatus.OK, remaining_percent=25.0),
            UsageInfo(Provider.CODEX, UsageStatus.LOGIN_REQUIRED, message="login"),
        ]
        output = format_usage_list(entries)
        self.assertIn("provider\tstatus", output)
        self.assertIn("grok\tok", output)
        self.assertIn("codex\tlogin_required", output)


class ProviderLoginTests(unittest.TestCase):
    def test_provider_login_command(self):
        grok = provider_login_command(Provider.GROK)
        codex = provider_login_command(Provider.CODEX)
        claude = provider_login_command(Provider.CLAUDE)
        self.assertIsNotNone(grok)
        self.assertIsNotNone(codex)
        self.assertIsNotNone(claude)
        self.assertEqual(grok[-1], "login")
        self.assertEqual(codex[-1], "login")
        self.assertEqual(claude[-2:], ["auth", "login"])

    def test_launch_provider_login(self):
        with mock.patch(
            "usage_logic.provider_login_command",
            return_value=["/usr/bin/grok", "login"],
        ):
            with mock.patch("usage_logic._launch_terminal_script") as terminal:
                ok, message = launch_provider_login(Provider.GROK)
        self.assertTrue(ok)
        self.assertEqual(message, "")
        terminal.assert_called_once()
        launched = terminal.call_args.args[0]
        self.assertIn("grok", launched)
        self.assertIn("login", launched)

    def test_launch_provider_login_missing_cli(self):
        with mock.patch("usage_logic.provider_login_command", return_value=None):
            with mock.patch("usage_logic._launch_terminal_script") as terminal:
                ok, message = launch_provider_login(Provider.CLAUDE)
        self.assertFalse(ok)
        self.assertIn("Claude Code CLI", message)
        terminal.assert_called_once()


class CliTests(unittest.TestCase):
    def test_usage_status_list_mode(self):
        from usage_status import main

        fake_entries = [
            UsageInfo(Provider.GROK, UsageStatus.OK, remaining_percent=50.0),
            UsageInfo(Provider.CODEX, UsageStatus.LOGIN_REQUIRED, message="login"),
            UsageInfo(Provider.CLAUDE, UsageStatus.LOGIN_REQUIRED, message="login"),
        ]
        stdout = io.StringIO()
        with mock.patch("usage_status.discover_usage", return_value=fake_entries):
            with mock.patch.object(sys, "stdout", stdout):
                code = main(["--list"])
        self.assertEqual(code, 0)
        self.assertIn("grok\tok", stdout.getvalue())
        self.assertIn("codex\tlogin_required", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()