# Template AI Spec *(spec.md — commit trước hạn chốt spec: 21:00 17/9, tại CP4 · quality bar chốt từ thời điểm nộp)*

> Cấu trúc phủ đúng "SPEC 8 phần" của chương trình: Bằng chứng (§1-§2) · Lát cắt (§4) · Canvas (đính kèm CP1) · Augment/Automate (§4) · 4 đường đi của trải nghiệm (§6) · Kiểu lỗi (§5) · Kiểm thử (§7) · Phân công (§8). Hướng dẫn viết từng mục: `02-guide.md`.

# AI SPEC — [Tên lát cắt] · Nhóm [XX] · Zone [X]
Hướng: [ ] A — VLearn  [ ] B — Trợ lý Học viên  [ ] C — Làn mở
Loại: [ ] Tối ưu tính năng có sẵn  [ ] Tính năng mới

## §1. User & Job
- Job executor + workflow (đính kèm worksheet JTBD / ảnh sơ đồ):
- Core JTBD (không tên sản phẩm/AI trong câu):
- Problem statement (KHÔNG chữ AI):
- Evidence (chuẩn A và/hoặc B — log đầy đủ trong repo):
  - Số liệu mining / kết quả khảo sát (n = ?, % xác nhận):
  - ≥5 quote/ví dụ nguyên văn + nguồn:

## §2. Impact & quyết định chọn
- Bảng impact ≥3 ứng viên (bao nhiêu người · tần suất · tốn gì mỗi lần · khả thi):
- Ứng viên ĐÃ LOẠI + vì sao:
- Ứng viên CHỌN + vì sao (bằng số):

## §3. Giải pháp tương tự đã nghiên cứu
- [Sản phẩm 1]: flow / đáng học / đáng né / mình khác gì
- [Sản phẩm 2]: ...

## §4. Thiết kế
- Lát cắt MỘT CÂU (1 user · 1 việc · 1 quyết định AI · 1 kết quả):
- Non-goals (≥3 thứ KHÔNG build):
- Mức prototype nhắm tới: [ ] Sketch [ ] Mock [ ] Working — phần nào mock, phần nào thật:
- Automation: [ ] augment [ ] conditional [ ] automate — lý do theo cost-of-error:
- §4b. Nguyên tắc đã áp dụng (≥4 — HAX/PAIR, xem guide):
  | Nguyên tắc | Áp cụ thể vào đâu trong prototype |
  |---|---|

## §5. Kiểu lỗi — 4 lớp chỗ khó và kịch bản R3

Prototype: [index1.html](index1.html), UI chạy tại trình duyệt với dữ liệu giả. Không gọi AI, không phân tích tài liệu tải lên, không xác minh nội dung sửa bằng AI. Trạng thái evidence là fixture mô phỏng, không phải số đo độ tin cậy thực tế.

**Trạng thái taxonomy:** chưa có `02-guide.md` §2.5 hoặc rubric gốc trong workspace. Ánh xạ dưới đây dựa vào ký hiệu tại §6 của template hiện có; cần đối chiếu tên/định nghĩa chính thức trước khi khẳng định đáp ứng taxonomy R3. Chưa xác nhận điểm rubric.

| Lớp theo template hiện có | Chỗ khó cụ thể của QuizAssistant | Quy tắc xử lý trong mock |
|---|---|---|
| ① Failure / không căn cứ | Topic Fine-tuning không có đoạn nguồn | Chặn sinh, nêu lý do, giữ nguyên bộ hiện tại; cho bổ sung tài liệu  |
| ② Low-confidence | Evaluation chỉ có tên, thiếu định nghĩa | Không suy diễn đáp án. Hiện thiếu gì/mâu thuẫn gì, yêu cầu nguồn hoặc giảng viên đối chiếu |
| ③ Ngoài phạm vi | Đòi câu hỏi Tài chính trong bài Introduction to LLM | Từ chối; cho quay về 4 topic đủ căn cứ, không tự đổi topic rồi sinh |
| ④ Đặc thù domain | Distractor trùng nhau, đáp án sai sau chỉnh sửa, câu đã duyệt bị sửa, số câu thiếu sau loại | Validate phương án; sửa phải duyệt lại; bù đúng cấu hình ban đầu, không lặp câu đã dùng/loại |

Quy tắc evidence: 4 topic LLM / Token / Prompting / RAG có nguồn mẫu; Evaluation có mention nhưng không đủ căn cứ; Fine-tuning không có nguồn. Nếu lựa chọn chứa một topic bị chặn, dừng toàn bộ yêu cầu và giữ nguyên quiz cũ, không âm thầm sinh một phần. “Tất cả chủ đề” chọn 4 topic đủ căn cứ. Các topic kiểm thử bất lợi được chọn thủ công.

| ID | Lớp / path | Cách kích hoạt trong prototype | Hành vi mong muốn / tiêu chí quan sát |
|---|---|---|---|
| R3-01 | Happy | Bình thường, 6 câu, 4 topic đủ căn cứ → Tạo thử thách | 6 câu, đáp án đúng hiện sẵn, giải thích và nguồn; tất cả chờ duyệt |
| R3-02 | ① Failure | Chọn thêm Fine-tuning → Tạo | “Chưa đủ căn cứ để sinh câu hỏi về topic này”; chỉ rõ 0 đoạn nguồn; quiz cũ không đổi |
| R3-04 | ② Low-confidence | Chọn Evaluation → Tạo | Nêu chỉ có tên topic, thiếu định nghĩa/ví dụ; không sinh; có nút thêm tài liệu |
| R3-06 | ③ Ngoài phạm vi | Chọn Tài chính → Tạo | Từ chối ngoài bài học; nút chỉ chọn topic đủ căn cứ; phải bấm Tạo lại |
| R3-07 | ③ Giới hạn hỗ trợ tệp | Thêm tệp không thuộc định dạng hỗ trợ hoặc >20 MB | Không thêm tệp đó, thông báo lỗi; tệp hợp lệ vẫn được thêm; không giả vờ trích xuất nguồn |
| R3-08 | ④ Correction | Duyệt câu → Sửa câu hỏi → đổi câu/đáp án/giải thích → Lưu | Đổi nội dung, hiện nhãn giảng viên đã sửa, về Chờ duyệt; không xuất câu này trước khi duyệt lại |
| R3-09 | ④ Correction | Sửa để hai phương án giống nhau hoặc để trống trường | Chặn lưu, chỉ rõ lỗi; nội dung đã lưu và trạng thái duyệt không đổi |
| R3-10 | ④ Bù câu | Tạo 6 câu → duyệt 1, loại 2 → đổi số cấu hình sang 1 → Bù | Bộ vẫn có 6 câu chưa bị loại; giữ câu đã duyệt; 2 câu mới chờ duyệt theo cấu hình lúc tạo; không dùng lại câu đã loại |
| R3-12 | ④ Giới hạn ngân hàng | Liên tục loại và bù đến hết ngân hàng phù hợp | Thông báo hết câu mẫu; vô hiệu nút bù, không lặp hoặc bịa câu để đủ số lượng |
| R3-13 | ④ Duyệt / xuất | Chỉ duyệt một số câu → Xuất | JSON chỉ có câu đã duyệt; câu đang sửa lại hoặc đã loại không xuất |
| R3-14 | ④ Hủy sửa | Mở sửa → đổi nội dung → Hủy hoặc Escape | Không thay đổi câu hoặc trạng thái duyệt |

## §6. Bốn đường đi của trải nghiệm

### Happy path
Chọn topic đủ nguồn + độ khó + số câu → Tạo thử thách → banner thành công → xem đáp án, giải thích và nguồn → duyệt → xuất JSON chỉ gồm câu đã duyệt. Các bộ quá nhỏ so với số yêu cầu hiển thị số câu thực tế và phần còn thiếu, không nhân bản câu hỏi.

### Low-confidence (②)
Chọn Evaluation → Tạo → thông báo “Chưa đủ căn cứ để sinh câu hỏi về topic này”, nêu thiếu định nghĩa/ví dụ → thêm tài liệu hoặc chỉ chọn topic đủ căn cứ → bấm Tạo lại. Thêm tệp chỉ đưa tệp vào danh sách; mock không tự đổi evidence sang đủ.

### Failure / không căn cứ (①)
Fine-tuning không có đoạn nguồn → từ chối, không sinh câu hỏi đại. Đã bỏ bộ chọn kịch bản và logic giả lập TIMEOUT/nguồn mâu thuẫn theo yêu cầu. Lỗi JavaScript bất ngờ vẫn có thông báo; người dùng bấm Tạo thử thách để thử lại.

### Correction (user sửa)
Sửa câu hỏi → form cho sửa câu dẫn, 4 lựa chọn, đáp án đúng, giải thích → validate bắt buộc và phương án không trùng → Lưu và duyệt lại → nhãn “Giảng viên đã sửa” + Chờ duyệt → đối chiếu nguồn giữ nguyên → duyệt lại → xuất. Hủy không ghi thay đổi. Mock không tự xác minh nội dung sửa có thực sự được nguồn chứng minh; quyết định cuối thuộc giảng viên.

### Ranh giới và bằng chứng triển khai
- Ngoài phạm vi (③): Tài chính bị chặn và có đường quay lại phạm vi hỗ trợ.
- Domain (④): bù thiếu câu theo cấu hình gốc, không tái sử dụng câu đã loại; dùng khóa câu gốc để chống trùng kể cả khi câu đã được sửa.
- Banner là trạng thái bền trên màn hình, không chỉ toast thoáng qua. Khi yêu cầu bị chặn, các câu vẫn hiển thị là bộ cũ và thông báo nói rõ bộ cũ được giữ nguyên.
- Lưu trong bộ nhớ phiên; tải lại trang sẽ khôi phục dữ liệu mẫu. Chưa có backend, AI thực, trích xuất file hay kiểm thử chất lượng AI. Không coi mock này là bằng chứng hoàn tất yêu cầu gọi AI thật tại CP3.

## §7. Kiểm thử
- Chiều chất lượng + định nghĩa kiểm chứng được:
- Golden set (≥20 case theo cơ cấu trong guide §2.6, file trong eval/):
- Quality bar (chốt từ hạn chốt spec của khoá, giữ nguyên sau đó): "Đạt khi ≥ ___% qua bộ, và ___"
- Kết quả các lượt chạy (bảng % — cập nhật đến trước CP6):

## §8. Phân công & kế hoạch
- Phân công có tên: spec / evidence / prompt / code / demo
- Willing users (≥2 tên) + kế hoạch vòng validation *(bonus, nếu làm)*:
- Multi-prototype (nếu làm): trục khác biệt của ≥2 phương án + lý do chọn:

## §9. Changelog
| Thời điểm | Đổi gì | Vì sao (trỏ về feedback/case nào) |


### Cập nhật prototype R3
- Bổ sung các path trong `index1.html`, 11 kịch bản tại §5, chỉnh sửa/duyệt lại, chặn thiếu căn cứ .
- Chưa đổi quality bar §7; chưa có định nghĩa taxonomy chính thức để xác nhận mapping.

### Trạng thái khởi đầu và loading
- Khi mở trang: màn phải chưa có quiz, không hiện câu mẫu, thống kê, nút bù hay tab duyệt.
- Bấm Tạo thử thách: hiển thị loading và skeleton khoảng 1,4 giây (mô phỏng), khóa cấu hình và chống bấm tạo lặp. Sau đó hiện kết quả hoặc thông báo path bị chặn/lỗi.
- Khi tạo lại bị lỗi hoặc thiếu căn cứ, bộ quiz trước đó vẫn còn; nếu đây là lần đầu thì trở về trạng thái chưa có quiz.

- Đã bỏ UI “Kịch bản xử lý · mô phỏng”, nhánh lỗi dịch vụ/nguồn mâu thuẫn và các nút phục hồi giả lập. Giữ loading, kiểm tra căn cứ theo topic và correction.


## Bổ sung Live Quiz

- Entry: Play Quiz ở màn kết quả, chỉ bật khi có câu đã duyệt. Tạo snapshot gồm nguyên câu hỏi, 4 phương án, đáp án đúng, topic, difficulty và provenance; không gọi AI hoặc thêm câu hỏi.
- Host: thiết lập thời gian → lobby PIN/link → Start → question → reveal + leaderboard → next → finished + báo cáo lớp. Restart giữ bộ câu hỏi/người chơi, reset điểm và tăng lượt. Close kết thúc phòng.
- Người học: PIN + tên → lobby → chọn đáp án → chờ chốt → xem giải thích/nguồn → xếp hạng cuối, đúng/sai/bỏ lỡ và topic sai nhiều.
- Điểm: đúng +1.000, sai/bỏ lỡ +0, không tính tốc độ, đồng điểm đồng hạng. Server quản lý deadline và đáp án, không gửi đáp án đúng trong phase question.
- Tạo quiz vẫn mock; Live Quiz dùng server Python và HTTP polling thật. Dữ liệu phòng trong RAM; hướng dẫn/giới hạn tại [LIVE_QUIZ.md](LIVE_QUIZ.md).
- Test: `tests/test_live_quiz.py` kiểm tra quyền host, đáp án ẩn, hết giờ, double-submit, snapshot, restart, join và hai HTTP client đồng thời.
