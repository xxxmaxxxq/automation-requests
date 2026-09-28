@echo off
setlocal

set "SUBJECT=TOYOTA YARIS A123BC777"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0transfer_iphone_photos.ps1" -Subject "%SUBJECT%" -Count 3 -Move

pause
