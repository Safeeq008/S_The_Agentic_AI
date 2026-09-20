@echo off
title Starting Agentic Search Application
echo ===================================================
echo   Starting 3D Agentic Search (Backend + Frontend)
echo ===================================================
echo.

rem Navigate to the directory where start.bat is located
cd /d "%~dp0"

echo [1/2] Launching FastAPI Backend on http://localhost:8000 ...
start "Agentic Search Backend" cmd /k "cd /d "%~dp0backend" && .\venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload"

timeout /t 2 /nobreak >nul

echo [2/2] Launching Vite Frontend on http://localhost:5173 ...
start "Agentic Search Frontend" cmd /k "cd /d "%~dp0frontend" && npm run dev"

echo.
echo ===================================================
echo   Application Servers Launched!
echo   - Backend:  http://localhost:8000
echo   - Frontend: http://localhost:5173
echo   (Note: Ensure Ollama is running in background)
echo ===================================================
echo.
pause
