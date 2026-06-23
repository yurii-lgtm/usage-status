"""Unit tests for usage_status bundle path helpers."""

from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

from usage_updates import UpdateCheckResult

from usage_status import (
    UpdateActionHandler,
    _acquire_single_instance,
    _assets_dir,
    _bundle_resource_root,
)


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


    def test_single_instance_lock_prevents_second_copy(self):
        import usage_status

        lock_path = usage_status._instance_lock_path()
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        if lock_path.exists():
            lock_path.unlink()
        try:
            self.assertTrue(_acquire_single_instance())
            self.assertFalse(_acquire_single_instance())
        finally:
            lock_path.unlink(missing_ok=True)


class UpdateHandlerTests(unittest.TestCase):
    def test_present_update_result_selector_is_valid(self):
        handler = UpdateActionHandler()
        result = UpdateCheckResult(current_version="1.0.0", latest_version="1.0.0")
        with mock.patch("usage_status._present_update_alert") as present:
            handler.performSelectorOnMainThread_withObject_waitUntilDone_(
                "presentUpdateResult:",
                result,
                True,
            )
            present.assert_called_once_with(result)

if __name__ == "__main__":
    unittest.main()