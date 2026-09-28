@echo off
setlocal

set "START_URL=%PORTAL_URL%"
set "DEBUG_PROFILE=%LOCALAPPDATA%\apex-work-browser-9222"

if exist "%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe" (
    start "" "%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe" --remote-debugging-port=9222 --user-data-dir="%DEBUG_PROFILE%" "%START_URL%"
    exit /b
)

if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" (
    start "" "%ProgramFiles%\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="%DEBUG_PROFILE%" "%START_URL%"
    exit /b
)

if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" (
    start "" "%LocalAppData%\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="%DEBUG_PROFILE%" "%START_URL%"
    exit /b
)

echo Не найден Brave или Chrome.
pause
