import os
import re
from typing import List, Dict, Any

from dotenv import load_dotenv
from openai import OpenAI

from app.rag.retrieve import search


# =========================
# 配置
# =========================
TOP_K = 4
FETCH_K = 30
MAX_CONTEXT_CHARS_PER_CHUNK = 1200
MAX_TOTAL_CONTEXT_CHARS = 4200


# =========================
# 模型客户端
# =========================
def load_client() -> OpenAI:
    load_dotenv()

    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise ValueError("Missing DASHSCOPE_API_KEY in .env")

    return OpenAI(
        api_key=api_key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
    )


def get_chat_model() -> str:
    load_dotenv()
    return os.getenv("CHAT_MODEL", "qwen-plus")


# =========================
# 文本工具
# =========================
def normalize_text(text: str) -> str:
    text = str(text)
    text = text.replace("�", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def truncate_text(text: str, max_chars: int = MAX_CONTEXT_CHARS_PER_CHUNK) -> str:
    text = normalize_text(text)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + " ..."


def make_source_label(item: Dict[str, Any], source_id: int) -> str:
    filename = item.get("filename", "")
    page_start = item.get("page_start", "")
    page_end = item.get("page_end", "")

    if page_start == page_end:
        page_text = f"page {page_start}"
    else:
        page_text = f"pages {page_start}-{page_end}"

    return f"[Source {source_id}] {filename}, {page_text}"


# =========================
# 上下文构造
# =========================
def deduplicate_results(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    再做一层轻量去重，避免高度相似文本重复进入 prompt
    """
    deduped: List[Dict[str, Any]] = []
    seen_keys = set()

    for item in results:
        text = normalize_text(item.get("text", ""))[:220]
        filename = str(item.get("filename", "")).lower()
        page_start = item.get("page_start", "")
        key = (filename, page_start, text)

        if key in seen_keys:
            continue

        seen_keys.add(key)
        deduped.append(item)

    return deduped


def format_context(results: List[Dict[str, Any]]) -> str:
    """
    把 retrieve 返回的结果拼成模型可读的 context
    """
    results = deduplicate_results(results)

    blocks = []
    total_chars = 0

    for i, item in enumerate(results, start=1):
        title = item.get("title", "")
        filename = item.get("filename", "")
        page_start = item.get("page_start", "")
        page_end = item.get("page_end", "")
        text = truncate_text(item.get("text", ""))

        block = (
            f"[Source {i}]\n"
            f"Title: {title}\n"
            f"File: {filename}\n"
            f"Pages: {page_start}-{page_end}\n"
            f"Content: {text}"
        )

        if total_chars + len(block) > MAX_TOTAL_CONTEXT_CHARS:
            break

        blocks.append(block)
        total_chars += len(block)

    return "\n\n".join(blocks)


# =========================
# Prompt
# =========================
def build_system_prompt() -> str:
    return (
        "You are an ITU knowledge assistant. "
        "You must answer strictly based on the retrieved source materials provided by the user. "
        "Do not use outside knowledge. "
        "Do not infer unsupported facts. "
        "If the evidence is incomplete or unclear, explicitly say so."
    )


def build_user_prompt(query: str, context: str) -> str:
    return f"""
Answer the question using ONLY the sources below.

Rules:
- Use only facts that are directly supported by the sources.
- Do not add background knowledge from outside the sources.
- If the sources do not fully answer the question, say that the available sources are insufficient.
- Keep the answer clear and concise.
- When you make a claim, support it with source references.
- At the end, include a "Citations:" section listing only the sources actually used.

Question:
{query}

Sources:
{context}

Output format:
Answer:
<one short paragraph>

Key points:
- <point 1>
- <point 2>
- <point 3 if needed>

Citations:
- [Source X]
- [Source Y]
""".strip()


# =========================
# 问答主流程
# =========================
def ask(query: str, top_k: int = TOP_K, fetch_k: int = FETCH_K) -> Dict[str, Any]:
    retrieved = search(query, top_k=top_k, fetch_k=fetch_k)

    if not retrieved:
        return {
            "query": query,
            "answer": "Answer:\nI could not find relevant information in the current knowledge base.\n\nKey points:\n- No relevant sources were retrieved.\n\nCitations:\n- None",
            "citations": [],
            "results": []
        }

    context = format_context(retrieved)
    system_prompt = build_system_prompt()
    user_prompt = build_user_prompt(query, context)

    client = load_client()
    chat_model = get_chat_model()

    try:
        response = client.chat.completions.create(
            model=chat_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
        )
        answer = response.choices[0].message.content.strip()
    except Exception as e:
        answer = (
            "Answer:\n"
            "The model call failed.\n\n"
            "Key points:\n"
            f"- Error: {e}\n\n"
            "Citations:\n"
            "- None"
        )

    citations = [
        {
            "source_id": i + 1,
            "title": item.get("title", ""),
            "filename": item.get("filename", ""),
            "page_start": item.get("page_start", ""),
            "page_end": item.get("page_end", ""),
            "score": item.get("score", 0.0),
            "label": make_source_label(item, i + 1),
        }
        for i, item in enumerate(retrieved)
    ]

    return {
        "query": query,
        "answer": answer,
        "citations": citations,
        "results": retrieved,
        "context": context,
    }


# =========================
# 打印辅助
# =========================
def print_answer(result: Dict[str, Any]) -> None:
    print(f"\nQuestion: {result['query']}\n")
    print(result["answer"])
    print("\n" + "=" * 80)
    print("Retrieved Sources:\n")

    for c in result["citations"]:
        print(
            f"[Source {c['source_id']}] "
            f"{c['title']} | {c['filename']} | Pages {c['page_start']}-{c['page_end']} "
            f"| score={c['score']:.4f}"
        )


# =========================
# 测试入口
# =========================
if __name__ == "__main__":
    query = "What does the report say about the digital divide?"
    result = ask(query, top_k=4, fetch_k=30)
    print_answer(result)
