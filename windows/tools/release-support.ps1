function Resolve-ReleaseCommand([string]$Command) {
    $resolved = Get-Command $Command -CommandType Application -ErrorAction Stop | Select-Object -First 1
    return [string]$resolved.Source
}

function Invoke-ReleaseCommand([string]$Executable, [string[]]$Arguments) {
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Build tool failed with exit code $LASTEXITCODE`: $(Split-Path -Leaf $Executable)" }
}

function Remove-ReleaseDirectory([string]$Target, [string]$AllowedRoot) {
    $root = [IO.Path]::GetFullPath($AllowedRoot).TrimEnd('\', '/')
    $fullTarget = [IO.Path]::GetFullPath($Target).TrimEnd('\', '/')
    if (-not $fullTarget.StartsWith($root + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Refusing to remove a directory outside the build workspace.'
    }
    if (-not (Test-Path -LiteralPath $fullTarget)) { return }
    # A junction at any level could redirect deletion outside this tree.
    $current = Get-Item -LiteralPath $fullTarget -Force
    while ($current -and $current.FullName.Length -ge $root.Length) {
        if ($current.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Refusing to clean a reparse point.' }
        $current = $current.Parent
    }
    $resolvedRoot = (Resolve-Path -LiteralPath $root).ProviderPath.TrimEnd('\', '/')
    $resolvedTarget = (Resolve-Path -LiteralPath $fullTarget).ProviderPath
    if (-not $resolvedTarget.StartsWith($resolvedRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Resolved clean target escaped the build workspace.'
    }
    $redirect = Get-ChildItem -LiteralPath $resolvedTarget -Recurse -Force | Where-Object {
        $_.Attributes -band [IO.FileAttributes]::ReparsePoint
    } | Select-Object -First 1
    if ($redirect) { throw 'Refusing to clean a directory containing a reparse point.' }
    Remove-Item -LiteralPath $resolvedTarget -Recurse -Force
}
