@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -m venv .venv 2>nul || python -m venv .venv
)
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
echo China News Checker: http://127.0.0.1:5000
".venv\Scripts\python.exe" app.py
pause
