@echo off
rem Starts the backend (:8000), chat service (:8001) and frontend (:5173), each in its own window.
rem Ollama must already be running (:11434). First-time setup is in the root README.md.
set ROOT=%~dp0

rem Use each service's virtual environment when it exists, otherwise the Python on PATH.
set BPY=python
if exist "%ROOT%backend\.venv\Scripts\python.exe" set BPY=%ROOT%backend\.venv\Scripts\python.exe
set CPY=python
if exist "%ROOT%chat-service\.venv\Scripts\python.exe" set CPY=%ROOT%chat-service\.venv\Scripts\python.exe

start "Prudentia backend" /d "%ROOT%backend" cmd /k ""%BPY%" -m uvicorn backend.api.main:app --port 8000"
start "Prudentia chat service" /d "%ROOT%chat-service" cmd /k "set PYTHONUTF8=1&& set CHAT_ENGINE_MODE=http&& set CHAT_ENGINE_URL=http://127.0.0.1:8000&& "%CPY%" -m uvicorn chat_service.main:app --port 8001"
start "Prudentia frontend" /d "%ROOT%frontend" cmd /k "npm run dev"

echo Started. Open http://localhost:5173
