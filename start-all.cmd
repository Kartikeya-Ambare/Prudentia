@echo off
rem Starts the backend (:8000), chat service (:8001) and frontend (:5173), each in its own window.
rem Ollama must already be running (:11434). First-time setup is in the root README.md.
set ROOT=%~dp0

start "Prudentia backend" cmd /k "cd /d "%ROOT%backend" && python -m uvicorn backend.api.main:app --port 8000"
start "Prudentia chat service" cmd /k "cd /d "%ROOT%chat-service" && set PYTHONUTF8=1&& set CHAT_ENGINE_MODE=http&& set CHAT_ENGINE_URL=http://127.0.0.1:8000&& .venv\Scripts\python -m uvicorn chat_service.main:app --port 8001"
start "Prudentia frontend" cmd /k "cd /d "%ROOT%frontend" && npm run dev"

echo Started. Open http://localhost:5173
