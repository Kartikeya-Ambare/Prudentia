FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONUTF8=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app/chat-service

COPY chat-service/requirements.txt requirements.txt
RUN pip install -r requirements.txt

COPY chat-service/ .

# Engine: the real backend. Ollama runs in its own container. Both are set in docker-compose.yml.
ENV CHAT_ENGINE_MODE=http CHAT_ENGINE_URL=http://backend:8000 CHAT_OLLAMA_HOST=http://ollama:11434

EXPOSE 8001
CMD ["uvicorn", "chat_service.main:app", "--host", "0.0.0.0", "--port", "8001"]
