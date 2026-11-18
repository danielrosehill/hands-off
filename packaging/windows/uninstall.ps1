# Remove Hands Off for the current user. Settings in %APPDATA%\HandsOff are kept.
Get-Process HandsOff -ErrorAction SilentlyContinue | Stop-Process -Force
foreach ($dir in @([Environment]::GetFolderPath("Programs"), [Environment]::GetFolderPath("Startup"))) {
    Remove-Item (Join-Path $dir "Hands Off.lnk") -ErrorAction SilentlyContinue
}
Remove-Item (Join-Path $env:LOCALAPPDATA "Programs\HandsOff") -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "Hands Off removed."
