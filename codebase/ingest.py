# -*- coding: utf-8 -*-
"""Ingestion: biến slide PDF + transcript .md thành chunk có provenance.

Mỗi chunk sinh ra đã mang nguồn (file, page/turn, span text) — provenance
được gắn ngay từ lúc ingestion, không "gắn nguồn về sau".
Output: ingestion/chunks.json
"""
import json
import re
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "ingestion"
OUT_DIR.mkdir(exist_ok=True)

SLIDES = [
    {"file": "d1-slide-hackathon.pdf", "doc_id": "D1", "title": "Day 1 — AI & LLM Foundation"},
    {"file": "d2-slide-hackathon.pdf", "doc_id": "D2", "title": "Day 2 — Xác định bài toán cho AI"},
]
TRANSCRIPTS = [
    {"file": "transcript-Day 1.md", "doc_id": "T1", "turn_prefix": "T04"},
    {"file": "transcript-Day 2.md", "doc_id": "T2", "turn_prefix": ""},
]

# Bỏ các phần hành chính/tương tác không mang tri thức bài giảng
SKIP_SECTION_RE = re.compile(
    r"(Hoạt động lớp|chào lớp|giới thiệu giảng viên|nghỉ giữa giờ|hỏi đáp cuối|tổng kết buổi)",
    re.IGNORECASE,
)


def ingest_slides():
    """Mỗi trang slide = 1 chunk. Ngữ nghĩa: thứ tự trang trong file."""
    chunks = []
    for spec in SLIDES:
        doc = pymupdf.open(ROOT / spec["file"])
        for i, page in enumerate(doc):
            text = page.get_text().strip()
            # slide thường đọc theo cột; pymupdf trả theo block, giữ nguyên
            if len(text) < 5:
                continue
            chunks.append({
                "chunk_id": f'{spec["doc_id"]}-p{i + 1:02d}',
                "source_type": "slide",
                "doc_id": spec["doc_id"],
                "file": spec["file"],
                "page": i + 1,
                "text": text,
            })
    return chunks


def ingest_transcripts():
    """Mỗi lượt nói [Txx-NNN] = 1 chunk, kèm heading mục gần nhất."""
    chunks = []
    for spec in TRANSCRIPTS:
        content = (ROOT / spec["file"]).read_text(encoding="utf-8")
        current_section = ""
        # pattern: heading '## ...' hoặc turn '**[Txx-NNN]** text'
        token_re = re.compile(r"^(#{2,3}\s+.+|\*\*\[[^\]]+\]\*\*.*)$", re.MULTILINE)
        for m in token_re.finditer(content):
            line = m.group(0).strip()
            if line.startswith("#"):
                current_section = line.lstrip("# ").strip()
                continue
            turn_match = re.match(r"\*\*\[([^\]]+)\]\*\*\s*(.*)", line, re.DOTALL)
            if not turn_match:
                continue
            turn_id, text = turn_match.group(1), turn_match.group(2).strip()
            if not text or len(text) < 40:
                continue
            # lượt chỉ chứa ghi chú hành chính, không mang tri thức
            if re.match(r"^\[(Hoạt động lớp|học viên|không nghe rõ)", text):
                continue
            if SKIP_SECTION_RE.search(current_section):
                continue
            chunks.append({
                "chunk_id": f'{spec["doc_id"]}-{turn_id}',
                "source_type": "transcript",
                "doc_id": spec["doc_id"],
                "file": spec["file"],
                "turn": turn_id,
                "section": current_section,
                "text": text,
            })
    return chunks


def ingest_file(path):
    """Ingest 1 file bất kỳ: PDF -> chunk theo trang, .md -> chunk theo lượt nói.

    Dùng cho web app (upload tùy ý); giữ nguyên quy tắc provenance của bản batch.
    """
    path = Path(path)
    if path.suffix.lower() == ".pdf":
        doc_id = path.stem[:2].upper()
        chunks = []
        doc = pymupdf.open(path)
        for i, page in enumerate(doc):
            text = page.get_text().strip()
            if len(text) < 5:
                continue
            chunks.append({
                "chunk_id": f"{doc_id}-p{i + 1:02d}",
                "source_type": "slide",
                "doc_id": doc_id,
                "file": path.name,
                "page": i + 1,
                "text": text,
            })
        return chunks
    if path.suffix.lower() in (".md", ".txt"):
        content = path.read_text(encoding="utf-8")
        doc_id = path.stem[:2].upper()
        chunks = []
        current_section = ""
        # Preserve multiline turns; ordinary Markdown/TXT also works without turn markers.
        tokens = list(re.finditer(r"^(#{1,6}\s+[^\n]+|\*\*\[[^\]]+\]\*\*)", content, re.MULTILINE))
        spans = []
        if not tokens:
            spans = [("", None, content)]
        else:
            if content[:tokens[0].start()].strip():
                spans.append(("", None, content[:tokens[0].start()]))
            for i, token in enumerate(tokens):
                marker = token.group(0)
                end = tokens[i + 1].start() if i + 1 < len(tokens) else len(content)
                if marker.startswith('#'):
                    current_section = marker.lstrip('# ').strip()
                    turn = None
                else:
                    turn = marker[3:-3]
                spans.append((current_section, turn, content[token.end():end]))
        for section, turn, body in spans:
            if SKIP_SECTION_RE.search(section):
                continue
            body = body.strip()
            for offset in range(0, len(body), 3000):
                text = body[offset:offset + 3000].strip()
                if not text:
                    continue
                code = (turn + (f"-{offset // 3000 + 1}" if offset else "")) if turn else f"TXT-{len(chunks) + 1:03d}"
                chunks.append({"chunk_id": f"{doc_id}-{code}", "source_type": "transcript",
                               "doc_id": doc_id, "file": path.name, "turn": code,
                               "section": section, "text": text})
        return chunks
    raise ValueError(f"Định dạng chưa hỗ trợ: {path.suffix} (chỉ PDF/.md/.txt)")


def main():
    slide_chunks = ingest_slides()
    transcript_chunks = ingest_transcripts()
    all_chunks = slide_chunks + transcript_chunks

    out = {
        "meta": {
            "source_files": [s["file"] for s in SLIDES + TRANSCRIPTS],
            "n_slide_chunks": len(slide_chunks),
            "n_transcript_chunks": len(transcript_chunks),
            "provenance_rule": "chunk_id -> (file, page | turn); span quote giữ nguyên từ text",
        },
        "chunks": all_chunks,
    }
    (OUT_DIR / "chunks.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"slide chunks: {len(slide_chunks)}")
    print(f"transcript chunks: {len(transcript_chunks)} (sau khi bỏ mục hành chính)")
    print(f"-> {OUT_DIR / 'chunks.json'}")
    # preview vài chunk
    for c in all_chunks[:2] + all_chunks[-2:]:
        print("-", c["chunk_id"], "|", c["text"][:80].replace("\n", " "))


if __name__ == "__main__":
    main()
