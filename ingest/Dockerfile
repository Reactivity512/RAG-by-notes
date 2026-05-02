FROM python:3.11-slim

# Отключаем буферизацию вывода (видны логи в реальном времени)
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Устанавливаем системные зависимости:
# - git: требуется GitPython для работы с репозиториями
# - gcc/g++: нужны для компиляции некоторых pip-пакетов (например, langchain deps)
RUN apt-get update && \
    apt-get install -y --no-install-recommends git gcc g++ && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Кэшируем слой с зависимостями (ускоряет повторные сборки)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем только нужный скрипт
COPY ingest.py .

# По умолчанию запускает скрипт, но можно переопределить в docker run
CMD ["python", "ingest.py"]