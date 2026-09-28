@echo off
setlocal

cd /d "%~dp0.."

python "%CD%\training_site.py"
pause
