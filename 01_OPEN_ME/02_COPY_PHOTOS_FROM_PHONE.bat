@echo off
setlocal

cd /d "%~dp0.."

set "SUBJECT="
set /p SUBJECT=Enter the same subject/folder name: 

set "COUNT=3"
set /p COUNT=How many latest photos to copy? Press Enter for 3: 
if "%COUNT%"=="" set "COUNT=3"

python "%CD%\create_request copy 2.py" --photos-only --subject "%SUBJECT%" --photo-count %COUNT%
pause
