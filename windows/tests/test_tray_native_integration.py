"""Opt-in live Windows tray/foreground integration using disposable windows.

Set CODEXCONTROL_NATIVE_UI_TESTS=1 to run on an unlocked interactive desktop.
The fixture never constructs stores, reads accounts, or controls real apps.
"""

from __future__ import annotations

import ctypes
import json
import os
import queue
import threading
import time
import tkinter as tk
import unittest
from ctypes import wintypes

from PIL import Image
from pystray._util import win32

from codexcontrol_windows.app import CodexControlWindowsApp
from codexcontrol_windows.native_window import _window_handle, _windows_api, bring_window_to_front


class RecordingQueue(queue.Queue):
    def __init__(self) -> None:
        super().__init__()
        self.callback_thread_ids: list[int] = []

    def put(self, item, *args, **kwargs) -> None:
        self.callback_thread_ids.append(threading.get_ident())
        super().put(item, *args, **kwargs)


@unittest.skipUnless(
    os.name == "nt" and os.environ.get("CODEXCONTROL_NATIVE_UI_TESTS") == "1",
    "Opt-in live Windows UI integration requires an unlocked desktop",
)
class NativeTrayIntegrationTests(unittest.TestCase):
    def test_actual_tray_message_loop_to_main_thread_restores_and_raises_panel(self) -> None:
        root = tk.Tk()
        root.title("CodexControl isolated panel test")
        root.geometry("260x120+50+50")
        cover = tk.Toplevel(root)
        cover.title("CodexControl isolated cover test")
        cover.geometry("260x120+65+65")
        app = CodexControlWindowsApp.__new__(CodexControlWindowsApp)
        app.root = root
        app.events = RecordingQueue()
        app._quitting = False
        app._create_icon_image = lambda state, size: Image.new("RGBA", (size, size), "#59d6ca")
        evidence: list[dict] = []
        main_thread = threading.get_ident()
        api = _windows_api()
        self.assertIsNotNone(api)
        user32 = api.user32
        user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.PostMessageW.restype = wintypes.BOOL
        user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
        user32.GetWindow.restype = wintypes.HWND
        user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        icon = None

        def panel_above_cover() -> bool:
            target = _window_handle(root, api)
            cursor = user32.GetWindow(_window_handle(cover, api), 3)  # GW_HWNDPREV
            for _ in range(300):
                if not cursor:
                    return False
                if cursor == target:
                    return True
                cursor = user32.GetWindow(cursor, 3)
            return False

        def click_and_dispatch(scenario: str) -> None:
            foreground_before = user32.GetForegroundWindow()
            self.assertTrue(user32.PostMessageW(icon._hwnd, win32.WM_NOTIFY, 0, win32.WM_LBUTTONUP))
            deadline = time.monotonic() + 3
            event = None
            while time.monotonic() < deadline:
                root.update()
                try:
                    event = app.events.get_nowait()
                    break
                except queue.Empty:
                    time.sleep(0.005)
            self.assertEqual(event, ("tray_action", "show"))
            self.assertNotEqual(app.events.callback_thread_ids[-1], main_thread)
            app._dispatch_event(event)
            root.update()
            handle = _window_handle(root, api)
            foreground_after = user32.GetForegroundWindow()
            topmost = bool(user32.GetWindowLongPtrW(handle, -20) & 0x8)  # WS_EX_TOPMOST
            above = panel_above_cover()
            evidence.append({
                "scenario": scenario, "foreground_before": foreground_before,
                "foreground_after": foreground_after, "panel_hwnd": handle,
                "panel_is_foreground": foreground_after == handle,
                "panel_above_cover": above, "state": root.state(),
                "left_topmost": topmost,
                "callback_on_worker": app.events.callback_thread_ids[-1] != main_thread,
            })
            self.assertEqual(root.state(), "normal")
            self.assertFalse(user32.IsIconic(handle))
            self.assertEqual(foreground_after, handle)
            self.assertTrue(above)
            self.assertFalse(topmost)

        try:
            root.update()
            app._setup_tray_icon()
            icon = app.tray_icon
            self.assertIsNotNone(icon)
            icon.title = "CodexControl isolated integration test"
            deadline = time.monotonic() + 3
            while (not icon._hwnd or not icon.visible) and time.monotonic() < deadline:
                root.update()
                time.sleep(0.005)
            self.assertTrue(icon._hwnd and icon.visible)
            bring_window_to_front(cover)
            cover.update()
            self.assertFalse(panel_above_cover(), "The cover must obscure the panel before its tray click")
            click_and_dispatch("already_open_obscured")
            click_and_dispatch("repeated_click")
            root.withdraw()
            root.update()
            self.assertEqual(root.state(), "withdrawn")
            click_and_dispatch("hidden")
            handle = _window_handle(root, api)
            user32.ShowWindow(handle, 6)  # SW_MINIMIZE
            root.update()
            self.assertTrue(user32.IsIconic(handle))
            click_and_dispatch("minimized")
        finally:
            if icon is not None:
                icon.stop()
                thread = getattr(icon, "_thread", None)
                if thread is not None:
                    thread.join(timeout=3)
            root.destroy()
            print("NATIVE_TRAY_EVIDENCE=" + json.dumps(evidence))


if __name__ == "__main__":
    unittest.main()
