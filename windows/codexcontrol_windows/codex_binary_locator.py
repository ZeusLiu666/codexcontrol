from __future__ import annotations

import json
import os
import re
import shutil
import struct
import subprocess
from pathlib import Path


_VERSION_TIMEOUT_SECONDS = 2
_DISCOVERY_TIMEOUT_SECONDS = 4
_CLI_VERSION = re.compile(r"(?m)^codex-cli\s+\d+\.\d+\.\d+(?:[0-9A-Za-z.+-]*)\s*$")
_APPX_QUERY = """
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
ConvertTo-Json -Compress -InputObject @(
    Get-AppxPackage -Name OpenAI.Codex |
        Sort-Object Version -Descending |
        Select-Object -ExpandProperty InstallLocation
)
"""


def resolve() -> str | None:
    # Resolve afresh for every login: Desktop updates replace both the package
    # directory and the hash-named directory containing its extracted CLI.
    seen: set[str] = set()

    def first_valid(candidates: list[Path]) -> str | None:
        for candidate in candidates:
            key = os.path.normcase(os.path.abspath(str(candidate)))
            if key in seen:
                continue
            seen.add(key)
            if _is_codex_cli(candidate):
                return str(candidate)
        return None

    binary = shutil.which("codex")
    if binary:
        found = first_valid([Path(binary)])
        if found:
            return found

    found = first_valid(_path_candidates())
    if found:
        return found

    # The extracted Desktop CLI is inexpensive to discover and works while
    # Desktop is closed. Check actual executable files, not just hash folders:
    # another (newer) hash folder can contain only rg.exe.
    found = first_valid(_desktop_cache_candidates())
    if found:
        return found

    found = first_valid(_where_candidates())
    if found:
        return found

    # Invoke PowerShell only when the local/PATH candidates were exhausted.
    # Query the current user's registered packages instead of hard-coding a
    # versioned WindowsApps path or depending on Desktop being running.
    return first_valid(_appx_path_candidates())


def _path_candidates() -> list[Path]:
    local_app_data = _local_app_data()
    home = Path.home()
    return [
        local_app_data / "OpenAI" / "Codex" / "bin" / "codex.exe",
        home / ".bun" / "bin" / "codex.exe",
        home / "AppData" / "Local" / "Microsoft" / "WindowsApps" / "codex.exe",
        local_app_data / "Programs" / "OpenAI" / "Codex" / "bin" / "codex.exe",
    ]


def _local_app_data() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))


def _desktop_cache_candidates() -> list[Path]:
    root = _local_app_data() / "OpenAI" / "Codex" / "bin"
    candidates: list[tuple[int, Path]] = []
    try:
        for candidate in root.glob("*/codex.exe"):
            try:
                if candidate.is_file():
                    candidates.append((candidate.stat().st_mtime_ns, candidate))
            except OSError:
                continue
    except OSError:
        return []
    candidates.sort(key=lambda item: (-item[0], str(item[1]).casefold()))
    return [candidate for _, candidate in candidates]


def _where_candidates() -> list[Path]:
    try:
        result = subprocess.run(
            ["where.exe", "codex"],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_DISCOVERY_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    return [Path(line.strip()) for line in result.stdout.splitlines() if line.strip()]


def _appx_path_candidates() -> list[Path]:
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", _APPX_QUERY],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_DISCOVERY_TIMEOUT_SECONDS,
            check=False,
        )
        if result.returncode != 0:
            return []
        locations = json.loads(result.stdout.lstrip("\ufeff"))
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return []
    # Accept both PowerShell's single-string and array JSON representations.
    if isinstance(locations, str):
        locations = [locations]
    if not isinstance(locations, list):
        return []
    candidates: list[Path] = []
    for location in locations:
        if isinstance(location, str) and location.strip():
            root = Path(location)
            candidates.extend([root / "app" / "resources" / "codex.exe", root / "resources" / "codex.exe"])
    return candidates


def _is_codex_cli(candidate: Path) -> bool:
    try:
        if not candidate.is_file():
            return False
        # Never launch Desktop's GUI Codex.exe, including an app execution
        # alias found on PATH. Batch wrappers remain valid legacy candidates.
        if candidate.suffix.lower() == ".exe" and not _is_console_executable(candidate):
            return False
        result = subprocess.run(
            [str(candidate), "--version"],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_VERSION_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    output = (result.stdout or "") + "\n" + (result.stderr or "")
    return result.returncode == 0 and _CLI_VERSION.search(output) is not None


def _is_console_executable(candidate: Path) -> bool:
    try:
        with candidate.open("rb") as stream:
            if stream.read(2) != b"MZ":
                return False
            stream.seek(60)
            pe_offset = struct.unpack("<I", stream.read(4))[0]
            stream.seek(pe_offset)
            if stream.read(4) != b"PE\0\0":
                return False
            stream.seek(pe_offset + 24 + 68)
            # IMAGE_SUBSYSTEM_WINDOWS_CUI; the GUI subsystem is 2.
            return struct.unpack("<H", stream.read(2))[0] == 3
    except (OSError, ValueError, struct.error):
        return False
