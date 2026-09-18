# Live Quiz — chạy và demo

## Khởi động

Dùng Python 3.10 trở lên. Cài dependency cho ứng dụng tích hợp:

```bash
python -m pip install -r requirements.txt
python server.py
```

Mở `http://localhost:8000`. Với nhiều thiết bị, giảng viên mở `http://<IP-LAN-của-máy-host>:8000` rồi chia sẻ link phòng; người học dùng cùng Wi-Fi và phải truy cập được cổng 8000 của máy host. `localhost` trên điện thoại là chính điện thoại đó, không phải máy giảng viên.

Có thể đổi cổng bằng `python server.py --port 8080`. Server mặc định lắng nghe `0.0.0.0`; chỉ dùng trên một máy với `--host 127.0.0.1` nếu cần. Trình tạo quiz và Live Quiz đều cần server này; cấu hình API key trong `.env` để phân tích tài liệu và tạo quiz. Không dùng `python -m http.server` vì server tĩnh không có API phòng chơi.

## Giảng viên

1. Tạo quiz, kiểm tra nguồn và duyệt câu hỏi. Nút **Play Quiz** bật khi có ít nhất một câu đã duyệt.
2. Bấm **Play Quiz**, chọn thời gian mỗi câu và số người tham gia tối đa (1–100, mặc định 30, không tính host) rồi **Tạo phòng chơi**. Chỉ câu đã duyệt được chụp thành một bộ cố định trong phòng; không sinh thêm câu mới.
3. Chia sẻ link `live.html?room=PIN`. Phòng chờ hiển thị PIN, số chỗ đã dùng / giới hạn và danh sách người đã tham gia. Khi đủ chỗ, server từ chối người mới; người đã tham gia vẫn kết nối lại được. Có thể nhập PIN thủ công tại `/live.html`.
4. Khi có người chơi, bấm **Start Quiz**. Mỗi câu có bộ đếm giờ riêng.
5. Hết giờ hoặc mọi người đã trả lời sẽ tự chốt câu. Host cũng có thể chốt sớm. Hiện đáp án, giải thích, nguồn và bảng xếp hạng tạm thời; host bấm **Câu tiếp theo**.
6. Sau câu cuối, chọn **Xem kết quả cuối**: xem xếp hạng, điểm, đúng/sai/bỏ lỡ, chủ đề sai nhiều và phân bố lựa chọn từng câu. Có thể tải JSON kết quả.
7. **Restart quiz / Chơi lại cùng bộ quiz** đưa cả phòng về lobby, giữ PIN, người chơi và câu hỏi, đặt điểm về 0. Tải kết quả trước nếu cần giữ bản riêng.
8. **Kết thúc phòng** đóng lượt chơi, hiển thị báo cáo các câu đã chốt; không mở lại phòng đã đóng. Quay về bộ quiz để tạo phòng mới.

Rời màn hình host không đóng phòng. Dùng nút **Mở phòng PIN** để trở lại; tải lại cùng tab cũng khôi phục phiên host. Bộ quiz trong phòng độc lập với chỉnh sửa sau đó trên màn tạo quiz. Không thể sửa câu hỏi ngay giữa lượt chơi.

## Người học

- Mở link hoặc nhập PIN và tên, không cần tài khoản. Tên phải khác người đã có trong phòng.
- Chỉ nhận người mới trong phòng chờ. Người đã tham gia có thể tải lại trang để kết nối lại cùng phiên trên cùng trình duyệt.
- Chọn một đáp án và chốt một lần. Đáp án đã ghi nhận có nền tím đậm, viền nổi và nhãn ✓ ĐÃ CHỌN; các lựa chọn còn lại mờ đi. Đây là xác nhận lựa chọn, không phải xác nhận đáp án đúng. Đúng +1.000 điểm; sai hoặc bỏ lỡ +0. Không cộng điểm tốc độ.
- Đáp án đúng và lời giải chỉ được server gửi khi câu kết thúc. Điểm và hạn trả lời do server quyết định; sửa đồng hồ thiết bị không thay đổi kết quả.
- Điểm bằng nhau có cùng hạng. Số câu sai và bỏ lỡ được tách riêng. Chủ đề sai nhiều tính trên câu đã trả lời sai, không cộng câu bỏ lỡ.
- Chơi thử nhiều người trên cùng máy: dùng trình duyệt khác hoặc cửa sổ riêng tư. Các tab chung localStorage có thể khôi phục cùng người chơi.

## Phạm vi hiện tại

- Live Quiz có đồng bộ HTTP thật (poll mỗi giây), không phải người chơi giả. Tạo câu hỏi và nguồn vẫn là dữ liệu mẫu của prototype hiện có.
- Không có database: phòng/kết quả mất khi dừng server; phòng hết hạn sau 12 giờ không hoạt động. Giới hạn 100 người/phòng và 200 phòng trong bộ nhớ chưa phải cam kết chịu tải; kiểm thử hiện tại dùng hai client đồng thời.
- Trạng thái “đã tham gia” là danh sách đăng ký trong phòng, không phải chỉ báo người chơi đang online. Mất kết nối không dừng đồng hồ; không trả lời kịp sẽ được tính bỏ lỡ.
- Host được nhận diện bằng token riêng; người học không được start, next, restart hay đóng phòng. Token không nằm trong link chia sẻ. Đây là bản dùng thử trong lớp, chưa phải dịch vụ công khai có quản trị tài khoản.
- Câu đã duyệt được kiểm tra định dạng và trạng thái khi tạo phòng. Chưa có tài khoản/nguồn dữ liệu phê duyệt phía server để xác minh danh tính giảng viên; bộ quiz do trình tạo gửi lên.

## Kiểm tra

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
node tests/r3-ui.test.js
node tests/live-ui.test.js
```

Backend tests: snapshot đã duyệt, ẩn đáp án/token, quyền host, điểm và đồng hạng, hết giờ, đáp án lặp, restart, request cũ, đóng phòng và hai người gửi HTTP đồng thời. UI tests dùng DOM giả lập; không thay thế kiểm tra hình ảnh trên trình duyệt.
