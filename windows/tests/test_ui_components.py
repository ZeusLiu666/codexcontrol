"""Component regressions; no application, account store, or visible windows."""
import sys
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

from codexcontrol_windows.ui_components import ActionButton, IconButton, ToolTip, _workarea_for_widget


class IconButtonSizingTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        self.root.destroy()

    def test_small_icon_buttons_stay_square_at_large_text_scale(self):
        self.root.tk.call('tk', 'scaling', 2.0)
        for size in (24, 26, 28, 32, 36):
            with self.subTest(size=size):
                button = IconButton(self.root, 'close', size=size)
                self.root.update_idletasks()
                self.assertEqual(size, button.winfo_reqwidth())
                self.assertEqual(size, button.winfo_reqheight())
                button.destroy()

    def test_button_with_text_grows_to_fit_scaled_font(self):
        self.root.tk.call('tk', 'scaling', 2.0)
        button = ActionButton(self.root, 'Switch account', height=24, font=('Segoe UI', 14))
        self.root.update_idletasks()
        self.assertGreater(button.winfo_reqheight(), 24)
        self.assertGreaterEqual(button.winfo_reqheight(), button._font.metrics('linespace') + 10)

    def test_tooltips_register_on_target_for_cancelling_clipped_details(self):
        target = tk.Label(self.root, text='Token usage')
        first, second = ToolTip(target, 'Today'), ToolTip(target, 'All time')
        self.assertEqual([first, second], target._control_tooltips)
        first.schedule()
        pending = first._job
        for tooltip in target._control_tooltips:
            tooltip.hide()
        self.assertNotIn(pending, self.root.tk.call('after', 'info'))
        first.destroy()
        self.assertEqual([second], target._control_tooltips)
        second.destroy()
        self.assertEqual([], target._control_tooltips)

    def test_hidden_details_ancestor_blocks_new_and_queued_tooltips(self):
        details = tk.Frame(self.root)
        nested = tk.Frame(details)
        target = tk.Label(nested, text='Token usage')
        tooltip = ToolTip(target, '120,000 tokens')
        tooltip.schedule()
        first_job = tooltip._job
        self.assertIsNotNone(first_job)  # Ordinary controls retain their behavior.
        details._details_visible = False
        nested._details_visible = True  # A child cannot override a hidden ancestor.
        tooltip.schedule()
        self.assertIsNone(tooltip._job)
        self.assertNotIn(first_job, self.root.tk.call('after', 'info'))
        details._details_visible = True
        tooltip.schedule()
        second_job = tooltip._job
        self.assertIsNotNone(second_job)
        details._details_visible = False
        with patch.object(target, 'winfo_viewable', return_value=True), \
             patch('codexcontrol_windows.ui_components.tk.Toplevel', side_effect=AssertionError('Hidden details must not open a tooltip')):
            tooltip.show()
        self.assertIsNone(tooltip._job)
        self.assertNotIn(second_job, self.root.tk.call('after', 'info'))
        self.assertIsNone(tooltip.window)
        tooltip.destroy()


@unittest.skipUnless(sys.platform == 'win32', 'Windows monitor API')
class TooltipMonitorTests(unittest.TestCase):
    def test_control_crossing_monitor_edge_uses_center_and_monitor_workarea(self):
        widget = Mock()
        widget.winfo_rootx.return_value = -20
        widget.winfo_rooty.return_value = 100
        widget.winfo_width.return_value = 60
        widget.winfo_height.return_value = 30
        widget.winfo_screenwidth.return_value = 1920
        widget.winfo_screenheight.return_value = 1080

        def workarea(_handle, pointer):
            info = pointer._obj
            info.work.left, info.work.top = 0, 0
            info.work.right, info.work.bottom = 1920, 1040
            return 1

        with patch('ctypes.windll.user32.MonitorFromPoint', return_value=1) as monitor, \
             patch('ctypes.windll.user32.GetMonitorInfoW', side_effect=workarea):
            self.assertEqual((0, 0, 1920, 1040), _workarea_for_widget(widget))
            point, flags = monitor.call_args.args
            self.assertEqual((10, 115), (point.x, point.y))
            self.assertEqual(2, flags)

    def test_monitor_lookup_failure_keeps_screen_bounds(self):
        widget = Mock()
        widget.winfo_rootx.return_value = 10
        widget.winfo_rooty.return_value = 100
        widget.winfo_width.return_value = widget.winfo_height.return_value = 32
        widget.winfo_screenwidth.return_value = 1920
        widget.winfo_screenheight.return_value = 1080
        with patch('ctypes.windll.user32.MonitorFromPoint', return_value=0), \
             patch('ctypes.windll.user32.GetMonitorInfoW', return_value=0):
            self.assertEqual((0, 0, 1920, 1080), _workarea_for_widget(widget))


if __name__ == '__main__':
    unittest.main()
