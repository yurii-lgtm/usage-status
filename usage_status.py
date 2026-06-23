#!/usr/bin/env python3
"""macOS menu bar indicator for Grok, Codex, and Claude subscription usage."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

from usage_logic import (
    Provider,
    UsageInfo,
    UsageStatus,
    _provider_title,
    discover_usage,
    format_reset_clock,
    format_reset_time,
    format_usage_detail,
    format_usage_list,
    format_usage_menu_title,
    launch_provider_login,
)
from usage_preferences import (
    load_display_preferences,
    save_display_preferences,
)

REFRESH_INTERVAL_SECONDS = 60.0


def _bundle_resource_root() -> str:
    if getattr(sys, "frozen", False):
        return os.environ.get("RESOURCEPATH", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _assets_dir() -> str:
    return os.path.join(_bundle_resource_root(), "assets")


_TOOL_DIR = _bundle_resource_root()
_ASSETS_DIR = _assets_dir()
_GROK_ICON_PATH = os.path.join(_ASSETS_DIR, "grok-rgb.png")
_GROK_MENU_ICON_PATH = os.path.join(_ASSETS_DIR, "grok-menu.png")
_GROK_MENUBAR_ICON_PATH = os.path.join(_ASSETS_DIR, "grok-menubar-18.png")

MENUBAR_ICON_PATHS = {
    Provider.GROK: _GROK_MENUBAR_ICON_PATH,
    Provider.CODEX: os.path.join(_ASSETS_DIR, "codex-menubar-18.png"),
    Provider.CLAUDE: os.path.join(_ASSETS_DIR, "claude-menubar-18.png"),
}

LEGACY_AUTOSAVE_NAMES = (
    "com.bot.usage-status",
    "com.bot.usage-status.grok",
    "com.bot.usage-status.codex",
    "com.bot.usage-status.claude",
    "com.bot.usage-status.v2",
    "com.bot.usage-status.v2.grok",
    "com.bot.usage-status.v2.codex",
    "com.bot.usage-status.v2.claude",
    "com.bot.usage-status.v3.settings",
)

PROVIDER_AUTOSAVE_NAMES = {
    Provider.GROK: "com.bot.usage-status.v3.grok",
    Provider.CODEX: "com.bot.usage-status.v3.codex",
    Provider.CLAUDE: "com.bot.usage-status.v3.claude",
}

PROVIDER_ORDER = (Provider.GROK, Provider.CODEX, Provider.CLAUDE)

# New items land left of existing ones: create Claude first, Grok last.
MENU_BAR_CREATE_ORDER = (Provider.CLAUDE, Provider.CODEX, Provider.GROK)

MENU_BAR_ICON_SIZE = 18.0
MENU_ICON_SIZE = 20.0
HUD_ICON_SIZE = 18.0

ICON_PATHS = {
    Provider.CODEX: (
        "/Applications/Codex.app/Contents/Resources/app.icns",
        os.path.expanduser("~/Applications/Codex.app/Contents/Resources/app.icns"),
    ),
    Provider.CLAUDE: (
        "/Applications/Claude.app/Contents/Resources/electron.icns",
        os.path.expanduser("~/Applications/Claude.app/Contents/Resources/electron.icns"),
    ),
    Provider.GROK: (
        _GROK_ICON_PATH,
        os.path.join(_ASSETS_DIR, "grok.png"),
        os.path.expanduser("~/.grok/icon.png"),
        "/Applications/Grok.app/Contents/Resources/app.icns",
        os.path.expanduser("~/Applications/Grok.app/Contents/Resources/app.icns"),
    ),
}


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AI usage menu bar tool")
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print usage for Grok, Codex, and Claude and exit",
    )
    parser.add_argument(
        "--probe",
        action="store_true",
        help="Initialize menu bar status items, log readiness, and exit",
    )
    parser.add_argument(
        "--no-hud",
        action="store_true",
        help="Hide the floating usage panel (menu bar only)",
    )
    return parser


def run_list_mode() -> int:
    entries = discover_usage()
    sys.stdout.write(format_usage_list(entries))
    return 0


def run_probe_mode() -> int:
    from AppKit import NSStatusBar, NSVariableStatusItemLength

    entries = discover_usage()
    status_bar = NSStatusBar.systemStatusBar()
    for _provider in PROVIDER_ORDER:
        status_item = status_bar.statusItemWithLength_(NSVariableStatusItemLength)
        if status_item is None:
            print("usage-status: failed to create NSStatusItem", file=sys.stderr, flush=True)
            return 1
    print(
        f"usage-status: probe ready providers={len(entries)}",
        file=sys.stderr,
        flush=True,
    )
    print("usage-status: probe complete", file=sys.stderr, flush=True)
    return 0


def _ns_rect(x: float, y: float, width: float, height: float):
    return ((x, y), (width, height))


def _color_ns_color(name: str):
    from AppKit import NSColor

    colors = {
        "green": NSColor.systemGreenColor(),
        "yellow": NSColor.systemYellowColor(),
        "red": NSColor.systemRedColor(),
        "black": NSColor.blackColor(),
        "orange": NSColor.systemOrangeColor(),
        "blue": NSColor.systemBlueColor(),
    }
    return colors.get(name, NSColor.secondaryLabelColor())


def _status_dot_image(color_name: str, size: float = 10.0):
    from AppKit import NSBezierPath, NSImage, NSMakeRect

    image = NSImage.alloc().initWithSize_((size, size))
    image.lockFocus()
    _color_ns_color(color_name).setFill()
    NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(0, 0, size, size)).fill()
    image.unlockFocus()
    return image


def _draw_letter_icon(letter: str, size: float = 18.0, fill_color_name: str = "black"):
    from AppKit import (
        NSBezierPath,
        NSFontAttributeName,
        NSForegroundColorAttributeName,
        NSImage,
        NSMakeRect,
        NSFont,
        NSColor,
    )
    from Foundation import NSString

    image = NSImage.alloc().initWithSize_((size, size))
    image.lockFocus()
    _color_ns_color(fill_color_name).setFill()
    NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(1, 1, size - 2, size - 2)).fill()

    font_size = size * 0.55
    attrs = {
        NSFontAttributeName: NSFont.boldSystemFontOfSize_(font_size),
        NSForegroundColorAttributeName: NSColor.whiteColor(),
    }
    text = NSString.stringWithString_(letter)
    text_size = text.sizeWithAttributes_(attrs)
    text.drawAtPoint_withAttributes_(
        (
            (size - text_size.width) / 2,
            (size - text_size.height) / 2,
        ),
        attrs,
    )
    image.unlockFocus()
    return image


def _draw_grok_icon(size: float = 18.0):
    from AppKit import NSBezierPath, NSImage, NSMakeRect, NSColor

    image = NSImage.alloc().initWithSize_((size, size))
    image.lockFocus()
    NSColor.blackColor().setFill()
    NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
        NSMakeRect(0.5, 0.5, size - 1, size - 1), size * 0.22, size * 0.22
    ).fill()

    stroke = max(2.0, size * 0.16)
    inset = size * 0.28
    path = NSBezierPath.bezierPath()
    path.setLineWidth_(stroke)
    path.setLineCapStyle_(1)  # round
    NSColor.whiteColor().setStroke()
    path.moveToPoint_((inset, inset))
    path.lineToPoint_((size - inset, size - inset))
    path.moveToPoint_((size - inset, inset))
    path.lineToPoint_((inset, size - inset))
    path.stroke()
    image.unlockFocus()
    image.setTemplate_(False)
    return image


def _load_image_from_path(path: str, size: float, *, template: bool = False):
    from AppKit import NSImage

    if not path or not os.path.isfile(path):
        return None
    image = NSImage.alloc().initWithContentsOfFile_(path)
    if image is None:
        return None
    image.setTemplate_(template)
    image.setSize_((size, size))
    return image


def _load_menu_bar_image(path: str, point_size: float, *, template: bool = True):
    from AppKit import NSBitmapImageRep, NSImage
    from Foundation import NSData

    if not path or not os.path.isfile(path):
        return None

    with open(path, "rb") as handle:
        raw = handle.read()
    data = NSData.dataWithBytes_length_(raw, len(raw))
    rep = NSBitmapImageRep.imageRepWithData_(data)
    if rep is None:
        return None

    pixels_wide = rep.pixelsWide()
    pixels_high = rep.pixelsHigh()
    if pixels_wide <= 0 or pixels_high <= 0:
        return None

    scale = max(pixels_wide, pixels_high) / point_size
    image = NSImage.alloc().initWithSize_((point_size, point_size))
    image.setTemplate_(template)
    rep.setSize_((pixels_wide / scale, pixels_high / scale))
    image.addRepresentation_(rep)
    return image


def _menu_bar_grok_icon(size: float = MENU_BAR_ICON_SIZE):
    image = _load_menu_bar_image(_GROK_MENUBAR_ICON_PATH, size, template=True)
    if image is not None:
        return image
    image = _load_image_from_path(_GROK_MENU_ICON_PATH, size, template=True)
    if image is not None:
        return image
    return _draw_grok_icon(size)


def _menu_bar_provider_icon(provider: Provider, size: float = MENU_BAR_ICON_SIZE):
    if provider == Provider.GROK:
        return _menu_bar_grok_icon(size)

    path = MENUBAR_ICON_PATHS.get(provider)
    if path:
        image = _load_menu_bar_image(path, size, template=False)
        if image is not None:
            return image

    return _provider_icon(provider, size)


def _provider_icon(provider: Provider, size: float = MENU_BAR_ICON_SIZE):
    for path in ICON_PATHS.get(provider, ()):
        image = _load_image_from_path(path, size)
        if image is not None:
            return image

    if provider == Provider.CODEX:
        return _draw_letter_icon("C", size, "blue")
    if provider == Provider.CLAUDE:
        return _draw_letter_icon("A", size, "orange")
    return _draw_grok_icon(size)


def _menu_bar_provider_image(
    provider: Provider,
    color_name: str,
    *,
    icon_size: float = MENU_BAR_ICON_SIZE,
    dot_size: float = 6.0,
    gap: float = 3.0,
):
    from AppKit import NSImage

    provider_image = _provider_icon(provider, icon_size)
    dot_image = _status_dot_image(color_name, dot_size)
    if provider_image is None:
        return None

    width = icon_size + gap + dot_size
    height = max(icon_size, dot_size + 2.0)
    composite = NSImage.alloc().initWithSize_((width, height))
    composite.setTemplate_(False)
    composite.lockFocus()
    provider_image.drawInRect_fromRect_operation_fraction_(
        _ns_rect(0, (height - icon_size) / 2, icon_size, icon_size),
        _ns_rect(0, 0, icon_size, icon_size),
        0,
        1.0,
    )
    if dot_image is not None:
        dot_y = (height - dot_size) / 2
        dot_image.drawInRect_fromRect_operation_fraction_(
            _ns_rect(icon_size + gap, dot_y, dot_size, dot_size),
            _ns_rect(0, 0, dot_size, dot_size),
            0,
            1.0,
        )
    composite.unlockFocus()
    return composite


def _provider_button_suffix(entry: UsageInfo) -> str:
    if entry.status == UsageStatus.OK and entry.remaining_percent is not None:
        return f"{entry.remaining_percent:.0f}%"
    if entry.status == UsageStatus.LOGIN_REQUIRED:
        return "—"
    return "!"


def _provider_menu_title(entry: UsageInfo) -> str:
    return format_usage_menu_title(entry)


def _summary_status_color(entries: list[UsageInfo]) -> str:
    priority = {"red": 0, "yellow": 1, "green": 2}
    colors = [entry.status_color for entry in entries]
    return min(colors, key=lambda color: priority.get(color, 1))


def _provider_button_title(entry: UsageInfo) -> str:
    return f" {_provider_button_suffix(entry)}"


class AuthActionHandler:
    """NSObject bridge so status bar button sign-in actions fire."""

    def __new__(cls):
        from Foundation import NSObject
        import objc

        class _AuthHandler(NSObject):
            def signInProvider_(self, sender) -> None:
                raw = str(sender.representedObject() or "")
                try:
                    provider = Provider(raw)
                except ValueError:
                    return
                launch_provider_login(provider)

        return _AuthHandler.alloc().init()


class DisplayActionHandler:
    """NSObject bridge for hiding providers and editing display settings."""

    def __new__(cls, app: UsageStatusApp):
        from Foundation import NSObject
        import objc

        class _DisplayHandler(NSObject):
            def hideProvider_(self, sender) -> None:
                raw = str(sender.representedObject() or "")
                try:
                    provider = Provider(raw)
                except ValueError:
                    return
                app.set_provider_visible(provider, False)

            def toggleProvider_(self, sender) -> None:
                raw = str(sender.representedObject() or "")
                try:
                    provider = Provider(raw)
                except ValueError:
                    return
                visible = app.is_provider_visible(provider)
                app.set_provider_visible(provider, not visible)

            def showAllProviders_(self, _sender) -> None:
                app.set_all_providers_visible(True)

        return _DisplayHandler.alloc().init()


def _add_hide_provider_menu_item(
    menu,
    ns_menu_item,
    handler,
    provider: Provider,
    *,
    app: UsageStatusApp,
) -> None:
    if app.visible_provider_count() <= 1 and app.is_provider_visible(provider):
        return

    from Foundation import NSString

    item = ns_menu_item.alloc().initWithTitle_action_keyEquivalent_(
        f"Hide {_provider_title(provider)}", "hideProvider:", ""
    )
    item.setTarget_(handler)
    item.setRepresentedObject_(NSString.stringWithString_(provider.value))
    menu.addItem_(item)


def _add_display_settings_menu_items(
    menu,
    ns_menu_item,
    display_handler,
    *,
    app: UsageStatusApp,
) -> None:
    from Foundation import NSString

    header = ns_menu_item.alloc().initWithTitle_action_keyEquivalent_(
        "Show in Menu Bar", None, ""
    )
    header.setEnabled_(False)
    menu.addItem_(header)

    for provider in PROVIDER_ORDER:
        item = ns_menu_item.alloc().initWithTitle_action_keyEquivalent_(
            f"    {_provider_title(provider)}", "toggleProvider:", ""
        )
        item.setTarget_(display_handler)
        item.setRepresentedObject_(NSString.stringWithString_(provider.value))
        item.setState_(1 if app.is_provider_visible(provider) else 0)
        menu.addItem_(item)

    show_all = ns_menu_item.alloc().initWithTitle_action_keyEquivalent_(
        "    Show All Services", "showAllProviders:", ""
    )
    show_all.setTarget_(display_handler)
    menu.addItem_(show_all)


def _add_reauthenticate_menu_item(menu, ns_menu_item, handler, provider: Provider) -> None:
    from Foundation import NSString

    item = ns_menu_item.alloc().initWithTitle_action_keyEquivalent_(
        "Reauthenticate...", "signInProvider:", ""
    )
    item.setTarget_(handler)
    item.setRepresentedObject_(NSString.stringWithString_(provider.value))
    menu.addItem_(item)


def _add_provider_menu_items(menu, ns_menu_item, entry: UsageInfo) -> None:
    header = ns_menu_item.alloc().initWithTitle_action_keyEquivalent_(
        _provider_menu_title(entry), None, ""
    )
    header.setEnabled_(False)
    header.setImage_(_provider_icon(entry.provider, MENU_ICON_SIZE))
    menu.addItem_(header)

    if entry.status == UsageStatus.OK:
        summary = ns_menu_item.alloc().initWithTitle_action_keyEquivalent_(
            f"    {entry.display_label}", None, ""
        )
        summary.setEnabled_(False)
        menu.addItem_(summary)

        if entry.reset_at is not None:
            reset_item = ns_menu_item.alloc().initWithTitle_action_keyEquivalent_(
                f"    Resets {format_reset_clock(entry.reset_at)} "
                f"({format_reset_time(entry.reset_at)})",
                None,
                "",
            )
            reset_item.setEnabled_(False)
            menu.addItem_(reset_item)

        for limit in entry.limits:
            limit_item = ns_menu_item.alloc().initWithTitle_action_keyEquivalent_(
                f"    {limit.name}: {limit.remaining_percent:.0f}% left · "
                f"resets {format_reset_time(limit.reset_at)}",
                None,
                "",
            )
            limit_item.setEnabled_(False)
            menu.addItem_(limit_item)
    else:
        message_item = ns_menu_item.alloc().initWithTitle_action_keyEquivalent_(
            f"    {entry.display_label}", None, ""
        )
        message_item.setEnabled_(False)
        menu.addItem_(message_item)


def _configure_provider_button_action(
    entry: UsageInfo,
    *,
    status_item,
    button,
    menu,
    handler,
) -> None:
    from AppKit import NSEventMaskLeftMouseDown
    from Foundation import NSString

    if entry.status == UsageStatus.LOGIN_REQUIRED:
        status_item.setMenu_(None)
        button.setTarget_(handler)
        button.setAction_("signInProvider:")
        button.setRepresentedObject_(NSString.stringWithString_(entry.provider.value))
        button.setToolTip_(f"Click to sign in to {_provider_title(entry.provider)}")
        button.sendActionOn_(NSEventMaskLeftMouseDown)
        return

    button.setTarget_(None)
    button.setAction_(None)
    button.setRepresentedObject_(None)
    button.sendActionOn_(0)
    button.setToolTip_(format_usage_menu_title(entry))
    status_item.setMenu_(menu)


class ProviderBarItem:
    def __init__(
        self,
        provider: Provider,
        *,
        status_bar,
        ns_menu,
        ns_menu_item,
        auth_handler,
        display_handler,
        app: UsageStatusApp,
    ) -> None:
        self.provider = provider
        self._auth_handler = auth_handler
        self._display_handler = display_handler
        self._app = app
        self.status_item = status_bar.statusItemWithLength_(-1)
        self.status_item.setHighlightMode_(True)
        self.status_item.setVisible_(True)
        self.status_item.setAutosaveName_(PROVIDER_AUTOSAVE_NAMES[provider])
        self.menu = ns_menu.alloc().init()
        self.status_item.setMenu_(self.menu)
        self._NSMenuItem = ns_menu_item
        self._entry: UsageInfo | None = None

        button = self.status_item.button()
        if button is not None:
            from AppKit import NSFont

            button.setFont_(NSFont.systemFontOfSize_(11))
            button.setImagePosition_(2)  # NSImageLeft
            button.setImageScaling_(3)  # NSImageScaleNone

    def set_visible(self, visible: bool) -> None:
        self.status_item.setVisible_(visible)

    def update(self, entry: UsageInfo) -> None:
        self._entry = entry
        button = self.status_item.button()
        if button is None:
            return

        icon = _menu_bar_provider_icon(entry.provider, MENU_BAR_ICON_SIZE)
        if icon is not None:
            button.setImage_(icon)
        button.setAlternateImage_(None)
        button.setTitle_(_provider_button_title(entry))
        self._rebuild_menu(entry)
        _configure_provider_button_action(
            entry,
            status_item=self.status_item,
            button=button,
            menu=self.menu,
            handler=self._auth_handler,
        )

    def _rebuild_menu(self, entry: UsageInfo) -> None:
        self.menu.removeAllItems()
        _add_provider_menu_items(self.menu, self._NSMenuItem, entry)
        self.menu.addItem_(self._NSMenuItem.separatorItem())
        _add_hide_provider_menu_item(
            self.menu,
            self._NSMenuItem,
            self._display_handler,
            entry.provider,
            app=self._app,
        )
        _add_reauthenticate_menu_item(
            self.menu,
            self._NSMenuItem,
            self._auth_handler,
            entry.provider,
        )
        self.menu.addItem_(self._NSMenuItem.separatorItem())
        _add_display_settings_menu_items(
            self.menu,
            self._NSMenuItem,
            self._display_handler,
            app=self._app,
        )
        self.menu.addItem_(self._NSMenuItem.separatorItem())
        quit_item = self._NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Quit Usage Status", "terminate:", "q"
        )
        self.menu.addItem_(quit_item)


def _hud_summary_text(entries: list[UsageInfo]) -> str:
    labels = {
        Provider.GROK: "Grok",
        Provider.CODEX: "Codex",
        Provider.CLAUDE: "Claude",
    }
    parts = []
    for entry in entries:
        name = labels.get(entry.provider, entry.provider.value)
        parts.append(f"{name} {_provider_button_suffix(entry)}")
    return "   ".join(parts)


class UsageHudPanel:
    def __init__(self) -> None:
        from AppKit import (
            NSBackingStoreBuffered,
            NSColor,
            NSFloatingWindowLevel,
            NSFont,
            NSPanel,
            NSScreen,
            NSTextField,
            NSViewMaxXMargin,
            NSViewWidthSizable,
            NSWindowCollectionBehaviorCanJoinAllSpaces,
            NSWindowCollectionBehaviorFullScreenAuxiliary,
            NSWindowStyleMaskClosable,
            NSWindowStyleMaskTitled,
            NSWindowStyleMaskUtilityWindow,
        )

        visible = NSScreen.mainScreen().visibleFrame()
        width, height = 380.0, 34.0
        x = visible.origin.x + visible.size.width - width - 16.0
        y = visible.origin.y + visible.size.height - height
        label_x = 10.0

        self.panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            ((x, y), (width, height)),
            NSWindowStyleMaskTitled
            | NSWindowStyleMaskClosable
            | NSWindowStyleMaskUtilityWindow,
            NSBackingStoreBuffered,
            False,
        )
        self.panel.setTitle_("AI Usage")
        self.panel.setLevel_(NSFloatingWindowLevel + 1)
        self.panel.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorFullScreenAuxiliary
        )
        self.panel.setHidesOnDeactivate_(False)
        self.panel.setFloatingPanel_(True)
        self.panel.setBecomesKeyOnlyIfNeeded_(True)
        self.panel.setBackgroundColor_(NSColor.windowBackgroundColor())

        self.label = NSTextField.alloc().initWithFrame_(
            ((label_x, 7), (width - label_x - 10, 18))
        )
        self.label.setBezeled_(False)
        self.label.setDrawsBackground_(False)
        self.label.setEditable_(False)
        self.label.setSelectable_(False)
        self.label.setBordered_(False)
        self.label.setFont_(NSFont.monospacedSystemFontOfSize_weight_(12, 0.5))
        self.label.setAutoresizingMask_(NSViewWidthSizable | NSViewMaxXMargin)

        content = self.panel.contentView()
        if content is not None:
            content.addSubview_(self.label)
        self.panel.orderFrontRegardless()

    def update(self, entries: list[UsageInfo]) -> None:
        self.label.setStringValue_(_hud_summary_text(entries))
        if not self.panel.isVisible():
            self.panel.orderFrontRegardless()

    def close(self) -> None:
        self.panel.orderOut_(None)


def _clear_menu_bar_defaults(autosave_names: tuple[str, ...]) -> None:
    for autosave_name in autosave_names:
        for key_prefix in (
            "NSStatusItem Preferred Position ",
            "NSStatusItem Visible ",
        ):
            subprocess.run(
                [
                    "defaults",
                    "delete",
                    "com.apple.controlcenter",
                    f"{key_prefix}{autosave_name}",
                ],
                check=False,
            )


def _apply_menu_bar_positions(enabled_providers: set[Provider]) -> None:
    _clear_menu_bar_defaults(LEGACY_AUTOSAVE_NAMES)
    for provider in PROVIDER_ORDER:
        autosave_name = PROVIDER_AUTOSAVE_NAMES[provider]
        visible = provider in enabled_providers
        subprocess.run(
            [
                "defaults",
                "write",
                "com.apple.controlcenter",
                f"NSStatusItem Visible {autosave_name}",
                "-bool",
                "true" if visible else "false",
            ],
            check=False,
        )


class UsageStatusApp:
    def __init__(self, *, show_hud: bool = True) -> None:
        from AppKit import (
            NSApplication,
            NSMenu,
            NSMenuItem,
            NSStatusBar,
            NSTimer,
        )
        from Foundation import NSRunLoop, NSRunLoopCommonModes

        self._entries: list[UsageInfo] = []
        self._enabled_providers = load_display_preferences()
        self.app = NSApplication.sharedApplication()
        _apply_menu_bar_positions(self._enabled_providers)
        status_bar = NSStatusBar.systemStatusBar()
        self._auth_handler = AuthActionHandler()
        self._display_handler = DisplayActionHandler(self)
        items_by_provider: dict[Provider, ProviderBarItem] = {}
        for provider in MENU_BAR_CREATE_ORDER:
            items_by_provider[provider] = ProviderBarItem(
                provider,
                status_bar=status_bar,
                ns_menu=NSMenu,
                ns_menu_item=NSMenuItem,
                auth_handler=self._auth_handler,
                display_handler=self._display_handler,
                app=self,
            )
        self._provider_items_by_provider = items_by_provider
        self._provider_items = [
            items_by_provider[provider] for provider in PROVIDER_ORDER
        ]
        self._hud_panel = UsageHudPanel() if show_hud else None

        self._apply_provider_visibility()
        self.refresh_menu()

        visible_count = sum(
            1 for provider in PROVIDER_ORDER if provider in self._enabled_providers
        )
        print(
            f"usage-status: menu bar ready items={visible_count}/{len(PROVIDER_ORDER)} "
            f"hud={'on' if self._hud_panel is not None else 'off'}",
            file=sys.stderr,
            flush=True,
        )

        self.timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            REFRESH_INTERVAL_SECONDS,
            self,
            "refreshMenu:",
            None,
            True,
        )
        NSRunLoop.currentRunLoop().addTimer_forMode_(self.timer, NSRunLoopCommonModes)

    def refreshMenu_(self, _timer) -> None:
        self.refresh_menu()

    def is_provider_visible(self, provider: Provider) -> bool:
        return provider in self._enabled_providers

    def visible_provider_count(self) -> int:
        return sum(
            1 for provider in PROVIDER_ORDER if provider in self._enabled_providers
        )

    def set_provider_visible(self, provider: Provider, visible: bool) -> None:
        if visible:
            self._enabled_providers.add(provider)
        else:
            self._enabled_providers.discard(provider)
        save_display_preferences(self._enabled_providers)
        self._apply_provider_visibility()
        self._rebuild_visible_provider_menus()

    def set_all_providers_visible(self, visible: bool) -> None:
        if visible:
            self._enabled_providers = set(PROVIDER_ORDER)
        else:
            self._enabled_providers = set()
        save_display_preferences(self._enabled_providers)
        self._apply_provider_visibility()
        self._rebuild_visible_provider_menus()

    def _apply_provider_visibility(self) -> None:
        for provider, item in self._provider_items_by_provider.items():
            item.set_visible(provider in self._enabled_providers)

    def _rebuild_visible_provider_menus(self) -> None:
        if not self._entries:
            return
        by_provider = {entry.provider: entry for entry in self._entries}
        for provider, item in self._provider_items_by_provider.items():
            if provider not in self._enabled_providers:
                continue
            item.update(by_provider[provider])

    def refresh_menu(self) -> None:
        entries = discover_usage()
        by_provider = {entry.provider: entry for entry in entries}
        self._entries = [by_provider[provider] for provider in PROVIDER_ORDER]
        for provider, item in self._provider_items_by_provider.items():
            if provider not in self._enabled_providers:
                continue
            item.update(by_provider[provider])
        if self._hud_panel is not None:
            visible_entries = [
                entry
                for entry in self._entries
                if entry.provider in self._enabled_providers
            ]
            self._hud_panel.update(visible_entries)

    def run(self) -> None:
        self.app.setActivationPolicy_(1)
        self.app.finishLaunching()
        self.app.activateIgnoringOtherApps_(True)
        self.app.run()


def run_menu_bar_app(*, show_hud: bool = True) -> int:
    app = UsageStatusApp(show_hud=show_hud)
    app.run()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.list:
        return run_list_mode()
    if args.probe:
        return run_probe_mode()

    return run_menu_bar_app(show_hud=not args.no_hud)


if __name__ == "__main__":
    raise SystemExit(main())