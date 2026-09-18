# -*- coding: utf-8 -*-
"""Extraction: mỗi chunk -> concepts/edges theo schema C1, provenance gắn sẵn.

Schema theo đề C1:
  Node: concept (definition, example, misconception, assessment)
  Edge: prerequisite, broader/narrower, related, example-of, contradicts
  Provenance: source file, page/turn, quote span, confidence

Output: extraction/graph_raw.json (chưa merge alias)
"""
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# --- nạp .env thủ công (tránh thêm dependency) ---
ENV_FILE = ROOT / ".env"
if ENV_FILE.exists():
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def call_llm(system: str, user: str) -> str:
    """Gọi LLM theo provider cấu hình trong .env: LLM_PROVIDER + API key."""
    provider = os.environ.get("LLM_PROVIDER", "openai")
    if provider == "gemini":
        import urllib.request

        key = os.environ["GEMINI_API_KEY"]
        model = os.environ.get("LLM_MODEL", "gemini-2.0-flash")
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={key}"
        )
        body = json.dumps({
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"parts": [{"text": user}]}],
            "generationConfig": {"temperature": 0.1, "response_mime_type": "application/json"},
        }).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.load(r)
        return data["candidates"][0]["content"]["parts"][0]["text"]

    if provider == "anthropic":
        import urllib.request

        key = os.environ["ANTHROPIC_API_KEY"]
        model = os.environ.get("LLM_MODEL", "claude-sonnet-4-20250514")
        url = "https://api.anthropic.com/v1/messages"
        body = json.dumps({
            "model": model,
            "max_tokens": 4000,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }).encode()
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json",
                     "x-api-key": key, "anthropic-version": "2023-06-01"},
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.load(r)
        return data["content"][0]["text"]

    # mặc định: OpenAI / bất kỳ endpoint tương thích OpenAI
    from urllib.request import Request, urlopen

    key = os.environ["OPENAI_API_KEY"]
    base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model = os.environ.get("LLM_MODEL", "gpt-4o-mini")
    url = f"{base}/chat/completions"
    body = json.dumps({
        "model": model,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }).encode()
    req = Request(url, data=body,
                  headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    with urlopen(req, timeout=60) as r:
        data = json.load(r)
    return data["choices"][0]["message"]["content"]


SYSTEM_PROMPT = """Bạn là bộ trích tri thức cho bài giảng AI (khóa AI20k, tiếng Việt).
Nhiệm vụ: đọc MỘT đoạn tài liệu (slide hoặc transcript) và trích ra các KHÁI NIỆM (concept)
cùng QUAN HỆ giữa chúng, theo JSON schema dưới đây. QUY TẮC BẮT BUỘC:

1. "quote" phải là CHUỖI NGUYÊN VĂN sao chép đúng từ đoạn tài liệu (tối đa ~25 từ, giữ chính tả gốc).
   Không được diễn giải lại. Nếu không trích được nguyên văn thì bỏ mục đó.
2. Chỉ trích khái niệm mang tri thức bài giảng (VD: attention, embedding, agent, problem statement...).
   BỎ: lời chào, hành chính lớp, ví dụ đời thường thuần túy không định nghĩa khái niệm.
3. Mỗi concept: name (dạng chuẩn, tiếng Việt nếu tài liệu dùng tiếng Việt), aliases (tên khác nếu có
   trong đoạn), definition (1-2 câu diễn giải NGHĨA, không cần nguyên văn), type
   (concept | example | misconception), confidence 0-1.
4. Edges: chỉ nối các concept CÓ TRONG danh sách concepts của lần trích này.
   Types: prerequisite (A cần biết trước B), broader (A rộng hơn B), related, example-of, contradicts.
5. misconception: chỉ đánh dấu khi tài liệu NÓI RÕ đây là hiểu lầm phổ biến.

Xuất ĐÚNG một JSON object:
{
 "concepts": [
  {"local_id": 1, "name": "...", "aliases": [], "type": "concept",
   "definition": "...", "quote": "...", "confidence": 0.9}
 ],
 "edges": [
  {"from": 1, "to": 2, "type": "prerequisite", "evidence_quote": "...", "confidence": 0.8}
 ]
}"""


def parse_json(raw: str) -> dict:
    """LLM đôi khi bọc json trong ```...``` — lọc lấy JSON thật."""
    raw = raw.strip()
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return {"concepts": [], "edges": []}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"concepts": [], "edges": []}


def main(limit: int | None = None):
    data = json.loads((ROOT / "ingestion" / "chunks.json").read_text(encoding="utf-8"))
    chunks = data["chunks"]
    if limit:
        chunks = chunks[:limit]

    out_path = ROOT / "extraction" / "graph_raw.jsonl"
    out_path.parent.mkdir(exist_ok=True)
    done_ids = set()
    if out_path.exists():  # resume: không gọi lại chunk đã xong
        for line in out_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    done_ids.add(json.loads(line)["chunk_id"])
                except json.JSONDecodeError:
                    pass

    n_ok = n_empty = n_err = 0
    with out_path.open("a", encoding="utf-8") as f:
        for i, chunk in enumerate(chunks):
            if chunk["chunk_id"] in done_ids:
                continue
            user_msg = (
                f"NGUỒN: file {chunk['file']}, "
                f"{'trang ' + str(chunk['page']) if chunk['source_type'] == 'slide' else 'lượt nói ' + chunk['turn']}\n"
                f"ĐOẠN TÀI LIỆU:\n{chunk['text'][:4000]}"
            )
            try:
                raw = None
                for attempt in range(4):  # retry 503/429 (server quá tải / rate limit)
                    try:
                        raw = call_llm(SYSTEM_PROMPT, user_msg)
                        break
                    except Exception as e:
                        msg = str(e)
                        is_transient = "503" in msg or "429" in msg or "500" in msg
                        if attempt == 3 or not is_transient:
                            raise
                        wait = 5 * (attempt + 1)
                        print(f"  [retry {attempt + 1}] {chunk['chunk_id']}: {msg[:60]} — chờ {wait}s")
                        time.sleep(wait)
                parsed = parse_json(raw)
            except Exception as e:
                print(f"[ERR] {chunk['chunk_id']}: {e}")
                n_err += 1
                time.sleep(2)
                continue

            concepts = parsed.get("concepts", [])
            if not concepts:
                n_empty += 1
            else:
                n_ok += 1
            record = {
                "chunk_id": chunk["chunk_id"],
                "provenance": {
                    "file": chunk["file"],
                    **({"page": chunk["page"]} if chunk["source_type"] == "slide"
                       else {"turn": chunk["turn"], "section": chunk.get("section", "")}),
                },
                "concepts": concepts,
                "edges": parsed.get("edges", []),
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            time.sleep(0.5)  # OpenAI rate limit thoáng; chỉ cần nhịp nhẹ tránh burst
            if (i + 1) % 10 == 0:
                print(f"  {i + 1}/{len(chunks)} chunk... (ok={n_ok}, trống={n_empty}, lỗi={n_err})")

    print(f"\nXong: ok={n_ok}, không trích được={n_empty}, lỗi={n_err}")
    print(f"-> {out_path}")


if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    main(limit)
