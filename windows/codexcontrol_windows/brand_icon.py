from __future__ import annotations

import math

from PIL import Image, ImageDraw


def build_orbit_dial_icon(
    size: int,
    *,
    accent: str,
    core: str = "#ddfff2",
    panel_fill: str = "#18242d",
    panel_fill_end: str = "#0c131b",
    dark: str = "#0b1219",
    border: str = "#34434b",
    glow: str = "#172b27",
) -> Image.Image:
    """Draw the C control mark at tray and application-icon sizes.

    Keep the original renderer name and palette arguments for existing callers.
    The broad open ring and control bar retain their shape at 16 pixels; status
    colors tint the ring while the light bar stays legible on dark taskbars.
    """
    if size <= 0:
        raise ValueError("Icon size must be positive")
    scale = 4
    pixels = size * scale
    unit = pixels / 64.0
    image = Image.new("RGBA", (pixels, pixels), (0, 0, 0, 0))
    panel = Image.new("RGBA", image.size, (0, 0, 0, 0))
    panel_draw = ImageDraw.Draw(panel)
    top_rgb = _hex_to_rgb(panel_fill)
    bottom_rgb = _hex_to_rgb(panel_fill_end)
    for y in range(pixels):
        mix = y / max(1, pixels - 1)
        rgb = tuple(round(start + (end - start) * mix) for start, end in zip(top_rgb, bottom_rgb))
        panel_draw.line((0, y, pixels, y), fill=rgb + (255,))

    # Restrict every background effect to the rounded panel, keeping the icon's
    # outer corners transparent for Explorer, the taskbar and the system tray.
    mask = Image.new("L", image.size, 0)
    mask_draw = ImageDraw.Draw(mask)
    bounds = tuple(value * unit for value in (5.0, 5.0, 59.0, 59.0))
    mask_draw.rounded_rectangle(bounds, radius=14.0 * unit, fill=255)
    image.paste(panel, (0, 0), mask)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(bounds, radius=14.0 * unit, outline=border, width=max(1, round(0.75 * unit)))

    # A single generous C-shaped stroke avoids tiny orbit dots and details that
    # disappear or look like noise when Windows renders a small tray icon.
    center = 32.0 * unit
    radius = 17.2 * unit
    stroke = 7.0 * unit
    # A restrained inner shadow separates the mark from different custom panel
    # palettes without adding decoration outside the main silhouette.
    _round_arc(draw, (center, center + 0.55 * unit), radius, dark, stroke + 0.6 * unit)
    _round_arc(draw, (center, center), radius, accent, stroke)
    draw.rounded_rectangle(
        tuple(value * unit for value in (35.5, 28.6, 50.5, 35.4)),
        radius=3.4 * unit,
        fill=core,
    )

    # `glow` remains an accepted legacy palette argument. The new flat mark
    # needs no blurred halo, so its transparent margin stays crisp.
    return image.resize((size, size), Image.Resampling.LANCZOS)


def _round_arc(
    draw: ImageDraw.ImageDraw,
    center: tuple[float, float],
    radius: float,
    color: str,
    width: float,
) -> None:
    x, y = center
    outer = radius + width / 2
    draw.arc((x - outer, y - outer, x + outer, y + outer), 42, 318, fill=color, width=max(1, round(width)))
    cap = width / 2
    for angle in (42, 318):
        cap_x = x + radius * math.cos(math.radians(angle))
        cap_y = y + radius * math.sin(math.radians(angle))
        draw.ellipse((cap_x - cap, cap_y - cap, cap_x + cap, cap_y + cap), fill=color)


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
