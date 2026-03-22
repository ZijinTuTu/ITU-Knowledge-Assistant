from pathlib import Path
import json
import os
from typing import List, Dict, Any

import faiss
import numpy as np
from dotenv import load_dotenv
from openai import OpenAI


# =========================
# 路径
# =========================
BASE_DIR = Path(r"E:\MyProjects\ITUassistant")
INDEX_DIR = BASE_DIR / "data" / "index"

FAISS_INDEX_PATH = INDEX_DIR / "itu_chunks.faiss"
METADATA_PATH = INDEX_DIR / "chunk_metadata.json"


# =========================
# 配置
# =========================
EMBEDDING_MODEL = "text-embedding-v4"
TOP_K = 5


def load_client() -> OpenAI:
    load_dotenv()
    api_key = os.getenv("DASHSCOPE_API_KEY")

    if not api_key:
        raise ValueError("Missing DASHSCOPE_API_KEY")

    return OpenAI(
        api_key=api_key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
    )


def load_index():
    if not FAISS_INDEX_PATH.exists():
        raise FileNotFoundError("FAISS index not found")

    if not METADATA_PATH.exists():
        raise FileNotFoundError("Metadata file not found")

    index = faiss.read_index(str(FAISS_INDEX_PATH))

    with open(METADATA_PATH, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    return index, metadata


def embed_query(client: OpenAI, query: str) -> np.ndarray:
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=[query],
    )

    vector = np.array([response.data[0].embedding], dtype=np.float32)
    faiss.normalize_L2(vector)
    return vector


def search(query: str, top_k: int = TOP_K) -> List[Dict[str, Any]]:
    client = load_client()
    index, metadata = load_index()

    # 1️⃣ query → 向量
    query_vector = embed_query(client, query)

    # 2️⃣ 搜索
    scores, indices = index.search(query_vector, top_k)

    # 3️⃣ 还原文本
    results = []

    for score, idx in zip(scores[0], indices[0]):
        if idx < 0:
            continue

        item = metadata[idx].copy()
        item["score"] = float(score)

        results.append(item)

    return results


# =========================
# 测试入口
# =========================
if __name__ == "__main__":
    query = "What does the report say about the digital divide?"

    results = search(query, top_k=3)

    print(f"\nQuery: {query}\n")

    for i, r in enumerate(results, 1):
        print(f"[{i}] score={r['score']:.4f}")
        print(f"Title: {r['title']}")
        print(f"Pages: {r['page_start']}-{r['page_end']}")
        print(r["text"][:300])
        print("-" * 60)
