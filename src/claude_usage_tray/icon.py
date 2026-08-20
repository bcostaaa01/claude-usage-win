"""Draws the tray icon: a ring gauge for the most urgent usage window."""

from __future__ import annotations

from PIL import Image, ImageDraw

from . import colors

SIZE = 64
_STROKE = 8


def render_gauge(pct: float) -> Image.Image:
    """A circular progress ring, 0-100%, color-coded like a battery meter."""

    pct = max(0.0, min(100.0, pct))
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    bbox = (_STROKE, _STROKE, SIZE - _STROKE, SIZE - _STROKE)

    draw.ellipse(bbox, outline=colors.TRACK_RGBA, width=_STROKE)
    if pct > 0:
        sweep = 360 * (pct / 100)
        draw.arc(bbox, start=-90, end=-90 + sweep, fill=colors.rgba_for(pct), width=_STROKE)
    return img


def render_placeholder(color: tuple[int, int, int, int] = colors.ERROR_RGBA) -> Image.Image:
    """Shown when usage can't be fetched yet (no data, error, etc.)."""

    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    bbox = (_STROKE, _STROKE, SIZE - _STROKE, SIZE - _STROKE)
    draw.ellipse(bbox, outline=color, width=_STROKE)
    draw.line((SIZE * 0.35, SIZE * 0.65, SIZE * 0.65, SIZE * 0.35), fill=color, width=_STROKE - 2)
    draw.line((SIZE * 0.35, SIZE * 0.35, SIZE * 0.65, SIZE * 0.65), fill=color, width=_STROKE - 2)
    return img
