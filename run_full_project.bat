@echo off
setlocal

cd /d "%~dp0"

call "%~dp0start_work_browser_9222.bat"
timeout /t 3 /nobreak >nul

python "%~dp0create_request copy 2.py"
pause
