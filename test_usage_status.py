"""Unit tests for usage_status bundle path helpers."""

from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

from usage_status import _assets_dir, _bundle_resource_root


class BundlePathTests(unittest.TestCase):
    def test_bundle_resource_root_uses_file_dir_in_dev(self):
        import usage_status

        path = _bundle_resource_root()
        self.assertEqual(path, os.path.dirname(os.path.abspath(usage_status.__file__)))

    def test_assets_dir_points_at_project_assets_in_dev(self):
        import usage_status

        assets = _assets_dir()
        self.assertTrue(os.path.isdir(assets))
        self.assertTrue(os.path.isfile(os.path.join(assets, "grok-menubar-18.png")))

    def test_assets_dir_uses_resourcepath_when_frozen(self):
        with mock.patch.object(sys, "frozen", True, create=True):
            with mock.patch.dict(os.environ, {"RESOURCEPATH": "/tmp/Usage Status.app/Contents/Resources"}):
                self.assertEqual(
                    _assets_dir(),
                    "/tmp/Usage Status.app/Contents/Resources/assets",
                )


if __name__ == "__main__":
    unittest.main()