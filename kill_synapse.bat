@echo off
setlocal enabledelayedexpansion
echo Arret de Synapse (port 8082)...

set "killed="
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8082 .*LISTENING"') do (
    echo "%%a" | findstr /x "!killed!" >nul 2>&1 || (
        taskkill /PID %%a /F >nul 2>&1 && echo Killed PID %%a
        set "killed=!killed! %%a"
    )
)

echo Arret des subprocessus uvicorn orphelins (spawn_main)...
for /f "tokens=2" %%a in ('tasklist /FI "IMAGENAME eq python.exe" /FO TABLE /NH 2^>nul') do (
    for /f "tokens=*" %%b in ('wmic process where "ProcessId=%%a" get CommandLine /VALUE 2^>nul ^| findstr /i "spawn_main"') do (
        taskkill /PID %%a /F >nul 2>&1 && echo Killed orphan PID %%a
    )
)

echo Done.
pause
