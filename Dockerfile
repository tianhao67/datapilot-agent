FROM python:3.12-slim

WORKDIR /app
COPY . .
RUN python scripts/build_db.py

ENV PYTHONUNBUFFERED=1 \
    LLM_PROVIDER=ollama \
    OLLAMA_HOST=http://host.docker.internal:11434 \
    OLLAMA_MODEL=qwen2.5-coder:3b

EXPOSE 8000
CMD ["python", "web/server.py", "--host", "0.0.0.0", "--port", "8000"]
