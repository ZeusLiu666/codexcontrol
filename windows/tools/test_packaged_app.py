"""Exercise both shipped packages on a disposable GitHub-hosted Windows runner."""
import ctypes
from ctypes import wintypes as wt
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import zipfile

from pystray._util import win32
from release_tools import PORTABLE_FILES


def wait_for(description, probe, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = probe()
        if result:
            return result
        time.sleep(.1)
    raise RuntimeError(f"Timed out waiting for {description}")


user = ctypes.WinDLL("user32", use_last_error=True)
kernel = ctypes.WinDLL("kernel32", use_last_error=True)
window_callback = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)


def bind(library, name, result, *args):
    function = getattr(library, name)
    function.restype, function.argtypes = result, args
    return function


enum_windows = bind(user, "EnumWindows", wt.BOOL, window_callback, wt.LPARAM)
get_title = bind(user, "GetWindowTextW", ctypes.c_int, wt.HWND, wt.LPWSTR, ctypes.c_int)
get_class = bind(user, "GetClassNameW", ctypes.c_int, wt.HWND, wt.LPWSTR, ctypes.c_int)
get_pid = bind(user, "GetWindowThreadProcessId", wt.DWORD, wt.HWND, ctypes.POINTER(wt.DWORD))
is_visible = bind(user, "IsWindowVisible", wt.BOOL, wt.HWND)
open_process = bind(kernel, "OpenProcess", wt.HANDLE, wt.DWORD, wt.BOOL, wt.DWORD)
close_handle = bind(kernel, "CloseHandle", wt.BOOL, wt.HANDLE)
get_image = bind(kernel, "QueryFullProcessImageNameW", wt.BOOL, wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD))
send = bind(user, "SendMessageW", ctypes.c_ssize_t, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
post = bind(user, "PostMessageW", wt.BOOL, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
menu_count = bind(user, "GetMenuItemCount", ctypes.c_int, wt.HMENU)
menu_text = bind(user, "GetMenuStringW", ctypes.c_int, wt.HMENU, wt.UINT, wt.LPWSTR, ctypes.c_int, wt.UINT)


def windows():
    handles = []

    @window_callback
    def collect(hwnd, _):
        handles.append(hwnd)
        return True

    enum_windows(collect, 0)
    return handles


def text_of(function, hwnd):
    buffer = ctypes.create_unicode_buffer(256)
    function(hwnd, buffer, len(buffer))
    return buffer.value


def owner(hwnd):
    pid = wt.DWORD()
    get_pid(hwnd, ctypes.byref(pid))
    return pid.value


def panel_for(executable):
    for hwnd in windows():
        if not is_visible(hwnd) or text_of(get_title, hwnd) != "CodexControl":
            continue
        pid = owner(hwnd)
        process = open_process(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if process:
            try:
                path = ctypes.create_unicode_buffer(32768)
                length = wt.DWORD(len(path))
                if get_image(process, 0, path, ctypes.byref(length)) and Path(path.value) == executable:
                    return hwnd, pid
            finally:
                close_handle(process)


def quit_via_tray(pid):
    # Pystray registers two windows of the same class. Only its icon window
    # handles notifications. Filter both by the packaged app's process.
    trays = wait_for("tray creation", lambda: [
        hwnd for hwnd in windows() if owner(hwnd) == pid
        and text_of(get_class, hwnd).endswith("SystemTrayIcon")
    ])
    for hwnd in trays:
        post(hwnd, win32.WM_NOTIFY, 0, win32.WM_RBUTTONUP)
    popup = wait_for("the tray menu", lambda: next((
        hwnd for hwnd in windows() if owner(hwnd) == pid and is_visible(hwnd)
        and text_of(get_class, hwnd) == "#32768"
    ), None))
    menu = send(popup, 0x01E1, 0, 0)  # MN_GETHMENU
    # The native popup's last item is Quit. Verify the text, then exercise
    # normal menu keyboard navigation without moving the runner's mouse.
    last = menu_count(menu) - 1
    label = ctypes.create_unicode_buffer(100)
    if last < 0 or not menu_text(menu, last, label, len(label), 0x0400) or label.value != "Quit":
        raise RuntimeError("Quit was missing from the packaged app's tray menu")
    for key in (0x23, 0x0D):  # End, Enter
        if not post(popup, 0x0100, key, 1):  # WM_KEYDOWN to the owning menu thread
            raise ctypes.WinError()



def launch_and_quit(executable, env):
    process = subprocess.Popen([executable], cwd=executable.parent, env=env)
    try:
        hwnd, pid = wait_for("visible packaged dashboard", lambda: panel_for(executable), timeout=60)
        post(hwnd, 0x0010, 0, 0)  # WM_CLOSE
        wait_for("close-to-tray", lambda: not is_visible(hwnd))
        quit_via_tray(pid)
        if process.wait(timeout=30) != 0:
            raise RuntimeError("Packaged app did not exit cleanly")
    finally:
        if process.poll() is None:
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], timeout=15)
    support = Path(env["APPDATA"]) / "CodexControl"
    if json.loads((support / "accounts.json").read_text())["accounts"] != []:
        raise RuntimeError("Expected an empty isolated account list")
    if (support / "ui-errors.log").exists():
        raise RuntimeError("A dashboard callback failed during the smoke test")
    print(f"Verified {executable.parent.name} dashboard, close-to-tray and Quit", flush=True)


def main(version):
    if os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted" or os.environ.get("RUNNER_OS") != "Windows":
        raise SystemExit("This installation smoke test requires a disposable GitHub-hosted Windows runner")
    artifacts = Path("ReleaseArtifacts").resolve()
    stem = f"CodexControl-{version}-windows-x64"
    with tempfile.TemporaryDirectory(dir=os.environ["RUNNER_TEMP"]) as temp:
        root = Path(temp)
        profile = root / "profile"
        env = os.environ.copy()
        for key, path in (("USERPROFILE", profile), ("APPDATA", profile / "Roaming"),
                          ("LOCALAPPDATA", profile / "Local"), ("CODEX_HOME", profile / ".codex")):
            path.mkdir(parents=True, exist_ok=True)
            env[key] = str(path)
        portable, installed = root / "portable", root / "installed"
        with zipfile.ZipFile(artifacts / f"{stem}-portable.zip") as archive:
            if sorted(archive.namelist()) != sorted(PORTABLE_FILES):
                raise RuntimeError("Unexpected portable contents")
            archive.extractall(portable)
        launch_and_quit(portable / "CodexControl.exe", env)
        flags = ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"]
        subprocess.run([artifacts / f"{stem}-Setup.exe", *flags, "/SP-", "/NOICONS",
                        f"/DIR={installed}"], env=env, check=True, timeout=120)
        if not (installed / f"CodexControl-{version}.ico").is_file():
            raise RuntimeError("Installer omitted the versioned icon")
        try:
            launch_and_quit(installed / "CodexControl.exe", env)
        finally:
            subprocess.run([installed / "unins000.exe", *flags], env=env, check=True, timeout=120)
        wait_for("uninstallation", lambda: not (installed / "CodexControl.exe").exists())
        if not (Path(env["APPDATA"]) / "CodexControl" / "accounts.json").is_file():
            raise RuntimeError("Uninstall removed profile data")
        print("Verified silent install, uninstall and profile retention", flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
