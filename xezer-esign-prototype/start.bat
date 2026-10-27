@echo off
REM One-command demo start (Windows): builds the frontend and serves everything on http://localhost:8000
cd /d "%~dp0backend"
if not exist .venv python -m venv .venv
call .venv\Scripts\activate.bat
pip install -q -r requirements.txt

cd ..\frontend
if not exist node_modules call npm install
call npm run build

cd ..\backend
echo.
echo   Xezer e-Imza prototype: http://localhost:8000
echo.
python -m uvicorn app.main:app --port 8000