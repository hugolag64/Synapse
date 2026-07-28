@echo off
cd /d "%~dp0"
call .venv\Scripts\activate
set "SYNAPSE_ENV=prod"
python main.py
pause
