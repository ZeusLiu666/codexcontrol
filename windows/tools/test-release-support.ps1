$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'release-support.ps1')
$testRoot = Join-Path ([IO.Path]::GetFullPath($env:TEMP)) ('CodexControl-release-tests-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testRoot | Out-Null
try {
    # Reproduce hosted runners with more than one same-named executable on PATH.
    # Only resolve these copies; never execute the synthetic command name.
    $firstTools = Join-Path $testRoot 'first-tools'
    $secondTools = Join-Path $testRoot 'second-tools'
    New-Item -ItemType Directory -Path $firstTools, $secondTools | Out-Null
    $whereExecutable = (Get-Command 'where.exe' -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
    $probeName = 'codexcontrol-release-probe.exe'
    $firstProbe = Join-Path $firstTools $probeName
    Copy-Item -LiteralPath $whereExecutable -Destination $firstProbe
    Copy-Item -LiteralPath $whereExecutable -Destination (Join-Path $secondTools $probeName)
    $previousProcessPath = $env:PATH
    try {
        $env:PATH = "$firstTools;$secondTools;$previousProcessPath"
        $duplicateCommands = @(Get-Command $probeName -CommandType Application -ErrorAction Stop)
        if ($duplicateCommands.Count -ne 2) { throw 'Duplicate-PATH fixture did not reproduce two command matches.' }
        $resolvedCommand = Resolve-ReleaseCommand $probeName
        if ($resolvedCommand -isnot [string] -or $resolvedCommand -ne $firstProbe) {
            throw 'Command resolution must return one string using the first PATH match.'
        }
        $resolvedAgain = Resolve-ReleaseCommand $resolvedCommand
        if ($resolvedAgain -isnot [string] -or $resolvedAgain -ne $firstProbe) {
            throw 'Nested command resolution must preserve an explicit executable path.'
        }
    } finally {
        $env:PATH = $previousProcessPath
    }
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
    # The exit-7 fixture above is an expected failure. Do not leak its status to
    # the GitHub Actions PowerShell wrapper after the checks have passed.
    $global:LASTEXITCODE = 0
    Write-Output 'Release support checks passed: duplicate-PATH resolution, containment, reparse points, native failures.'
} finally {
    Remove-ReleaseDirectory $testRoot ([IO.Path]::GetFullPath($env:TEMP))
}
