from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, ImageDraw, ImageFont
from codexcontrol_windows.brand_icon import build_orbit_dial_icon


ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)
BRAND_ACCENT = "#61e6b1"


def build_icon(size: int) -> Image.Image:
    return build_orbit_dial_icon(size, accent=BRAND_ACCENT)


def build_preview() -> Image.Image:
    preview = Image.new("RGB", (1080, 580), "#eef2f1")
    draw = ImageDraw.Draw(preview)
    font = ImageFont.load_default(size=17)
    title_font = ImageFont.load_default(size=28)
    draw.text((38, 26), "CodexControl / Windows", fill="#18262a", font=title_font)
    draw.text((38, 68), "C control mark  /  Mint on charcoal", fill="#536664", font=font)
    preview.paste(build_icon(256), (44, 127), build_icon(256))
    draw.text((48, 405), "Application icon / 256 px", fill="#536664", font=font)

    draw.rounded_rectangle((354, 116, 1042, 326), radius=18, fill="#10171f")
    draw.text((378, 135), "Native Windows sizes", fill="#c1d0cb", font=font)
    for index, size in enumerate((16, 24, 32, 48, 64)):
        center_x = 414 + index * 133
        icon = build_icon(size)
        preview.paste(icon, (center_x - size // 2, 215 - size // 2), icon)
        draw.text((center_x - 22, 278), str(size) + " px", fill="#9badac", font=font)

    draw.text((378, 356), "Tray states / enlarged from 32 px", fill="#536664", font=font)
    for index, (label, accent) in enumerate((
        ("Neutral", "#b0ddd0"),
        ("Available", "#94c8ad"),
        ("Warning", "#ddbc85"),
        ("Unavailable", "#df9e9a"),
    )):
        x = 382 + index * 166
        icon = build_orbit_dial_icon(
            32, accent=accent, panel_fill="#24272d", panel_fill_end="#1b1d22",
            dark="#181c20", border="#373d44",
        ).resize((96, 96), Image.Resampling.NEAREST)
        preview.paste(icon, (x, 399), icon)
        draw.text((x - 2, 514), label, fill="#536664", font=font)
    return preview


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    assets_dir = root / "build-assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    output_path = assets_dir / "CodexControl.ico"

    frames = [build_icon(size) for size in ICON_SIZES]
    frames[-1].save(
        output_path,
        format="ICO",
        sizes=[(size, size) for size in ICON_SIZES],
        append_images=frames[:-1],
    )
    build_preview().save(assets_dir / "CodexControl-preview.png")
    print(output_path)


if __name__ == "__main__":
    main()
