@echo off
setlocal
cd /d %~dp0
if not exist .venv (
  python -m venv .venv
)
call .venv\Scripts\activate
python -m pip install -r requirements.txt
python -m uvicorn mock_ats_api:app --host 127.0.0.1 --port 8001
