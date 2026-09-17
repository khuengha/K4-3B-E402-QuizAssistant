# Canvas 7 dòng (CP1)

Canvas nộp ở CP1 theo scaffold `02-guide.md` §1.5 — mỗi dòng một ý, cả canvas vừa một trang. Dưới đây là 3 bài của các nhóm khoá trước (đã ẩn tên, chỉnh nhẹ), kèm ghi chú vì sao đạt. Số liệu trong ví dụ viết dạng `XX/XXX` — nhóm bạn phải tự đếm trên `data/` của khoá này và ghi số thật.


| # | Dòng | Nội dung |
|---|---|---|
| 1 | Track + đề |C1 · Knowledge-to-Lesson — Graph tri thức và bài học thích ứng
| 2 | Job executor (ai · đang ở đâu · làm gì) |Giảng viên đang chuẩn bị quiz ôn tập cho một bài học từ các tài liệu/slides trước và sau buổi giảng. |
| 3 | Pain một câu (ai – đang làm gì – vướng đâu – hậu quả) |Khi tạo quiz từ slide và transcript, giảng viên khó đảm bảo chất lượng và độ bao phủ của bộ câu hỏi: đáp án đúng có thể nổi bật do dài/ngắn bất thường hoặc bị ám chỉ, các phương án nhiễu có thể không liên quan; câu hỏi thường chỉ tập trung vào một số phần rải rác thay vì bao phủ toàn bộ bài; đồng thời thiếu nguồn tham chiếu để kiểm tra câu hỏi và đáp án dựa trên nội dung nào. Hậu quả là giảng viên phải tự rà soát, chỉnh sửa và dò lại tài liệu trước khi có thể sử dụng quiz. |
| 4 | 1–2 bằng chứng đầu (số + cách đếm + mã hội thoại/tin nhắn, hoặc khảo sát/phỏng vấn có số người) | **Phỏng vấn 5 người: 3/5 (P02, P03, P04) từng dùng AI tạo quiz; P02 lo về chất lượng đầu ra và độ phân hóa câu hỏi, P03 ghi nhận quiz có thể không bao phủ bài giảng, đáp án dài/ngắn không đồng đều và tốn công review, P04 chưa từng tạo quiz trước đây, nhưng vẫn đang có nhu cầu thử công cụ nếu việc tạo quiz được hỗ trợ tốt, P05 có khó khăn khi tạo quiz, đặc biệt là đảm bảo chất lượng câu hỏi vì câu hỏi dễ bị hallucinate .** |
| 5 | Lát cắt MỘT CÂU (1 user · 1 việc · 1 quyết định AI · 1 kết quả) | Một giảng viên · tạo quiz theo số câu, độ khó và phạm vi topic đã chọn · AI chỉ sinh câu hỏi từ các concept có đủ bằng chứng trong knowledge graph · kết quả là bộ quiz có topic và mã đoạn/trang nguồn để giảng viên duyệt hoặc loại.
 |
| 6 | AI tự làm đến đâu + 1 dòng lý do · ≥3 willing users ngoài nhóm | Tự: đọc knowledge graph, chọn concept theo topic/độ khó/số câu đã cấu hình, sinh câu hỏi + đáp án + distractor và gắn mã đoạn/trang nguồn. Không tự: sinh câu hỏi từ nội dung không có hoặc không đủ bằng chứng trong knowledge graph, và không tự xuất bản quiz chưa được giảng viên duyệt. Lý do: cần đảm bảo quiz có căn cứ, đủ độ tin cậy và vẫn giữ quyền kiểm soát cuối cùng cho giảng viên. Willing users (ngoài nhóm, đã hỏi và đồng ý): Lab Coach M, Lab Coach H, Lab Coach Đ|
| 7 | Phân công có tên | 7. Phân công: Nguyễn Hà Khuê — extract text slide, xây knowledge graph, provenance + bộ dữ liệu kiểm thử chuẩn · Nguyễn Hoàng Anh — AI quiz generation, prompt, logic chọn concept, backend/API + output validation · Nguyễn Huy Hoàng — UI cấu hình/duyệt quiz, evaluation, user test + demo/changelog.|
