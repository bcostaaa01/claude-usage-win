"""Draws the tray icon: a ring gauge for the most urgent usage window."""

from __future__ import annotations

from PIL import Image, ImageDraw

SIZE = 64
_STROKE = 8

_COLOR_OK = (60, 170, 90, 255)
_COLOR_WARN = (230, 165, 30, 255)
_COLOR_CRIT = (215, 60, 60, 255)
_COLOR_TRACK = (120, 120, 120, 90)
_COLOR_ERROR = (140, 140, 140, 255)


def _color_for(pct: float) -> tuple[int, int, int, int]:
    if pct >= 90:
        return _COLOR_CRIT
    if pct >= 70:
        return _COLOR_WARN
    return _COLOR_OK


def render_gauge(pct: float) -> Image.Image:
    """A circular progress ring, 0-100%, color-coded like a battery meter."""

    pct = max(0.0, min(100.0, pct))
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    bbox = (_STROKE, _STROKE, SIZE - _STROKE, SIZE - _STROKE)

    draw.ellipse(bbox, outline=_COLOR_TRACK, width=_STROKE)
    if pct > 0:
        sweep = 360 * (pct / 100)
        draw.arc(bbox, start=-90, end=-90 + sweep, fill=_color_for(pct), width=_STROKE)
    return img


def render_placeholder(color: tuple[int, int, int, int] = _COLOR_ERROR) -> Image.Image:
    """Shown when usage can't be fetched yet (no data, error, etc.)."""

    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    bbox = (_STROKE, _STROKE, SIZE - _STROKE, SIZE - _STROKE)
    draw.ellipse(bbox, outline=color, width=_STROKE)
    draw.line((SIZE * 0.35, SIZE * 0.65, SIZE * 0.65, SIZE * 0.35), fill=color, width=_STROKE - 2)
    draw.line((SIZE * 0.35, SIZE * 0.35, SIZE * 0.65, SIZE * 0.65), fill=color, width=_STROKE - 2)
    return img
