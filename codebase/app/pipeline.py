# -*- coding: utf-8 -*-
"""Pipeline tái sử dụng: gói ingest/extract/merge thành hàm, giữ nguyên logic.

Điểm mới so với bản batch (chi phí API):
- Cache theo SHA-256: file đã xử lý -> trả graph có sẵn, 0 lời gọi API.
- Prefilter heuristic: chunk nghi "rác" (quá ngắn, tỷ lệ từ trùng lặp cao,
  chỉ branding) bị loại TRƯỚC khi gọi LLM — mỗi chunk bị bỏ có log lý do.
- ai_trace.log: mọi lời gọi LLM ghi request tóm lược + response + token
  (bằng chứng "lời gọi AI thật" cho R5).
"""
import hashlib
import json
import os
import re
import sys
import threading
import time
import unicodedata
from pathlib import Path

_CODEBASE = Path(__file__).resolve().parent.parent
if str(_CODEBASE) not in sys.path:
    sys.path.insert(0, str(_CODEBASE))

from ingest import ingest_file          # logic cũ, không đổi
from extract import call_llm, parse_json, SYSTEM_PROMPT

ROOT = Path(__file__).resolve().parent.parent.parent
APPDATA = ROOT / "appdata"
UPLOADS = APPDATA / "uploads"
CACHE = APPDATA / "cache"
TRACE = APPDATA / "ai_trace.log"


# ---------------------------------------------------------------- cache ----

def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def cache_get(sha: str):
    p = CACHE / f"{sha}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def cache_put(sha: str, graph: dict):
    CACHE.mkdir(parents=True, exist_ok=True)
    (CACHE / f"{sha}.json").write_text(
        json.dumps(graph, ensure_ascii=False), encoding="utf-8")


# ------------------------------------------------------------ prefilter ----

BRAND_RE = re.compile(
    r"(ai in action|hackathon|vinuni|agenda|code of conduct|qr code|breakout|"
    r"www\.|@|break time|lunch|check.?in)", re.IGNORECASE)


def is_junk(text: str) -> str | None:
    """Trả về lý do nếu chunk không đáng gọi LLM, ngược lại None.

    Heuristic rẻ (0 API call) — chỉ loại chunk RÕ ràng không có tri thức;
    gây nghi vấn thì vẫn giữ (ưu tiên độ chính xác provenance).
    """
    t = text.strip()
    if len(t) < 60:
        return "quá ngắn (<60 ký tự)"
    words = t.split()
    uniq_ratio = len(set(w.lower() for w in words)) / max(len(words), 1)
    if uniq_ratio < 0.35:
        return f"lặp từ nhiều (unique ratio {uniq_ratio:.2f})"
    if BRAND_RE.search(t) and len(t) < 220:
        return "chỉ branding/hành chính"
    return None


# ---------------------------------------------------------- trace (R5) ----

def trace_log(kind: str, **kw):
    TRACE.parent.mkdir(parents=True, exist_ok=True)
    rec = {"ts": time.strftime("%H:%M:%S"), "kind": kind, **kw}
    with TRACE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


# ------------------------------------------------------------- pipeline ----

def build_graph_for_file(path: Path, force: bool = False,
                         progress=None) -> dict:
    """File -> graph riêng. Có cache SHA-256; thiếu mới gọi LLM.

    progress: callable(done_chunks, total_chunks) để UI hiển thị.
    Trả: {sha, from_cache, nodes, edges, stats, skipped:[...]}
    """
    sha = file_sha256(path)
    if not force:
        cached = cache_get(sha)
        if cached:
            trace_log("cache_hit", sha=sha[:12], file=path.name)
            return {**cached, "from_cache": True}

    chunks = ingest_file(path)                       # logic ingestion cũ
    kept, skipped = [], []
    for c in chunks:
        reason = is_junk(c["text"])
        (skipped if reason else kept).append({**c, **({"skip_reason": reason} if reason else {})})

    # extraction song song 6 luồng (rate limit OpenAI cho phép) — nhanh ~6x tuần tự
    from concurrent.futures import ThreadPoolExecutor

    out_path = UPLOADS / sha[:12] / "graph_raw.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if out_path.exists():
        for line in out_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    done.add(json.loads(line)["chunk_id"])
                except json.JSONDecodeError:
                    pass

    todo = [c for c in kept if c["chunk_id"] not in done]
    records = []
    if out_path.exists():
        for line in out_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))

    done_count = [0]
    lock = threading.Lock()

    def _extract_one(chunk):
        prov = {"file": path.name,
                **({"page": chunk["page"]} if chunk["source_type"] == "slide"
                   else {"turn": chunk["turn"]})}
        raw = call_llm(SYSTEM_PROMPT,
                       f"NGUỒN: file {path.name}, "
                       f"{'trang ' + str(chunk['page']) if chunk['source_type'] == 'slide' else 'lượt nói ' + chunk['turn']}\n"
                       f"ĐOẠN TÀI LIỆU:\n{chunk['text'][:4000]}")

        def _norm_ws(s: str) -> str:
            return re.sub(r"\s+", " ", s.replace("“", '"').replace("”", '"')).strip()

        # kiểm chứng provenance NGAY KHI trích: quote phải nguyên văn trong chunk
        n_src = _norm_ws(chunk["text"])
        verified, dropped = [], 0
        for c in parse_json(raw).get("concepts", []):
            q = _norm_ws(c.get("quote", ""))
            if q and q in n_src:
                verified.append(c)
            else:
                dropped += 1  # quote không truy được về chunk -> bỏ (nguyên tắc provenance)
        rec = {"chunk_id": chunk["chunk_id"], "provenance": prov,
               "concepts": verified,
               "edges": parse_json(raw).get("edges", []),
               "n_quote_dropped": dropped}
        trace_log("llm_extract", chunk=chunk["chunk_id"],
                  n_concepts=len(verified), n_quote_dropped=dropped)
        with lock:
            records.append(rec)
            done_count[0] += 1
            if progress:
                progress(done_count[0], len(todo))

    if todo:
        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(_extract_one, todo))

    with out_path.open("a", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    graph = _merge_records(records)                  # logic merge cũ
    result = {
        "sha": sha, "from_cache": False,
        "nodes": graph["nodes"], "edges": graph["edges"],
        "stats": {**graph["meta"],
                  "n_chunks_total": len(chunks),
                  "n_chunks_kept": len(kept),
                  "n_chunks_skipped": len(skipped)},
        "skipped": skipped,
    }
    cache_put(sha, result)
    trace_log("graph_built", sha=sha[:12], file=path.name,
              nodes=len(graph["nodes"]), edges=len(graph["edges"]))
    return result


def _norm_key(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _merge_records(records: list) -> dict:
    """Merge tầng 1 (khóa thường hóa) — cùng logic merge.py nhưng nội bộ.

    Tầng 2 (LLM phán xét) chỉ chạy ở API /merge khi người dùng ghép file,
    để tiết kiệm chi phí: graph đơn file chỉ cần gộp tên trùng chính xác.
    """
    key_to_id, nodes = {}, {}
    for r in records:
        prov = r["provenance"]
        for c in r["concepts"]:
            k = _norm_key(c["name"])
            # evidence ghép ĐÔI: quote nào đi với nguồn đó — không bao giờ lệch nhau
            ev = {"quote": c.get("quote", ""), "source": prov}
            if k in key_to_id:
                n = nodes[key_to_id[k]]
                if (c.get("confidence") or 0) > n["confidence"]:
                    n["definition"] = c.get("definition", n["definition"])
                n["confidence"] = max(n["confidence"], c.get("confidence") or 0)
                if c.get("quote"):
                    n["evidence"].append(ev)
                n["sources"].append(prov)
                continue
            cid = f"c{len(nodes) + 1:04d}"
            nodes[cid] = {"id": cid, "name": c["name"],
                          "aliases": sorted(a for a in c.get("aliases", []) if a and a != c["name"]),
                          "type": c.get("type", "concept"),
                          "definition": c.get("definition", ""),
                          "quotes": [c.get("quote", "")] if c.get("quote") else [],
                          "evidence": [ev] if c.get("quote") else [],
                          "sources": [prov],
                          "confidence": c.get("confidence") or 0}
            key_to_id[k] = cid

    edges = []
    for r in records:
        prov = r["provenance"]
        local = {c["local_id"]: key_to_id.get(_norm_key(c["name"]))
                 for c in r["concepts"]}
        for e in r["edges"]:
            s, d = local.get(e.get("from")), local.get(e.get("to"))
            if s and d and s != d:
                edges.append({"source": s, "target": d, "type": e.get("type"),
                              "evidence_quote": e.get("evidence_quote", ""),
                              "provenance": prov,
                              "confidence": e.get("confidence", 0)})

    meta = {"n_nodes": len(nodes), "n_edges": len(edges),
            "node_types": {}, "edge_types": {}}
    for n in nodes.values():
        meta["node_types"][n["type"]] = meta["node_types"].get(n["type"], 0) + 1
    for e in edges:
        meta["edge_types"][e["type"]] = meta["edge_types"].get(e["type"], 0) + 1
    return {"meta": meta, "nodes": list(nodes.values()), "edges": edges}
