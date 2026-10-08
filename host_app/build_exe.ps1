[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $scriptDir

$venvDir = Join-Path $scriptDir ".venv-build"
$venvPython = Join-Path $venvDir "Scripts\python.exe"

if (-not (Test-Path -LiteralPath $venvPython)) {
    $bootstrap = Get-Command python -ErrorAction SilentlyContinue
    if ($null -eq $bootstrap) {
        throw "Python 3 was not found. Install Python 3.11-3.13 and retry."
    }
    Write-Host "[1/6] Creating isolated build environment: $venvDir"
    & $bootstrap.Source -m venv $venvDir
    if ($LASTEXITCODE -ne 0) { throw "Failed to create the virtual environment." }
} else {
    Write-Host "[1/6] Reusing isolated build environment: $venvDir"
}

Write-Host "[2/6] Installing pinned runtime and packaging dependencies"
& $venvPython -m pip install --disable-pip-version-check -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }

Write-Host "[3/6] Running automated tests"
& $venvPython -m pytest -q tests
if ($LASTEXITCODE -ne 0) { throw "Tests failed; packaging was stopped." }

# Exercise both widget trees before packaging.  These runs close themselves
# and catch Tk layout/tab-switch regressions that protocol-only tests cannot.
& $venvPython main.py --demo can --smoke-test
if ($LASTEXITCODE -ne 0) { throw "CAN GUI smoke test failed; packaging was stopped." }
& $venvPython main.py --demo bmi --smoke-test
if ($LASTEXITCODE -ne 0) { throw "BMI GUI smoke test failed; packaging was stopped." }

Write-Host "[4/6] Building Windows onedir application"
& $venvPython -m PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    --windowed `
    --name RA8D1_EDGE_AI_STUDIO `
    --manifest ra8d1_edge_ai_studio.manifest `
    --collect-submodules serial `
    --add-data "LICENSE;." `
    --add-data "README.md;." `
    --add-data "OPEN_SOURCE_REVIEW.md;." `
    --add-data "THIRD_PARTY_NOTICES.md;." `
    --add-data "samples;samples" `
    --distpath dist `
    --workpath build `
    main.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller packaging failed." }

$exePath = Join-Path $scriptDir "dist\RA8D1_EDGE_AI_STUDIO\RA8D1_EDGE_AI_STUDIO.exe"
if (-not (Test-Path -LiteralPath $exePath)) {
    throw "Packaging completed without the expected executable: $exePath"
}

Write-Host "[5/6] Creating portable ZIP"
# Keep human-readable operation/licensing files beside the EXE as well as in
# PyInstaller's internal data directory.  Users should not need to hunt inside
# implementation folders for wiring and launch instructions.
$distDir = Join-Path $scriptDir "dist\RA8D1_EDGE_AI_STUDIO"
foreach ($document in @("README.md", "LICENSE", "OPEN_SOURCE_REVIEW.md", "THIRD_PARTY_NOTICES.md")) {
    Copy-Item -LiteralPath (Join-Path $scriptDir $document) -Destination $distDir -Force
}
$zipPath = Join-Path $scriptDir "dist\RA8D1_EDGE_AI_STUDIO_Windows_x64.zip"
Compress-Archive -Path (Join-Path $scriptDir "dist\RA8D1_EDGE_AI_STUDIO\*") `
    -DestinationPath $zipPath `
    -CompressionLevel Optimal `
    -Force
if (-not (Test-Path -LiteralPath $zipPath)) {
    throw "ZIP packaging failed: $zipPath"
}

Write-Host "[6/6] Done"
Write-Host "Executable: $exePath"
Write-Host "Portable ZIP: $zipPath"
Write-Host "Distribute the complete dist\RA8D1_EDGE_AI_STUDIO directory, not only the EXE."
