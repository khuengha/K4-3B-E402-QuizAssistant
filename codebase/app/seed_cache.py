# -*- coding: utf-8 -*-
"""Seed cache app từ kết quả batch đã chạy hôm qua (không tốn API).

- Tách graph_raw.jsonl theo file nguồn -> graph per-file (dùng _merge_records).
- Chuyển chunks.json (217 chunk) -> chunks.json per-file cho View source.
- Ghi appdata/cache/<sha>.json theo SHA-256 file gốc.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "codebase"))
sys.path.insert(0, str(ROOT / "codebase" / "app"))

from pipeline import APPDATA, CACHE, UPLOADS, _merge_records, file_sha256

FILES = [
    "d1-slide-hackathon.pdf",
    "d2-slide-hackathon.pdf",
    "transcript-Day 1.md",
    "transcript-Day 2.md",
]


def main():
    raw = [json.loads(l) for l in
           (ROOT / "extraction" / "graph_raw.jsonl").read_text(encoding="utf-8").splitlines()
           if l.strip()]
    all_chunks = json.loads((ROOT / "ingestion" / "chunks.json").read_text(encoding="utf-8"))["chunks"]

    # graph_raw của batch cũ dùng provenance.file = tên file gốc -> tách theo file
    # LƯU Ý: 21 chunk đầu trích bằng Gemini dùng "d1-slide-hackathon.pdf" giống hệt
    # -> gộp tự nhiên theo file, đúng ý.
    for fname in FILES:
        sha = file_sha256(ROOT / fname)
        recs = [r for r in raw if r["provenance"]["file"] == fname]
        chunks = [c for c in all_chunks if c["file"] == fname]
        graph = _merge_records(recs)
        stats = {**graph["meta"], "n_chunks_total": len(chunks),
                 "n_chunks_kept": len(recs), "n_chunks_skipped": 0,
                 "seeded_from": "batch run 17/9"}
        cache = {"sha": sha, "from_cache": True, "nodes": graph["nodes"],
                 "edges": graph["edges"], "stats": stats, "skipped": []}
        CACHE.mkdir(parents=True, exist_ok=True)
        (CACHE / f"{sha}.json").write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        up = UPLOADS / sha[:12]
        up.mkdir(parents=True, exist_ok=True)
        (up / "chunks.json").write_text(json.dumps(chunks, ensure_ascii=False), encoding="utf-8")
        print(f"{fname}: sha={sha[:12]} nodes={len(graph['nodes'])} edges={len(graph['edges'])} chunks={len(chunks)}")
    print("Seed xong.")


if __name__ == "__main__":
    main()
