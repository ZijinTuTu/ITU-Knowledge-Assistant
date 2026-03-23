from pathlib import Path
import json
import os
import re
from typing import List, Dict, Any, Tuple

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
FETCH_K = 20  # 先多取一些候选，再后处理

NOISE_KEYWORDS = [
    "foreword",
    "table of contents",
    "contents",
    "methodology",
    "list of figures",
    "list of tables",
]

# 对一些高价值词给一点轻量加权
BOOST_TERMS = [
    "digital divide",
    "gender divide",
    "affordability",
    "internet use",
    "low-income",
    "rural",
    "urban",
    "barriers",
    "skills",
]


# =========================
# OpenAI / DashScope
# =========================
def load_client() -> OpenAI:
    load_dotenv()
    api_key = os.getenv("DASHSCOPE_API_KEY")

    if not api_key:
        raise ValueError("Missing DASHSCOPE_API_KEY")

    return OpenAI(
        api_key=api_key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
    )


# =========================
# 索引加载
# =========================
def load_index() -> Tuple[faiss.Index, List[Dict[str, Any]]]:
    if not FAISS_INDEX_PATH.exists():
        raise FileNotFoundError(f"FAISS index not found: {FAISS_INDEX_PATH}")

    if not METADATA_PATH.exists():
        raise FileNotFoundError(f"Metadata file not found: {METADATA_PATH}")

    index = faiss.read_index(str(FAISS_INDEX_PATH))

    with open(METADATA_PATH, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    return index, metadata


# =========================
# Query embedding
# =========================
def embed_query(client: OpenAI, query: str) -> np.ndarray:
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=[query],
    )

    vector = np.array([response.data[0].embedding], dtype=np.float32)
    faiss.normalize_L2(vector)
    return vector


# =========================
# 文本工具
# =========================
def normalize_text_for_match(text: str) -> str:
    text = text.lower()
    text = text.replace("�", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def make_preview(text: str, max_chars: int = 300) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "..."


def token_overlap_score(query: str, text: str) -> float:
    """
    一个很轻量的词重合分，用来辅助排序。
    不追求复杂，只求稳定。
    """
    q = set(re.findall(r"[a-zA-Z]{3,}", query.lower()))
    t = set(re.findall(r"[a-zA-Z]{3,}", text.lower()))

    if not q or not t:
        return 0.0

    overlap = q & t
    return len(overlap) / max(len(q), 1)


# =========================
# 噪声判断
# =========================
def is_noise_item(item: Dict[str, Any]) -> bool:
    title = normalize_text_for_match(str(item.get("title", "")))
    text = normalize_text_for_match(str(item.get("text", "")))

    # 标题或正文含明显噪声词，且文本不长，通常是目录/前言/方法页
    for kw in NOISE_KEYWORDS:
        if kw in title:
            return True
        if kw in text and len(text) < 1200:
            return True

    # 纯目录风格
    if re.search(r"\.{5,}", text):
        return True

    # 太短的块一般信息密度差
    if len(text) < 80:
        return True

    return False


# =========================
# 结果去重
# =========================
def dedup_key(item: Dict[str, Any]) -> Tuple[str, int]:
    """
    避免同一文档、相邻页的重复块霸榜。
    """
    filename = str(item.get("filename", "")).lower()
    page_start = int(item.get("page_start", 0))

    # 页码分桶：相邻页算一类，减少同一位置重复结果
    page_bucket = page_start // 2
    return filename, page_bucket


# =========================
# 简单重排
# =========================
def rerank_results(query: str, raw_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    reranked = []

    query_norm = normalize_text_for_match(query)

    # query 词
    query_terms = [
        t for t in re.findall(r"[a-zA-Z]{3,}", query_norm)
        if t not in {"what", "does", "the", "report", "say", "about"}
    ]

    # 更有意义的短语加权
    phrase_boosts = {
        "digital divide": 0.10,
        "gender divide": 0.08,
        "urban-rural divide": 0.08,
        "rural divide": 0.06,
        "low-income": 0.06,
        "affordability": 0.06,
        "barriers": 0.05,
        "offline": 0.04,
        "universal access": 0.05,
        "meaningful connectivity": 0.05,
        "internet use": 0.04,
    }

    for item in raw_results:
        text = str(item.get("text", ""))
        title = str(item.get("title", ""))
        base_score = float(item.get("score", 0.0))

        text_norm = normalize_text_for_match(text)
        title_norm = normalize_text_for_match(title)

        bonus = 0.0

        # 1. query 词重合（降低权重，避免泛词误伤）
        overlap = token_overlap_score(query_norm, text_norm)
        bonus += overlap * 0.04

        # 2. query 中的重要词出现在正文里，加一点分
        strong_query_hits = 0
        for term in query_terms:
            if term in text_norm:
                strong_query_hits += 1
        bonus += min(strong_query_hits * 0.012, 0.05)

        # 3. 标题命中要更严格，不再用任意 term
        # 只有比较强的主题词出现在标题里才加分
        important_title_terms = {"digital", "divide", "internet", "affordability", "gender", "rural", "urban"}
        if any(term in title_norm for term in important_title_terms if term in query_terms):
            bonus += 0.02

        # 4. 关键短语强加分
        for phrase, weight in phrase_boosts.items():
            if phrase in text_norm:
                bonus += weight

        # 5. 通用高价值词小加分
        for term in BOOST_TERMS:
            if term in text_norm:
                bonus += 0.01

        # 6. 明显噪声：强惩罚
        if is_noise_item(item):
            bonus -= 0.28

        # 7. Foreword / Contents / Methodology 专门再压
        if "foreword" in title_norm or text_norm.startswith("foreword"):
            bonus -= 0.18

        if "table of contents" in title_norm or "table of contents" in text_norm:
            bonus -= 0.25

        if "contents" == title_norm.strip():
            bonus -= 0.20

        if "methodology" in title_norm or text_norm.startswith("methodology"):
            bonus -= 0.12

        # 8. 太短的段落再减一点
        if len(text_norm) < 180:
            bonus -= 0.05

        final_score = base_score + bonus

        new_item = item.copy()
        new_item["raw_score"] = base_score
        new_item["score"] = final_score
        reranked.append(new_item)

    reranked.sort(key=lambda x: x["score"], reverse=True)
    return reranked



# =========================
# 主搜索
# =========================
def search(query: str, top_k: int = TOP_K, fetch_k: int = FETCH_K) -> List[Dict[str, Any]]:
    client = load_client()
    index, metadata = load_index()

    # 1. query -> 向量
    query_vector = embed_query(client, query)

    # 2. FAISS 初筛
    scores, indices = index.search(query_vector, fetch_k)

    raw_results: List[Dict[str, Any]] = []

    for score, idx in zip(scores[0], indices[0]):
        if idx < 0:
            continue
        if idx >= len(metadata):
            continue

        item = metadata[idx].copy()
        item["score"] = float(score)
        raw_results.append(item)

    # 3. 先过滤明显噪声
    filtered = [item for item in raw_results if not is_noise_item(item)]

    # 如果过滤后太少，退回原始结果，避免空结果
    if len(filtered) < max(3, top_k):
        filtered = raw_results

    # 4. 简单重排
    reranked = rerank_results(query, filtered)

    # 5. 去重
    final_results: List[Dict[str, Any]] = []
    seen = set()

    for item in reranked:
        key = dedup_key(item)
        if key in seen:
            continue
        seen.add(key)
        final_results.append(item)

        if len(final_results) >= top_k:
            break

    return final_results


# =========================
# 打印辅助
# =========================
def print_results(query: str, results: List[Dict[str, Any]]) -> None:
    print(f"\nQuery: {query}\n")

    for i, r in enumerate(results, 1):
        print(f"[{i}] score={r['score']:.4f} raw_score={r.get('raw_score', r['score']):.4f}")
        print(f"Title: {r.get('title', '')}")
        print(f"File: {r.get('filename', '')}")
        print(f"Pages: {r.get('page_start', '')}-{r.get('page_end', '')}")
        print(make_preview(r.get("text", ""), 320))
        print("-" * 60)


# =========================
# 测试入口
# =========================
if __name__ == "__main__":
    query = "What does the report say about the digital divide?"
    results = search(query, top_k=5, fetch_k=20)
    print_results(query, results)

