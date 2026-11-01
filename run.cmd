@echo off
rem Start the Rest Brain API (extra arguments are passed on, e.g. run.cmd --port 9000).
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Virtual environment missing. Run setup.cmd first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m brain %*
