# -*- coding: utf-8 -*-
"""Merge & Entity Resolution: graph_raw.jsonl -> graph.json

Giải quyết pain point chính của đề C1: "dùng tên khác cho cùng khái niệm".

Chiến lược 2 tầng (tiết kiệm chi phí, mọi quyết định đều có log):
1. Gộp theo khóa thường hóa: name/alias viết thường, bỏ dấu thanh
   ("LLM" == "large language model" == "llm").
2. Cặp tên khác nhau nhưng giống nhau >80% (difflib, không cần embedding)
   -> gọi LLM phán xét "có phải cùng khái niệm không". Log lại toàn bộ.

Conflict resolution: cùng concept nhiều định nghĩa -> giữ định nghĩa confidence
cao nhất làm chính, GIỮ TOÀN BỘ provenance (1 concept nhiều nguồn = điểm cộng).

Output: extraction/graph.json + extraction/merge_log.json
"""
import difflib
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ENV_FILE = ROOT / ".env"
if ENV_FILE.exists():
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def call_llm(system: str, user: str) -> str:
    """Cùng cơ chế gọi LLM như extract.py (gemini/openai/anthropic)."""
    provider = os.environ.get("LLM_PROVIDER", "openai")
    import urllib.request

    if provider == "gemini":
        key = os.environ["GEMINI_API_KEY"]
        model = os.environ.get("LLM_MODEL", "gpt-4o-mini")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
        body = json.dumps({
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"parts": [{"text": user}]}],
            "generationConfig": {"temperature": 0, "response_mime_type": "application/json"},
        }).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)["candidates"][0]["content"]["parts"][0]["text"]

    key = os.environ["OPENAI_API_KEY"]
    base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model = os.environ.get("LLM_MODEL", "gpt-4o-mini")
    body = json.dumps({
        "model": model, "temperature": 0,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "response_format": {"type": "json_object"},
    }).encode()
    req = urllib.request.Request(
        f"{base}/chat/completions", data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)["choices"][0]["message"]["content"]


def norm_key(s: str) -> str:
    """Khóa thường hóa: viết thường, bỏ dấu thanh (giữ nguyên âm gốc), bỏ ký tự lạ."""
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")  # bỏ dấu thanh
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


MERGE_JUDGE_SYSTEM = """Bạn là trọng tài hợp nhất khái niệm (entity resolution) cho đồ thị tri thức bài giảng AI.
Cho 2 tên khái niệm xuất hiện trong cùng bộ slide/transcript, hãy trả lời JSON:
{"same": true/false, "reason": "..."}
Chỉ same=true khi chúng CHẮC CHẮN chỉ cùng một khái niệm (ví dụ "LLM" và "large language model").
Ví dụ khác nhau: "attention" và "self-attention" có thể là same=true; "embedding" và "vector" là false."""


def main():
    records = []
    path = ROOT / "extraction" / "graph_raw.jsonl"
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    if not records:
        print("Không có dữ liệu graph_raw.jsonl — chạy extract.py trước.")
        sys.exit(1)

    # ---------- tầng 1: gộp theo khóa thường hóa ----------
    key_to_master = {}     # norm_key -> concept_id
    nodes = {}             # concept_id -> node

    def get_node(name, aliases, node_type, definition, quote, prov, confidence):
        k = norm_key(name)
        if k in key_to_master:
            cid = key_to_master[k]
            nodes[cid]["aliases"].update(a for a in aliases if a)
            nodes[cid]["sources"].append(prov)
            if (confidence or 0) > nodes[cid]["confidence"]:
                nodes[cid]["definition"] = definition
            nodes[cid]["confidence"] = max(nodes[cid]["confidence"], confidence or 0)
            return cid
        cid = f"c{len(nodes) + 1:04d}"
        nodes[cid] = {
            "id": cid, "name": name,
            "aliases": set(a for a in aliases if a and a != name),
            "type": node_type, "definition": definition,
            "quotes": [quote] if quote else [],
            "sources": [prov],
            "confidence": confidence or 0,
        }
        key_to_master[k] = cid
        # alias cũng trỏ về node này
        for a in aliases:
            ak = norm_key(a)
            if ak and ak not in key_to_master:
                key_to_master[ak] = cid
        return cid

    local_map_per_chunk = {}
    for r in records:
        prov = r["provenance"]
        local_map = {}
        for c in r["concepts"]:
            local_map[c["local_id"]] = get_node(
                c["name"], c.get("aliases", []), c.get("type", "concept"),
                c.get("definition", ""), c.get("quote", ""), prov, c.get("confidence", 0),
            )
        local_map_per_chunk[r["chunk_id"]] = local_map

    n_after_l1 = len(nodes)

    # ---------- tầng 2: LLM phán xét các cặp tên giống nhau ----------
    merge_log = {"layer1_exact": n_after_l1, "layer2_candidates": [], "layer2_merged": []}
    names = list(nodes.items())
    checked = set()
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            (id1, n1), (id2, n2) = names[i], names[j]
            if id1 not in nodes or id2 not in nodes or id1 == id2:
                continue
            sim = difflib.SequenceMatcher(None, norm_key(n1["name"]), norm_key(n2["name"])).ratio()
            if sim < 0.75 or norm_key(n1["name"]) == norm_key(n2["name"]):
                continue
            pair_key = tuple(sorted([id1, id2]))
            if pair_key in checked:
                continue
            checked.add(pair_key)
            merge_log["layer2_candidates"].append(
                {"a": n1["name"], "b": n2["name"], "sim": round(sim, 2)})
            try:
                raw = call_llm(MERGE_JUDGE_SYSTEM,
                               f"Tên 1: {n1['name']}\nTên 2: {n2['name']}")
                m = re.search(r"\{.*\}", raw, re.DOTALL)
                verdict = json.loads(m.group(0)) if m else {"same": False}
            except Exception as e:
                verdict = {"same": False, "reason": f"lỗi LLM: {e}"}
            if verdict.get("same"):
                # gộp id2 vào id1 (giữ id nhỏ hơn), gom provenance
                nodes[id1]["aliases"].add(nodes[id2]["name"])
                nodes[id1]["aliases"].update(nodes[id2]["aliases"])
                nodes[id1]["quotes"].extend(nodes[id2]["quotes"])
                nodes[id1]["sources"].extend(nodes[id2]["sources"])
                nodes[id1]["confidence"] = max(nodes[id1]["confidence"], nodes[id2]["confidence"])
                # redirect mọi key trỏ sang id2
                for k, v in key_to_master.items():
                    if v == id2:
                        key_to_master[k] = id1
                del nodes[id2]
                merge_log["layer2_merged"].append(
                    {"kept": n1["name"], "merged_away": n2["name"], "reason": verdict.get("reason", "")})

    # ---------- dựng edges với id đã merge ----------
    edges = []
    for r in records:
        local_map = local_map_per_chunk[r["chunk_id"]]
        for e in r["edges"]:
            src, dst = e.get("from"), e.get("to")
            if src not in local_map or dst not in local_map:
                continue
            cid_src = key_to_master.get(_find_current(local_map[src], nodes), local_map[src])
            cid_dst = key_to_master.get(_find_current(local_map[dst], nodes), local_map[dst])
            # sau merge có thể 2 đầu trùng nhau -> bỏ self-loop
            if cid_src == cid_dst or cid_src not in nodes or cid_dst not in nodes:
                continue
            edges.append({
                "source": cid_src, "target": cid_dst, "type": e.get("type"),
                "evidence_quote": e.get("evidence_quote", ""),
                "provenance": r["provenance"], "confidence": e.get("confidence", 0),
            })

    # chuẩn hóa set -> list để serialize
    for n in nodes.values():
        n["aliases"] = sorted(n["aliases"])
        # sources: file + page/turn duy nhất
        seen, uniq = set(), []
        for s in n["sources"]:
            key = (s["file"], s.get("page"), s.get("turn"))
            if key not in seen:
                seen.add(key)
                uniq.append(s)
        n["sources"] = uniq

    graph = {
        "meta": {
            "n_chunks": len(records),
            "n_nodes_layer1": n_after_l1,
            "n_nodes_final": len(nodes),
            "n_edges": len(edges),
            "edge_types": {},
            "node_types": {},
        },
        "nodes": sorted(nodes.values(), key=lambda n: n["id"]),
        "edges": edges,
    }
    for n in nodes.values():
        graph["meta"]["node_types"][n["type"]] = graph["meta"]["node_types"].get(n["type"], 0) + 1
    for e in edges:
        graph["meta"]["edge_types"][e["type"]] = graph["meta"]["edge_types"].get(e["type"], 0) + 1

    (ROOT / "extraction" / "graph.json").write_text(
        json.dumps(graph, ensure_ascii=False, indent=1), encoding="utf-8")
    (ROOT / "extraction" / "merge_log.json").write_text(
        json.dumps(merge_log, ensure_ascii=False, indent=1), encoding="utf-8")

    m = graph["meta"]
    print(f"Nodes: tầng 1 gộp còn {n_after_l1}, sau LLM gộp thêm -> {m['n_nodes_final']}")
    print(f"Edges: {m['n_edges']} | node types: {m['node_types']} | edge types: {m['edge_types']}")
    print(f"-> extraction/graph.json, extraction/merge_log.json")


def _find_current(local_id, nodes):
    """local_id có thể đã bị xóa sau merge — trả id còn tồn tại."""
    return local_id if local_id in nodes else local_id


if __name__ == "__main__":
    main()
