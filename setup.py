"""Build a standalone Usage Status.app with py2app."""

from setuptools import setup

APP = ["usage-status.py"]
DATA_FILES = []
OPTIONS = {
    "argv_emulation": False,
    "iconfile": "assets/UsageStatus.icns",
    "plist": {
        "CFBundleName": "Usage Status",
        "CFBundleDisplayName": "Usage Status",
        "CFBundleGetInfoString": "Grok, Codex, and Claude usage in your menu bar",
        "CFBundleIdentifier": "com.bot.usage-status",
        "CFBundleVersion": "1.0.4",
        "CFBundleShortVersionString": "1.0.4",
        "LSMinimumSystemVersion": "13.0",
        "LSUIElement": True,
        "NSHighResolutionCapable": True,
    },
    "packages": [
        "usage_logic",
        "usage_preferences",
        "usage_updates",
        "objc",
        "cryptography",
    ],
    "includes": ["AppKit", "Foundation"],
    "resources": ["assets"],
    "site_packages": False,
    "excludes": [
        "numpy",
        "matplotlib",
        "pandas",
        "scipy",
        "PIL",
        "test",
        "setuptools",
        "pip",
        "wheel",
        "black",
    ],
}

setup(
    name="Usage Status",
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)