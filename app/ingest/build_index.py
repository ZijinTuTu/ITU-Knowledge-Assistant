from __future__ import annotations

from pathlib import Path
import json
import os
from typing import List, Dict, Any

import faiss
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI


# =========================
# 路径
# =========================
BASE_DIR = Path(r"E:\MyProjects\ITUassistant")
CHUNKS_CSV = BASE_DIR / "data" / "exports" / "chunks.csv"
INDEX_DIR = BASE_DIR / "data" / "index"

INDEX_DIR.mkdir(parents=True, exist_ok=True)

FAISS_INDEX_PATH = INDEX_DIR / "itu_chunks.faiss"
METADATA_PATH = INDEX_DIR / "chunk_metadata.json"
BUILD_INFO_PATH = INDEX_DIR / "build_info.json"


# =========================
# 模型配置
# =========================
EMBEDDING_MODEL = "text-embedding-v4"
BATCH_SIZE = 10


def load_client() -> OpenAI:
    load_dotenv()

    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise ValueError("Missing DASHSCOPE_API_KEY in .env")

    return OpenAI(
        api_key=api_key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
    )


def load_chunks(csv_path: Path) -> pd.DataFrame:
    if not csv_path.exists():
        raise FileNotFoundError(f"Chunks CSV not found: {csv_path}")

    df = pd.read_csv(csv_path)

    required_cols = [
        "chunk_id",
        "filename",
        "title",
        "source_org",
        "doc_type",
        "year",
        "language",
        "page_start",
        "page_end",
        "chunk_chars",
        "text",
    ]

    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns in chunks.csv: {missing}")

    df["text"] = df["text"].fillna("").astype(str).str.strip()
    df["title"] = df["title"].fillna("").astype(str).str.strip()

    # 基础过滤
    df = df[df["text"] != ""].copy()
    df = df[df["chunk_chars"].fillna(0).astype(int) >= 120].copy()

    # chunk 级去重
    df["text_hash"] = df["text"].map(lambda x: hash(x))
    df = df.drop_duplicates(subset=["text_hash"]).drop(columns=["text_hash"])

    df = df.reset_index(drop=True)

    if df.empty:
        raise ValueError("No valid chunk text found in chunks.csv")

    return df


def prepare_embedding_text(row: pd.Series) -> str:
    """
    embedding 文本尽量简洁。
    不要塞 filename / 页码 / 一堆 metadata，避免干扰语义。
    """
    title = str(row.get("title", "")).strip()
    text = str(row.get("text", "")).strip()

    if title:
        return f"{title}\n\n{text}"
    return text


def get_embeddings_batch(client: OpenAI, texts: List[str], model: str) -> List[List[float]]:
    response = client.embeddings.create(
        model=model,
        input=texts,
    )
    return [item.embedding for item in response.data]


def build_faiss_index(vectors: np.ndarray):
    if vectors.dtype != np.float32:
        vectors = vectors.astype("float32")

    # 归一化后 + Inner Product = 近似 cosine similarity
    faiss.normalize_L2(vectors)

    dim = vectors.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(vectors)
    return index


def build_metadata(df: pd.DataFrame) -> List[Dict[str, Any]]:
    metadata: List[Dict[str, Any]] = []

    for _, row in df.iterrows():
        metadata.append({
            "chunk_id": row["chunk_id"],
            "filename": row["filename"],
            "title": row["title"],
            "source_org": row["source_org"],
            "doc_type": row["doc_type"],
            "year": None if pd.isna(row["year"]) else int(row["year"]),
            "language": row["language"],
            "page_start": int(row["page_start"]),
            "page_end": int(row["page_end"]),
            "chunk_chars": int(row["chunk_chars"]),
            "text": row["text"],
        })

    return metadata


def main() -> None:
    print("Loading chunks...")
    df = load_chunks(CHUNKS_CSV)
    print(f"Loaded {len(df)} chunks.")

    print("Preparing texts for embedding...")
    texts = [prepare_embedding_text(row) for _, row in df.iterrows()]

    client = load_client()

    print(f"Generating embeddings with model: {EMBEDDING_MODEL}")
    all_embeddings: List[List[float]] = []

    total = len(texts)
    for start in range(0, total, BATCH_SIZE):
        end = min(start + BATCH_SIZE, total)
        batch_texts = texts[start:end]
        print(f"  Embedding batch {start + 1}-{end} / {total}")
        batch_embeddings = get_embeddings_batch(client, batch_texts, EMBEDDING_MODEL)
        all_embeddings.extend(batch_embeddings)

    vectors = np.array(all_embeddings, dtype=np.float32)
    print(f"Embeddings shape: {vectors.shape}")

    print("Building FAISS index...")
    index = build_faiss_index(vectors)

    print(f"Saving FAISS index to: {FAISS_INDEX_PATH}")
    faiss.write_index(index, str(FAISS_INDEX_PATH))

    print("Saving metadata...")
    metadata = build_metadata(df)
    with open(METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    build_info = {
        "embedding_model": EMBEDDING_MODEL,
        "chunk_count": len(metadata),
        "vector_dim": int(vectors.shape[1]),
        "faiss_index_type": "IndexFlatIP",
        "normalized": True,
        "faiss_index_path": str(FAISS_INDEX_PATH),
        "metadata_path": str(METADATA_PATH),
        "source_chunks_csv": str(CHUNKS_CSV),
    }

    with open(BUILD_INFO_PATH, "w", encoding="utf-8") as f:
        json.dump(build_info, f, ensure_ascii=False, indent=2)

    print("\nDone.")
    print(f"Index saved: {FAISS_INDEX_PATH}")
    print(f"Metadata saved: {METADATA_PATH}")
    print(f"Build info saved: {BUILD_INFO_PATH}")


if __name__ == "__main__":
    main()
