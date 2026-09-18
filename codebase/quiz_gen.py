# -*- coding: utf-8 -*-
"""Quiz Generator — lát cắt sản phẩm chính của C1.

Kịch bản (đúng gợi ý BTC): "Giảng viên cần quiz một chương — AI trích 10 câu
kèm trang nguồn, giảng viên duyệt từng câu."

Nguyên tắc bắt buộc:
- Mỗi câu quiz PHẢI trỏ về concept trong graph, concept đó PHẢI có provenance
  (file + trang/lượt nói + quote). Không có nguồn => không xuất câu.
- Câu hỏi + đáp án được sinh từ definition/quotes của CHÍNH concept đó
  (grounded, không mượn tri thức ngoài tài liệu).

Output: quiz/quiz_draft.json (bản nháp để giảng viên duyệt)
        quiz/quiz_review.json (audit trail accept/reject — ghi đè khi duyệt)
"""
import json
import os
import random
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "codebase"))

ENV_FILE = ROOT / ".env"
if ENV_FILE.exists():
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from extract import call_llm, parse_json  # tái dùng cơ chế gọi LLM + parse JSON


def build_quiz_prompt(concepts_batch, all_names):
    """Sinh quiz từ MỘT nhóm concept, chỉ dùng tri thức trong payload."""
    payload = []
    for c in concepts_batch:
        payload.append({
            "concept": c["name"],
            "definition": c["definition"],
            "quotes": [q for q in c["quotes"] if q][:2],
            "source": _fmt_source(c["sources"][0]) if c["sources"] else None,
        })
    system = """Bạn là người ra đề quiz cho bài giảng AI (khóa AI20k, tiếng Việt).
QUY TẮC BẮT BUỘC:
1. Chỉ hỏi nội dung CÓ TRONG payload — không thêm tri thức ngoài.
2. Mỗi câu: 4 lựa chọn, đúng 1. Distraction là khái niệm CÓ trong all_names
   nhưng sai nghĩa với câu hỏi.
3. "explanation" phải trích dẫn quote nguyên văn từ payload.
4. Không hỏi "theo slide/trang X..." — hỏi kiến thức, nguồn chỉ để giảng viên kiểm tra.
Xuất JSON: {"questions": [{"concept": "...", "question": "...", "options": ["A","B","C","D"],
 "answer_index": 0, "explanation": "...", "source": "file + trang/lượt"}]}"""
    user = f"PAYLOAD:\n{json.dumps(payload, ensure_ascii=False)}\n\nALL_NAMES (t distractors):\n{'; '.join(all_names)}"
    return system, user


def _fmt_source(s):
    if "page" in s:
        return f'{s["file"]} · trang {s["page"]}'
    return f'{s["file"]} · lượt {s.get("turn", "?")}'


def main(n_questions: int = 10, seed: int = 42):
    random.seed(seed)  # tái lập được (rubric UX/reproducibility)
    graph = json.loads((ROOT / "extraction" / "graph.json").read_text(encoding="utf-8"))
    nodes = [n for n in graph["nodes"] if n["type"] == "concept" and n["sources"] and n["quotes"]]
    all_names = [n["name"] for n in nodes]
    print(f"Concepts đủ điều kiện (có nguồn + quote): {len(nodes)}/{len(graph['nodes'])}")

    # chọn ngẫu nhiên concept, ưu tiên concept có nhiều nguồn nhất cho chắc chất lượng
    nodes.sort(key=lambda n: -len(n["sources"]))
    pool = nodes[: max(n_questions * 3, 30)]
    picked = random.sample(pool, min(n_questions, len(pool)))

    questions = []
    # sinh theo lô 5 concept/call để giảm số lời gọi API
    for i in range(0, len(picked), 5):
        batch = picked[i:i + 5]
        system, user = build_quiz_prompt(batch, all_names[:60])
        for attempt in range(3):
            try:
                raw = call_llm(system, user)
                parsed = parse_json(raw)
                qs = parsed.get("questions", [])
                break
            except Exception as e:
                print(f"  [retry] {e}")
                time.sleep(5 * (attempt + 1))
                qs = []
        # gắn provenance từ graph vào mỗi câu (không tin source do LLM tự khai)
        node_by_name = {n["name"].lower(): n for n in batch}
        for q in qs:
            node = node_by_name.get(q.get("concept", "").lower())
            if not node:
                continue  # LLM hỏi về concept ngoài batch -> bỏ (chống ảo giác)
            q["concept_id"] = node["id"]
            q["provenance"] = node["sources"]
            q["source_display"] = _fmt_source(node["sources"][0])
            q["quotes"] = node["quotes"][:2]
            questions.append(q)
        time.sleep(1.5)

    # nếu thiếu câu do lọc, lấy tạm các câu đã có (trung thực trong số đo)
    out = {
        "meta": {
            "n_requested": n_questions, "n_generated": len(questions),
            "seed": seed, "source_graph": "extraction/graph.json",
            "policy": "chỉ sinh câu hỏi trên concept có provenance trong graph",
        },
        "questions": questions,
        "review": {},  # giảng viên duyệt: {"q1": "accept" | "reject", ...}
    }
    quiz_dir = ROOT / "quiz"
    quiz_dir.mkdir(exist_ok=True)
    (quiz_dir / "quiz_draft.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Sinh được {len(questions)}/{n_questions} câu (sau lọc concept ngoài batch)")
    print(f"-> quiz/quiz_draft.json")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    main(n)
