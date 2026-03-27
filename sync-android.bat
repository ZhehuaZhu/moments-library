@echo off
setlocal
cd /d "%~dp0"

echo Syncing Android app shell...
call npm run cap:sync
if errorlevel 1 (
  echo.
  echo Sync failed.
  pause
  exit /b 1
)

echo.
echo Android shell synced successfully.
pause
