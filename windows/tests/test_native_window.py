from __future__ import annotations

import ctypes
import unittest
from ctypes import wintypes
from types import SimpleNamespace
from unittest.mock import Mock, patch

from codexcontrol_windows.native_window import (
    HWND_NOTOPMOST, HWND_TOPMOST, SW_RESTORE, SW_SHOW,
    _Win32Api, apply_window_appearance, bring_window_to_front,
)


class NativeWindowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.handle = 0x123456789  # Must retain its full value on a 64-bit host.
        self.root = Mock()
        self.root.winfo_exists.return_value = True
        self.root.winfo_id.return_value = 0x101
        self.user32 = Mock()
        self.user32.GetAncestor.return_value = self.handle
        self.user32.IsWindow.return_value = True
        self.user32.IsIconic.return_value = False
        self.user32.GetForegroundWindow.return_value = self.handle
        self.user32.IsHungAppWindow.return_value = False
        self.user32.GetWindowThreadProcessId.return_value = 2
        self.user32.AttachThreadInput.return_value = True
        self.kernel32 = Mock()
        self.kernel32.GetCurrentThreadId.return_value = 1
        self.dwmapi = Mock()
        self.dwmapi.DwmSetWindowAttribute.return_value = 0
        self.api = SimpleNamespace(user32=self.user32, kernel32=self.kernel32, dwmapi=self.dwmapi)
        self.api_patch = patch("codexcontrol_windows.native_window._windows_api", return_value=self.api)
        self.api_patch.start()
        self.addCleanup(self.api_patch.stop)

    def test_already_open_panel_is_raised_without_remaining_topmost(self) -> None:
        self.assertTrue(bring_window_to_front(self.root))
        self.root.deiconify.assert_called_once_with()
        self.root.focus_force.assert_called_once_with()
        self.user32.ShowWindow.assert_called_once_with(self.handle, SW_SHOW)
        self.assertEqual(
            [call.args[1] for call in self.user32.SetWindowPos.call_args_list],
            [HWND_TOPMOST, HWND_NOTOPMOST],
        )
        self.user32.AttachThreadInput.assert_not_called()

    def test_minimized_panel_is_restored(self) -> None:
        self.user32.IsIconic.return_value = True
        bring_window_to_front(self.root)
        self.user32.ShowWindow.assert_called_once_with(self.handle, SW_RESTORE)

    def test_denied_foreground_attempt_temporarily_shares_input_then_detaches(self) -> None:
        self.user32.GetForegroundWindow.side_effect = [0x202, 0x202, self.handle]
        self.assertTrue(bring_window_to_front(self.root))
        self.assertEqual(
            [call.args for call in self.user32.AttachThreadInput.call_args_list],
            [(1, 2, True), (1, 2, False)],
        )
        self.assertEqual(self.user32.SetForegroundWindow.call_count, 2)

    def test_exception_during_activation_still_detaches_and_clears_topmost(self) -> None:
        self.user32.GetForegroundWindow.return_value = 0x202
        self.user32.SetFocus.side_effect = OSError("Activation failed")
        self.assertFalse(bring_window_to_front(self.root))
        self.user32.AttachThreadInput.assert_any_call(1, 2, False)
        self.assertEqual(self.user32.SetWindowPos.call_args.args[1], HWND_NOTOPMOST)

    def test_hung_foreground_application_does_not_share_input_queues(self) -> None:
        self.user32.GetForegroundWindow.return_value = 0x202
        self.user32.IsHungAppWindow.return_value = True
        self.assertFalse(bring_window_to_front(self.root))
        self.user32.AttachThreadInput.assert_not_called()
        self.assertEqual(self.user32.SetWindowPos.call_args.args[1], HWND_NOTOPMOST)

    def test_same_thread_does_not_attach_to_itself(self) -> None:
        self.user32.GetForegroundWindow.return_value = 0x202
        self.user32.GetWindowThreadProcessId.return_value = 1
        self.assertFalse(bring_window_to_front(self.root))
        self.user32.AttachThreadInput.assert_not_called()

    def test_destroyed_window_is_ignored(self) -> None:
        self.root.winfo_exists.return_value = False
        self.assertFalse(bring_window_to_front(self.root))
        self.root.deiconify.assert_not_called()
        self.user32.SetWindowPos.assert_not_called()

    def test_native_api_unavailable_uses_tk_fallback(self) -> None:
        with patch("codexcontrol_windows.native_window._windows_api", return_value=None):
            self.assertTrue(bring_window_to_front(self.root))
        self.root.lift.assert_called_once_with()
        self.root.focus_force.assert_called_once_with()

    def test_frame_colors_and_optional_backdrop_use_correct_dwm_values(self) -> None:
        values = {}

        def record_attribute(handle, number, value, size):
            self.assertEqual(handle, self.handle)
            self.assertEqual(size, ctypes.sizeof(wintypes.DWORD))
            values[number] = ctypes.cast(value, ctypes.POINTER(wintypes.DWORD)).contents.value
            return 0

        self.dwmapi.DwmSetWindowAttribute.side_effect = record_attribute
        result = apply_window_appearance(
            self.root, {"bg": "#080d12", "hairline": "#263442", "text": "#f3f7fb"},
            backdrop="mica",
        )
        self.assertTrue(all(result.values()))
        self.assertEqual(values, {
            20: 1, 33: 2, 34: 0x423426, 35: 0x120D08, 36: 0xFBF7F3, 38: 2,
        })

    def test_unsupported_dwm_attributes_are_nonfatal_and_dark_mode_has_fallback(self) -> None:
        self.dwmapi.DwmSetWindowAttribute.side_effect = [-1, 0, -1, -1]
        result = apply_window_appearance(self.root, {"bg": "#080d12"})
        self.assertEqual(result, {
            "dark_frame": True, "rounded_corners": False, "caption_color": False,
        })
        self.assertEqual(
            [call.args[1] for call in self.dwmapi.DwmSetWindowAttribute.call_args_list],
            [20, 19, 33, 35],
        )

    def test_bad_color_does_not_block_other_attributes(self) -> None:
        result = apply_window_appearance(self.root, {"hairline": "invalid", "text": "#f3f7fb"})
        self.assertFalse(result["border_color"])
        self.assertTrue(result["caption_text_color"])

    def test_native_bindings_use_pointer_sized_window_handles(self) -> None:
        _Win32Api(self.user32, self.kernel32, self.dwmapi)
        self.assertIs(self.user32.GetAncestor.restype, wintypes.HWND)
        self.assertIs(self.user32.GetForegroundWindow.restype, wintypes.HWND)
        self.assertEqual(self.user32.SetWindowPos.argtypes[:2], [wintypes.HWND, wintypes.HWND])
        self.assertEqual(
            self.dwmapi.DwmSetWindowAttribute.argtypes,
            [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD],
        )


if __name__ == "__main__":
    unittest.main()
