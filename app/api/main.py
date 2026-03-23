from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.rag.retrieve import search
from app.rag.ask import ask

import traceback


app = FastAPI(
    title="ITU Assistant API",
    description="RAG API for querying the ITU knowledge base",
    version="0.1.0",
)

# 开发阶段先放开，后面上线再收紧
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================
# 请求 / 响应模型
# =========================
class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, description="User question")
    top_k: int = Field(4, ge=1, le=10, description="Final number of results")
    fetch_k: int = Field(30, ge=1, le=100, description="Candidate results before reranking")


class RetrieveItem(BaseModel):
    chunk_id: Optional[str] = None
    filename: str
    title: str
    source_org: Optional[str] = None
    doc_type: Optional[str] = None
    year: Optional[int] = None
    language: Optional[str] = None
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    chunk_chars: Optional[int] = None
    text: str
    score: float
    raw_score: Optional[float] = None


class RetrieveResponse(BaseModel):
    query: str
    count: int
    results: List[RetrieveItem]


class CitationItem(BaseModel):
    source_id: int
    title: str
    filename: str
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    score: float
    label: Optional[str] = None


class AskResponse(BaseModel):
    query: str
    answer: str
    citations: List[CitationItem]
    results: List[RetrieveItem]


# =========================
# 路由
# =========================
@app.get("/")
def root() -> Dict[str, str]:
    return {
        "message": "ITU Assistant API is running",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health")
def health() -> Dict[str, str]:
    return {
        "status": "ok",
        "service": "ITU Assistant API",
    }


@app.post("/retrieve", response_model=RetrieveResponse)
def retrieve_endpoint(req: QueryRequest) -> RetrieveResponse:
    try:
        results = search(req.query, top_k=req.top_k, fetch_k=req.fetch_k)
        return RetrieveResponse(
            query=req.query,
            count=len(results),
            results=results,
        )
    except Exception as e:
        print("\n[RETRIEVE ERROR]")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Retrieve failed: {str(e)}")


@app.post("/ask", response_model=AskResponse)
def ask_endpoint(req: QueryRequest) -> AskResponse:
    try:
        result = ask(req.query, top_k=req.top_k, fetch_k=req.fetch_k)
        return AskResponse(
            query=result["query"],
            answer=result["answer"],
            citations=result["citations"],
            results=result["results"],
        )
    except Exception as e:
        print("\n[ASK ERROR]")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Ask failed: {str(e)}")

