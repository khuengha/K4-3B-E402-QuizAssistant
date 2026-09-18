# Feedback Log — Validation Lessonleaf (Track C1)

> Mỗi người dùng 1 mục. Quote ghi **NGUYÊN VĂN** lời họ nói — không diễn giải, không đặt lại lời.
> Rubric R6 (bonus +8): ≥2 người ngoài nhóm dùng thử prototype + ≥1 thay đổi từ feedback được ghi trong `spec.md` §9 Changelog.

---

## Phần A — Baseline phỏng vấn 

> 5 coach đã phỏng vấn về workflow soạn quiz hiện tại (evidence mining — `spec.md` §1). Đây là pain gốc; session ở Phần B dùng để đối chiếu xem thiết kế có giải được không.

| Người | Pain chính | Quote nguyên văn (17/9) |
|---|---|---|
| Lab Coach M | Tạo quiz qua nhiều bước, phiền | "Anh dùng ChatGPT và NotebookLLM để tạo quiz thấy phiền vì phải qua nhiều bước" |
| Lab Coach H | AI hay tạo đáp án sai, tốn công review | "Anh nghe record bài giảng rồi lấy key nhờ ChatGPT tạo quiz, mà AI hay tạo đáp án sai mất công review" |
| Lab Coach T | Phải tự review vì câu trả lời dài nhất thường là đáp án đúng | "Anh thấy câu trả lời dài nhất thì thường là đáp án đúng nên là anh phải hay review lại" |
| Lab Coach Đ | Chưa từng làm quiz, có nhu cầu trải nghiệm | "Anh chưa phải làm quiz bao giờ, anh mong được trải nghiệm dự án của bọn em" |
| Lab Coach D | Workflow 2 bước NotebookLM → ChatGPT | "Anh vẫn làm gần đây các quiz qua 2 bước NotebookLLM lấy tinh túy rồi bỏ vào ChatGPT sinh quiz" |

**Baseline → thiết kế đã chốt (đối chiếu khi quan sát session):**
- "qua nhiều bước" → một flow duy nhất: upload → cấu hình → tạo → duyệt → xuất (`spec.md` §4).
- "AI hay tạo đáp án sai" → quote bắt buộc nguyên văn + kiểm chứng tự động; lượt đo gần nhất 99.1% concept / 96.7% edge có căn cứ, mục sai bị loại khỏi graph (`spec.md` §7).
- "đáp án dài nhất là đáp án đúng" → distractor sinh từ cùng evidence nhưng ý khác nhau, không diễn đạt lại (prompt trong `codebase/app/server.py`).
- "tốn công review" → duyệt từng câu accept/reject/sửa; câu reject không tái xuất lần sinh sau, audit trail `quiz_review.json` (`spec.md` §6).

---

## Phần B — Session dùng thử 

### Người dùng 1 — Lab Coach M (Lab coach, giảng dạy thực tế — willing user chốt ở `spec.md` §8)

- **Ngày:** 18/9/2026 · **Thời lượng:** ~15 phút
- **Task giao (đọc y nguyên):** "Bạn hãy dùng trang này để tạo một bộ quiz ôn tập cho buổi học của bạn, duyệt và xuất bộ quiz đã duyệt."

**Quan sát (họ tự làm gì, kẹt đâu):**
- Upload xong phải chờ chunking/phân tích; trong lúc chờ không rõ hệ thống đang làm gì và bước kế tiếp là gì, phải hỏi người quan sát.

**Quote nguyên văn (≥1 — bắt buộc):**
> "upload xong r sao nữa e, đợi xíu mới tạo hả"

---

### Người dùng 2 — Lab Coach H (Lab coach, giảng dạy thực tế — willing user chốt ở `spec.md` §8)

- **Ngày:** 18/9/2026 · **Thời lượng:** ~15 phút
- **Task giao:** (như trên)

**Quan sát (họ tự làm gì, kẹt đâu):**
- Không kẹt ở bước nào: upload xong → tạo quiz suôn sẻ.

**Quote nguyên văn (≥1 — bắt buộc):**
> "giao diện đẹp, dễ nhìn, câu hỏi cũng đầy đủ nguồn"


**Câu quiz bị reject + lý do (đối chiếu audit `quiz_review.json`):** Không ghi nhận câu nào bị reject trong quan sát.

**Có dùng hết flow không (upload → chọn topic → tạo → duyệt → xuất):** Đủ — đã duyệt quiz (upload → tạo → duyệt).


---

## Phần C — Tổng hợp thay đổi từ feedback

> Mỗi thay đổi phải có thêm 1 dòng mới trong §9 Changelog `spec.md` (thời điểm · đổi gì · vì sao trỏ về feedback). Không đổi gì thì ghi rõ lý do giữ nguyên.

| Feedback (ai nói) | Quyết định | Lý do |
|---|---|---|
| Coach M — "upload xong r sao nữa e, đợi xíu mới tạo hả" (không rõ đang có gì xảy ra / bước kế tiếp khi chờ phân tích) | Đã đổi: mục "01 Tài liệu" hiện dòng trạng thái khi có file đang xử lý — "AI đang phân tích … (đang chia đoạn / chunk x/y)" + gợi ý bước kế tiếp (chọn "Nguồn tạo quiz" → bấm Tạo quiz) | Sửa trong `index1.html` (element `#doc-status` + `renderFiles`); ghi §9 Changelog `spec.md` dòng 18/9 22:35 |
| Coach H — "giao diện đẹp, dễ nhìn, câu hỏi cũng đầy đủ nguồn" | Giữ nguyên — provenance hiển thị ngay trong UI là điểm mạnh, người dùng xác nhận đúng nhu cầu | Phản hồi tích cực, không cần đổi; provenance là nguyên tắc thiết kế §4b của `spec.md` |

**4 dòng cuối bảng** (theo yêu cầu rubric):
1. **Chủ đề lặp nhiều nhất:** cả 2 coach đều chạy hết flow không cần hỗ trợ, không ai phải reject câu nào; điểm vướng duy nhất — không rõ trạng thái khi chờ phân tích (Coach M)
2. **Sẽ sửa gì trước demo:** dòng trạng thái khi phân tích tài liệu — đã sửa 18/9 (xem bảng trên)
3. **Giữ nguyên gì và vì sao:** provenance từng câu (nguồn + quote xem được ngay trong UI) — Coach H xác nhận "câu hỏi cũng đầy đủ nguồn"
4. **Gì để dành sau:** các lát cắt đã loại ở `spec.md` §2 — adaptive (B), graph diff (C), phát hiện mâu thuẫn slide↔transcript (D)
