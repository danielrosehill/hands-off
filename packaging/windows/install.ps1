# Install Hands Off for the current user (no admin needed).
# Copies the app to %LOCALAPPDATA%\Programs\HandsOff, adds Start-menu and
# Startup shortcuts, and starts it. Run from the extracted release folder:
#   powershell -ExecutionPolicy Bypass -File install.ps1
$ErrorActionPreference = "Stop"
$src  = Split-Path -Parent $MyInvocation.MyCommand.Path
$dest = Join-Path $env:LOCALAPPDATA "Programs\HandsOff"

Get-Process HandsOff -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Milliseconds 500
if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }
New-Item -ItemType Directory -Path $dest | Out-Null
Copy-Item (Join-Path $src "HandsOff\*") $dest -Recurse
Copy-Item (Join-Path $src "uninstall.ps1") $dest

$exe   = Join-Path $dest "HandsOff.exe"
$shell = New-Object -ComObject WScript.Shell
foreach ($dir in @([Environment]::GetFolderPath("Programs"), [Environment]::GetFolderPath("Startup"))) {
    $lnk = $shell.CreateShortcut((Join-Path $dir "Hands Off.lnk"))
    $lnk.TargetPath = $exe
    $lnk.WorkingDirectory = $dest
    $lnk.Description = "Toddler-proof keyboard & mouse lock"
    $lnk.Save()
}
Start-Process $exe
Write-Host "Hands Off installed to $dest and started (tray icon). It will start at sign-in."
