import os
import re
import git
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional

from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from langchain_community.document_loaders import TextLoader
from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.models import Distance, VectorParams, PointStruct
from tqdm import tqdm
import ollama

# --- Конфигурация ---
REPO_URL = "https://github.com/Reactivity512/Notes.git"
LOCAL_REPO_PATH = "./notes_repo"
COLLECTION_NAME = "tech_notes"
EMBEDDING_MODEL = "nomic-embed-text" # 768 измерений
VECTOR_SIZE = 768

# --- Шаг 1: Клонирование / Обновление репозитория ---
def sync_repo():
    if not os.path.exists(LOCAL_REPO_PATH):
        print(f"Клонирую {REPO_URL}...")
        git.Repo.clone_from(REPO_URL, LOCAL_REPO_PATH, depth=1) # depth=1 для скорости
    else:
        print("Обновляю репозиторий...")
        repo = git.Repo(LOCAL_REPO_PATH)
        repo.remotes.origin.pull(depth=1)
    return LOCAL_REPO_PATH

# --- Шаг 2: Парсинг Markdown с сохранением структуры заголовков ---
def parse_markdown_with_headers(file_path: str) -> List[Dict[str, Any]]:
    """
    Разбивает Markdown на чанки, сохраняя иерархию заголовков в метаданных.
    Это нужно для того, чтобы при поиске "Kafka vs RabbitMQ" мы знали, 
    что чанк находится в разделе "Infrastructure -> Message Brokers".
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        text = f.read()
    
    # Заголовки, которые мы хотим отслеживать
    headers_to_split_on = [
        ("#", "Header 1"),
        ("##", "Header 2"),
        ("###", "Header 3"),
    ]
    
    # Сплиттер, который понимает Markdown структуру
    markdown_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=headers_to_split_on,
        strip_headers=False  # Оставляем заголовки в тексте чанка для контекста
    )
    
    md_header_splits = markdown_splitter.split_text(text)
    
    # Второй уровень сплиттинга: если чанк получился слишком большим (> 1000 символов)
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=100,
        separators=["\n\n", "\n", ". ", " ", ""]
    )
    
    final_chunks = []
    for doc in md_header_splits:
        # Сохраняем метаданные о заголовках + добавляем путь к файлу
        metadata = doc.metadata.copy()
        metadata["source_file"] = str(file_path)
        metadata["repo_path"] = str(Path(file_path).relative_to(LOCAL_REPO_PATH))
        
        # Если чанк маленький, оставляем как есть
        if len(doc.page_content) < 1200:
            final_chunks.append({
                "text": doc.page_content,
                "metadata": metadata
            })
        else:
            # Иначе бьем дальше стандартным сплиттером
            sub_chunks = text_splitter.split_text(doc.page_content)
            for sub_text in sub_chunks:
                final_chunks.append({
                    "text": sub_text,
                    "metadata": metadata
                })
    
    return final_chunks

# --- Шаг 3: Создание BM25 индекса и Векторов ---
class HybridSearcher:
    def __init__(self):
        # Увеличиваем таймаут до 60 секунд
        self.qdrant_client = QdrantClient(host=os.getenv("QDRANT_HOST", "localhost"), port=6333, timeout=60)
        self.embedding_model = EMBEDDING_MODEL
        
    def setup_collection(self):
        """Создает коллекцию с поддержкой плотных (векторы) и разреженных (BM25/Splade) векторов"""
        if not self.qdrant_client.collection_exists(COLLECTION_NAME):
            self.qdrant_client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config={
                    "dense": VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE)
                },
                sparse_vectors_config={
                    # Qdrant сам посчитает BM25 или TF-IDF разреженные векторы из текста
                    "bm25": models.SparseVectorParams(
                        index=models.SparseIndexParams(
                            on_disk=False
                        )
                    )
                }
            )
            print(f"✅ Коллекция '{COLLECTION_NAME}' создана с поддержкой dense + sparse векторов")
            
            # Создаем индексы для payload (метаданных) для быстрой фильтрации
            self.qdrant_client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name="metadata.source_file",
                field_schema="keyword"
            )
            self.qdrant_client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name="metadata.repo_path",
                field_schema="keyword"
            )
    
    def get_embedding(self, text: str) -> List[float]:
        """Получение вектора через Ollama"""
        response = ollama.embeddings(model=self.embedding_model, prompt=text)
        return response["embedding"]
    
    def index_chunks(self, chunks: List[Dict]):
        """Загрузка чанков в Qdrant (оптимизированная)"""
        points = []
        for idx, chunk in enumerate(tqdm(chunks, desc="Индексация чанков")):
            # Генерация ID
            unique_str = f"{chunk['metadata']['repo_path']}_{chunk['text'][:100]}"
            point_id = hashlib.md5(unique_str.encode()).hexdigest()
            
            # Dense вектор
            dense_vector = self.get_embedding(chunk["text"])
            
            payload = {
                "text": chunk["text"],
                "metadata": chunk["metadata"]
            }
            
            points.append(
                PointStruct(
                    id=point_id,
                    vector={"dense": dense_vector},
                    payload=payload
                )
            )
            
            # Отправляем батчами по 50 (меньше нагрузка на сеть)
            if len(points) >= 50:
                self.qdrant_client.upsert(
                    collection_name=COLLECTION_NAME,
                    points=points,
                    wait=False  # <-- КРИТИЧЕСКИ ВАЖНО: Не ждать подтверждения от всех реплик
                )
                points = []
        
        # Отправляем остатки
        if points:
            self.qdrant_client.upsert(
                collection_name=COLLECTION_NAME,
                points=points,
                wait=False
            )
        
        print(f"✅ Загружено {len(chunks)} чанков в Qdrant (индексация в фоне)")
    
    def hybrid_search(self, query: str, limit: int = 5) -> List:
        """
        Гибридный поиск: 
        1. Dense (семантический) - находим смысл.
        2. Sparse (BM25) - находим точные ключевые слова.
        3. RRF (Reciprocal Rank Fusion) - объединяем результаты.
        """
        # Получаем dense вектор запроса
        query_vector = self.get_embedding(query)
        
        # Выполняем гибридный поиск
        # Qdrant сам применит RRF для объединения dense и sparse результатов
        search_result = self.qdrant_client.query_points(
            collection_name=COLLECTION_NAME,
            prefetch=[
                # Ветка 1: Плотный векторный поиск
                models.Prefetch(
                    query=query_vector,
                    using="dense",
                    limit=limit * 2  # Берем с запасом для слияния
                ),
                # Ветка 2: Разреженный поиск (BM25)
                models.Prefetch(
                    query=models.SparseVector(
                        # Qdrant автоматически преобразует текст в sparse вектор 
                        # на основе индекса BM25
                        indices=..., # В реальном коде нужно использовать fastembed или transformers
                        values=...
                    ),
                    using="bm25",
                    limit=limit * 2
                ),
            ],
            query=models.FusionQuery(
                fusion=models.Fusion.RRF  # Reciprocal Rank Fusion
            ),
            with_payload=True,
            limit=limit
        )
        
        return search_result.points

# --- Шаг 4: Запуск индексации ---
def main():
    # Синхронизация репозитория
    repo_path = sync_repo()
    
    # Поиск всех .md файлов
    md_files = list(Path(repo_path).rglob("*.md"))
    print(f"Найдено {len(md_files)} Markdown файлов")
    
    # Парсинг с чанкингом
    all_chunks = []
    for md_file in md_files:
        # Пропускаем служебные файлы и лицензии
        if "LICENSE" in str(md_file) or "README" in str(md_file):
            continue
        try:
            chunks = parse_markdown_with_headers(str(md_file))
            all_chunks.extend(chunks)
        except Exception as e:
            print(f"❌ Ошибка обработки {md_file}: {e}")
    
    print(f"Нарезано {len(all_chunks)} чанков")
    
    # Инициализация поисковика и загрузка в Qdrant
    searcher = HybridSearcher()
    searcher.setup_collection()
    searcher.index_chunks(all_chunks)

if __name__ == "__main__":
    main()