@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  python -m venv .venv
) else (
  py -3 -m venv .venv
)
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto failed
if not exist .env copy .env.example .env >nul
echo Setup complete. Edit .env for API mode, then run 02_run.cmd.
pause
exit /b 0
:failed
echo Setup failed. Install Python 3.11 or newer and check internet access.
pause
exit /b 1
