# Build the Windows x86_64 release natively on Windows.
#
# Run from a PowerShell prompt in the repository root:
#   powershell -ExecutionPolicy Bypass -File .\build_windows.ps1
#
# Needs Python 3.12 from python.org, installed with the "py launcher" (the default).
# Everything else is fetched into a private virtual environment under .winbuild\.
# The result is release\MapGen-Portable-Windows-x86_64\MapGen.exe with its _internal\
# folder beside it - keep the whole folder together.
#
# This is the same sequence build_windows_from_linux.sh runs under Wine: create a
# virtual environment, install the pinned build requirements, freeze mapgen_portable.spec.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Build = Join-Path $Root ".winbuild"
$Venv = Join-Path $Build "venv"
$Python = Join-Path $Venv "Scripts\python.exe"

New-Item -ItemType Directory -Force -Path $Build | Out-Null
if (-not (Test-Path $Python)) {
    Write-Host "Creating the build environment with Python 3.12..."
    & py -3.12 -m venv $Venv
    if ($LASTEXITCODE -ne 0) { throw "Python 3.12 is required (install it from python.org with the py launcher)." }
}
& $Python -m pip install --disable-pip-version-check -q -r (Join-Path $Root "requirements-build.txt")
if ($LASTEXITCODE -ne 0) { throw "pip could not install the build requirements." }

# A rebuild must never destroy the user's generated worlds or settings that live
# inside the release folder: stash them and restore after the build.
$Release = Join-Path $Root "release\MapGen-Portable-Windows-x86_64"
$Keep = Join-Path $Build "keep"
Remove-Item -Recurse -Force $Keep -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $Keep | Out-Null
if (Test-Path (Join-Path $Release "output")) { Move-Item (Join-Path $Release "output") (Join-Path $Keep "output") }
if (Test-Path (Join-Path $Release "portable-settings.json")) { Move-Item (Join-Path $Release "portable-settings.json") $Keep }
Remove-Item -Recurse -Force $Release -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path (Join-Path $Root "release") | Out-Null

& $Python -m PyInstaller --noconfirm --clean `
    --distpath (Join-Path $Root "release") `
    --workpath (Join-Path $Build "pyinstaller-work") `
    (Join-Path $Root "mapgen_portable.spec")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed; see the messages above." }

if (Test-Path (Join-Path $Keep "output")) { Move-Item (Join-Path $Keep "output") (Join-Path $Release "output") }
else { New-Item -ItemType Directory -Force -Path (Join-Path $Release "output") | Out-Null }
if (Test-Path (Join-Path $Keep "portable-settings.json")) { Move-Item (Join-Path $Keep "portable-settings.json") $Release }
Copy-Item (Join-Path $Root "README.md") (Join-Path $Release "README.txt")
Copy-Item (Join-Path $Root "LICENSE") (Join-Path $Release "LICENSE.txt")
Copy-Item (Join-Path $Root "THIRD-PARTY-NOTICES.md") (Join-Path $Release "THIRD-PARTY-NOTICES.txt")

$Hash = (Get-FileHash -Algorithm SHA256 (Join-Path $Release "MapGen.exe")).Hash.ToLower()
"$Hash  MapGen-Portable-Windows-x86_64/MapGen.exe" | Set-Content -Encoding ascii (Join-Path $Root "release\MapGen-Portable-Windows-x86_64.sha256")

Write-Host "Portable release: $Release"
