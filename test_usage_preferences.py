"""Unit tests for menu bar display preferences."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from usage_logic import Provider
from usage_preferences import (
    load_display_preferences,
    normalize_enabled_providers,
    save_display_preferences,
)


class DisplayPreferenceTests(unittest.TestCase):
    def test_normalize_defaults_to_all_providers(self):
        self.assertEqual(normalize_enabled_providers(None), set(Provider))
        self.assertEqual(normalize_enabled_providers(["grok", "bad"]), {Provider.GROK})

    def test_round_trip_preferences(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            enabled = {Provider.GROK, Provider.CLAUDE}
            save_display_preferences(enabled, path)
            loaded = load_display_preferences(path)
            self.assertEqual(loaded, enabled)
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["enabled_providers"], ["grok", "claude"])


if __name__ == "__main__":
    unittest.main()