@echo off
setlocal
cd /d "%~dp0"

echo Syncing all module workspaces from the current CODE-preview branch...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\sync-all-modules.ps1"
if errorlevel 1 (
  echo.
  echo Sync failed.
  pause
  exit /b 1
)

echo.
echo All module workspaces synced successfully.
pause
