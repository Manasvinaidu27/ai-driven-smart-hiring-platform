@echo off
cd /d "%~dp0"
start "Recruiter Portal" cmd /k "python app.py"
timeout /t 2 >nul
start "Analytics Dashboard" cmd /k "python -m streamlit run streamlit_app.py"
