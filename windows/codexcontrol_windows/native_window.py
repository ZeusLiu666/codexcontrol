"""Native frame styling and user-requested activation of a Tk window.

Call these helpers on the Tk thread. Windows may refuse keyboard activation
under its foreground-lock policy, so activation is best effort; z-order is
raised independently and the window is never left permanently topmost.
"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from functools import lru_cache
from typing import Any, Mapping


GA_ROOT = 2
SW_SHOW = 5
SW_RESTORE = 9
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
RDW_INVALIDATE = 0x0001
RDW_ERASE = 0x0004
RDW_ALLCHILDREN = 0x0080
RDW_UPDATENOW = 0x0100
APP_USER_MODEL_ID = "CodexControl.Windows"


def set_app_identity() -> bool:
    """Use the installed shortcut identity instead of a launcher's taskbar icon."""
    if os.name != "nt":
        return False
    try:
        shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        set_identity = shell32.SetCurrentProcessExplicitAppUserModelID
        set_identity.argtypes = [wintypes.LPCWSTR]
        set_identity.restype = ctypes.c_long
        return set_identity(APP_USER_MODEL_ID) == 0
    except (OSError, AttributeError):
        return False


class _Win32Api:
    def __init__(self, user32: Any, kernel32: Any, dwmapi: Any | None) -> None:
        self.user32 = user32
        self.kernel32 = kernel32
        self.dwmapi = dwmapi
        # Explicit pointer-sized HWND types matter on 64-bit Windows. Leaving
        # ctypes defaults in place can truncate handles to a 32-bit integer.
        signatures = {
            "GetAncestor": ([wintypes.HWND, wintypes.UINT], wintypes.HWND),
            "IsWindow": ([wintypes.HWND], wintypes.BOOL),
            "IsIconic": ([wintypes.HWND], wintypes.BOOL),
            "ShowWindow": ([wintypes.HWND, ctypes.c_int], wintypes.BOOL),
            "GetForegroundWindow": ([], wintypes.HWND),
            "SetForegroundWindow": ([wintypes.HWND], wintypes.BOOL),
            "BringWindowToTop": ([wintypes.HWND], wintypes.BOOL),
            "SetActiveWindow": ([wintypes.HWND], wintypes.HWND),
            "SetFocus": ([wintypes.HWND], wintypes.HWND),
            "SetWindowPos": (
                [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                 ctypes.c_int, ctypes.c_int, wintypes.UINT],
                wintypes.BOOL,
            ),
            "GetWindowThreadProcessId": (
                [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)], wintypes.DWORD,
            ),
            "AttachThreadInput": (
                [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL], wintypes.BOOL,
            ),
            "IsHungAppWindow": ([wintypes.HWND], wintypes.BOOL),
            "RedrawWindow": (
                [wintypes.HWND, ctypes.POINTER(wintypes.RECT), wintypes.HANDLE, wintypes.UINT],
                wintypes.BOOL,
            ),
        }
        for name, (arguments, result) in signatures.items():
            function = getattr(user32, name)
            function.argtypes = arguments
            function.restype = result
        kernel32.GetCurrentThreadId.argtypes = []
        kernel32.GetCurrentThreadId.restype = wintypes.DWORD
        if dwmapi is not None:
            dwmapi.DwmSetWindowAttribute.argtypes = [
                wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
            ]
            dwmapi.DwmSetWindowAttribute.restype = ctypes.c_long


@lru_cache(maxsize=1)
def _windows_api() -> _Win32Api | None:
    if os.name != "nt":
        return None
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        try:
            dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
        except OSError:
            dwmapi = None
        return _Win32Api(user32, kernel32, dwmapi)
    except (OSError, AttributeError):
        return None


def _window_handle(root: Any, api: _Win32Api) -> int | None:
    child = int(root.winfo_id())
    # Tk's winfo_id identifies its client window; DWM and activation need the
    # decorated outermost window, which is not always its immediate parent.
    handle = api.user32.GetAncestor(child, GA_ROOT) or child
    return int(handle) if api.user32.IsWindow(handle) else None


def flush_native_paint(widget: Any) -> bool:
    """Drain native paint for this Tk subtree, without focus or style changes.

    Only a mapped window owned by the calling Tk thread is eligible. Use its
    client HWND directly, never an ancestor or another application's window.
    Explicit Tk Expose events can then draw after pending WM_PAINT erasures.
    """
    try:
        api = _windows_api()
        if api is None or not widget.winfo_exists() or not widget.winfo_ismapped():
            return False
        handle = int(widget.winfo_id())
        user32 = api.user32
        if not user32.IsWindow(handle):
            return False
        owner_thread = user32.GetWindowThreadProcessId(handle, None)
        if not owner_thread or owner_thread != api.kernel32.GetCurrentThreadId():
            return False
        flags = RDW_INVALIDATE | RDW_ERASE | RDW_ALLCHILDREN | RDW_UPDATENOW
        return bool(user32.RedrawWindow(handle, None, None, flags))
    except Exception:
        # Tk destruction or an unavailable/failed native call falls back to
        # the caller's normal Tk Expose path, without changing window state.
        return False


def _activate_window(api: _Win32Api, handle: int) -> bool:
    user32 = api.user32
    user32.BringWindowToTop(handle)
    user32.SetForegroundWindow(handle)
    if user32.GetForegroundWindow() == handle:
        return True

    foreground = user32.GetForegroundWindow()
    # Never share input queues with an unresponsive foreground window. This
    # avoids turning a tray click into a hang of the application's UI thread.
    if not foreground or user32.IsHungAppWindow(foreground):
        return False
    current_thread = api.kernel32.GetCurrentThreadId()
    foreground_thread = user32.GetWindowThreadProcessId(foreground, None)
    if not foreground_thread or foreground_thread == current_thread:
        return False
    attached = False
    try:
        attached = bool(user32.AttachThreadInput(current_thread, foreground_thread, True))
        if attached:
            user32.BringWindowToTop(handle)
            user32.SetActiveWindow(handle)
            user32.SetForegroundWindow(handle)
            user32.SetFocus(handle)
            return user32.GetForegroundWindow() == handle
        return False
    finally:
        if attached:
            user32.AttachThreadInput(current_thread, foreground_thread, False)


def bring_window_to_front(root: Any) -> bool:
    """Show/restore the panel and raise it above other ordinary windows.

    This also works when the panel is already open behind another application.
    The return value reports native foreground activation, when available.
    """
    try:
        if not root.winfo_exists():
            return False
        root.deiconify()
        root.update_idletasks()
        api = _windows_api()
        if api is None:
            root.lift()
            root.focus_force()
            return True
        handle = _window_handle(root, api)
        if handle is None:
            return False
        user32 = api.user32
        user32.ShowWindow(handle, SW_RESTORE if user32.IsIconic(handle) else SW_SHOW)
        flags = SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW | SWP_NOACTIVATE
        # Raise even when Windows declines keyboard focus, then immediately
        # release topmost status so normal switching between apps still works.
        try:
            user32.SetWindowPos(handle, HWND_TOPMOST, 0, 0, 0, 0, flags)
            activated = _activate_window(api, handle)
        finally:
            user32.SetWindowPos(handle, HWND_NOTOPMOST, 0, 0, 0, 0, flags)
        if activated:
            root.focus_force()
        return activated
    except Exception:
        # Window destruction or a denied native call must never surface as a
        # tray callback error. Tk provides a useful fallback where possible.
        try:
            root.lift()
            root.focus_force()
        except Exception:
            pass
        return False


def _colorref(value: str) -> int:
    color = value.removeprefix("#")
    if len(color) != 6:
        raise ValueError("Expected a six-digit RGB color")
    red, green, blue = (int(color[index:index + 2], 16) for index in (0, 2, 4))
    return red | (green << 8) | (blue << 16)


def apply_window_appearance(
    root: Any,
    palette: Mapping[str, str] | None = None,
    *,
    backdrop: str | None = None,
) -> dict[str, bool]:
    """Apply native dark frame, rounded corners, and matching frame colors.

    Unsupported DWM attributes fail independently on older Windows versions.
    Optional ``backdrop='mica'`` or ``'acrylic'`` requests the Windows 11 system
    material, but Tk paints opaque client widgets over it. It does not make
    the Tk content transparent and is not a substitute for composited widgets.
    """
    applied: dict[str, bool] = {}
    try:
        api = _windows_api()
        if api is None or api.dwmapi is None or not root.winfo_exists():
            return applied
        root.update_idletasks()
        handle = _window_handle(root, api)
        if handle is None:
            return applied

        def attribute(number: int, value: int) -> bool:
            try:
                native_value = wintypes.DWORD(value)
                result = api.dwmapi.DwmSetWindowAttribute(
                    handle, number, ctypes.byref(native_value), ctypes.sizeof(native_value),
                )
                return result == 0
            except (OSError, ValueError, AttributeError):
                return False

        applied["dark_frame"] = attribute(20, 1) or attribute(19, 1)
        applied["rounded_corners"] = attribute(33, 2)  # DWMWCP_ROUND
        colors = palette or {}
        for name, number, key in (
            ("border_color", 34, "hairline"),
            ("caption_color", 35, "bg"),
            ("caption_text_color", 36, "text"),
        ):
            color = colors.get(key)
            if color:
                try:
                    applied[name] = attribute(number, _colorref(color))
                except ValueError:
                    applied[name] = False
        if backdrop in {"mica", "acrylic"}:
            applied["system_backdrop"] = attribute(38, 2 if backdrop == "mica" else 3)
    except Exception:
        pass
    return applied
