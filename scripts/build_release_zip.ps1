# Build release ZIP from project root (Windows). Mirrors build_release_zip.sh.
# Usage: build_release_zip.ps1 [-Target release|source|all]
param(
    [ValidateSet("release", "source", "all")]
    [string]$Target = "release"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$Version = & python -c "from bot.version import __version__; print(__version__)"
$OutDir = Join-Path $Root "dist"
if (-not (Test-Path $OutDir)) { New-Item -ItemType Directory -Path $OutDir | Out-Null }

function Build-ReleaseZip {
    $ZipPath = Join-Path $OutDir "resellerbot-$Version.zip"
    if (Test-Path $ZipPath) { Remove-Item -Force $ZipPath }

    $IncludeDirs = @("bot", "db", "services", "xui", "deploy", "scripts")
    $IncludeFiles = @(
        "requirements.txt", "RELEASE.json", "README.md", "CHANGELOG.md", "LICENSE"
    )

    $TempDir = Join-Path $env:TEMP "resellerbot-release-$Version"
    if (Test-Path $TempDir) { Remove-Item -Recurse -Force $TempDir }
    New-Item -ItemType Directory -Path $TempDir | Out-Null

    function Should-SkipFile($RelativePath) {
        $p = $RelativePath -replace '\\', '/'
        if ($p -match '/__pycache__/') { return $true }
        if ($p -match '\.pyc$') { return $true }
        if ($p -match '\.py[cod]$') { return $true }
        return $false
    }

    foreach ($dir in $IncludeDirs) {
        $src = Join-Path $Root $dir
        if (-not (Test-Path $src)) { continue }
        Get-ChildItem -Path $src -Recurse -File | ForEach-Object {
            $rel = $_.FullName.Substring($Root.Length + 1)
            if (Should-SkipFile $rel) { return }
            $dest = Join-Path $TempDir $rel
            $destDir = Split-Path -Parent $dest
            if (-not (Test-Path $destDir)) { New-Item -ItemType Directory -Path $destDir -Force | Out-Null }
            Copy-Item $_.FullName $dest
        }
    }

    foreach ($file in $IncludeFiles) {
        $src = Join-Path $Root $file
        if (Test-Path $src) { Copy-Item $src (Join-Path $TempDir $file) }
    }

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::CreateFromDirectory($TempDir, $ZipPath)

    Remove-Item -Recurse -Force $TempDir
    Write-Host "Created $ZipPath"
}

function Build-SourceZip {
    $ZipPath = Join-Path $OutDir "resellerbot-$Version-source.zip"
    if (Test-Path $ZipPath) { Remove-Item -Force $ZipPath }
    & git archive --format=zip "--prefix=resellerbot-$Version/" HEAD -o $ZipPath
    Write-Host "Created $ZipPath"
}

switch ($Target) {
    "release" { Build-ReleaseZip }
    "source" { Build-SourceZip }
    "all" {
        Build-ReleaseZip
        Build-SourceZip
    }
}
