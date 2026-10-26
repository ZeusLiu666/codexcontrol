[CmdletBinding()]
param(
    [string]$Python = 'python.exe',
    [ValidatePattern('^\d+\.\d+\.\d+$')][string]$Version = '1.2.9',
    [string]$InnoSetupCompiler = '',
    [string]$OutputDirectory = '',
    [switch]$InstallDependencies,
    [switch]$SkipBuild,
    [switch]$Clean
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'tools\release-support.ps1')
$windowsRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$repoRoot = Split-Path -Parent $windowsRoot
$pythonExecutable = Resolve-ReleaseCommand $Python
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) { $OutputDirectory = Join-Path $repoRoot 'ReleaseArtifacts' }
$releaseRoot = [IO.Path]::GetFullPath($OutputDirectory)
if ([string]::IsNullOrWhiteSpace($InnoSetupCompiler)) {
    $compilerCommand = Get-Command 'ISCC.exe' -ErrorAction SilentlyContinue
    if ($compilerCommand) { $InnoSetupCompiler = $compilerCommand.Source }
    foreach ($candidate in @(
        (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe')
    )) {
        if ([string]::IsNullOrWhiteSpace($InnoSetupCompiler) -and (Test-Path -LiteralPath $candidate -PathType Leaf)) { $InnoSetupCompiler = $candidate }
    }
}
if ([string]::IsNullOrWhiteSpace($InnoSetupCompiler)) { throw 'Inno Setup 6.5.3 is required; pass -InnoSetupCompiler with the path to ISCC.exe.' }
$compiler = Resolve-ReleaseCommand $InnoSetupCompiler
# ISCC 6.5.3 has an intentionally zeroed FileVersion; pin the official binary.
$compilerHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $compiler).Hash
if ($compilerHash -ne 'BEE85A645A2C4E1BE05024815CF80DBF0B52343EAAD1F8330C85F63DF0D0FB1E') { throw 'Use the official pinned Inno Setup 6.5.3 compiler.' }
if (-not $SkipBuild) {
    & (Join-Path $windowsRoot 'build.ps1') -Python $pythonExecutable -Version $Version -InstallDependencies:$InstallDependencies -Clean:$Clean
}
$exe = Join-Path $windowsRoot 'dist\CodexControl.exe'
if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw 'Build CodexControl.exe before packaging.' }
New-Item -ItemType Directory -Path $releaseRoot -Force | Out-Null
$packageRoot = Join-Path $windowsRoot 'build\windows-package'
Remove-ReleaseDirectory $packageRoot $windowsRoot
New-Item -ItemType Directory -Path $packageRoot -Force | Out-Null
# Only these named files may enter the release. Never copy a source tree/profile.
$packageFiles = [ordered]@{
    'CodexControl.exe' = $exe
    'install.ps1' = (Join-Path $windowsRoot 'install.ps1')
    'README.md' = (Join-Path $windowsRoot 'README.md')
    'LICENSE' = (Join-Path $repoRoot 'LICENSE')
}
foreach ($name in $packageFiles.Keys) {
    Copy-Item -LiteralPath $packageFiles[$name] -Destination (Join-Path $packageRoot $name) -Force
}
Invoke-ReleaseCommand $pythonExecutable @((Join-Path $windowsRoot 'tools\release_tools.py'), 'third-party-notices', '--output', (Join-Path $packageRoot 'THIRD_PARTY_NOTICES.txt'))
$baseName = "CodexControl-$Version-windows-x64"
$zipPath = Join-Path $releaseRoot "$baseName-portable.zip"
$setupPath = Join-Path $releaseRoot "$baseName-Setup.exe"
Invoke-ReleaseCommand $pythonExecutable @((Join-Path $windowsRoot 'tools\release_tools.py'), 'portable-zip', '--source', $packageRoot, '--output', $zipPath)
Get-ChildItem -LiteralPath $packageRoot -File | ForEach-Object { $_.LastWriteTimeUtc = [datetime]'2026-01-01T00:00:00Z' }
Invoke-ReleaseCommand $compiler @('/Qp', "/DAppVersion=$Version", "/DPayloadDir=$packageRoot", "/O$releaseRoot", "/F$baseName-Setup", (Join-Path $windowsRoot 'CodexControl.iss'))
if (-not (Test-Path -LiteralPath $setupPath -PathType Leaf)) { throw 'Inno Setup did not produce the expected installer.' }
$hashPath = Join-Path $releaseRoot 'SHA256SUMS-windows.txt'
$hashLines = foreach ($artifact in @($setupPath, $zipPath)) {
    '{0}  {1}' -f (Get-FileHash -Algorithm SHA256 -LiteralPath $artifact).Hash.ToLowerInvariant(), (Split-Path -Leaf $artifact)
}
[IO.File]::WriteAllText($hashPath, ($hashLines -join "`n") + "`n", [Text.UTF8Encoding]::new($false))
Write-Output $setupPath
Write-Output $zipPath
Write-Output $hashPath
