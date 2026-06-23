#!/usr/bin/env python3
"""Build Usage Status app/repo icons from bundled provider assets."""

from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")
ICONSET = os.path.join(ROOT, "build", "UsageStatus.iconset")


def _load_image(path: str):
    from AppKit import NSBitmapImageRep, NSImage
    from Foundation import NSData

    with open(path, "rb") as handle:
        data = NSData.dataWithBytes_length_(handle.read(), os.path.getsize(path))
    rep = NSBitmapImageRep.imageRepWithData_(data)
    if rep is None:
        raise RuntimeError(f"failed to load image: {path}")
    size = max(rep.pixelsWide(), rep.pixelsHigh())
    image = NSImage.alloc().initWithSize_((size, size))
    image.addRepresentation_(rep)
    return image


def _draw_app_icon(size: int = 1024):
    from AppKit import (
        NSBezierPath,
        NSColor,
        NSCompositingOperationSourceOver,
        NSFont,
        NSFontAttributeName,
        NSForegroundColorAttributeName,
        NSImage,
    )
    from Foundation import NSString

    canvas = NSImage.alloc().initWithSize_((size, size))
    canvas.lockFocus()

    radius = size * 0.22
    NSColor.colorWithCalibratedWhite_alpha_(0.12, 1.0).setFill()
    path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
        ((0, 0), (size, size)), radius, radius
    )
    path.fill()

    icons = (
        ("grok-menubar-18.png", 0.14),
        ("codex-menubar-18.png", 0.42),
        ("claude-menubar-18.png", 0.70),
    )
    icon_size = size * 0.22
    y = (size - icon_size) / 2.0
    for filename, x_ratio in icons:
        image = _load_image(os.path.join(ASSETS, filename))
        x = size * x_ratio
        image.drawInRect_fromRect_operation_fraction_(
            ((x, y), (icon_size, icon_size)),
            ((0, 0), (image.size().width, image.size().height)),
            NSCompositingOperationSourceOver,
            1.0,
        )

    attrs = {
        NSFontAttributeName: __import__("AppKit").NSFont.boldSystemFontOfSize_(size * 0.09),
        NSForegroundColorAttributeName: NSColor.whiteColor(),
    }
    label = NSString.stringWithString_("Usage")
    text_size = label.sizeWithAttributes_(attrs)
    label.drawAtPoint_withAttributes_(
        ((size - text_size.width) / 2.0, size * 0.08), attrs
    )

    canvas.unlockFocus()
    return canvas


def _draw_social_preview(width: int = 1280, height: int = 640):
    from AppKit import NSColor, NSCompositingOperationSourceOver, NSImage

    canvas = NSImage.alloc().initWithSize_((width, height))
    canvas.lockFocus()
    NSColor.colorWithCalibratedRed_green_blue_alpha_(0.07, 0.08, 0.11, 1.0).setFill()
    __import__("AppKit").NSBezierPath.fillRect_(((0, 0), (width, height)))

    app_icon = _draw_app_icon(512)
    icon_x = width * 0.08
    icon_y = (height - 512) / 2.0
    app_icon.drawInRect_fromRect_operation_fraction_(
        ((icon_x, icon_y), (512, 512)),
        ((0, 0), (512, 512)),
        NSCompositingOperationSourceOver,
        1.0,
    )

    from AppKit import NSFont, NSFontAttributeName, NSForegroundColorAttributeName
    from Foundation import NSString

    title_attrs = {
        NSFontAttributeName: NSFont.boldSystemFontOfSize_(64),
        NSForegroundColorAttributeName: NSColor.whiteColor(),
    }
    body_attrs = {
        NSFontAttributeName: NSFont.systemFontOfSize_(30),
        NSForegroundColorAttributeName: NSColor.colorWithCalibratedWhite_alpha_(0.82, 1.0),
    }
    NSString.stringWithString_("Usage Status").drawAtPoint_withAttributes_(
        (width * 0.42, height * 0.42),
        title_attrs,
    )
    NSString.stringWithString_(
        "SuperGrok · Codex · Claude in your menu bar"
    ).drawAtPoint_withAttributes_(
        (width * 0.42, height * 0.28),
        body_attrs,
    )

    canvas.unlockFocus()
    return canvas


def _save_png(image, path: str) -> None:
    from AppKit import NSBitmapImageFileTypePNG, NSBitmapImageRep
    from Foundation import NSData

    os.makedirs(os.path.dirname(path), exist_ok=True)
    rep = NSBitmapImageRep.alloc().initWithData_(image.TIFFRepresentation())
    if rep is None:
        raise RuntimeError(f"failed to encode image for {path}")
    data = rep.representationUsingType_properties_(NSBitmapImageFileTypePNG, None)
    if data is None:
        raise RuntimeError(f"failed to write png for {path}")
    data.writeToFile_atomically_(path, True)


def _write_iconset(master_path: str) -> None:
    mapping = (
        ("icon_16x16.png", 16),
        ("icon_16x16@2x.png", 32),
        ("icon_32x32.png", 32),
        ("icon_32x32@2x.png", 64),
        ("icon_128x128.png", 128),
        ("icon_128x128@2x.png", 256),
        ("icon_256x256.png", 256),
        ("icon_256x256@2x.png", 512),
        ("icon_512x512.png", 512),
        ("icon_512x512@2x.png", 1024),
    )
    os.makedirs(ICONSET, exist_ok=True)
    for filename, px in mapping:
        out = os.path.join(ICONSET, filename)
        subprocess.run(
            ["sips", "-z", str(px), str(px), master_path, "--out", out],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def main() -> int:
    master = os.path.join(ASSETS, "app-icon-1024.png")
    icon_512 = os.path.join(ASSETS, "repo-icon-512.png")
    social = os.path.join(ROOT, "docs", "social-preview.png")
    icns = os.path.join(ASSETS, "UsageStatus.icns")

    icon = _draw_app_icon(1024)
    _save_png(icon, master)
    subprocess.run(
        ["sips", "-z", "512", "512", master, "--out", icon_512],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _save_png(_draw_social_preview(), social)
    _write_iconset(master)
    subprocess.run(["iconutil", "-c", "icns", ICONSET, "-o", icns], check=True)
    print(f"wrote {master}")
    print(f"wrote {icon_512}")
    print(f"wrote {social}")
    print(f"wrote {icns}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())