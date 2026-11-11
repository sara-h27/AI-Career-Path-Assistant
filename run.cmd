@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo First run: creating virtual environment and installing requirements...
  py -3 -m venv .venv 2>nul || python -m venv .venv
  .venv\Scripts\python.exe -m pip install -r requirements.txt || goto failed
)
if not exist .env copy .env.example .env >nul
echo Open http://127.0.0.1:8000
.venv\Scripts\python.exe -m uvicorn server:app --port 8000
exit /b 0
:failed
echo Setup failed. Install Python 3.11+ and check internet access.
exit /b 1
