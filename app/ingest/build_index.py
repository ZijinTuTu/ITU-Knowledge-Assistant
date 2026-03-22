from pathlib import Path
import json
import os
from typing import Any, Dict, List

import faiss
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI


# =========================
# 路径配置
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
    """
    读取 chunks.csv
    """
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

    # 清理空文本
    df["text"] = df["text"].fillna("").astype(str).str.strip()
    df = df[df["text"] != ""].reset_index(drop=True)

    if df.empty:
        raise ValueError("No valid chunk text found in chunks.csv")

    return df


def prepare_embedding_text(row: pd.Series) -> str:
    """
    给 embedding 用的文本。
    这里不只放正文，也加一点轻量 metadata，帮助语义检索更稳。
    """
    title = str(row.get("title", "")).strip()
    doc_type = str(row.get("doc_type", "")).strip()
    filename = str(row.get("filename", "")).strip()
    page_start = row.get("page_start", "")
    page_end = row.get("page_end", "")
    text = str(row.get("text", "")).strip()

    parts = [
        f"Title: {title}",
        f"Document type: {doc_type}",
        f"Filename: {filename}",
        f"Pages: {page_start}-{page_end}",
        f"Content: {text}",
    ]
    return "\n".join(parts)


def get_embeddings_batch(client: OpenAI, texts: List[str], model: str) -> List[List[float]]:
    """
    批量生成 embedding
    """
    response = client.embeddings.create(
        model=model,
        input=texts,
    )
    return [item.embedding for item in response.data]


def build_faiss_index(vectors: np.ndarray):
    if vectors.dtype != np.float32:
        vectors = vectors.astype("float32")

    faiss.normalize_L2(vectors)

    dim = vectors.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(vectors)
    return index


def build_metadata(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    保存与 FAISS 向量一一对应的 metadata
    """
    metadata: List[Dict[str, Any]] = []

    for _, row in df.iterrows():
        metadata.append(
            {
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
            }
        )

    return metadata


def main() -> None:
    print("Loading chunks...")
    df = load_chunks(CHUNKS_CSV)
    print(f"Loaded {len(df)} chunks.")

    print("Preparing texts for embedding...")
    texts = df["text"].astype(str).tolist()

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
