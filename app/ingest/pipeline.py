from __future__ import annotations

from pathlib import Path
import json
import re
import hashlib
from typing import Any, Dict, List, Optional, Tuple

import fitz  # pymupdf
import pandas as pd


# =========================
# 路径配置
# =========================
BASE_DIR = Path(r"E:\MyProjects\ITUassistant")
PDF_DIR = BASE_DIR / "data" / "itu_pdfs"
PARSED_DIR = BASE_DIR / "data" / "parsed"
CHUNKS_DIR = BASE_DIR / "data" / "chunks"
EXPORT_DIR = BASE_DIR / "data" / "exports"

PARSED_DIR.mkdir(parents=True, exist_ok=True)
CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
EXPORT_DIR.mkdir(parents=True, exist_ok=True)


# =========================
# 切分参数
# =========================
TARGET_CHARS = 1200
MAX_CHARS = 1700
MIN_CHARS = 250
OVERLAP_PARAGRAPHS = 1

NOISE_KEYWORDS = [
    "table of contents",
    "contents",
    "foreword",
    "methodology",
    "list of figures",
    "list of tables",
]

TITLE_STOPWORDS = {
    "foreword",
    "contents",
    "table of contents",
    "methodology",
}


# =========================
# 基础清洗
# =========================
def clean_control_chars(text: str) -> str:
    if not isinstance(text, str):
        return ""
    return re.sub(r"[\x00-\x08\x0B-\x0C\x0E-\x1F]", "", text)


def normalize_text(text: str) -> str:
    if not isinstance(text, str):
        return ""

    text = clean_control_chars(text)

    # 常见 PDF 垃圾字符
    text = text.replace("�", "")
    text = text.replace("\uf0b7", " ")
    text = text.replace("\u00a0", " ")

    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # 去掉目录点线
    text = re.sub(r"[.·•]{5,}", " ", text)

    # 去掉多余空格
    text = re.sub(r"[ \t]+", " ", text)

    # 行尾空白
    text = re.sub(r"[ \t]+\n", "\n", text)

    # 连续空行
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def clean_for_excel(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    value = clean_control_chars(value)
    value = value.replace("�", "")
    if len(value) > 30000:
        value = value[:30000] + " ...[TRUNCATED]"
    return value


# =========================
# 标题 / 文档类型猜测
# =========================
def guess_year(filename: str) -> Optional[int]:
    m = re.search(r"(20\d{2})", filename)
    return int(m.group(1)) if m else None


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


def guess_title_from_filename(filename: str) -> str:
    stem = Path(filename).stem.lower()

    # facts_2022.pdf / facts_2024.pdf
    m = re.fullmatch(r"facts_(20\d{2})", stem)
    if m:
        year = m.group(1)
        return f"Measuring Digital Development: Facts and Figures {year}"

    # itu_annual_report_2024.pdf
    m = re.fullmatch(r"itu_annual_report_(20\d{2})", stem)
    if m:
        year = m.group(1)
        return f"ITU Annual Report {year}"

    # mdd_2024_lldc.pdf
    m = re.fullmatch(r"mdd_(20\d{2})_lldc", stem)
    if m:
        year = m.group(1)
        return f"Measuring Digital Development {year} - LLDC"

    # 兜底
    title = stem.replace("_", " ").replace("-", " ").strip()
    title = re.sub(r"\s{2,}", " ", title)
    return title.title()


def looks_like_title_line(line: str) -> bool:
    s = line.strip()
    lower = s.lower()

    if not s:
        return False

    if len(s) < 8 or len(s) > 120:
        return False

    if lower in TITLE_STOPWORDS:
        return False

    if re.fullmatch(r"[ivxlcdm\d]+", lower):
        return False

    # 太像完整句子
    if s.endswith("."):
        return False

    # 太像正文句子
    sentence_like_markers = [
        "the ",
        "and ",
        "with ",
        "yet ",
        "this ",
        "our ",
        "it ",
        "in ",
    ]
    if sum(marker in lower for marker in sentence_like_markers) >= 3:
        return False

    # 目录风格
    if re.search(r"\.{5,}\s*\d+$", s):
        return False

    return True


def infer_title_from_pages(pages: List[Dict[str, Any]], fallback: str) -> str:
    """
    标题抽取策略：
    1. 优先识别强规则标题
    2. 否则从前两页找最像标题的短行
    3. 最后回退到文件名标题
    """
    candidate_scores: List[Tuple[int, str]] = []

    for page_idx, page in enumerate(pages[:2], start=1):
        lines = [ln.strip() for ln in page["text"].splitlines() if ln.strip()]

        for line_idx, ln in enumerate(lines[:20], start=1):
            lower = ln.lower()

            # 强规则：Facts and Figures
            if "measuring digital development" in lower and "facts and figures" in lower:
                year_match = re.search(r"(20\d{2})", ln)
                if year_match:
                    return f"Measuring Digital Development: Facts and Figures {year_match.group(1)}"
                return "Measuring Digital Development: Facts and Figures"

            # 强规则：Annual Report
            if "annual report on the implementation" in lower:
                year_match = re.search(r"(20\d{2})", ln)
                if year_match:
                    return f"ITU Annual Report {year_match.group(1)}"
                return "ITU Annual Report"

            if not looks_like_title_line(ln):
                continue

            score = 0
            if page_idx == 1:
                score += 20

            if line_idx <= 5:
                score += 20
            elif line_idx <= 10:
                score += 10

            if 20 <= len(ln) <= 80:
                score += 15
            elif 12 <= len(ln) <= 100:
                score += 8

            title_keywords = [
                "facts and figures",
                "measuring digital development",
                "annual report",
                "digital development",
                "report",
            ]
            for kw in title_keywords:
                if kw in lower:
                    score += 10

            candidate_scores.append((score, ln))

    if candidate_scores:
        candidate_scores.sort(key=lambda x: x[0], reverse=True)
        best = candidate_scores[0][1]
        best = re.sub(r"\s{2,}", " ", best).strip()
        return best[:120]

    return fallback


# =========================
# 页面级噪声判断
# =========================
def is_probably_noise_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return True

    lower = s.lower()

    # 纯页码 / 罗马数字
    if re.fullmatch(r"[ivxlcdm\d]+", lower):
        return True

    # 目录项风格
    if re.search(r"\.{5,}\s*\d+$", s):
        return True

    # 大量异常替代字符
    if s.count("�") >= 3:
        return True

    # 很短的装饰线
    if re.fullmatch(r"[-_=]{3,}", s):
        return True

    return False


def is_noise_paragraph(text: str) -> bool:
    s = text.strip()
    lower = s.lower()

    if not s:
        return True

    if len(s) < 20:
        return True

    for kw in NOISE_KEYWORDS:
        if kw in lower and len(s) < 1000:
            return True

    if re.search(r"(foreword|contents|methodology).{0,50}\d+$", lower):
        return True

    if re.search(r"[.·•]{5,}", s):
        return True

    alnum = sum(ch.isalnum() for ch in s)
    if alnum / max(len(s), 1) < 0.35:
        return True

    return False


# =========================
# PDF 解析
# =========================
def extract_pdf(pdf_path: Path) -> Dict[str, Any]:
    doc = fitz.open(pdf_path)
    pages: List[Dict[str, Any]] = []
    total_chars = 0

    for page_num, page in enumerate(doc, start=1):
        raw_text = page.get_text("text")
        text = normalize_text(raw_text)

        # 页面内先按行去掉明显噪声
        lines = []
        for line in text.splitlines():
            line = line.strip()
            if is_probably_noise_line(line):
                continue
            lines.append(line)

        text = "\n".join(lines).strip()
        total_chars += len(text)

        pages.append({
            "page": page_num,
            "text": text,
            "char_count": len(text),
        })

    title_from_filename = guess_title_from_filename(pdf_path.name)
    title_from_pages = infer_title_from_pages(pages, title_from_filename)

    # 如果页面标题明显像正文/机构名/前言，则优先回退到文件名标题
    bad_title_markers = [
        "serve humanity",
        "international telecommunication union",
        "foreword",
    ]
    title_lower = title_from_pages.lower()
    if any(marker in title_lower for marker in bad_title_markers):
        title = title_from_filename
    else:
        title = title_from_pages

    parsed_doc = {
        "filename": pdf_path.name,
        "title": title,
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


# =========================
# 段落切分
# =========================
def split_page_into_paragraphs(page_text: str) -> List[str]:
    if not page_text.strip():
        return []

    blocks = re.split(r"\n\s*\n", page_text)
    paragraphs: List[str] = []

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        merged = " ".join(lines)
        merged = re.sub(r"\s{2,}", " ", merged).strip()

        if not merged:
            continue
        if is_noise_paragraph(merged):
            continue

        paragraphs.append(merged)

    return paragraphs


def collect_paragraph_units(parsed_doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    units: List[Dict[str, Any]] = []

    for page in parsed_doc["pages"]:
        page_num = page["page"]
        paras = split_page_into_paragraphs(page["text"])

        for para in paras:
            if len(para) < 30:
                continue
            units.append({
                "page": page_num,
                "text": para,
            })

    return units


# =========================
# chunk 构建
# =========================
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


def chunk_document(
    parsed_doc: Dict[str, Any],
    target_chars: int = TARGET_CHARS,
    max_chars: int = MAX_CHARS,
    min_chars: int = MIN_CHARS,
    overlap_paragraphs: int = OVERLAP_PARAGRAPHS,
) -> List[Dict[str, Any]]:
    units = collect_paragraph_units(parsed_doc)
    chunks: List[Dict[str, Any]] = []

    current_units: List[Dict[str, Any]] = []
    current_len = 0
    chunk_index = 1

    def flush():
        nonlocal current_units, current_len, chunk_index, chunks
        if not current_units:
            return

        text = "\n\n".join(u["text"] for u in current_units).strip()
        if len(text) < min_chars:
            return

        page_start = current_units[0]["page"]
        page_end = current_units[-1]["page"]

        chunks.append(
            build_chunk_record(
                parsed_doc=parsed_doc,
                chunk_index=chunk_index,
                page_start=page_start,
                page_end=page_end,
                text=text,
            )
        )
        chunk_index += 1

        if overlap_paragraphs > 0:
            current_units = current_units[-overlap_paragraphs:]
            current_len = sum(len(u["text"]) + 2 for u in current_units)
        else:
            current_units = []
            current_len = 0

    for unit in units:
        unit_len = len(unit["text"]) + 2

        if len(unit["text"]) > max_chars:
            if current_units:
                flush()

            long_text = unit["text"]
            start = 0
            step = max_chars - 180

            while start < len(long_text):
                end = min(start + max_chars, len(long_text))
                piece = long_text[start:end].strip()
                if len(piece) >= min_chars:
                    chunks.append(
                        build_chunk_record(
                            parsed_doc=parsed_doc,
                            chunk_index=chunk_index,
                            page_start=unit["page"],
                            page_end=unit["page"],
                            text=piece,
                        )
                    )
                    chunk_index += 1

                if end >= len(long_text):
                    break
                start += step

            current_units = []
            current_len = 0
            continue

        if current_len + unit_len <= target_chars:
            current_units.append(unit)
            current_len += unit_len
            continue

        if current_len >= min_chars:
            flush()

        current_units.append(unit)
        current_len += unit_len

        if current_len >= max_chars:
            flush()

    if current_units:
        text = "\n\n".join(u["text"] for u in current_units).strip()
        if len(text) >= min_chars:
            page_start = current_units[0]["page"]
            page_end = current_units[-1]["page"]
            chunks.append(
                build_chunk_record(
                    parsed_doc=parsed_doc,
                    chunk_index=chunk_index,
                    page_start=page_start,
                    page_end=page_end,
                    text=text,
                )
            )

    return chunks


# =========================
# 去重
# =========================
def stable_text_hash(text: str) -> str:
    return hashlib.md5(text.encode("utf-8", errors="ignore")).hexdigest()


def document_content_signature(parsed_doc: Dict[str, Any]) -> str:
    parts = []
    for p in parsed_doc["pages"]:
        txt = p["text"].strip()
        if txt:
            parts.append(txt[:3000])
    joined = "\n".join(parts[:8])
    return stable_text_hash(joined)


# =========================
# 保存
# =========================
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

    docs_df.to_csv(EXPORT_DIR / "documents.csv", index=False, encoding="utf-8-sig")
    chunks_df.to_csv(EXPORT_DIR / "chunks.csv", index=False, encoding="utf-8-sig")

    docs_excel_df = docs_df.copy()
    docs_excel_df = docs_excel_df.apply(lambda col: col.map(clean_for_excel))

    chunks_excel_df = chunks_df.copy()
    if "text" in chunks_excel_df.columns:
        chunks_excel_df["text_preview"] = chunks_excel_df["text"].astype(str).str[:500]
        chunks_excel_df = chunks_excel_df.drop(columns=["text"])
    chunks_excel_df = chunks_excel_df.apply(lambda col: col.map(clean_for_excel))

    docs_excel_df.to_excel(EXPORT_DIR / "documents.xlsx", index=False)
    chunks_excel_df.to_excel(EXPORT_DIR / "chunks.xlsx", index=False)


# =========================
# 主流程
# =========================
def main() -> None:
    pdf_files = sorted(PDF_DIR.glob("*.pdf"))
    if not pdf_files:
        print(f"No PDF files found in: {PDF_DIR}")
        return

    print(f"Found {len(pdf_files)} PDF files.\n")

    doc_rows: List[Dict[str, Any]] = []
    chunk_rows: List[Dict[str, Any]] = []
    seen_signatures: Dict[str, str] = {}

    for pdf_path in pdf_files:
        print(f"Processing: {pdf_path.name}")

        try:
            parsed_doc = extract_pdf(pdf_path)

            if parsed_doc["char_count"] < 1000:
                print(f"  -> skipped: too little text ({parsed_doc['char_count']} chars)")
                continue

            signature = document_content_signature(parsed_doc)
            if signature in seen_signatures:
                print(f"  -> skipped duplicate of: {seen_signatures[signature]}")
                continue
            seen_signatures[signature] = pdf_path.name

            chunks = chunk_document(parsed_doc)

            if not chunks:
                print("  -> skipped: no valid chunks")
                continue

            parsed_output_path = PARSED_DIR / f"{pdf_path.stem}.json"
            chunks_output_path = CHUNKS_DIR / f"{pdf_path.stem}.jsonl"

            save_parsed_json(parsed_doc, parsed_output_path)
            save_chunks_jsonl(chunks, chunks_output_path)

            doc_rows.append({
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
                "content_signature": signature,
            })

            chunk_rows.extend(chunks)

            print(
                f"  -> title={parsed_doc['title'][:80]!r}, "
                f"pages={parsed_doc['page_count']}, chars={parsed_doc['char_count']}, chunks={len(chunks)}"
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
