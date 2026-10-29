@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Run 01_setup.cmd first.
  pause
  exit /b 1
)
.venv\Scripts\python.exe -m unittest discover -s tests -v
set "test_result=%errorlevel%"
pause
exit /b %test_result%
