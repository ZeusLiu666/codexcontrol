[CmdletBinding()]
param(
    [string]$Python = 'python.exe',
    [ValidatePattern('^\d+\.\d+\.\d+$')][string]$Version = '1.2.8',
    [switch]$InstallDependencies,
    [switch]$Clean
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'tools\release-support.ps1')
$windowsRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$pythonExecutable = Resolve-ReleaseCommand $Python
$workDir = Join-Path $windowsRoot 'build'
$distDir = Join-Path $windowsRoot 'dist'
if ($Clean) {
    Remove-ReleaseDirectory $workDir $windowsRoot
    Remove-ReleaseDirectory $distDir $windowsRoot
}
New-Item -ItemType Directory -Path $workDir -Force | Out-Null
$requirements = Join-Path $windowsRoot 'requirements-build.txt'
if ($InstallDependencies) {
    Invoke-ReleaseCommand $pythonExecutable @('-m', 'pip', 'install', '--disable-pip-version-check', '-r', $requirements)
}
Invoke-ReleaseCommand $pythonExecutable @((Join-Path $windowsRoot 'tools\release_tools.py'), 'verify-dependencies', '--requirements', $requirements)
Invoke-ReleaseCommand $pythonExecutable @((Join-Path $windowsRoot 'tools\generate_app_icon.py'))
$versionResource = Join-Path $workDir 'version-info.txt'
Invoke-ReleaseCommand $pythonExecutable @((Join-Path $windowsRoot 'tools\release_tools.py'), 'version-resource', '--version', $Version, '--output', $versionResource)
$previousEpoch = [Environment]::GetEnvironmentVariable('SOURCE_DATE_EPOCH', 'Process')
$previousResource = [Environment]::GetEnvironmentVariable('CODEXCONTROL_VERSION_RESOURCE', 'Process')
try {
    # Fixed timestamps remove the build machine's time from PE metadata.
    $env:SOURCE_DATE_EPOCH = '1767225600'
    $env:CODEXCONTROL_VERSION_RESOURCE = $versionResource
    Invoke-ReleaseCommand $pythonExecutable @('-m', 'PyInstaller', '--noconfirm', '--clean', '--distpath', $distDir, '--workpath', $workDir, (Join-Path $windowsRoot 'CodexControl.spec'))
} finally {
    [Environment]::SetEnvironmentVariable('SOURCE_DATE_EPOCH', $previousEpoch, 'Process')
    [Environment]::SetEnvironmentVariable('CODEXCONTROL_VERSION_RESOURCE', $previousResource, 'Process')
}
$builtExe = Join-Path $distDir 'CodexControl.exe'
if (-not (Test-Path -LiteralPath $builtExe -PathType Leaf)) { throw 'PyInstaller did not produce CodexControl.exe.' }
Write-Output "Built: $builtExe"
