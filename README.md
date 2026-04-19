# RAG Service — Гибридный поиск по техническим заметкам

[![Python](https://img.shields.io/badge/Python-3.11-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green.svg)](https://fastapi.tiangolo.com)
[![Qdrant](https://img.shields.io/badge/Qdrant-1.12-orange.svg)](https://qdrant.tech)
[![Ollama](https://img.shields.io/badge/Ollama-0.4.5-black.svg)](https://ollama.ai)
[![Docker](https://img.shields.io/badge/Docker-✔-blue.svg)](https://docker.com)

**RAG Service** — это система для семантического и гибридного поиска по личным техническим заметкам. Проект построен на связке **FastAPI** + **Qdrant** + **Ollama**.


## ✨ Возможности

- **🔍 Гибридный поиск** — объединение семантического (Dense) и ключевого (BM25) поиска через Qdrant
- **🤖 RAG генерация** — ответы на вопросы с использованием контекста из заметок
- **📄 Умный чанкинг** — разбивка Markdown с сохранением иерархии заголовков
- **🎨 Веб-интерфейс** — встроенный UI для тестирования `/search` и `/rag`
- **🐳 Docker-ready** — полностью контейнеризирован

---

## 🏗 Архитектура

```text
┌─────────────────────────────────────────────────────────────┐
│                      Пользователь                           │
│         (Браузер / HTTP Client / Telegram Bot)              │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI (Stateless)                      │
│                  • Асинхронные запросы                      │
│                  • Встроенный UI (/)                        │
└─────────────┬───────────────────────────────┬───────────────┘
              │                               │
              ▼                               ▼
┌─────────────────────────┐      ┌─────────────────────────────┐
│   Qdrant (Stateful)     │      │      Ollama (локально)      │
│  • Векторная БД         │      │  • Embedding модель         │
│  • Dense + Sparse       │      │  • LLM для генерации        │
│  • Persistent Volume    │      │  • nomic-embed-text         │
└─────────────────────────┘      │  • qwen3:4b / mistral       │
                                 └─────────────────────────────┘
```

## ⚡ Быстрый старт

### 1. Требования
Docker + Docker Compose V2
Ollama, запущенная локально на хосте:
```bash
ollama serve  # должен отвечать на http://localhost:11434
```

### 2. Запуск
```bash
# Собрать и запустить Qdrant + API
docker compose up -d

# UI и API доступны по адресу:
#  http://localhost:8000/
```

### 3. Ингест данных (ручной запуск)
```bash
# Запустить ingest.py в изолированном контейнере
docker compose run --rm ingest
```

## 📁 Структура проекта

```
├── docker-compose.yml
├── api/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── api.py          # FastAPI приложение + UI на /
│   └── static/
│       └── index.html  # UI
├── ingest/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── ingest.py       # Скрипт индексации документов
└── qdrant_storage/     # Persist-данные Qdrant (авто-создаётся)
```

## ⚙️ Конфигурация

### Переменные окружения

| Переменная | Значение по умолчанию | Описание
|--|--|--
| `QDRANT_HOST` | `qdrant` | Хост Qdrant внутри Docker-сети


### Порты

| Сервис | Порт | Назначение
|--|--|--
| API + UI | `8000` | Веб-интерфейс и REST API
| Qdrant HTTP | `6333` | REST API Qdrant
| Qdrant gRPC | `6334` | gRPC интерфейс

## 🚀 Установка и запуск Ollama

Ollama должна быть запущена локально на хосте

```bash
# Установите Ollama с официального сайта:
# https://ollama.com/download

# Запустите сервер (обычно автоматически)
ollama serve

# Скачайте необходимые модели
ollama pull nomic-embed-text    # Для эмбеддингов (~274 MB)
ollama pull qwen3:4b            # Для генерации
# или альтернатива:
ollama pull mistral
```

Проверка:
```bash
ollama list
# Должны увидеть:
# nomic-embed-text:latest
# qwen3:4b:latest
# или
# mistral:latest
```

## 🎯 Доступ к сервису
После успешного запуска:

| URL | Описание
|--|--
| http://localhost:8000/ | Веб-интерфейс для тестирования
| http://localhost:8000/docs | Swagger документация API
| http://localhost:8000/health | Healthcheck эндпоинт
| http://localhost:6333/dashboard | Qdrant Dashboard


## ⚠️ Troubleshooting

| Проблема | Решение
|--|--
| Connection refused к Ollama | Убедитесь, что ollama serve запущен. На Linux может потребоваться `--network host` или указание реального IP хоста
| Qdrant не сохраняет данные | Проверьте права на папку `./qdrant_storage`: `chmod -R 777 ./qdrant_storage`
| UI не грузится | Откройте http://localhost:8000/docs — если Swagger работает, проверьте, что корневой эндпоинт `/` возвращает статический файл

## 💻 Использование

Через веб-интерфейс

* Откройте http://localhost:8000/
* Выберите вкладку:
	- "Поиск документов" — для поиска чанков
	- "RAG генерация" — для получения ответов с контекстом

* Введите запрос и нажмите "Найти" или "Сгенерировать ответ"

## 📡 API Endpoints

| Метод | Endpoint | Описание | Параметры
|--|--|--|--
| GET | `/` | Веб-интерфейс | -
| GET | `/health` | Статус сервиса | -
| POST | `/api/v1/search` | Поиск документов | `query`, `limit`, `hybrid`
| POST | `/api/v1/rag` | RAG генерация | `question`, `use_hybrid_search`

### Параметры запросов

| Параметр | Тип | По умолчанию | Описание
|--|--|--|--
| `query` / `question` | `string` | - | Поисковый запрос или вопрос
| `limit` | `int` | 5 | Количество возвращаемых документов
| `hybrid` / `use_hybrid_search` | `bool` | `true` | Использовать гибридный поиск (Dense + BM25)

## 🛠 Технологии

| Компонент | Технология
|--|--
| API Framework | FastAPI
| Vector DB | Qdrant
| LLM Runtime | Ollama
| Embedding Model | nomic-embed-text
| LLM Model | qwen3:4b / mistral
|Container | Docker

## 📝 Лицензия

MIT License
