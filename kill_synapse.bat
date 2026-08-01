@echo off
setlocal enabledelayedexpansion
echo Arret de Synapse (port 8082)...

:: 1. Tuer tous les processus écoutant directement sur le port 8082
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8082 .*LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
    if !errorlevel! equ 0 echo PID %%a libere du port 8082.
)

:: 2. Tuer les processus Python exécutant Synapse main.py ou Uvicorn reloaders
for /f "tokens=2 delims=," %%a in ('wmic process where "name='python.exe' and commandline like '%%main.py%%'" get processid /format:csv 2^>nul ^| findstr /r "[0-9]"') do (
    taskkill /PID %%a /F >nul 2>&1
    if !errorlevel! equ 0 echo Processus Synapse Python (PID %%a) arrete.
)

:: 3. Tuer les sous-processus uvicorn orphelins (spawn_main)
for /f "tokens=2 delims=," %%a in ('wmic process where "name='python.exe' and commandline like '%%spawn_main%%'" get processid /format:csv 2^>nul ^| findstr /r "[0-9]"') do (
    taskkill /PID %%a /F >nul 2>&1
    if !errorlevel! equ 0 echo Sous-processus orphelin (PID %%a) arrete.
)

echo.
echo Port 8082 nettoye avec succes.
pause
