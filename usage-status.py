#!/usr/bin/env python3
"""Py2app entry point; executable name matches CFBundleExecutable."""

from usage_status import main

if __name__ == "__main__":
    raise SystemExit(main())