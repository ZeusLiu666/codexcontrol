[CmdletBinding()]
param(
    [string]$SourceExe = '',
    [switch]$EnableStartup,
    [switch]$Launch
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Get-CodexControlIconFileName {
    param([string]$ProductVersion)
    # A file version is metadata, not a trusted path segment. Accept only the
    # numeric Windows version form before incorporating it into a filename.
    if ($ProductVersion -cnotmatch '\A[0-9]+\.[0-9]+\.[0-9]+(?:\.[0-9]+)?\z') {
        throw 'The executable ProductVersion must contain three or four numeric components.'
    }
    try { $parsedVersion = [version]$ProductVersion }
    catch { throw 'The executable ProductVersion is not a valid Windows version.' }
    if ($parsedVersion.Major -gt 65535 -or $parsedVersion.Minor -gt 65535 -or
        $parsedVersion.Build -gt 65535 -or $parsedVersion.Revision -gt 65535) {
        throw 'The executable ProductVersion components must not exceed 65535.'
    }
    return "CodexControl-$ProductVersion.ico"
}

if ([string]::IsNullOrWhiteSpace($SourceExe)) {
    $SourceExe = Join-Path $PSScriptRoot 'CodexControl.exe'
    if (-not (Test-Path -LiteralPath $SourceExe -PathType Leaf)) { $SourceExe = Join-Path $PSScriptRoot 'dist\CodexControl.exe' }
}
$SourceExe = (Resolve-Path -LiteralPath $SourceExe -ErrorAction Stop).ProviderPath
$sourceIcon = Join-Path (Split-Path -Parent $SourceExe) 'CodexControl.ico'
$iconFileName = $null
if (Test-Path -LiteralPath $sourceIcon -PathType Leaf) {
    $productVersion = [Diagnostics.FileVersionInfo]::GetVersionInfo($SourceExe).ProductVersion
    $iconFileName = Get-CodexControlIconFileName $productVersion
}
$installDir = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'Programs\CodexControl'))
$installedExe = Join-Path $installDir 'CodexControl.exe'
# Stop only an older copy at this exact install destination.
Get-CimInstance Win32_Process -Filter "Name = 'CodexControl.exe'" | Where-Object {
    $_.ExecutablePath -and [string]::Equals($_.ExecutablePath, $installedExe, [StringComparison]::OrdinalIgnoreCase)
} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop }
New-Item -ItemType Directory -Path $installDir -Force | Out-Null
if (-not [string]::Equals($SourceExe, $installedExe, [StringComparison]::OrdinalIgnoreCase)) { Copy-Item -LiteralPath $SourceExe -Destination $installedExe -Force }
$shortcutIcon = $installedExe
if ($iconFileName) {
    $installedIcon = Join-Path $installDir $iconFileName
    if (-not [string]::Equals($sourceIcon, $installedIcon, [StringComparison]::OrdinalIgnoreCase)) {
        Copy-Item -LiteralPath $sourceIcon -Destination $installedIcon -Force
    }
    $shortcutIcon = $installedIcon
}
foreach ($name in @('LICENSE', 'README.md', 'THIRD_PARTY_NOTICES.txt')) {
    $source = Join-Path (Split-Path -Parent $SourceExe) $name
    if (Test-Path -LiteralPath $source -PathType Leaf) { Copy-Item -LiteralPath $source -Destination (Join-Path $installDir $name) -Force }
}
$shell = New-Object -ComObject WScript.Shell
$shortcutPath = Join-Path ([Environment]::GetFolderPath('Programs')) 'CodexControl.lnk'
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $installedExe
$shortcut.WorkingDirectory = $installDir
$shortcut.IconLocation = "$shortcutIcon,0"
$shortcut.Description = 'CodexControl'
$shortcut.Save()
$startupPath = Join-Path ([Environment]::GetFolderPath('Startup')) 'CodexControl.lnk'
if ($EnableStartup) {
    $startup = $shell.CreateShortcut($startupPath)
    $startup.TargetPath = $installedExe
    $startup.Arguments = '--hidden'
    $startup.WorkingDirectory = $installDir
    $startup.IconLocation = "$shortcutIcon,0"
    $startup.Save()
} elseif (Test-Path -LiteralPath $startupPath -PathType Leaf) {
    $existing = $shell.CreateShortcut($startupPath)
    if ([string]::Equals($existing.TargetPath, $installedExe, [StringComparison]::OrdinalIgnoreCase)) { Remove-Item -LiteralPath $startupPath -Force }
}
if ($Launch) { Start-Process -FilePath $installedExe -WorkingDirectory $installDir -WindowStyle Hidden }
Write-Output "Installed: $installedExe"
Write-Output 'For a registered uninstaller, use the Setup.exe release.'
