@echo off
setlocal

cd /d "%~dp0.."

set "SUBJECT="
set /p SUBJECT=Enter subject, for example KIA QLE SPORTAGE A123BC777: 

call "%CD%\start_work_browser_9222.bat"
timeout /t 3 /nobreak >nul

python "%CD%\create_request copy 2.py" --site-only --subject "%SUBJECT%"
pause
