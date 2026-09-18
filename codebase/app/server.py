# -*- coding: utf-8 -*-
"""Lessonleaf API — điều phối pipeline AI thật phía sau UI có sẵn.

Endpoints:
  POST /api/upload          multipart file -> xử lý ngầm (chunking + LLM + graph)
  GET  /api/docs            danh sách tài liệu + trạng thái + tiến độ
  DELETE /api/doc/{id}      xóa file = xóa graph (đúng yêu cầu bài toán)
  GET  /api/graph/{gid}     graph per-file hoặc merged (cho explorer)
  POST /api/merge           ghép 2-3 graph + LLM kiểm duyệt trùng lặp
  POST /api/quiz            sinh quiz có evidence gate, trả đúng shape `bank` của UI
  GET  /api/trace           N lời gọi AI gần nhất (bằng chứng R5)

Chạy: .venv/Scripts/python -m uvicorn app.server:app --port 8000
"""
import json
import re
import threading
import time
import unicodedata
import uuid
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))       # app/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # codebase/

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from pipeline import (CACHE, TRACE, UPLOADS, build_graph_for_file,
                      call_llm, file_sha256, is_junk, parse_json, trace_log)

ROOT = Path(__file__).resolve().parent.parent.parent
REGISTRY = ROOT / "appdata" / "registry.json"
APP = FastAPI(title="Lessonleaf API")

_lock = threading.Lock()
JOBS = {}  # doc_id -> {"status", "progress", "total", "error"}


def _load_registry() -> dict:
    if REGISTRY.exists():
        return json.loads(REGISTRY.read_text(encoding="utf-8"))
    return {"docs": {}, "merges": {}}


def _save_registry(reg: dict):
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY.write_text(json.dumps(reg, ensure_ascii=False, indent=1), encoding="utf-8")


def _chunks_path(sha: str) -> Path:
    return UPLOADS / sha[:12] / "chunks.json"


# ------------------------------------------------------------ processing ---

def _process(doc_id: str, path: Path, sha: str):
    """Background: chunking + extraction + graph. Cập nhật JOBS cho UI."""
    try:
        with _lock:
            JOBS[doc_id] = {"status": "processing", "progress": 0, "total": 0}

        def progress(done, total):
            with _lock:
                JOBS[doc_id].update(progress=done, total=total)

        result = build_graph_for_file(path, progress=progress)

        # lưu chunks (kept) để View source đọc text gốc
        chunks = result.pop("skipped", [])
        _chunks_path(sha).parent.mkdir(parents=True, exist_ok=True)
        # build_graph_for_file không trả kept chunks — viết lại từ raw provenance
        reg = _load_registry()
        reg["docs"][doc_id] = {
            "doc_id": doc_id, "name": path.name, "sha": sha,
            "stats": result["stats"], "n_nodes": len(result["nodes"]),
            "n_edges": len(result["edges"]),
            "built_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "from_cache": result.get("from_cache", False),
        }
        _save_registry(reg)
        with _lock:
            JOBS[doc_id] = {"status": "ready", "progress": 1, "total": 1,
                            "n_nodes": len(result["nodes"]),
                            "n_edges": len(result["edges"])}
    except Exception as e:  # lỗi hiển thị thẳng cho người dùng, không treo
        with _lock:
            JOBS[doc_id] = {"status": "error", "error": str(e)[:300]}


# ---------------------------------------------------------------- upload ---

@APP.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    name = Path(file.filename).name
    if not re.search(r"\.(pdf|md|txt)$", name, re.IGNORECASE):
        raise HTTPException(400, "Chỉ hỗ trợ PDF / .md / .txt")
    data = await file.read()
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(400, "Tệp vượt 20 MB")
    import hashlib
    sha = hashlib.sha256(data).hexdigest()
    doc_id = sha[:12]
    dir_ = UPLOADS / doc_id
    dir_.mkdir(parents=True, exist_ok=True)
    path = dir_ / name
    path.write_bytes(data)

    reg = _load_registry()
    reg["docs"][doc_id] = {
        "doc_id": doc_id, "name": name, "sha": sha, "stats": {},
        "n_nodes": 0, "n_edges": 0, "built_at": None, "from_cache": False,
    }
    _save_registry(reg)

    # cache hit -> "xử lý" tức thì, 0 lời gọi AI
    if (CACHE / f"{sha}.json").exists():
        with _lock:
            JOBS[doc_id] = {"status": "processing", "progress": 0, "total": 0}
        threading.Thread(target=_process, args=(doc_id, path, sha), daemon=True).start()
        return {"doc_id": doc_id, "sha": sha, "cached": True}
    threading.Thread(target=_process, args=(doc_id, path, sha), daemon=True).start()
    return {"doc_id": doc_id, "sha": sha, "cached": False}


@APP.get("/api/docs")
def docs():
    reg = _load_registry()
    with _lock:
        out = []
        for d in reg["docs"].values():
            job = JOBS.get(d["doc_id"], {})
            status = job.get("status", "ready" if d["built_at"] else "queued")
            out.append({**d, "status": status,
                        "progress": job.get("progress"), "total": job.get("total"),
                        "error": job.get("error")})
    return out


@APP.delete("/api/doc/{doc_id}")
def delete_doc(doc_id: str):
    reg = _load_registry()
    doc = reg["docs"].get(doc_id)
    if not doc:
        raise HTTPException(404, "Không tìm thấy tài liệu")
    # xóa graph của file + cache (xóa file = xóa graph, đúng yêu cầu)
    import shutil
    shutil.rmtree(UPLOADS / doc_id, ignore_errors=True)
    (CACHE / f"{doc['sha']}.json").unlink(missing_ok=True)
    del reg["docs"][doc_id]
    # merge nào còn trỏ tới file đã xóa thì đánh dấu lỗi
    for m in reg["merges"].values():
        if doc_id in m.get("doc_ids", []):
            m["stale"] = True
    _save_registry(reg)
    with _lock:
        JOBS.pop(doc_id, None)
    trace_log("doc_deleted", doc_id=doc_id)
    return {"ok": True}


# ----------------------------------------------------------------- graph ---

def _get_graph(gid: str) -> dict:
    reg = _load_registry()
    if gid in reg["docs"]:
        doc = reg["docs"][gid]
        cached = (CACHE / f"{doc['sha']}.json")
        if cached.exists():
            return json.loads(cached.read_text(encoding="utf-8"))
        raise HTTPException(404, "Graph chưa sẵn sàng")
    if gid in reg["merges"]:
        return reg["merges"][gid]["graph"]
    raise HTTPException(404, "Không tìm thấy graph")


@APP.get("/api/graph/{gid}")
def get_graph(gid: str):
    g = _get_graph(gid)
    return {"nodes": g["nodes"], "edges": g["edges"], "stats": g.get("stats", g.get("meta", {}))}


@APP.get("/api/source")
def get_source(gid: str, page: int | None = None, turn: str | None = None):
    """Text gốc của 1 trang slide / 1 lượt nói (cho dialog View source)."""
    cp = _chunks_path(gid)
    if not cp.exists():
        raise HTTPException(404, "Không có chunks lưu cho tài liệu này")
    for c in json.loads(cp.read_text(encoding="utf-8")):
        if page is not None and c.get("page") == page:
            return c
        if turn and c.get("turn") == turn:
            return c
    raise HTTPException(404, "Không tìm thấy nguồn")


# ----------------------------------------------------------------- merge ---

JUDGE_SYSTEM = """Bạn là trọng tài hợp nhất khái niệm cho đồ thị tri thức bài giảng.
Cho 2 tên khái niệm, trả JSON: {"same": true/false, "reason": "..."}
Chỉ same=true khi chúng CHẮC CHẮN cùng một khái niệm ("LLM" và "large language model" -> true;
"attention" và "self-attention" -> true; "embedding" và "vector" -> false)."""


@APP.post("/api/merge")
def merge(payload: dict):
    doc_ids = payload.get("doc_ids", [])
    reg = _load_registry()
    if not 2 <= len(doc_ids) <= 3:
        raise HTTPException(400, "Chọn 2–3 tài liệu để ghép")
    graphs = []
    for did in doc_ids:
        if did not in reg["docs"]:
            raise HTTPException(404, f"Thiếu tài liệu {did}")
        g = _get_graph(did)
        for n in g["nodes"]:
            n["_doc"] = did
        graphs.append(g)

    # map id node cũ -> tên (để rewrite edges sau khi gộp)
    old_name = {}  # (doc_id, old_node_id) -> norm tên
    for g in graphs:
        for n in g["nodes"]:
            old_name[(n["_doc"], n["id"])] = _norm_key(n["name"])

    # tầng 1: gộp theo khóa thường hóa, giữ provenance cả 2 nguồn
    key_to_id, nodes = {}, {}
    for g in graphs:
        for n in g["nodes"]:
            k = _norm_key(n["name"])
            if k in key_to_id:
                m = nodes[key_to_id[k]]
                m["_dup_docs"].append(n["_doc"])
                if n["confidence"] > m["confidence"]:
                    m["definition"] = n["definition"]
                m["confidence"] = max(m["confidence"], n["confidence"])
                m["quotes"].extend(q for q in n["quotes"] if q not in m["quotes"])
                m["sources"].extend(s for s in n["sources"] if s not in m["sources"])
                continue
            cid = f"m{len(nodes) + 1:04d}"
            nodes[cid] = {**n, "id": cid, "_dup_docs": [n["_doc"]]}
            key_to_id[k] = cid

    # tầng 2: LLM kiểm duyệt cặp tên giống nhau (khác khóa thường hóa)
    names = list(nodes.values())
    checked, merged_pairs, llm_calls = set(), [], 0
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            if a["id"] not in nodes or b["id"] not in nodes:
                continue
            import difflib
            sim = difflib.SequenceMatcher(None, _norm_key(a["name"]), _norm_key(b["name"])).ratio()
            if sim < 0.75:
                continue
            pair = tuple(sorted([a["id"], b["id"]]))
            if pair in checked:
                continue
            checked.add(pair)
            raw = call_llm(JUDGE_SYSTEM, f"Tên 1: {a['name']}\nTên 2: {b['name']}")
            llm_calls += 1
            verdict = parse_json(raw) or {}
            if verdict.get("same"):
                keep, away = (a, b) if a["id"] < b["id"] else (b, a)
                keep["aliases"] = sorted(set(keep.get("aliases", []) + [away["name"]]))
                keep["quotes"].extend(q for q in away["quotes"] if q not in keep["quotes"])
                keep["sources"].extend(s for s in away["sources"] if s not in keep["sources"])
                keep["_dup_docs"].extend(away["_dup_docs"])
                del nodes[away["id"]]
                merged_pairs.append({"kept": keep["name"], "merged_away": away["name"],
                                     "reason": verdict.get("reason", "")})

    duplicates = [n for n in nodes.values() if len(set(n["_dup_docs"])) > 1]
    # edges: map id cũ qua tên -> id mới (node trùng đã gộp nên edge tự nối đúng)
    by_key = {}
    for n in nodes.values():
        by_key[_norm_key(n["name"])] = n["id"]
    edges = []
    seen_edges = set()
    for g, did in zip(graphs, doc_ids):
        for e in g["edges"]:
            s = by_key.get(old_name.get((did, e["source"])))
            t = by_key.get(old_name.get((did, e["target"])))
            if not s or not t or s == t:
                continue
            key = (s, t, e["type"])
            if key in seen_edges:
                continue  # trùng cạnh khi ghép 2 file cùng khái niệm
            seen_edges.add(key)
            edges.append(e)
    mid = f"merge_{uuid.uuid4().hex[:8]}"
    graph = {"meta": {"n_nodes": len(nodes), "n_edges": len(edges)},
             "nodes": list(nodes.values()), "edges": edges}
    reg["merges"][mid] = {
        "merge_id": mid, "doc_ids": doc_ids, "graph": graph,
        "report": {
            "n_before": sum(len(g["nodes"]) for g in graphs),
            "n_after": len(nodes),
            "n_duplicates_across_docs": len(duplicates),
            "duplicate_examples": [n["name"] for n in duplicates[:15]],
            "layer2_llm_pairs": merged_pairs,
            "n_llm_calls": llm_calls,
        },
        "built_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    _save_registry(reg)
    trace_log("merge", merges=mid, llm_calls=llm_calls,
              before=reg["merges"][mid]["report"]["n_before"],
              after=len(nodes))
    return {"merge_id": mid, "report": reg["merges"][mid]["report"]}


def _norm_key(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# ------------------------------------------------------------------ quiz --

QUIZ_SYSTEM = """Bạn là người ra đề quiz cho bài giảng AI (tiếng Việt), sinh câu hỏi TỪ KNOWLEDGE GRAPH.
Mỗi concept bạn nhận có: name, definition, quote nguyên văn từ tài liệu, provenance (trang slide / lượt nói).
QUY TẮC:
1. Chỉ dùng nội dung trong payload — không thêm tri thức ngoài.
2. Mỗi câu: 4 phương án, đúng 1; distractor là khái niệm khác trong payload (nhiễu hợp lý).
3. explanation phải dựa trên quote nguyên văn của concept.
4. Độ khó do NGƯỜI DÙNG chỉ định trong payload-level. Chỉ dùng đúng level đó cho MỌI câu:
   "Dễ" = hỏi định nghĩa trực tiếp; "Trung bình" = so sánh/quan hệ giữa khái niệm, tình huống vận dụng nhẹ;
   "Khó" = case ứng dụng, phân tích, loại trừ nhiễu. KHÔNG tự gán level khác.
   (Nếu payload-level là "Kết hợp" thì trộn đều 3 mức.)
5. Không nhắc "theo slide/trang" trong câu hỏi — nguồn chỉ để giảng viên kiểm tra.
6. SINH ĐỦ MỘT CÂU CHO TỪNG CONCEPT TRONG PAYLOAD — không bỏ sót, không sinh thêm concept khác.
Xuất JSON: {"questions": [{"concept": "<name đúng như payload>", "q": "...", "a": ["","","",""],
 "correct": 0, "level": "<payload-level>", "explain": "..."}]}"""


@APP.post("/api/quiz")
def quiz(payload: dict):
    gid = payload["graph_id"]
    count = int(payload.get("count", 6))
    level = payload.get("level", "Kết hợp")          # Dễ | Trung bình | Khó | Kết hợp
    topics = payload.get("topics") or []             # rỗng = toàn bài
    g = _get_graph(gid)

    # EVIDENCE GATE: chỉ concept có quote + nguồn; thiếu bằng chứng -> skip + báo
    pool = [n for n in g["nodes"]
            if n.get("quotes") and n.get("sources") and n["type"] == "concept"]
    skipped = sorted(n["name"] for n in g["nodes"]
                     if n["type"] == "concept" and n not in pool)
    if topics:
        wanted = {t.lower() for t in topics}
        def _match(n):
            hay = {n["name"].lower(), *{a.lower() for a in n.get("aliases", [])}}
            # substring 2 chiều: "agent" khớp "Agent trong AI", "Transformer" khớp "Transformers"
            return any(w in h or h in w for h in hay for w in wanted if len(w) >= 4 or len(h) >= 4)
        pool = [n for n in pool if _match(n)]
    if not pool:
        raise HTTPException(400, "Không có concept đủ bằng chứng cho phạm vi đã chọn")

    # đọc chunks để trả title/text cho View source (shape `bank` của UI)
    chunks = {}
    cp = _chunks_path(gid)
    if cp.exists():
        for c in json.loads(cp.read_text(encoding="utf-8")):
            key = (c.get("page"), c.get("turn"))
            chunks[key] = c

    import random
    random.seed(int(payload.get("seed", 42)))
    random.shuffle(pool)
    # Chọn phủ đều topic: chia vòng tròn (round-robin) từng nhóm topic,
    # mỗi vòng lấy 1 concept mới của mỗi topic — không topic nào bị bỏ qua.
    if topics and len(topics) > 1:
        wanted = [t.lower() for t in topics]
        def _owns(n, w):
            hay = {n["name"].lower(), *{a.lower() for a in n.get("aliases", [])}}
            # topic ngắn (<4 ký tự như "GPT", "AI") chỉ khớp prefix/đúng từ,
            # topic dài khớp substring 2 chiều
            return any(h == w or (len(w) >= 4 and (w in h or h in w))
                       or (len(w) < 4 and h.startswith(w + " ")) for h in hay)
        groups = {w: [n for n in pool if _owns(n, w)] for w in wanted}
        for g in groups.values():
            random.shuffle(g)
        picked, order = [], list(wanted)
        i = 0
        while len(picked) < count + 4 and any(groups[g] for g in order):
            w = order[i % len(order)]
            if groups[w]:
                picked.append(groups[w].pop(0))
            i += 1
            if i > 500:
                break
        # nhóm còn dư (ít topic) bổ sung vào cuối
        rest = [n for g in groups.values() for n in g]
        random.shuffle(rest)
        picked += rest
        picked = picked[: max(count + 4, 1)]
    else:
        picked = pool[: max(count + 4, 1)]  # dư 4 concept dự phòng: LLM thỉnh thoảng trả thiếu
    # sinh theo lô 5 concept/1 call, CÁC LÔ CHẠY SONG SONG (tổng thời gian = 1 lô)
    from concurrent.futures import ThreadPoolExecutor

    batches = [picked[i:i + 5] for i in range(0, len(picked), 5)]

    def _gen_batch(batch):
        payload_llm = [{"concept": n["name"], "definition": n["definition"],
                        "quote": n["quotes"][0], "sources": [n["sources"][0]]}
                       for n in batch]
        last_err = None
        for attempt in range(3):
            try:
                raw = call_llm(QUIZ_SYSTEM, json.dumps(
                    {"level": level, "concepts": payload_llm}, ensure_ascii=False))
                return batch, parse_json(raw)
            except Exception as e:
                last_err = e
                trace_log("quiz_retry", attempt=attempt + 1)
        raise last_err

    with ThreadPoolExecutor(max_workers=4) as ex:
        results = list(ex.map(_gen_batch, batches))

    questions = []
    for batch_idx, (batch, parsed) in enumerate(results, 1):
        by_name = {n["name"].lower(): n for n in batch}
        for q in parsed.get("questions", []):
            node = by_name.get(q.get("concept", "").lower())
            if not node:
                continue  # concept ngoài batch -> loại (chống ảo giác)
            # provenance ghép đôi: nguồn của CHÍNH quote dùng sinh câu
            ev = {"quote": node["quotes"][0], "source": node["sources"][0]}
            page, code, title, text = None, None, node["name"], ev["quote"]
            s = ev["source"]
            c = chunks.get((s.get("page"), s.get("turn")))
            if s.get("page") is not None:
                page = s["page"]
                if c:
                    title = c["text"].split("\n")[0][:80]
                    text = c["text"]
            elif s.get("turn"):
                code = s["turn"]
                if c:
                    title = c.get("section") or node["name"]
                    text = c["text"]
            questions.append({
                "topic": node["name"],
                "level": level if level != "Kết hợp" else q.get("level", "Trung bình"),
                "q": q.get("q"), "a": q.get("a"), "correct": q.get("correct"),
                "page": page, "page_total": 24, "code": code or "—",
                "title": title, "text": text, "explain": q.get("explain", ""),
                "quote": ev["quote"],
                "concept_id": node["id"],
            })
        trace_log("llm_quiz", batch=batch_idx, n_concepts=len(batch),
                  n_questions=len(parsed.get("questions", [])))
    # lọc câu lỗi (thiếu q/a/correct) rồi cắt đúng count
    questions = [q for q in questions if q.get("q") and q.get("a") and 4 > q.get("correct", -1) >= 0]
    questions = questions[:count]
    # thiếu thì sinh bù TRONG CÙNG 1 request: dùng concept chưa dùng trong pool
    if len(questions) < count:
        used_ids = {q["concept_id"] for q in questions}
        rest = [n for n in pool if n["id"] not in used_ids][: count - len(questions)]
        if rest:
            payload_llm = [{"concept": n["name"], "definition": n["definition"],
                            "quote": n["quotes"][0], "sources": [n["sources"][0]]} for n in rest]
            try:
                raw = call_llm(QUIZ_SYSTEM, json.dumps({"level": level, "concepts": payload_llm}, ensure_ascii=False))
                extra = parse_json(raw).get("questions", [])
                by_name = {n["name"].lower(): n for n in rest}
                for q in extra:
                    node = by_name.get(q.get("concept", "").lower())
                    if not node:
                        continue
                    page, code = None, "—"
                    for s in node["sources"]:
                        if s.get("page") is not None:
                            page = s["page"]
                    questions.append({
                        "topic": node["name"],
                        "level": level if level != "Kết hợp" else q.get("level", "Trung bình"),
                        "q": q.get("q"), "a": q.get("a"), "correct": q.get("correct"),
                        "page": page, "page_total": 24, "code": code,
                        "title": node["name"], "text": node["quotes"][0],
                        "explain": q.get("explain", ""), "quote": node["quotes"][0],
                        "concept_id": node["id"],
                    })
                trace_log("llm_quiz_topup", n_needed=count - len(questions) + len(rest))
            except Exception as e:
                trace_log("quiz_topup_failed", err=str(e)[:100])
        questions = questions[:count]
    return {"questions": questions, "skipped": skipped[:20],
            "n_pool": len(pool), "graph_id": gid}


@APP.get("/api/trace")
def trace(n: int = 20):
    if not TRACE.exists():
        return []
    lines = TRACE.read_text(encoding="utf-8").splitlines()[-n:]
    return [json.loads(l) for l in lines if l.strip()]


# ----------------------------------------------------------------- static -

@APP.get("/")
def index():
    return FileResponse(ROOT / "codebase" / "app" / "static" / "index1.html")


APP.mount("/static", StaticFiles(directory=ROOT / "codebase" / "app" / "static"), name="static")
