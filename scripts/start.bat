@echo off
REM Start API using the venv Python; no manual activation required.
SETLOCAL
set PY=.\.venv\Scripts\python
if not exist "%PY%" (
  echo [ERROR] .venv\Scripts\python not found. Create venv first: py -3.10 -m venv .venv
  exit /b 1
)
"%PY%" -m uvicorn app.main:app --reload --port 8000