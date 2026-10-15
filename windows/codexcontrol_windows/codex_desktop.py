from __future__ import annotations

import base64
import os
import subprocess
from pathlib import Path, PureWindowsPath

from .file_locations import APP_SUPPORT_DIRECTORY, DESKTOP_SESSION_STATE_ENTRIES, codex_desktop_session_root, ensure_directories


DEFAULT_RESTART_DELAY_SECONDS = 0.8
RESTART_LOG_PATH = APP_SUPPORT_DIRECTORY / "codex-desktop-restart.log"
RESTART_STATUS_PATH = APP_SUPPORT_DIRECTORY / "codex-desktop-restart-status.json"
RESTART_SCRIPT_PATH = APP_SUPPORT_DIRECTORY / "codex-desktop-restart.ps1"
POWERSHELL_EXE = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"


class CodexDesktopControlError(RuntimeError):
    """Friendly Codex Desktop control error."""


def build_restart_script(
    delay_seconds: float = DEFAULT_RESTART_DELAY_SECONDS,
    session_root: Path | None = None,
    backup_destination: Path | None = None,
    restore_source: Path | None = None,
    target_auth_path: Path | None = None,
    ambient_auth_path: Path | None = None,
    diagnostic_only: bool = False,
) -> str:
    delay_ms = max(0, int(round(delay_seconds * 1000)))
    log_path = _powershell_literal_path(RESTART_LOG_PATH)
    effective_session_root = session_root or codex_desktop_session_root()
    session_root_literal = _powershell_path_or_null(effective_session_root)
    backup_destination_literal = _powershell_path_or_null(backup_destination)
    restore_source_literal = _powershell_path_or_null(restore_source)
    session_entries_literal = _powershell_string_array(DESKTOP_SESSION_STATE_ENTRIES)

    script = f"""
$ErrorActionPreference = 'Stop'
$logPath = {log_path}
$statusPath = {_powershell_literal_path(RESTART_STATUS_PATH)}
$targetAuthPath = {_powershell_path_or_null(target_auth_path)}
$ambientAuthPath = {_powershell_path_or_null(ambient_auth_path)}
$diagnosticOnly = {"$true" if diagnostic_only else "$false"}
$sessionRoot = {session_root_literal}
$backupDestination = {backup_destination_literal}
$restoreSource = {restore_source_literal}
$sessionEntries = {session_entries_literal}
New-Item -ItemType Directory -Path ([System.IO.Path]::GetDirectoryName($logPath)) -Force | Out-Null
function Write-Log([string]$message) {{
    Add-Content -LiteralPath $logPath -Value ("[{{0}}] {{1}}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss.fff'), $message)
}}
function Clear-SessionEntry([string]$root, [string]$relativePath) {{
    if (-not $root) {{
        return
    }}
    $rootFull = [System.IO.Path]::GetFullPath($root).TrimEnd('\')
    $targetPath = [System.IO.Path]::GetFullPath((Join-Path $root $relativePath))
    if ($relativePath -notin $sessionEntries -or -not $targetPath.StartsWith($rootFull + '\', [System.StringComparison]::OrdinalIgnoreCase)) {{
        throw 'Session cleanup path is outside the expected directory.'
    }}
    if (Test-Path -LiteralPath $targetPath) {{
        Remove-Item -LiteralPath $targetPath -Recurse -Force -ErrorAction Stop
    }}
}}
function Copy-SessionEntry([string]$sourceRoot, [string]$destinationRoot, [string]$relativePath) {{
    if (-not $sourceRoot -or -not $destinationRoot) {{
        return
    }}
    $sourcePath = Join-Path $sourceRoot $relativePath
    if (-not (Test-Path -LiteralPath $sourcePath)) {{
        return
    }}
    $destinationPath = Join-Path $destinationRoot $relativePath
    $parentPath = [System.IO.Path]::GetDirectoryName($destinationPath)
    if ($parentPath) {{
        New-Item -ItemType Directory -Path $parentPath -Force | Out-Null
    }}
    $item = Get-Item -LiteralPath $sourcePath -Force
    if ($item.PSIsContainer) {{
        Copy-Item -LiteralPath $sourcePath -Destination $destinationPath -Recurse -Force
        return
    }}
    Copy-Item -LiteralPath $sourcePath -Destination $destinationPath -Force
}}
function Sync-DesktopSessionState() {{
    if (-not $sessionRoot) {{
        Write-Log 'Desktop session root was not detected.'
        return
    }}
    Write-Log ("Desktop session root: " + $sessionRoot)
    Write-Log ("Backup destination: " + $(if ($backupDestination) {{ $backupDestination }} else {{ '<none>' }}))
    Write-Log ("Restore source: " + $(if ($restoreSource) {{ $restoreSource }} else {{ '<none>' }}))
    if (-not (Test-Path -LiteralPath $sessionRoot)) {{
        Write-Log ("Desktop session root is missing: " + $sessionRoot)
        return
    }}
    if ($backupDestination) {{
        New-Item -ItemType Directory -Path $backupDestination -Force | Out-Null
        foreach ($relativePath in $sessionEntries) {{
            try {{
                Clear-SessionEntry $backupDestination $relativePath
                Copy-SessionEntry $sessionRoot $backupDestination $relativePath
                Write-Log ("Backed up session entry: " + $relativePath)
            }} catch {{
                Write-Log ("Failed to back up session entry " + $relativePath + ": " + $_.Exception.Message)
            }}
        }}
        Write-Log ("Backed up desktop session state to " + $backupDestination)
    }}
    if ($restoreSource) {{
        if (-not (Test-Path -LiteralPath $restoreSource)) {{
            Write-Log ("Restore source is missing; leaving the current desktop session in place: " + $restoreSource)
            return
        }}
        $restoreErrors = @()
        foreach ($relativePath in $sessionEntries) {{
            try {{
                Clear-SessionEntry $sessionRoot $relativePath
                Copy-SessionEntry $restoreSource $sessionRoot $relativePath
                Write-Log ("Restored session entry: " + $relativePath)
            }} catch {{
                $restoreErrors += $relativePath
                Write-Log ("Failed to restore session entry " + $relativePath + ": " + $_.Exception.Message)
            }}
        }}
        if ($restoreErrors.Count -gt 0) {{
            throw ('Failed to restore desktop session entries: ' + ($restoreErrors -join ', '))
        }}
        Write-Log ("Restored desktop session state from " + $restoreSource)
    }}
}}
""".strip()
    return script + "\n" + RESTART_FLOW.replace("__DELAY_MS__", str(delay_ms))



def encode_powershell_script(script: str) -> str:
    return base64.b64encode(script.encode("utf-16le")).decode("ascii")


def restart_codex_desktop(
    delay_seconds: float = DEFAULT_RESTART_DELAY_SECONDS,
    session_root: Path | None = None,
    backup_destination: Path | None = None,
    restore_source: Path | None = None,
    target_auth_path: Path | None = None,
    ambient_auth_path: Path | None = None,
) -> subprocess.Popen:
    ensure_directories()
    RESTART_STATUS_PATH.unlink(missing_ok=True)
    RESTART_SCRIPT_PATH.write_text(
        build_restart_script(
            delay_seconds,
            session_root=session_root,
            backup_destination=backup_destination,
            restore_source=restore_source,
            target_auth_path=target_auth_path,
            ambient_auth_path=ambient_auth_path,
        ),
        encoding="utf-8-sig",
    )

    try:
        return _launch_hidden_powershell(RESTART_SCRIPT_PATH)
    except OSError as error:
        raise CodexDesktopControlError("Failed to restart Codex Desktop.") from error


def _powershell_literal_path(path: Path) -> str:
    normalized_path = str(PureWindowsPath(str(path)))
    return "'" + normalized_path.replace("'", "''") + "'"


def _powershell_path_or_null(path: Path | None) -> str:
    if path is None:
        return "$null"
    return _powershell_literal_path(path)


def _powershell_string_array(values: tuple[str, ...]) -> str:
    quoted = ", ".join("'" + value.replace("'", "''") + "'" for value in values)
    return f"@({quoted})"


def build_restart_command(script_path: Path = RESTART_SCRIPT_PATH) -> list[str]:
    powershell_exe = str(PureWindowsPath(str(POWERSHELL_EXE)))
    normalized_script_path = str(PureWindowsPath(str(script_path)))
    return [
        powershell_exe,
        "-NoProfile",
        "-NonInteractive",
        "-WindowStyle",
        "Hidden",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        normalized_script_path,
    ]


def _launch_hidden_powershell(script_path: Path) -> subprocess.Popen:
    # Keep the helper completely detached from the interactive desktop.  The
    # old launcher could briefly create a console window on some Windows 11
    # builds even though PowerShell received -WindowStyle Hidden.
    startup_info = subprocess.STARTUPINFO()
    startup_info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup_info.wShowWindow = 0  # SW_HIDE

    creation_flags = 0
    creation_flags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
    creation_flags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

    return subprocess.Popen(
        build_restart_command(script_path),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        startupinfo=startup_info,
        creationflags=creation_flags,
        close_fds=True,
    )


RESTART_FLOW = r'''
function Test-GuiExecutable([string]$path) {
    if (-not $path -or -not (Test-Path -LiteralPath $path -PathType Leaf)) { return $false }
    $stream = $null
    $reader = $null
    try {
        $stream = [System.IO.File]::Open($path, 'Open', 'Read', 'ReadWrite')
        $reader = New-Object System.IO.BinaryReader($stream)
        if ($reader.ReadUInt16() -ne 0x5A4D -or $stream.Length -lt 64) { return $false }
        $stream.Position = 0x3C
        $offset = $reader.ReadInt32()
        if ($offset -lt 64 -or $offset + 94 -gt $stream.Length) { return $false }
        $stream.Position = $offset
        if ($reader.ReadUInt32() -ne 0x00004550) { return $false }
        $stream.Position = $offset + 24
        $magic = $reader.ReadUInt16()
        if ($magic -ne 0x10B -and $magic -ne 0x20B) { return $false }
        $stream.Position = $offset + 24 + 68
        return $reader.ReadUInt16() -eq 2
    } catch { return $false }
    finally {
        if ($reader) { $reader.Dispose() }
        elseif ($stream) { $stream.Dispose() }
    }
}
function Test-DesktopPath([string]$path) {
    if (-not $path) { return $false }
    if ($path -match '(?i)\\(?:resources|bin)\\') { return $false }
    $leaf = [System.IO.Path]::GetFileName($path)
    if ($leaf -ieq 'ChatGPT.exe') {
        if ($path -notmatch '(?i)\\OpenAI\.Codex_[^\\]+\\app\\ChatGPT\.exe$') { return $false }
    } elseif ($leaf -ine 'Codex.exe') { return $false }
    return Test-GuiExecutable $path
}
function Write-RestartStatus([string]$state, [string]$detail) {
    @{ state = $state; detail = $detail; updatedAt = (Get-Date).ToUniversalTime().ToString('o') } |
        ConvertTo-Json -Compress | Set-Content -LiteralPath $statusPath -Encoding UTF8
}
function Invoke-HiddenTaskkill([int]$processId) {
    $info = New-Object System.Diagnostics.ProcessStartInfo
    $info.FileName = Join-Path $env:WINDIR 'System32\taskkill.exe'
    $info.Arguments = '/PID ' + $processId + ' /F'
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $process = [System.Diagnostics.Process]::Start($info)
    $out = $process.StandardOutput.ReadToEnd()
    $err = $process.StandardError.ReadToEnd()
    $process.WaitForExit()
}
try {
    Write-Log 'Restart requested.'
    Write-RestartStatus 'starting' 'Locating Codex Desktop'
    $allProcesses = @(Get-CimInstance Win32_Process)
    $mainProcess = $allProcesses | Where-Object {
        $_.CommandLine -notmatch '--type=' -and (Test-DesktopPath $_.ExecutablePath)
    } | Sort-Object CreationDate | Select-Object -First 1
    $launcherPath = $mainProcess.ExecutablePath
    if (-not $launcherPath) {
        $package = Get-AppxPackage | Where-Object {
            $_.Name -eq 'OpenAI.Codex' -or $_.PackageFamilyName -like 'OpenAI.Codex_*'
        } | Sort-Object Version -Descending | Select-Object -First 1
        if ($package -and $package.InstallLocation) {
            $manifestPath = Join-Path $package.InstallLocation 'AppxManifest.xml'
            if (Test-Path -LiteralPath $manifestPath) {
                [xml]$manifest = Get-Content -LiteralPath $manifestPath -Raw
                $application = $manifest.SelectSingleNode("//*[local-name()='Application' and @Id='App']")
                if ($application) {
                    $candidate = Join-Path $package.InstallLocation $application.GetAttribute('Executable')
                    if (Test-DesktopPath $candidate) { $launcherPath = $candidate }
                }
            }
            if (-not $launcherPath) {
                foreach ($leaf in @('ChatGPT.exe', 'Codex.exe')) {
                    $candidate = Join-Path $package.InstallLocation ('app\' + $leaf)
                    if (Test-DesktopPath $candidate) { $launcherPath = $candidate; break }
                }
            }
        }
    }
    if (-not $launcherPath) { throw 'Unable to locate a valid Codex Desktop GUI executable.' }
    Write-Log ('Using GUI launcher path: ' + $launcherPath)
    $desktopProcesses = @($allProcesses | Where-Object { $_.ExecutablePath -ieq $launcherPath })
    if ($diagnosticOnly) {
        @{launcherPath=$launcherPath; desktopProcessIds=@($desktopProcesses | ForEach-Object { $_.ProcessId }); gui=$true} | ConvertTo-Json -Compress
        exit 0
    }
    Start-Sleep -Milliseconds __DELAY_MS__
    Write-RestartStatus 'stopping' 'Closing Codex Desktop'
    # Stop only the validated GUI and its own Codex backend children. Never
    # terminate unrelated terminals or another ChatGPT application by name.
    $guiIds = @($desktopProcesses | ForEach-Object { $_.ProcessId })
    $backendProcesses = @($allProcesses | Where-Object {
        $_.ParentProcessId -in $guiIds -and $_.Name -ieq 'codex.exe' -and
        ($_.ExecutablePath -match '(?i)\\OpenAI\\Codex\\bin\\' -or $_.ExecutablePath -match '(?i)\\resources\\codex\.exe$')
    })
    foreach ($process in @($backendProcesses) + @($desktopProcesses)) {
        try { Invoke-HiddenTaskkill $process.ProcessId } catch { Write-Log ('Stop attempt failed: ' + $_.Exception.Message) }
    }
    $deadline = (Get-Date).AddSeconds(12)
    do {
        $remaining = @(Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -ieq $launcherPath })
        if ($remaining.Count -eq 0) { break }
        foreach ($process in $remaining) {
            try { Invoke-HiddenTaskkill $process.ProcessId } catch {}
        }
        Start-Sleep -Milliseconds 250
    } while ((Get-Date) -lt $deadline)
    if (@(Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -ieq $launcherPath }).Count -gt 0) {
        throw 'Codex Desktop did not exit. Session restore and relaunch were stopped.'
    }
    Write-Log 'All Codex Desktop GUI processes exited.'
    Write-RestartStatus 'restoring' 'Applying account session'
    if ($targetAuthPath -and $ambientAuthPath) {
        # Reapply after the old GUI has stopped to avoid its exit-time writes.
        $authTemp = $ambientAuthPath + '.codexcontrol.tmp'
        Copy-Item -LiteralPath $targetAuthPath -Destination $authTemp -Force
        Move-Item -LiteralPath $authTemp -Destination $ambientAuthPath -Force
    }
    Sync-DesktopSessionState
    Start-Sleep -Milliseconds 350
    $launchInfo = New-Object System.Diagnostics.ProcessStartInfo
    $launchInfo.FileName = $launcherPath
    $launchInfo.WorkingDirectory = [System.IO.Path]::GetDirectoryName($launcherPath)
    $launchInfo.UseShellExecute = $false
    $launchInfo.CreateNoWindow = $true
    $desktop = [System.Diagnostics.Process]::Start($launchInfo)
    $deadline = (Get-Date).AddSeconds(10)
    do {
        Start-Sleep -Milliseconds 250
        $running = @(Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -ieq $launcherPath })
        if ($running.Count -gt 0) { break }
    } while ((Get-Date) -lt $deadline)
    if ($running.Count -eq 0) { throw 'Codex Desktop did not relaunch.' }
    Write-Log 'Codex Desktop GUI relaunched.'
    Write-RestartStatus 'complete' 'Codex Desktop restarted'
} catch {
    Write-Log ('Restart failed: ' + $_.Exception.Message)
    Write-RestartStatus 'failed' $_.Exception.Message
    exit 1
}

'''
