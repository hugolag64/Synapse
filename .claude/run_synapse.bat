@echo off
set SYNAPSE_ENV=prod
rem En mode prod le port par defaut est 8000 ; launch.json attend 8082.
set SYNAPSE_PORT=8082
"C:\Users\hugol\Desktop\Projet Python\Synapse\.venv\Scripts\python.exe" "C:\Users\hugol\Desktop\Projet Python\Synapse\main.py"
