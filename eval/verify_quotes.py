# -*- coding: utf-8 -*-
"""Kiểm chứng provenance: mọi quote phải là chuỗi con (sau chuẩn hóa) của chunk nguồn.

PDF trích text có xuống dòng giữa câu → chuẩn hóa khoảng trắng và dấu ngoặc
trước khi so khớp. Đây là số đo R4: "thử bao nhiêu, đúng bao nhiêu".

Output: eval/quote_audit.json + in tỉ lệ ra console.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def norm(s: str) -> str:
    s = re.sub(r"\s+", " ", s)
    return s.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'").strip()


def longest_common_span(quote: str, source: str) -> int:
    """Độ dài (ký tự) chuỗi con chung dài nhất — đo mức quote 'dựa vào nguồn'."""
    m, n = len(quote), len(source)
    if m == 0 or n == 0:
        return 0
    # DP quy hoạch động; quote/source đều ngắn (<500 ký tự) nên chạy nhanh
    prev = [0] * (n + 1)
    best = 0
    for i in range(1, m + 1):
        cur = [0] * (n + 1)
        qi = quote[i - 1]
        for j in range(1, n + 1):
            if qi == source[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best = cur[j]
        prev = cur
    return best


def classify(quote: str, source: str) -> str:
    """exact = nguyên văn; near = >=60% ký tự nằm trong 1 span chung; else = mismatch."""
    q, s = norm(quote), norm(source)
    if not q:
        return "empty"
    if q in s:
        return "exact"
    span = longest_common_span(q, s)
    return "near" if span / len(q) >= 0.6 else "mismatch"


def main():
    chunks = {
        c["chunk_id"]: c["text"]
        for c in json.loads((ROOT / "ingestion" / "chunks.json").read_text(encoding="utf-8"))["chunks"]
    }
    stats = {"concept_quotes": {"exact": 0, "near": 0, "mismatch": 0},
             "edge_quotes": {"exact": 0, "near": 0, "mismatch": 0}}
    failures = []
    for line in (ROOT / "extraction" / "graph_raw.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        src = norm(chunks[r["chunk_id"]])
        for c in r["concepts"]:
            cls = classify(c.get("quote", ""), src)
            stats["concept_quotes"][cls] += 1
            if cls == "mismatch":
                failures.append({"chunk_id": r["chunk_id"], "kind": "concept", "quote": c.get("quote", "")})
        for e in r["edges"]:
            cls = classify(e.get("evidence_quote", ""), src)
            stats["edge_quotes"][cls] += 1
            if cls == "mismatch":
                failures.append({"chunk_id": r["chunk_id"], "kind": "edge", "quote": e.get("evidence_quote", "")})

    cq, eq = stats["concept_quotes"], stats["edge_quotes"]
    ct = sum(cq.values()); et = sum(eq.values())
    report = {
        "concept_quote_verbatim": {"exact": cq["exact"], "near_match": cq["near"], "mismatch": cq["mismatch"],
                                   "pct_exact": round(100 * cq["exact"] / ct, 1) if ct else None,
                                   "pct_supported": round(100 * (cq["exact"] + cq["near"]) / ct, 1) if ct else None},
        "edge_quote_verbatim": {"exact": eq["exact"], "near_match": eq["near"], "mismatch": eq["mismatch"],
                                "pct_exact": round(100 * eq["exact"] / et, 1) if et else None,
                                "pct_supported": round(100 * (eq["exact"] + eq["near"]) / et, 1) if et else None},
        "failure_detail": failures,
        "method": "exact = chuỗi con nguyên văn (sau chuẩn hóa); near = >=60% quote nằm trong 1 span chung với nguồn; mismatch = còn lại",
    }
    out = ROOT / "eval" / "quote_audit.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Quote concept: exact {cq['exact']}/{ct} ({report['concept_quote_verbatim']['pct_exact']}%) "
          f"+ near {cq['near']} -> supported {report['concept_quote_verbatim']['pct_supported']}% | mismatch {cq['mismatch']}")
    print(f"Quote edge  : exact {eq['exact']}/{et} ({report['edge_quote_verbatim']['pct_exact']}%) "
          f"+ near {eq['near']} -> supported {report['edge_quote_verbatim']['pct_supported']}% | mismatch {eq['mismatch']}")
    print(f"Chi tiết mismatch -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
