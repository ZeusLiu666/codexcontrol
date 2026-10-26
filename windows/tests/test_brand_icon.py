from __future__ import annotations

from pathlib import Path
import unittest

from PIL import Image, ImageChops

from codexcontrol_windows.brand_icon import build_orbit_dial_icon


def _pixels(image: Image.Image):
    return [image.getpixel((x, y)) for y in range(image.height) for x in range(image.width)]


class BrandIconTests(unittest.TestCase):
    def test_tray_and_application_sizes_have_transparent_corners_and_no_clipping(self) -> None:
        for size in (16, 24, 32, 48, 64, 128, 256):
            with self.subTest(size=size):
                image = build_orbit_dial_icon(size, accent="#61e6b1")
                self.assertEqual(image.mode, "RGBA")
                self.assertEqual(image.size, (size, size))
                alpha = image.getchannel("A")
                for corner in ((0, 0), (size - 1, 0), (0, size - 1), (size - 1, size - 1)):
                    self.assertEqual(alpha.getpixel(corner), 0)
                # A subpixel antialiasing fringe is harmless; the solid panel
                # must remain inset on all sides rather than be cropped.
                solid = alpha.point(lambda value: 255 if value >= 128 else 0).getbbox()
                self.assertIsNotNone(solid)
                self.assertGreater(solid[0], 0)
                self.assertGreater(solid[1], 0)
                self.assertLess(solid[2], size)
                self.assertLess(solid[3], size)

    def test_small_mark_retains_bright_foreground_and_dark_negative_space(self) -> None:
        for size in (16, 24, 32):
            with self.subTest(size=size):
                image = build_orbit_dial_icon(size, accent="#61e6b1")
                pixels = _pixels(image)
                mint = [pixel for pixel in pixels if pixel[3] > 200 and pixel[1] > 150 and pixel[1] > pixel[0] + 30]
                dark = [pixel for pixel in pixels if pixel[3] > 200 and max(pixel[:3]) < 65]
                self.assertGreater(len(mint), size)
                self.assertGreater(len(dark), size * 2)
                # The neutral mark has no distracting red signal light.
                self.assertFalse(any(red > 160 and red > green * 1.4 for red, green, blue, alpha in pixels if alpha > 200))

    def test_status_colors_change_the_mark_without_changing_transparency(self) -> None:
        images = [
            build_orbit_dial_icon(32, accent=accent)
            for accent in ("#b0ddd0", "#94c8ad", "#ddbc85", "#df9e9a")
        ]
        for image in images[1:]:
            self.assertEqual(images[0].getchannel("A").tobytes(), image.getchannel("A").tobytes())
            difference = ImageChops.difference(images[0].convert("RGB"), image.convert("RGB"))
            changed = sum(max(pixel) > 20 for pixel in _pixels(difference))
            self.assertGreater(changed, 50)

    def test_legacy_palette_arguments_and_explicit_core_remain_supported(self) -> None:
        image = build_orbit_dial_icon(
            64, accent="#61e6b1", core="#ffffff", panel_fill="#16242c",
            panel_fill_end="#0d151b", dark="#081014", border="#2e4148", glow="#112521",
        )
        self.assertEqual(image.size, (64, 64))
        self.assertGreater(max(min(pixel[:3]) for pixel in _pixels(image)), 220)

    def test_published_ico_has_every_native_size(self) -> None:
        path = Path(__file__).resolve().parents[1] / "build-assets" / "CodexControl.ico"
        with Image.open(path) as image:
            expected = {(size, size) for size in (16, 24, 32, 48, 64, 128, 256)}
            self.assertEqual(image.ico.sizes(), expected)
            for dimensions in expected:
                frame = image.ico.getimage(dimensions)
                self.assertEqual(frame.size, dimensions)
                self.assertEqual(frame.getpixel((0, 0))[3], 0)


if __name__ == "__main__":
    unittest.main()
