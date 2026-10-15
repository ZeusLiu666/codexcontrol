"""Native repaint drains only an owned Tk subtree and leaves window state alone."""
import ctypes
import os
import time
import tkinter as tk
import unittest
from ctypes import wintypes
from types import SimpleNamespace
from unittest.mock import Mock, patch

from codexcontrol_windows.native_window import _Win32Api, flush_native_paint
from codexcontrol_windows.ui_components import RoundedPanel


class NativePaintTests(unittest.TestCase):
    def setUp(self):
        self.widget = Mock()
        self.widget.winfo_exists.return_value = True
        self.widget.winfo_ismapped.return_value = True
        self.widget.winfo_id.return_value = 0x123456789
        self.user32 = Mock()
        self.user32.IsWindow.return_value = True
        self.user32.GetWindowThreadProcessId.return_value = 123
        self.user32.RedrawWindow.return_value = True
        self.kernel32 = Mock()
        self.kernel32.GetCurrentThreadId.return_value = 123
        api = SimpleNamespace(user32=self.user32, kernel32=self.kernel32)
        self.api_patch = patch('codexcontrol_windows.native_window._windows_api', return_value=api)
        self.api_patch.start()
        self.addCleanup(self.api_patch.stop)

    def test_owned_client_handle_and_repaint_flags_do_not_touch_styles_or_focus(self):
        self.assertTrue(flush_native_paint(self.widget))
        self.user32.RedrawWindow.assert_called_once_with(0x123456789, None, None, 0x185)
        self.assertEqual(['IsWindow', 'GetWindowThreadProcessId', 'RedrawWindow'],
                         [call[0] for call in self.user32.method_calls])

    def test_unmapped_destroyed_invalid_or_foreign_thread_window_is_ignored(self):
        for case in ('unmapped', 'destroyed', 'invalid', 'foreign'):
            with self.subTest(case=case):
                self.widget.winfo_ismapped.return_value = case != 'unmapped'
                self.widget.winfo_exists.return_value = case != 'destroyed'
                self.user32.IsWindow.return_value = case != 'invalid'
                self.user32.GetWindowThreadProcessId.return_value = 999 if case == 'foreign' else 123
                self.assertFalse(flush_native_paint(self.widget))
        self.user32.RedrawWindow.assert_not_called()

    def test_unavailable_or_failed_native_api_leaves_tk_fallback_available(self):
        with patch('codexcontrol_windows.native_window._windows_api', return_value=None):
            self.assertFalse(flush_native_paint(self.widget))
        self.user32.RedrawWindow.return_value = False
        self.assertFalse(flush_native_paint(self.widget))
        self.user32.RedrawWindow.side_effect = OSError('Native drawing failed')
        self.assertFalse(flush_native_paint(self.widget))
        self.widget.winfo_id.side_effect = tk.TclError('bad window path')
        self.assertFalse(flush_native_paint(self.widget))

    def test_redraw_binding_preserves_pointer_sized_handles(self):
        _Win32Api(self.user32, self.kernel32, None)
        self.assertEqual([wintypes.HWND, ctypes.POINTER(wintypes.RECT), wintypes.HANDLE, wintypes.UINT],
                         self.user32.RedrawWindow.argtypes)
        self.assertIs(wintypes.BOOL, self.user32.RedrawWindow.restype)


@unittest.skipUnless(os.name == 'nt', 'Windows native paint')
class NativePaintTkTests(unittest.TestCase):
    def test_repeated_native_then_tk_paint_finishes_without_remapping_children(self):
        root = tk.Tk()
        root.withdraw()
        root.geometry('360x320+5000+5000')
        errors = []
        root.report_callback_exception = lambda *args: errors.append(args)
        try:
            panel = RoundedPanel(root, width=320, padding=12)
            panel.pack(fill='x')
            labels = [tk.Label(panel.inner, text=f'Test detail {index}', bg=panel.fill) for index in range(12)]
            for label in labels:
                label.pack(anchor='w')
            root.deiconify()
            root.update()
            ids = [label.winfo_id() for label in labels]
            started = time.perf_counter()
            for height in (70, 210, 90, 260, 64, 240):
                panel.set_height_override(height)
                root.update_idletasks()
                self.assertTrue(flush_native_paint(panel.canvas))
                self.assertGreater(panel.flush_visible_paint(), 0)
            elapsed = time.perf_counter() - started
            self.assertLess(elapsed, 5, f'Native repaint stalled: {elapsed:.3f}s')
            self.assertEqual(ids, [label.winfo_id() for label in labels])
            self.assertFalse(errors, errors)
        finally:
            root.destroy()


if __name__ == '__main__':
    unittest.main()
