from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import ollama
import os
from qdrant_client import QdrantClient
from qdrant_client.models import Prefetch, Fusion, FusionQuery
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Tech Notes RAG")

# --- Модели данных ---
class SearchRequest(BaseModel):
    query: str
    limit: int = 5
    hybrid: bool = True  # True = Dense + BM25, False = Только Dense

class DocumentResponse(BaseModel):
    text: str
    source: str
    headers: dict
    score: float

class RAGRequest(BaseModel):
    question: str
    use_hybrid_search: bool = True

class RAGResponse(BaseModel):
    answer: str
    sources: List[DocumentResponse]

# --- Клиенты ---
qdrant = QdrantClient(host=os.getenv("QDRANT_HOST", "localhost"), port=6333)
COLLECTION_NAME = "tech_notes"

# --- Функции поиска ---
def get_embedding(text: str) -> List[float]:
    response = ollama.embeddings(model="nomic-embed-text", prompt=text)
    return response["embedding"]

@app.post("/search", response_model=List[DocumentResponse])
async def search_documents(request: SearchRequest):
    """Простой поиск (без генерации)"""
    query_vector = get_embedding(request.query)
    
    if request.hybrid:
        # Гибридный поиск (упрощенная версия)
        # В реальности нужно использовать Sparse векторы, 
        # здесь показываем концепт с чистым Dense
        results = qdrant.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector,
            using="dense",
            limit=request.limit,
            with_payload=True
        )
    else:
        results = qdrant.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector,
            using="dense",
            limit=request.limit,
            with_payload=True
        )
    
    return [
        DocumentResponse(
            text=point.payload["text"],
            source=point.payload["metadata"]["repo_path"],
            headers={
                "h1": point.payload["metadata"].get("Header 1", ""),
                "h2": point.payload["metadata"].get("Header 2", ""),
                "h3": point.payload["metadata"].get("Header 3", ""),
            },
            score=point.score
        )
        for point in results.points
    ]

@app.post("/rag", response_model=RAGResponse)
async def rag_generate(request: RAGRequest):
    """Полный RAG: поиск + генерация ответа"""
    
    # 1. Поиск релевантных чанков
    query_vector = get_embedding(request.question)
    results = qdrant.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        using="dense",
        limit=3,
        with_payload=True
    )
    
    if not results.points:
        return RAGResponse(
            answer="Не найдено релевантных заметок.",
            sources=[]
        )
    
    # 2. Формирование контекста с учетом заголовков
    context_parts = []
    sources = []
    for point in results.points:
        meta = point.payload["metadata"]
        header_path = " > ".join(filter(None, [
            meta.get("Header 1", ""),
            meta.get("Header 2", ""),
            meta.get("Header 3", "")
        ]))
        context_parts.append(f"## {header_path}\n{point.payload['text']}")
        sources.append(DocumentResponse(
            text=point.payload["text"],
            source=meta["repo_path"],
            headers={"path": header_path},
            score=point.score
        ))
    
    context = "\n\n".join(context_parts)
    
    # 3. Генерация ответа
    prompt = f"""Ты — эксперт по технологиям, отвечающий на основе личных заметок разработчика.

Заметки (сгруппированы по разделам):
{context}

Вопрос: {request.question}

Дай развернутый, технически точный ответ, опираясь ТОЛЬКО на предоставленные заметки. 
Если информации недостаточно, укажи это и предложи переформулировать вопрос."""
    
    response = ollama.generate(
        model='qwen3:4b',
        prompt=prompt,
        options={'temperature': 0.1, 'num_ctx': 4096}
    )
    
    return RAGResponse(
        answer=response['response'],
        sources=sources
    )

@app.get("/health")
async def health():
    try:
        qdrant.get_collection(COLLECTION_NAME)
        return {"status": "ok", "qdrant": "connected"}
    except:
        return {"status": "error", "qdrant": "disconnected"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

app.mount("/", StaticFiles(directory="static", html=True), name="static")