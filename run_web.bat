@echo off
set PYTHONPATH=%~dp0src
python -m streamlit run app\streamlit_app.py
pause
