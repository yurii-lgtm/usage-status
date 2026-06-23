"""Tests for GitHub release update checks."""

from __future__ import annotations

import io
import json
import unittest
from unittest import mock

from usage_updates import (
    UpdateCheckResult,
    check_for_updates,
    is_newer_version,
    normalize_version,
    parse_latest_release,
)


class VersionParsingTests(unittest.TestCase):
    def test_normalize_version(self):
        self.assertEqual(normalize_version("v1.0.2"), (1, 0, 2))
        self.assertEqual(normalize_version("2.10.0"), (2, 10, 0))

    def test_is_newer_version(self):
        self.assertTrue(is_newer_version("1.0.1", "1.0.2"))
        self.assertFalse(is_newer_version("1.0.2", "1.0.2"))
        self.assertFalse(is_newer_version("1.1.0", "1.0.9"))


class ReleaseParsingTests(unittest.TestCase):
    def test_parse_latest_release_prefers_dmg_asset(self):
        payload = {
            "tag_name": "v1.0.2",
            "html_url": "https://github.com/yurii-lgtm/usage-status/releases/tag/v1.0.2",
            "assets": [
                {
                    "name": "Usage-Status.dmg",
                    "browser_download_url": "https://example.com/Usage-Status.dmg",
                }
            ],
        }
        latest, release_url, download_url = parse_latest_release(payload)
        self.assertEqual(latest, "1.0.2")
        self.assertIn("releases/tag", release_url)
        self.assertEqual(download_url, "https://example.com/Usage-Status.dmg")


class UpdateCheckTests(unittest.TestCase):
    def test_check_for_updates_when_current(self):
        payload = {
            "tag_name": "v1.0.2",
            "html_url": "https://github.com/yurii-lgtm/usage-status/releases/latest",
            "assets": [],
        }

        def fake_opener(_request, timeout=12):
            return io.BytesIO(json.dumps(payload).encode("utf-8"))

        result = check_for_updates(current_version="1.0.2", opener=fake_opener)
        self.assertIsInstance(result, UpdateCheckResult)
        self.assertFalse(result.update_available)
        self.assertEqual(result.latest_version, "1.0.2")
        self.assertEqual(result.error, "")

    def test_check_for_updates_when_outdated(self):
        payload = {
            "tag_name": "v1.0.3",
            "html_url": "https://github.com/yurii-lgtm/usage-status/releases/latest",
            "assets": [
                {
                    "name": "Usage-Status.dmg",
                    "browser_download_url": "https://example.com/Usage-Status.dmg",
                }
            ],
        }

        def fake_opener(_request, timeout=12):
            return io.BytesIO(json.dumps(payload).encode("utf-8"))

        result = check_for_updates(current_version="1.0.1", opener=fake_opener)
        self.assertTrue(result.update_available)
        self.assertEqual(result.download_url, "https://example.com/Usage-Status.dmg")

    def test_check_for_updates_handles_network_error(self):
        def fake_opener(_request, timeout=12):
            raise TimeoutError("timed out")

        result = check_for_updates(current_version="1.0.0", opener=fake_opener)
        self.assertIn("Update check failed", result.error)


if __name__ == "__main__":
    unittest.main()