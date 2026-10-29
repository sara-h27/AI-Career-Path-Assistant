@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Run 01_setup.cmd first.
  pause
  exit /b 1
)
echo Open http://127.0.0.1:8501 in your browser.
.venv\Scripts\python.exe -m streamlit run app.py
pause
