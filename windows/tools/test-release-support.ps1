$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'release-support.ps1')
$testRoot = Join-Path ([IO.Path]::GetFullPath($env:TEMP)) ('CodexControl-release-tests-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testRoot | Out-Null
try {
    $allowedRoot = Join-Path $testRoot 'allowed'
    $sibling = Join-Path $testRoot 'allowed-sibling'
    New-Item -ItemType Directory -Path $allowedRoot, $sibling | Out-Null
    $marker = Join-Path $sibling 'keep.txt'
    Set-Content -LiteralPath $marker -Value 'synthetic fixture'
    foreach ($unsafe in @($allowedRoot, $sibling, (Join-Path $allowedRoot '..\allowed-sibling'))) {
        $rejected = $false
        try { Remove-ReleaseDirectory $unsafe $allowedRoot } catch { $rejected = $true }
        if (-not $rejected) { throw 'Unsafe clean target was accepted.' }
    }
    if (-not (Test-Path -LiteralPath $marker)) { throw 'Sibling fixture was removed.' }
    $safeTarget = Join-Path $allowedRoot 'build'
    New-Item -ItemType Directory -Path $safeTarget | Out-Null
    Set-Content -LiteralPath (Join-Path $safeTarget 'remove.txt') -Value 'fixture'
    Remove-ReleaseDirectory $safeTarget $allowedRoot
    if (Test-Path -LiteralPath $safeTarget) { throw 'Safe clean target was not removed.' }
    $junction = Join-Path $allowedRoot 'redirect'
    New-Item -ItemType Junction -Path $junction -Target $sibling | Out-Null
    $rejected = $false
    try { Remove-ReleaseDirectory $junction $allowedRoot } catch { $rejected = $true }
    if (-not $rejected -or -not (Test-Path -LiteralPath $marker)) { throw 'Reparse-point guard failed.' }
    # Remove this fixture junction itself, never recurse through its target.
    [IO.Directory]::Delete($junction)
    $failureCommand = Join-Path $testRoot 'failure.cmd'
    Set-Content -LiteralPath $failureCommand -Value '@exit /b 7' -Encoding ascii
    $rejected = $false
    try { Invoke-ReleaseCommand $failureCommand @() } catch { $rejected = $true }
    if (-not $rejected) { throw 'Native command failure was ignored.' }
    Write-Output 'Release support checks passed: containment, reparse points, native failures.'
} finally {
    Remove-ReleaseDirectory $testRoot ([IO.Path]::GetFullPath($env:TEMP))
}
