FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_MODULE=main:app \
    PORT=8000

WORKDIR /app

# Установка Python-зависимостей (слой кэшируется, если requirements не менялся)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование кода
COPY main.py .
COPY static/index.html static/index.html

# Создаём непривилегированного пользователя (security best practice)
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE ${PORT}

# Healthcheck для оркестраторов (K8s, Docker Compose, Traefik и т.д.)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT}/health')" || exit 1

# Запуск ASGI-сервера
CMD ["sh", "-c", "uvicorn ${APP_MODULE} --host 0.0.0.0 --port ${PORT} --log-level info"]