"""The fast panel skin must preserve the original antialiased pixels."""
import unittest
from PIL import ImageChops

from codexcontrol_windows.ui_components import _surface, _surface_raster


class SurfaceRenderingTests(unittest.TestCase):
    def test_nine_slice_preserves_antialiasing_satin_and_focus_border(self):
        for width, height, radius, satin, focused in (
            (464, 198, 18, True, False),
            (464, 460, 18, True, False),
            (862, 618, 18, True, False),
            (350, 145, 12, False, False),
            (210, 95, 10, True, True),
            (26, 26, 10, False, False),
        ):
            with self.subTest(size=(width, height), satin=satin, focused=focused):
                args = (width, height, '#15202c', '#344759', '#0c121b', radius, 1, satin, focused)
                actual = _surface(*args)
                reference = _surface_raster(*args)
                self.assertEqual(actual.size, reference.size)
                self.assertEqual(((0, 0),) * 4, ImageChops.difference(actual, reference).getextrema())


if __name__ == '__main__':
    unittest.main()
