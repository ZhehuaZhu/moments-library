@echo off
setlocal
cd /d "%~dp0"

echo Opening Android project in Android Studio...
call npm run cap:open:android
if errorlevel 1 (
  echo.
  echo Open failed.
  pause
  exit /b 1
)

echo.
echo Android project opened.
pause
