# AI SPEC — Knowledge-to-Lesson (Graph-first) · Nhóm [Quote Assistant] · Track C1 · Zone [C3]

> **Hướng:** C — Làn mở: Lesson Studio (Knowledge-to-Lesson, sub-track C1)

> **Loại:** Tính năng mới — trên chuỗi sản xuất bài giảng VLearn

> **Chốt spec:** trước 21:00 · 18/9/2026 (CP4). Sau mốc này không sửa.

---

## §1. User & Job

**Job executor:** Người viết nội dung / giảng viên của Studio team (người trực tiếp biến slide thô thành bài giảng có quiz).

**Workflow hiện tại (đã mining từ tài liệu thật):**
1. Nhận slide gốc của buổi giảng (PDF ~29 trang/buổi) + transcript bài giảng (~90–100 lượt nói/buổi, bản sạch có mã `[Txx-NNN]`).
2. Đọc toàn bộ, tự tinh gọn: bỏ phần chào lớp/hoạt động hành chính, giữ lại tri thức.
3. Tự viết quiz ôn tập cho từng phần — tra nguồn thủ công từng câu hỏi.
4. Publish lên VLearn.

**Core JTBD:**
> "Khi tôi soạn quiz cho một buổi học, tôi muốn biết chắc mỗi câu hỏi bám đúng nội dung đã dạy và truy được về đúng chỗ trong tài liệu gốc, để tôi không phát cho học viên câu hỏi sai hoặc ngoài phạm vi."

**Problem statement:**
> Tài liệu thô lặp ý, dùng tên khác cho cùng khái niệm, và không có cấu trúc liên kết giữa các khái niệm. Người soạn quiz phải đọc lại toàn bộ, tự đối chiếu nguồn từng câu — công việc lặp lại, dễ sai, và không tích lũy được lần sau.

**Evidence:**
- Mining dữ liệu thật (đã thực hiện, số đo từ pipeline của nhóm):
  - 2 buổi giảng = **58 trang slide + 187 lượt nói transcript** (98 + 89), sau lọc hành chính còn **159 lượt mang tri thức**.
  - Slide Day 1 dùng khái niệm lặp qua nhiều trang với tên gọi khác nhau (VD: "mô hình ngôn ngữ lớn", "LLM", "large language model" cùng chỉ một khái niệm) — đây chính là chi phí đối chiếu của người soạn.
  - Transcript có sẵn mã đoạn `[Txx-NNN]` nhưng không được dùng để truy vết khi soạn quiz hiện tại.
- Phỏng vấn (5 người): **3/5 (P02, P03, P04) từng dùng AI tạo quiz**. P02 lo chất lượng đầu ra và độ phân hóa câu hỏi; P03 ghi nhận quiz có thể không bao phủ bài giảng, đáp án dài/ngắn không đồng đều, tốn công review; P04 chưa từng tạo quiz nhưng có nhu cầu nếu việc tạo quiz được hỗ trợ tốt; P05 vướng đảm bảo chất lượng — câu hỏi dễ bị hallucinate.
- Quote nguyên văn (từ phỏng vấn, tối thiểu 5): 
  - `"Anh dùng ChatGPT và NotebookLLM để tạo quiz thấy phiền vì phải qua nhiều bước" - Lab Coach M (17/09)`
  - `"Anh nghe record bài giảng rồi lấy key nhờ ChatGPT tạo quiz, mà AI hay tạo đáp án sai mất công review" - Lab Coach H (17/09)`
  - `"Anh thấy câu trả lời dài nhất thì thường là đáp án đúng nên là anh phải hay review lại" - Lab Coach T (17/09)`
  - `"Anh chưa phải làm quiz bao giờ, anh mong được trải nghiệm dự án của bọn em" - Lab Coach Đ (17/09)`
  - `"Anh vẫn làm gần đây các quiz qua 2 bước NotebookLLM lấy tinh túy rồi bỏ vào ChatGPT sinh quiz" - Lab Coach D (17/09)`

## §2. Impact & quyết định chọn

| Ứng viên lát cắt | Người hưởng | Tần suất | Chi phí hiện tại | Khả thi (1 ngày) |
|---|---|---|---|---|
| **A. Quiz kèm nguồn từ graph** (chọn) | Người soạn nội dung | Mỗi buổi học | Cao: đọc lại toàn bộ, tra nguồn thủ công từng câu | Cao — pipeline đã chạy được trên data thật |
| B. Lộ trình học thích ứng (adaptive) | Học viên cuối | Mỗi học viên | Trung bình (hiện không có) | Thấp — cần learner state + mastery model + fixture lớn |
| C. Graph diff khi tài liệu cập nhật | Studio team | Mỗi lần sửa slide | Trung bình | Trung bình — cần 2 phiên bản tài liệu |
| D. Phát hiện mâu thuẫn slide↔transcript | Giảng viên | Hiếm | Thấp | Thấp — cần cạnh `contradicts` đủ dày |

**Ứng viên đã loại:** B (adaptive) — phụ thuộc learner state thật, không có data học viên trong phạm vi hackathon, khối lượng gấp đôi; C, D — giá trị thật nhưng tần suất thấp hơn nhiều so với A.

**Chọn A vì:** tần suất cao nhất (mỗi buổi học), giải đúng pain "quiz trực tiếp không truy được nguồn" mà đề C1 nêu đích danh, và nhóm đã có bằng chứng data thật chạy được (không phải fixture tự bịa).

## §3. Giải pháp tương tự

| Sản phẩm | Flow | Đáng học | Đáng né | Mình khác gì |
|---|---|---|---|---|
| **Quizgecko / Quizizz AI** (sinh quiz từ tài liệu) | Upload PDF → quiz tự sinh | UX nhập liệu đơn giản, xuất kết quả nhanh | Không truy nguồn từng câu; không có graph khái niệm; khó kiểm chứng câu nào ảo giác | Mỗi câu bắt buộc trỏ concept → trang/lượt nói + quote nguyên văn; concept nằm trong graph có provenance |
| **NotebookLM** (Google) | Nguồn → tóm tắt/QA/Audio | Làm việc trực tiếp trên tài liệu người dùng đưa; trích dẫn nguồn | Trích dẫn mức "nguồn" chứ không đến span quote; không có cấu trúc khái niệm dùng lại được; đóng | Graph là artifact tái dùng (sinh quiz, phân tích prerequisite, diff về sau); provenance đến quote + mã đoạn transcript |
| **GraphRAG (Microsoft)** | Corpus → graph entity → QA toàn cục | Ý tưởng trích entity + relation theo chunk | Schema chung chung (ENTITY/RELATE), không khớp domain giáo khoa (prerequisite/misconception); khó giải thích từng quyết định | Schema theo đúng yêu cầu đề bài (concept/definition/example/misconception + prerequisite/broader/related/example-of/contradicts), mọi node/edge có provenance + confidence |

## §4. Thiết kế

**Lát cắt một câu:** *Người soạn nội dung chọn tài liệu (hoặc ghép 2–3 tài liệu) → hệ thống trích graph tri thức từ slide (mỗi khái niệm kèm nguồn) → cấu hình số câu, độ khó, phạm vi topic → AI chỉ sinh câu hỏi từ các concept có đủ bằng chứng trong graph, mỗi câu trỏ về nguồn → người soạn duyệt từng câu (accept/reject/sửa) trước khi dùng.*

**Non-goals (≥3):**
1. Không làm adaptive delivery / learner mastery (đề cho phép — ghi rõ để tránh phình scope).
2. Không tự xuất bản nội dung chưa duyệt (nguyên tắc an toàn của đề).
3. Không xử lý PDF scan/ảnh (data thật là PDF có lớp text — đã kiểm).

**Mức prototype:** Working — web app hoàn chỉnh (FastAPI + UI): upload PDF/.md → AI phân tích (chunking → extraction LLM → graph, có tiến độ từng chunk + cache SHA-256) → merge 2–3 graph có LLM kiểm duyệt trùng lặp → sinh quiz theo số câu/độ khó/phạm vi topic → duyệt từng câu (accept/reject/sửa) → xuất. Chạy thật trên data thật; provenance đến trang slide/lượt nói `[Txx-NNN]` + quote nguyên văn (bấm xem nguồn ngay trong UI).

**Automation level:** **Augment** — AI chỉ sinh bản nháp; quyết định cuối thuộc người soạn (duyệt từng câu). Lý do: cost-of-error cao (quiz sai phát cho cả lớp), đúng nguyên tắc "giáo viên override được" của đề.

**§4b — Nguyên tắc thiết kế (HAX/PAIR):**

| Nguyên tắc | Nơi áp dụng cụ thể |
|---|---|
| Trách nhiệm con người ở vòng lặp (Human in command) | Mọi câu quiz phải được accept/reject trước khi dùng, không auto-publish |
| Minh bạch nguồn gốc (Provenance) | Mỗi node/edge/câu quiz đều có file + trang/lượt + quote, bấm node trong explorer là thấy ngay |
| Bày tỏ độ không chắc chắn (Communicate uncertainty) | Mỗi concept/edge có confidence 0–1, câu nào không đủ provenance thì không xuất |
| Kiểm soát được & sửa được (Control) | Người soạn có thể từ chối câu hỏi, xem nguyên văn nguồn để tự kiểm chứng |
| Không áp đảo (giảm false positive) | Rule "quote không nguyên văn ⇒ bỏ mục" — thà ít mà đúng |

## §5. Kiểu lỗi — 4 lớp chỗ khó + kịch bản (≥8)

| # | Lớp | Kịch bản lỗi | Hệ xử lý |
|---|---|---|---|
| 1 | Input bẩn | Trang slide gần trống / toàn branding | Bỏ qua chunk <5 ký tự tại ingestion |
| 2 | Input bẩn | Lượt nói chỉ là hành chính lớp ("giải lao", "làm bài tập") | Lọc theo heading mục + pattern `[Hoạt động lớp:...]` |
| 3 | Ảo giác LLM | Model bịa khái niệm không có trong tài liệu | Quote phải nguyên văn (kiểm tra chuỗi con sau chuẩn hóa); không nguyên văn ⇒ bỏ |
| 4 | Ảo giác LLM | Model paraphrase quote thay vì trích nguyên văn | Chuẩn hóa khoảng trắng/dấu ngoặc rồi so khớp; đo tỷ lệ trong eval/ |
| 5 | Trùng lặp | Cùng khái niệm nhiều tên ("LLM" vs "mô hình ngôn ngữ lớn") | 2 tầng: khóa thường hóa + LLM phán xét cặp tương tự, có log |
| 6 | Gộp nhầm | 2 khái niệm khác bị gộp làm một | Chỉ gộp khi tên trùng hoặc LLM xác nhận; merge_log.json xem lại được |
| 7 | Quiz sai chiều | Câu hỏi đúng nhưng trỏ nguồn sai | Nguồn gắn từ graph (không tin source do LLM tự khai); concept ngoài batch bị loại |
| 8 | Hạ tầng | API quá tải (503) / rate limit (429) / key hết hạn (401) | Retry lùi dần + resume theo chunk đã xong; sinh quiz theo lô song song có giới hạn, tôn trọng quota provider; lỗi key hiển thị thẳng cho người dùng thay vì treo |
| 9 | Dữ liệu | JSON LLM trả về sai format | Trích JSON thật từ response; sai thì coi như rỗng, không chết pipeline |
| 10 | Provenance | Quote thuộc trang A nhưng link trỏ trang B (concept xuất hiện nhiều trang, nguồn lấy "nguồn cuối" hoặc "nguồn đầu" riêng rẽ) | Evidence ghép đôi ngay lúc extract: nguồn nào đi với quote đó; mọi đường sinh quiz (lô chính + bù câu) lấy cặp khớp, ưu tiên trang của definition — không lấy chéo |

## §6. Bốn đường đi

- **Happy path:** chọn tài liệu (hoặc ghép 2–3 tài liệu) → graph trích đúng → quiz theo số câu/độ khó/phạm vi đã cấu hình, mỗi câu có nguồn + quote → người soạn accept hết. Stat "độ bao phủ" đo theo concept trong bộ / pool đủ căn cứ (hoặc chủ đề / số chủ đề đã chọn).
- **Low-confidence:** concept confidence < 0.5 hoặc chỉ 1 nguồn → vẫn vào graph nhưng hiển thị rõ confidence; quiz chỉ chọn concept có ≥1 quote.
- **Failure / không căn cứ:** LLM trả rác, quote không nguyên văn → mục bị loại (không xuất câu hỏi không truy được nguồn); số lượng bị loại ghi vào số đo trung thực.
- **Correction:** người soạn reject câu hỏi → ghi audit trail `quiz_review.json`; câu bị reject không tái xuất trong lần sinh sau.
- **Ngoài phạm vi:** người dùng yêu cầu "soạn quiz cho tài liệu chưa ingest" → hệ thống trả lời rõ phạm vi: chỉ tài liệu đã nạp vào graph.
- **Đặc thù domain:** khái niệm dàn trải nhiều trang slide (definition ở trang A, các trang sau nhắc lại bằng tên gọi khác hoặc đưa ví dụ) → provenance ghép đôi ngay lúc extract: mỗi quote đi cùng đúng trang của nó, đường sinh quiz ưu tiên trang có definition — không lấy chéo trang.

## §7. Kiểm thử

**Chiều chất lượng:** (1) provenance đúng — quote phải là chuỗi con nguyên văn của chunk nguồn; (2) câu quiz bám đúng khái niệm + nguồn; (3) không sinh khái niệm ngoài tài liệu.

**Định nghĩa kiểm chứng được:** script `eval/verify_quotes.py` chạy trực tiếp trên `extraction/graph_raw.jsonl` — không cần người phán xét cho chiều (1).

**Golden set (≥20 case) — `eval/golden_set.json`:** 30 node được chọn ngẫu nhiên theo seed cố định từ graph 521 concept

**Quality bar:** *Đạt khi ≥ 90% quote nguyên văn qua bộ kiểm tự động, và ≥ 80% câu quiz sampling được đánh giá "nguồn thật hỗ trợ câu hỏi" bởi 3 thành viên nhóm.*

**Bảng kết quả các lượt chạy:**

| Lượt | Thời điểm | Quote nguyên văn (exact) | Có bằng chứng (exact+near) | Ghi chú |
|---|---|---|---|---|
| 1 | 17/9 (5 chunk thử) | 3/10 thô; 10/10 sau chuẩn hóa | — | Phát hiện: PDF xuống dòng giữa câu → cần normalize khi so khớp |
| 2 | 17/9 (đủ 217 chunk) | Concept 87.4% (745/852) · Edge 83.0% (498/600) | Concept 99.1% · Edge 96.7% | 3 mức phân loại: exact / near (≥60% quote nằm trong 1 span chung) / mismatch; 28/1452 mismatch bị loại khỏi graph |
| 3 | 18/9 (web app, graph riêng từng file upload) | Provenance ghép đôi lúc extract — quote không khớp chunk bị loại ngay khi trích (log `n_quote_dropped`) | — | D2 (29 trang) → 115 concept / 92 cạnh; ghép D1+D2 → 209 node / 195 cạnh, LLM kiểm duyệt trùng lặp có log |

**Số đo khác từ pipeline (17/9):**
- Extraction: 217 chunk → 216 xử lý (186 có tri thức, 9 chunk không concept, 1 lỗi mạng không phục hồi được).
- Graph sau merge: **521 concept** (508 concept, 10 example, 3 misconception) · **583 cạnh** (136 prerequisite, 62 broader, 353 related, 25 example-of, 7 contradicts) · entity resolution gộp 531 → 521 (10 cặp hợp nhất qua LLM, log trong `extraction/merge_log.json`).
- Quiz: sinh 10/10 câu, mỗi câu trỏ concept_id → nguồn file + trang/lượt nói + quote (xem `quiz/quiz_draft.json`).

**Quality bar (chốt từ thời điểm nộp):** *Đạt khi ≥ 90% quote có bằng chứng trong nguồn (exact + near), và ≥ 80% câu quiz sampling được đánh giá "nguồn thật hỗ trợ câu hỏi" bởi 3 thành viên nhóm.* → **Đạt: 99.1%/96.7% ≥ 90%.**

## §8. Phân công & kế hoạch

| Việc | Người phụ trách |
|---|---|
| Spec + kiến trúc + pipeline code + provenance | Nguyễn Hà Khuê, Nguyễn Huy Hoàng |
| AI quiz generation, prompt, logic chọn concept, backend/API + output validation | Nguyễn Hà Khuê, Nguyễn Hoàng Anh |
| UI cấu hình/duyệt quiz, evaluation, user test + demo/changelog | Cả nhóm |
| Evidence mining + phỏng vấn ≥3 người | Nguyễn Huy Hoàng, Nguyễn Hoàng Anh |

**Willing users (≥2, đã hỏi và đồng ý):** Lab Coach M, Lab Coach H, Lab Coach Đ — vòng validation: cho duyệt quiz draft, ghi nhận câu nào bị reject vì sao (R6 cần ≥1 thay đổi từ phản hồi, ghi §9).

**Multi-prototype (trục khác biệt ≥2 phương án):**
- Phương án 1 (đã làm): extraction theo chunk — 1 call LLM/chunk, provenance cột chặt vào từng khái niệm.
- Phương án 2 (đã loại sau thử 5 chunk đầu): extraction cả chương 1 call — nhanh hơn nhưng quote bị paraphrase nhiều hơn và khó localize nguồn.

## §9. Changelog

| Thời điểm | Đổi gì | Vì sao |
|---|---|---|
| 17/9 15:30 | Chọn Graph-first thay vì Adaptive-first | Có data thật (2 slide + 2 transcript), tránh rủi ro tự dựng fixture |
| 17/9 16:00 | Chọn text-first (PyMuPDF), bỏ hướng vision-LLM | PDF có lớp text đầy đủ (đã kiểm 58/58 trang); text-first giữ provenance chính xác nhất |
| 17/9 16:15 | Thêm chuẩn hóa khoảng trắng khi kiểm chứng quote | Phát hiện quote "không khớp" thực ra do PDF xuống dòng giữa câu — quote vẫn nguyên văn |
| 17/9 16:45 | Đổi model extraction sang `gemini-3-flash-preview` | Model stable bị 429 liên tục; preview model còn quota |
| 18/9 15:00 | Web app hoàn chỉnh thay UI mock: upload/merge/duyệt quiz chạy thật, provenance xem được ngay trong UI | Prototype đạt mức Working thực thụ trên data upload tùy ý, không bó 4 file cứng |
| 18/9 17:30 | Sửa bug provenance: đường bù câu hỏi lấy "nguồn cuối" trong khi quote là "nguồn đầu" | Quote thuộc trang A nhưng link trỏ trang B — đưa evidence ghép đôi vào mọi đường sinh quiz (lỗi lớp 10, §5) |
| 18/9 17:45 | Stat "chủ đề được bao phủ" đo theo pool khi chọn "Tất cả chủ đề" (trước đây hiện "—") | Trước đây không có danh sách chủ đề thì không đo được; đổi sang concept trong bộ / pool đủ căn cứ |
