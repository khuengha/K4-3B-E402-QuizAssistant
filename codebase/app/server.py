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

Chạy: python server.py (từ thư mục gốc)
"""
import copy
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

from fastapi import FastAPI, File, HTTPException, UploadFile, Request
from fastapi.responses import JSONResponse
from fastapi.responses import FileResponse

from pipeline import (CACHE, TRACE, UPLOADS, build_graph_for_file,
                      call_llm, file_sha256, is_junk, parse_json, trace_log)

ROOT = Path(__file__).resolve().parent.parent.parent
REGISTRY = ROOT / "appdata" / "registry.json"
APP = FastAPI(title="Lessonleaf API")

_lock = threading.RLock()
JOBS = {}  # doc_id -> {"status", "progress", "total", "error"}


def _load_registry() -> dict:
    if REGISTRY.exists():
        return json.loads(REGISTRY.read_text(encoding="utf-8"))
    return {"docs": {}, "merges": {}}


def _save_registry(reg: dict):
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    tmp = REGISTRY.with_suffix(".tmp")
    tmp.write_text(json.dumps(reg, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(REGISTRY)


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

        with _lock:
            if doc_id not in _load_registry()["docs"]:
                return
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
    name = Path((file.filename or "").replace("\\", "/")).name
    if not re.search(r"\.(pdf|md|txt)$", name, re.IGNORECASE):
        raise HTTPException(400, "Chỉ hỗ trợ PDF / .md / .txt")
    data = await file.read(20 * 1024 * 1024 + 1)
    if not data:
        raise HTTPException(400, "Tệp rỗng")
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(400, "Tệp vượt 20 MB")
    import hashlib
    sha = hashlib.sha256(data).hexdigest()
    doc_id = sha[:12]
    dir_ = UPLOADS / doc_id
    dir_.mkdir(parents=True, exist_ok=True)
    path = dir_ / name
    path.write_bytes(data)

    with _lock:
        reg = _load_registry()
        if JOBS.get(doc_id, {}).get("status") == "processing":
            return {"doc_id": doc_id, "sha": sha, "cached": False}
        reg["docs"][doc_id] = {
            "doc_id": doc_id, "name": name, "sha": sha, "stats": {},
            "n_nodes": 0, "n_edges": 0, "built_at": None, "from_cache": False,
        }
        _save_registry(reg)
        JOBS[doc_id] = {"status": "processing", "progress": 0, "total": 0}
    threading.Thread(target=_process, args=(doc_id, path, sha), daemon=True).start()
    return {"doc_id": doc_id, "sha": sha, "cached": (CACHE / f"{sha}.json").exists()}


@APP.get("/api/docs")
def docs():
    with _lock:
        reg = _load_registry()
        out = []
        for d in reg["docs"].values():
            job = JOBS.get(d["doc_id"], {})
            status = job.get("status", "ready" if d["built_at"] else "error")
            out.append({**d, "status": status,
                        "progress": job.get("progress"), "total": job.get("total"),
                        "error": job.get("error") or ("Xử lý bị gián đoạn. Hãy tải lại tệp." if status == "error" else None)})
    return out


@APP.delete("/api/doc/{doc_id}")
def delete_doc(doc_id: str):
    with _lock:
        reg = _load_registry()
        doc = reg["docs"].get(doc_id)
        if not doc:
            raise HTTPException(404, "Không tìm thấy tài liệu")
        if JOBS.get(doc_id, {}).get("status") == "processing":
            raise HTTPException(409, "Tài liệu đang xử lý. Hãy chờ hoàn tất trước khi xóa.")
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
        if reg["merges"][gid].get("stale"):
            raise HTTPException(409, "Nguồn của graph ghép đã bị xóa. Hãy ghép lại tài liệu.")
        return copy.deepcopy(reg["merges"][gid]["graph"])
    raise HTTPException(404, "Không tìm thấy graph")


@APP.get("/api/graph/{gid}")
def get_graph(gid: str):
    g = _get_graph(gid)
    return {"nodes": g["nodes"], "edges": g["edges"], "stats": g.get("stats", g.get("meta", {}))}


@APP.get("/api/source")
def get_source(gid: str, page: int | None = None, turn: str | None = None):
    """Text gốc của 1 trang slide / 1 lượt nói (cho dialog View source)."""
    if gid not in _load_registry()["docs"]:
        raise HTTPException(404, "Không tìm thấy tài liệu nguồn")
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
    if not isinstance(doc_ids, list) or not all(isinstance(d, str) for d in doc_ids) or not 2 <= len(set(doc_ids)) == len(doc_ids) <= 3:
        raise HTTPException(400, "Chọn 2–3 tài liệu để ghép")
    graphs = []
    for did in doc_ids:
        if did not in reg["docs"]:
            raise HTTPException(404, f"Thiếu tài liệu {did}")
        g = _get_graph(did)
        for n in g["nodes"]:
            n["_doc"] = did
            n["evidence"] = [{**ev, "source": {**ev["source"], "doc_id": did}} for ev in _evidence(n)]
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
                m["evidence"].extend(n["evidence"])
                m["aliases"] = sorted(set(m.get("aliases", []) + n.get("aliases", [])))
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
            try:
                raw = call_llm(JUDGE_SYSTEM, f"Tên 1: {a['name']}\nTên 2: {b['name']}")
            except Exception:
                raise HTTPException(502, "Không gọi được AI để ghép graph. Hãy thử lại.")
            llm_calls += 1
            verdict = parse_json(raw) or {}
            if verdict.get("same"):
                keep, away = (a, b) if a["id"] < b["id"] else (b, a)
                keep["aliases"] = sorted(set(keep.get("aliases", []) + away.get("aliases", []) + [away["name"]]))
                keep["evidence"].extend(away["evidence"])
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
        for name in [n["name"], *n.get("aliases", [])]:
            by_key[_norm_key(name)] = n["id"]
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
            edges.append({**e, "source": s, "target": t})
    mid = f"merge_{uuid.uuid4().hex[:8]}"
    graph = {"meta": {"n_nodes": len(nodes), "n_edges": len(edges)},
             "nodes": list(nodes.values()), "edges": edges}
    merged_record = {
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
    with _lock:
        reg = _load_registry()
        if any(did not in reg["docs"] for did in doc_ids):
            raise HTTPException(409, "Tài liệu đã bị xóa trong lúc ghép")
        reg["merges"][mid] = merged_record
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


def _evidence(node):
    pairs = node.get("evidence") or []
    if not pairs and node.get("quotes") and node.get("sources"):
        # Compatibility with graphs produced before paired evidence was stored.
        pairs = [{"quote": node["quotes"][0], "source": node["sources"][0]}]
    return [e for e in pairs if isinstance(e, dict) and e.get("quote") and
            isinstance(e.get("source"), dict) and
            (e["source"].get("page") or e["source"].get("turn"))]


def _valid_question(q):
    return (isinstance(q, dict) and isinstance(q.get("q"), str) and 0 < len(q["q"].strip()) <= 1000
            and isinstance(q.get("a"), list) and len(q["a"]) == 4
            and all(isinstance(a, str) and 0 < len(a.strip()) <= 500 for a in q["a"])
            and len({a.strip().casefold() for a in q["a"]}) == 4
            and type(q.get("correct")) is int and 0 <= q["correct"] < 4
            and isinstance(q.get("explain"), str) and 0 < len(q["explain"].strip()) <= 2000)


@APP.post("/api/quiz")
def quiz(payload: dict):
    gid, count = payload.get("graph_id"), payload.get("count", 6)
    level, topics = payload.get("level", "Kết hợp"), payload.get("topics", [])
    excluded = payload.get("exclude_concept_ids", [])
    if (not isinstance(gid, str) or type(count) is not int or not 1 <= count <= 100
            or level not in ("Dễ", "Trung bình", "Khó", "Kết hợp")
            or not isinstance(topics, list) or not all(isinstance(t, str) and t.strip() for t in topics)
            or not isinstance(excluded, list) or not all(isinstance(i, str) for i in excluded)
            or type(payload.get("seed", 42)) is not int):
        raise HTTPException(400, "Cấu hình sinh quiz không hợp lệ")
    graph = _get_graph(gid)
    pool = [n for n in graph["nodes"] if n.get("type") == "concept" and _evidence(n)
            and n["id"] not in excluded]
    skipped = [n["name"] for n in graph["nodes"] if n.get("type") == "concept" and not _evidence(n)]
    def matches(n, topic):
        wanted = topic.casefold()
        return any(wanted == name.casefold() or
                   (len(wanted) >= 4 and wanted in name.casefold()) or
                   name.casefold().startswith(wanted + " ")
                   for name in [n["name"], *n.get("aliases", [])])
    if topics:
        pool = [n for n in pool if any(matches(n, t) for t in topics)]
    if not pool:
        raise HTTPException(400, "Không còn concept đủ bằng chứng cho phạm vi đã chọn")
    import random
    from concurrent.futures import ThreadPoolExecutor
    rng = random.Random(payload.get("seed", 42))
    rng.shuffle(pool)
    # Cover selected topics before filling the remaining slots, without duplicate concepts.
    picked = []
    groups = [[n for n in pool if matches(n, t)] for t in topics] if topics else [pool[:]]
    while any(groups):
        for group in groups:
            if group:
                node = group.pop(0)
                if node not in picked:
                    picked.append(node)
    picked = picked[:count + 4]
    def generate(batch):
        items = [{"concept": n["name"], "definition": n.get("definition", ""),
                  "quote": _evidence(n)[0]["quote"], "sources": [_evidence(n)[0]["source"]]}
                 for n in batch]
        raw = call_llm(QUIZ_SYSTEM, json.dumps({"level": level, "concepts": items}, ensure_ascii=False))
        return batch, parse_json(raw)
    try:
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(generate, [picked[i:i+5] for i in range(0, len(picked), 5)]))
    except Exception:
        trace_log("quiz_failed", graph_id=gid)
        raise HTTPException(502, "Không gọi được dịch vụ AI. Kiểm tra cấu hình API và thử lại.")
    questions, used = [], set()
    reg = _load_registry()
    for batch, parsed in results:
        by_name = {n["name"].casefold(): n for n in batch}
        candidates = parsed.get("questions", []) if isinstance(parsed, dict) else []
        for q in candidates if isinstance(candidates, list) else []:
            if not _valid_question(q) or not isinstance(q.get("concept"), str):
                continue
            node = by_name.get(q["concept"].casefold())
            if not node or node["id"] in used:
                continue
            ev = _evidence(node)[0]
            source = ev["source"]
            doc_id = source.get("doc_id") or (gid if gid in reg["docs"] else None)
            chunks = []
            if doc_id and _chunks_path(doc_id).exists():
                chunks = json.loads(_chunks_path(doc_id).read_text(encoding="utf-8"))
            chunk = next((c for c in chunks if (c.get("page"), c.get("turn")) ==
                          (source.get("page"), source.get("turn"))), {})
            used.add(node["id"])
            questions.append({"q": q["q"], "a": q["a"], "correct": q["correct"],
                "topic": node["name"], "level": level if level != "Kết hợp" else
                    (q.get("level") if q.get("level") in ("Dễ", "Trung bình", "Khó") else "Trung bình"),
                "explain": q["explain"], "page": source.get("page"), "code": source.get("turn") or "—",
                "title": chunk.get("section") or node["name"], "text": chunk.get("text", ev["quote"]),
                "quote": ev["quote"], "source_file": source.get("file"), "source_doc_id": doc_id,
                "concept_id": node["id"], "graph_id": gid})
    questions = questions[:count]
    trace_log("llm_quiz", graph_id=gid, n_questions=len(questions), n_concepts=len(picked))
    if not questions:
        raise HTTPException(502, "AI chưa trả về câu hỏi hợp lệ. Hãy thử lại.")
    return {"questions": questions, "skipped": skipped[:20], "n_pool": len(pool), "graph_id": gid}


@APP.get("/api/trace")
def trace(n: int = 20):
    if not TRACE.exists():
        return []
    lines = TRACE.read_text(encoding="utf-8").splitlines()[-n:]
    return [json.loads(l) for l in lines if l.strip()]


# Serve only public assets; never mount the repository or uploaded data.
import importlib.util
_live_spec = importlib.util.spec_from_file_location("lessonleaf_live", ROOT / "server.py")
_live = importlib.util.module_from_spec(_live_spec)
_live_spec.loader.exec_module(_live)
STORE = _live.STORE


@APP.exception_handler(_live.APIError)
async def room_error(request, exc):
    return JSONResponse({"error": str(exc)}, status_code=exc.status)


@APP.post("/api/rooms", status_code=201)
def create_room(payload: dict):
    with STORE.lock:
        return STORE.create(payload)


@APP.get("/api/rooms/{pin}")
def room_state(pin: str, request: Request):
    with STORE.lock:
        return STORE.state(STORE.room(pin), request.headers.get("authorization", "").removeprefix("Bearer "))


@APP.post("/api/rooms/{pin}/{action}")
def room_action(pin: str, action: str, payload: dict, request: Request):
    token = request.headers.get("authorization", "").removeprefix("Bearer ")
    with STORE.lock:
        room = STORE.room(pin)
        if action == "join":
            return JSONResponse(STORE.join(room, payload), status_code=201)
        if action == "answer":
            STORE.answer(room, token, payload)
        else:
            STORE.action(room, token, action, payload)
        return STORE.state(room, token)


@APP.get("/api/merges")
def list_merges():
    return [{k: v for k, v in m.items() if k != "graph"} for m in _load_registry()["merges"].values()]


@APP.get("/")
def index():
    return FileResponse(ROOT / "index1.html")


@APP.get("/static/{name}")
@APP.get("/{name}")
def asset(name: str):
    if name not in {"index1.html", "live.html", "live.js", "live.css"}:
        raise HTTPException(404, "Không tìm thấy trang")
    return FileResponse(ROOT / name)
