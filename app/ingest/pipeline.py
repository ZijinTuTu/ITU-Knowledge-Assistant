from pathlib import Path
import json
import re
from typing import Any, Dict, List, Optional

import fitz  # pymupdf
import pandas as pd


BASE_DIR = Path(r"E:\MyProjects\ITUassistant")
PDF_DIR = BASE_DIR / "data" / "itu_pdfs"
PARSED_DIR = BASE_DIR / "data" / "parsed"
CHUNKS_DIR = BASE_DIR / "data" / "chunks"
EXPORT_DIR = BASE_DIR / "data" / "exports"

PARSED_DIR.mkdir(parents=True, exist_ok=True)
CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
EXPORT_DIR.mkdir(parents=True, exist_ok=True)


def clean_control_chars(text: str) -> str:
    """移除常见非法控制字符，保留换行和制表的基本可读性。"""
    if not isinstance(text, str):
        return text
    # Excel / openpyxl 常见非法字符范围
    text = re.sub(r"[\x00-\x08\x0B-\x0C\x0E-\x1F]", "", text)
    return text


def normalize_text(text: str) -> str:
    """统一 PDF 提取出的文本格式。"""
    if not isinstance(text, str):
        return ""

    text = clean_control_chars(text)

    # Windows 换行统一
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # 行尾多余空格
    text = re.sub(r"[ \t]+\n", "\n", text)

    # 连续空行收敛
    text = re.sub(r"\n{3,}", "\n\n", text)

    # 连续空格收敛
    text = re.sub(r"[ \t]{2,}", " ", text)

    return text.strip()


def clean_for_excel(value: Any) -> Any:
    """清洗为适合写入 Excel 的值。"""
    if not isinstance(value, str):
        return value

    value = clean_control_chars(value)

    # Excel 单元格字符数限制约 32767，留一点余量
    if len(value) > 30000:
        value = value[:30000] + " ...[TRUNCATED]"

    return value


def guess_year(filename: str) -> Optional[int]:
    match = re.search(r"(20\d{2})", filename)
    return int(match.group(1)) if match else None


def guess_doc_type(filename: str) -> str:
    name = filename.lower()

    if "annual" in name:
        return "annual_report"
    if "facts" in name or "figures" in name:
        return "statistics_report"
    if "strategic" in name or "strategy" in name or "plan" in name:
        return "strategy"
    if "trend" in name or "trends" in name:
        return "trend_report"
    if "regulation" in name or "regulations" in name:
        return "regulation"
    if "index" in name:
        return "index_report"

    return "report"


def guess_title(filename: str) -> str:
    stem = Path(filename).stem
    title = stem.replace("_", " ").replace("-", " ").strip()
    title = re.sub(r"\s{2,}", " ", title)
    return title.title()


def extract_pdf(pdf_path: Path) -> Dict[str, Any]:
    """提取 PDF 每页文本，并生成文档级 metadata。"""
    doc = fitz.open(pdf_path)
    pages: List[Dict[str, Any]] = []
    total_chars = 0

    for page_num, page in enumerate(doc, start=1):
        raw_text = page.get_text("text")
        text = normalize_text(raw_text)

        total_chars += len(text)
        pages.append(
            {
                "page": page_num,
                "text": text,
                "char_count": len(text),
            }
        )

    parsed_doc = {
        "filename": pdf_path.name,
        "title": guess_title(pdf_path.name),
        "source_org": "ITU",
        "doc_type": guess_doc_type(pdf_path.name),
        "year": guess_year(pdf_path.name),
        "language": "en",
        "page_count": len(pages),
        "char_count": total_chars,
        "source_path": str(pdf_path),
        "pages": pages,
    }

    return parsed_doc


def build_chunk_record(
    parsed_doc: Dict[str, Any],
    chunk_index: int,
    page_start: int,
    page_end: int,
    text: str,
) -> Dict[str, Any]:
    stem = Path(parsed_doc["filename"]).stem
    chunk_id = f"{stem}_p{page_start}_c{chunk_index:03d}"

    return {
        "chunk_id": chunk_id,
        "filename": parsed_doc["filename"],
        "title": parsed_doc["title"],
        "source_org": parsed_doc["source_org"],
        "doc_type": parsed_doc["doc_type"],
        "year": parsed_doc["year"],
        "language": parsed_doc["language"],
        "page_start": page_start,
        "page_end": page_end,
        "chunk_chars": len(text),
        "text": text,
    }


def chunk_pages(
    parsed_doc: Dict[str, Any],
    max_chars: int = 1800,
    overlap: int = 200,
    min_chunk_chars: int = 200,
) -> List[Dict[str, Any]]:
    """
    简单稳妥版切分策略：
    - 以页为单位累积
    - 到达阈值后输出一个 chunk
    - 保留少量 overlap
    """
    chunks: List[Dict[str, Any]] = []

    buffer = ""
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    chunk_index = 1

    for page_data in parsed_doc["pages"]:
        page_num = page_data["page"]
        page_text = page_data["text"].strip()

        if not page_text:
            continue

        if page_start is None:
            page_start = page_num

        candidate = f"{buffer}\n\n{page_text}".strip() if buffer else page_text

        if len(candidate) <= max_chars:
            buffer = candidate
            page_end = page_num
            continue

        # 当前 candidate 超长，先输出已有 buffer
        if buffer and len(buffer) >= min_chunk_chars and page_start is not None and page_end is not None:
            chunks.append(
                build_chunk_record(
                    parsed_doc=parsed_doc,
                    chunk_index=chunk_index,
                    page_start=page_start,
                    page_end=page_end,
                    text=buffer.strip(),
                )
            )
            chunk_index += 1

            tail = buffer[-overlap:] if overlap > 0 else ""
            buffer = f"{tail}\n\n{page_text}".strip() if tail else page_text
            page_start = page_num
            page_end = page_num
        else:
            # 如果单页本身特别长，则对单页进一步切块
            long_text = candidate
            start = 0
            step = max_chars - overlap if max_chars > overlap else max_chars

            while start < len(long_text):
                end = min(start + max_chars, len(long_text))
                piece = long_text[start:end].strip()

                if piece:
                    chunks.append(
                        build_chunk_record(
                            parsed_doc=parsed_doc,
                            chunk_index=chunk_index,
                            page_start=page_num,
                            page_end=page_num,
                            text=piece,
                        )
                    )
                    chunk_index += 1

                if end >= len(long_text):
                    break
                start += step

            buffer = ""
            page_start = None
            page_end = None

    # 收尾
    if buffer.strip() and page_start is not None and page_end is not None:
        chunks.append(
            build_chunk_record(
                parsed_doc=parsed_doc,
                chunk_index=chunk_index,
                page_start=page_start,
                page_end=page_end,
                text=buffer.strip(),
            )
        )

    return chunks


def save_parsed_json(parsed_doc: Dict[str, Any], output_path: Path) -> None:
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(parsed_doc, f, ensure_ascii=False, indent=2)


def save_chunks_jsonl(chunks: List[Dict[str, Any]], output_path: Path) -> None:
    with open(output_path, "w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")


def export_tables(doc_rows: List[Dict[str, Any]], chunk_rows: List[Dict[str, Any]]) -> None:
    docs_df = pd.DataFrame(doc_rows)
    chunks_df = pd.DataFrame(chunk_rows)

    # 完整导出，程序后续使用
    docs_df.to_csv(EXPORT_DIR / "documents.csv", index=False, encoding="utf-8-sig")
    chunks_df.to_csv(EXPORT_DIR / "chunks.csv", index=False, encoding="utf-8-sig")

    # Excel 版本：适合人工查看
    docs_excel_df = docs_df.copy()
    docs_excel_df = docs_excel_df.apply(lambda col: col.map(clean_for_excel))

    chunks_excel_df = chunks_df.copy()
    if "text" in chunks_excel_df.columns:
        chunks_excel_df["text_preview"] = chunks_excel_df["text"].astype(str).str[:500]
        chunks_excel_df = chunks_excel_df.drop(columns=["text"])

    chunks_excel_df = chunks_excel_df.apply(lambda col: col.map(clean_for_excel))

    docs_excel_df.to_excel(EXPORT_DIR / "documents.xlsx", index=False)
    chunks_excel_df.to_excel(EXPORT_DIR / "chunks.xlsx", index=False)


def main() -> None:
    pdf_files = sorted(PDF_DIR.glob("*.pdf"))

    if not pdf_files:
        print(f"No PDF files found in: {PDF_DIR}")
        return

    doc_rows: List[Dict[str, Any]] = []
    chunk_rows: List[Dict[str, Any]] = []

    print(f"Found {len(pdf_files)} PDF files.\n")

    for pdf_path in pdf_files:
        print(f"Processing: {pdf_path.name}")

        try:
            parsed_doc = extract_pdf(pdf_path)
            chunks = chunk_pages(parsed_doc)

            parsed_output_path = PARSED_DIR / f"{pdf_path.stem}.json"
            chunks_output_path = CHUNKS_DIR / f"{pdf_path.stem}.jsonl"

            save_parsed_json(parsed_doc, parsed_output_path)
            save_chunks_jsonl(chunks, chunks_output_path)

            doc_rows.append(
                {
                    "filename": parsed_doc["filename"],
                    "title": parsed_doc["title"],
                    "source_org": parsed_doc["source_org"],
                    "doc_type": parsed_doc["doc_type"],
                    "year": parsed_doc["year"],
                    "language": parsed_doc["language"],
                    "page_count": parsed_doc["page_count"],
                    "char_count": parsed_doc["char_count"],
                    "chunk_count": len(chunks),
                    "source_path": parsed_doc["source_path"],
                    "parsed_json": str(parsed_output_path),
                    "chunks_jsonl": str(chunks_output_path),
                }
            )

            chunk_rows.extend(chunks)

            print(
                f"  -> pages={parsed_doc['page_count']}, chars={parsed_doc['char_count']}, chunks={len(chunks)}"
            )

        except Exception as e:
            print(f"  [ERROR] Failed to process {pdf_path.name}: {e}")

    print("\nExporting tables...")
    export_tables(doc_rows, chunk_rows)

    print("\nDone.")
    print(f"Documents processed: {len(doc_rows)}")
    print(f"Total chunks: {len(chunk_rows)}")
    print(f"Parsed JSON dir: {PARSED_DIR}")
    print(f"Chunks JSONL dir: {CHUNKS_DIR}")
    print(f"Exports dir: {EXPORT_DIR}")


if __name__ == "__main__":
    main()
