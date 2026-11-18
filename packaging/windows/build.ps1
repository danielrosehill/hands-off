# Build the Windows release zip: dist\HandsOff-<version>-windows.zip
# Needs Python 3.10+ and uv. Usage: powershell -File packaging\windows\build.ps1
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $root
$version = (Select-String -Path pyproject.toml -Pattern '^version = "(.+)"').Matches[0].Groups[1].Value
uv run --no-project --python 3.12 --with pyinstaller --with PyQt5 pyinstaller `
    --noconfirm --clean --windowed --name HandsOff `
    --icon "$root\packaging\windows\handsoff.ico" `
    --add-data "$root\handsoff\resources;handsoff\resources" `
    --paths "$root" `
    --distpath build\win --workpath build\pyi --specpath build `
    "$root\packaging\windows\handsoff_main.py"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed ($LASTEXITCODE)" }
$stage = "build\HandsOff-$version-windows"
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory $stage | Out-Null
Copy-Item build\win\HandsOff $stage -Recurse
Copy-Item packaging\windows\install.ps1, packaging\windows\uninstall.ps1 $stage
New-Item -ItemType Directory dist -Force | Out-Null
Compress-Archive -Path "$stage\*" -DestinationPath "dist\HandsOff-$version-windows.zip" -Force
Write-Host "Built dist\HandsOff-$version-windows.zip"
