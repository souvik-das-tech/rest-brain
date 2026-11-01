@echo off
rem One-time setup: creates .venv and installs the dependencies.
cd /d "%~dp0"
where py >nul 2>nul && (set "PY=py -3.12") || (set "PY=python")
if not exist ".venv\Scripts\python.exe" (
    %PY% -m venv .venv || (echo Python 3.12+ is required. & pause & exit /b 1)
)
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt || (pause & exit /b 1)
where agy >nul 2>nul || if not exist "%LOCALAPPDATA%\agy\bin\agy.exe" (
    echo.
    echo NOTE: AGY CLI not found. Install it, then run `agy` once and sign in:
    echo   PowerShell:  irm https://antigravity.google/install.ps1 ^| iex
    echo   or:          winget install Google.AntigravityCLI
)
echo.
if not exist ".env" (copy .env.example .env >nul && echo Created .env - set BRAIN_USERNAME and BRAIN_PASSWORD in it.)
echo Done. Start with: pm2 start ecosystem.config.js   (or run.cmd)
pause
