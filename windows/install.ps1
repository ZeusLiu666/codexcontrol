[CmdletBinding()]
param(
    [string]$SourceExe = '',
    [switch]$EnableStartup,
    [switch]$Launch
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ([string]::IsNullOrWhiteSpace($SourceExe)) {
    $SourceExe = Join-Path $PSScriptRoot 'CodexControl.exe'
    if (-not (Test-Path -LiteralPath $SourceExe -PathType Leaf)) { $SourceExe = Join-Path $PSScriptRoot 'dist\CodexControl.exe' }
}
$SourceExe = (Resolve-Path -LiteralPath $SourceExe -ErrorAction Stop).ProviderPath
$installDir = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'Programs\CodexControl'))
$installedExe = Join-Path $installDir 'CodexControl.exe'
# Stop only an older copy at this exact install destination.
Get-CimInstance Win32_Process -Filter "Name = 'CodexControl.exe'" | Where-Object {
    $_.ExecutablePath -and [string]::Equals($_.ExecutablePath, $installedExe, [StringComparison]::OrdinalIgnoreCase)
} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop }
New-Item -ItemType Directory -Path $installDir -Force | Out-Null
if (-not [string]::Equals($SourceExe, $installedExe, [StringComparison]::OrdinalIgnoreCase)) { Copy-Item -LiteralPath $SourceExe -Destination $installedExe -Force }
foreach ($name in @('LICENSE', 'README.md', 'THIRD_PARTY_NOTICES.txt')) {
    $source = Join-Path (Split-Path -Parent $SourceExe) $name
    if (Test-Path -LiteralPath $source -PathType Leaf) { Copy-Item -LiteralPath $source -Destination (Join-Path $installDir $name) -Force }
}
$shell = New-Object -ComObject WScript.Shell
$shortcutPath = Join-Path ([Environment]::GetFolderPath('Programs')) 'CodexControl.lnk'
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $installedExe
$shortcut.WorkingDirectory = $installDir
$shortcut.IconLocation = $installedExe
$shortcut.Description = 'CodexControl'
$shortcut.Save()
$startupPath = Join-Path ([Environment]::GetFolderPath('Startup')) 'CodexControl.lnk'
if ($EnableStartup) {
    $startup = $shell.CreateShortcut($startupPath)
    $startup.TargetPath = $installedExe
    $startup.Arguments = '--hidden'
    $startup.WorkingDirectory = $installDir
    $startup.IconLocation = $installedExe
    $startup.Save()
} elseif (Test-Path -LiteralPath $startupPath -PathType Leaf) {
    $existing = $shell.CreateShortcut($startupPath)
    if ([string]::Equals($existing.TargetPath, $installedExe, [StringComparison]::OrdinalIgnoreCase)) { Remove-Item -LiteralPath $startupPath -Force }
}
if ($Launch) { Start-Process -FilePath $installedExe -WorkingDirectory $installDir -WindowStyle Hidden }
Write-Output "Installed: $installedExe"
Write-Output 'For a registered uninstaller, use the Setup.exe release.'
