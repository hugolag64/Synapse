@echo off
setlocal

rem Lance l'agent local EDNpro sans demander de token a chaque fois.
pushd "%~dp0"

set "PYTHON=%~dp0.venv\Scripts\python.exe"
set "AGENT=%~dp0scripts\ednpro\qcm_capture_agent.py"
set "CONFIG=%APPDATA%\Synapse\ednpro-capture-agent.json"
set "HEALTH=http://127.0.0.1:8876/health"

if not exist "%PYTHON%" (
    echo Python du venv introuvable : "%PYTHON%"
    pause
    exit /b 1
)

if not exist "%CONFIG%" (
    echo Configuration absente : "%CONFIG%"
    echo Lance d'abord scripts\ednpro\install_capture_agent.ps1.
    pause
    exit /b 1
)

rem Ne cree pas un deuxieme agent si le relais repond deja.
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
    "try { Invoke-WebRequest '%HEALTH%' -UseBasicParsing -TimeoutSec 2 | Out-Null; exit 0 } catch { exit 1 }"
if not errorlevel 1 (
    echo Agent EDNpro deja actif.
    popd
    exit /b 0
)

echo Demarrage de l'agent EDNpro...
start "Synapse EDNpro Capture Agent" /min "%PYTHON%" -u "%AGENT%" --config "%CONFIG%"
timeout /t 2 /nobreak >nul

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
    "try { Invoke-WebRequest '%HEALTH%' -UseBasicParsing -TimeoutSec 3 | Out-Null; exit 0 } catch { exit 1 }"
if errorlevel 1 (
    echo L'agent n'a pas encore repondu. Verifie la fenetre minimisee.
    popd
    exit /b 1
)

echo Agent EDNpro demarre. Tu peux fermer cette fenetre.
popd
exit /b 0
