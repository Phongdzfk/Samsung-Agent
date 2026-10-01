# KỊCH BẢN THUYẾT TRÌNH — BASELINE LIGHTMEM VÀ SO SÁNH VỚI APEX-MEM (12 slide, khoảng 11–12 phút)

> Mọi số trong kịch bản lấy từ 150/150 câu tập dev của cả hai hệ. Nếu chạy lại thì phải sửa kịch bản
> cho khớp slide. Dấu **↳** là gợi ý thao tác: chỉ vào đâu trên slide.

---

## Slide 1 · Tiêu đề (0:15)

Phần này em báo cáo đường cơ sở LightMem và phép so sánh đầu tiên với hệ thống của nhóm, APEX-MEM.
Cả hai hệ đã chạy đủ một trăm năm mươi câu của tập dev.

---

## Slide 2 · LightMem hoạt động thế nào (0:50)

↳ *Chỉ lần lượt năm thẻ.* LightMem nén hội thoại bằng LLMLingua-2, chia thành các chủ đề, gọi LLM
rút fact và metadata cho từng chủ đề, nhúng bằng MiniLM rồi lưu vào Qdrant. Khi hỏi thì lấy hai mươi
ký ức gần nhất đưa cho LLM trả lời.

↳ *Chỉ ô "Giới hạn quan trọng".* Em xin nhấn mạnh từ đầu một điểm sẽ giải thích kết quả sau này:
cấu hình gốc của LightMem chỉ lưu lượt của người dùng. Lời trợ lý không vào bộ nhớ.

Nhóm chọn bài này làm baseline vì đã bình duyệt, có mã nguồn chạy được trên đúng benchmark của nhóm,
và cách lưu ký ức khác hẳn hướng đồ thị của APEX-MEM nên đối chứng có ý nghĩa.

---

## Slide 3 · Thiết lập (1:15)

↳ *Chỉ bảng.* Dữ liệu là LongMemEval-S, năm trăm câu, mỗi câu một kho hội thoại riêng khoảng một
trăm mười lăm nghìn token. Nhóm chia một trăm năm mươi câu dev và ba trăm năm mươi câu test, phân
tầng theo loại, seed bốn mươi hai. File chia này nhóm đã đối chiếu với bản gốc xuất ra từ Kaggle,
trùng khớp một trăm phần trăm.

Một điểm em báo cáo thẳng: kế hoạch ghi dùng GPT-5.5, nhưng tài khoản không có quyền dùng model đó,
router báo lỗi 404. **Cả hai hệ đều chạy bằng gpt-5.6-luna**, và model chấm cũng dùng chung là
gpt-5.6-terra với prompt chấm chính thức của LongMemEval. Nhờ vậy hai hệ so được trực tiếp.

↳ *Chỉ hai dòng cuối, màu vàng.* Khác biệt chính giữa hai hệ nằm ở đây: LightMem chỉ lưu lượt người
dùng, APEX-MEM lưu cả lượt trợ lý. Em sẽ quay lại điểm này.

---

## Slide 4 · So sánh trực tiếp (1:30)

Đây là slide chính.

↳ *Chỉ hai ô số bên phải.* Gộp chung một trăm năm mươi câu: APEX-MEM đúng một trăm hai mươi bảy câu,
tám mươi bốn phẩy bảy phần trăm. LightMem đúng một trăm hai mươi hai câu, tám mươi mốt phẩy ba phần
trăm. Khoảng tin cậy chín mươi lăm phần trăm của hai hệ chồng lên nhau gần hết.

↳ *Chỉ biểu đồ.* Theo loại, năm trong sáu loại hai hệ gần như bằng nhau, chênh nhau một hai câu.
Cột khác biệt rõ nhất là loại đơn phiên trợ lý, APEX-MEM tám mươi hai phần trăm, LightMem bốn mươi
mốt phần trăm.

↳ *Chỉ dải vàng.* Em xin đọc đúng mức: chênh năm câu trên một trăm năm mươi câu. Nhóm câu từ chối
chỉ có bốn câu nên chưa nói được gì về năng lực biết từ chối.

---

## Slide 5 · Chênh lệch đến từ đâu (1:45)

↳ *Chỉ bốn ô bên trái.* Nhìn theo từng cặp câu hỏi: một trăm linh bảy câu cả hai cùng đúng, tám câu
cả hai cùng sai. APEX-MEM đúng riêng hai mươi câu, LightMem đúng riêng mười lăm câu. Kiểm định
McNemar cho p bằng không phẩy năm: **chưa có bằng chứng thống kê rằng hệ nào tốt hơn.**

↳ *Chỉ bảng bên phải.* Và nếu tách theo loại thì toàn bộ chênh lệch nằm ở một chỗ: loại lượt trợ lý,
APEX-MEM hơn bảy câu. Ở năm loại còn lại, LightMem hơn hai câu, tám mươi sáu phẩy năm so với tám mươi
lăm phần trăm.

↳ *Chỉ ô đỏ.* Khác biệt cấu hình em nói ở slide ba: loại câu hỏi này hỏi đúng về lời trợ lý, mà
APEX-MEM lưu lời trợ lý còn LightMem thì không.

↳ *Chỉ dải dưới cùng.* Em xin nói rõ: đây mới là giả thuyết. Muốn kiểm chứng phải chạy lại LightMem
loại này với cấu hình lưu cả lượt trợ lý. Đó là việc đầu tiên nhóm sẽ làm.

---

## Slide 6 · Kết quả riêng của LightMem (0:50)

↳ *Chỉ biểu đồ.* Trung bình theo loại bảy mươi tám phẩy chín phần trăm. Năm loại đạt từ bảy mươi
tám đến một trăm phần trăm, riêng lượt trợ lý bốn mươi mốt phần trăm.

↳ *Chỉ ô đỏ.* Nguyên nhân là cấu hình, không phải ngẫu nhiên. Bằng chứng ở slide sau.

---

## Slide 7 · Phân tích lỗi của LightMem (1:00)

Hai mươi tám câu sai, tập trung vào hai kiểu.

↳ *Chỉ danh sách bên trái.* Kiểu một là câu hỏi về lời trợ lý, mười câu. Kiểu hai là câu đếm qua
nhiều phiên, bảy câu: hệ đếm thiếu hoặc thừa. Ví dụ đáp án là bốn loại ẩm thực thì hệ trả lời sáu.

↳ *Chỉ dải dưới cùng.* Bằng chứng cho kiểu một: sáu trên mười câu sai loại này, hệ trả lời thẳng là
không tìm thấy thông tin trong bộ nhớ. Khớp với cấu hình chỉ lưu lượt người dùng.

Khác biệt quan trọng: kiểu một là lỗi cấu hình, sửa được. Kiểu hai là hạn chế thật của cách lưu ký ức.

---

## Slide 8 · Lỗi không nằm ở khâu tìm kiếm (1:30)

Slide này trả lời câu hỏi kế hoạch tuần ba đặt ra: sai là do không tìm thấy bằng chứng, hay tìm thấy
rồi mà vẫn suy luận sai?

↳ *Chỉ ô "Đo thế nào".* Mỗi ký ức LightMem trả về đều mở đầu bằng mốc thời gian của phiên chứa nó.
Khớp mốc đó với ngày từng phiên trong bộ dữ liệu là biết ký ức đến từ phiên nào, rồi so với nhãn phiên
chứa bằng chứng. Có hai câu trong đó hai phiên trùng mốc thời gian nên khớp chưa chắc chắn.

↳ *Chỉ số 99,3%.* Truy xuất trúng phiên chứa bằng chứng ở một trăm bốn mươi chín trên một trăm năm
mươi câu. Trong hai mươi tám câu sai, hai mươi bảy câu đã có bằng chứng trong tay mà vẫn trả lời sai.
Hệ APEX-MEM cũng tự đo cho thấy tương tự: recall bộ lọc chín mươi tám phẩy năm phần trăm.

Giới hạn em xin nói rõ: trúng phiên không có nghĩa là giữ được đúng chi tiết, vì LightMem nén trước
khi lưu. Nên hai mươi bảy câu đó là lỗi trích xuất hoặc lỗi suy luận, phép đo này chưa tách được.

Ví dụ có lỗi suy luận thật: một câu hỏi khoảng cách hai ngày, hệ nêu đúng cả hai mốc, hai mươi hai
tháng ba và mười lăm tháng tư, nhưng tính ra mười tám ngày thay vì hai mươi bốn.

---

## Slide 9 · Model chấm có đáng tin không (1:00)

Mọi con số đều do model chấm quyết định, nên nhóm kiểm tra bằng tay kết quả của LightMem.

↳ *Chỉ ô bên trái.* Soi hai mươi câu được chấm đúng, chọn ngẫu nhiên: không câu nào được cho điểm oan.

↳ *Chỉ ô bên phải.* Soi toàn bộ hai mươi tám câu bị chấm sai: hai câu nhóm cho rằng đáng lẽ nên tính
đúng. Một câu hệ đã nói đúng chuyện con mèo rụng lông nhưng vẫn bị chấm sai. Một câu hệ nêu đúng mười
chín ngày nhưng nói thêm một con số khác ở cuối.

Kết luận: model chấm không rộng tay nhưng hơi khắt khe, accuracy thật có thể cao hơn khoảng một phẩy
ba điểm. Vì cả hai hệ dùng chung một model chấm nên sai lệch này nhiều khả năng ảnh hưởng hai bên
tương tự. Em xin nói rõ là mới soi kết quả của LightMem.

---

## Slide 10 · Chi phí và thời gian (1:00)

↳ *Chỉ bảng.* APEX-MEM dựng bộ nhớ trung vị bảy phút, LightMem ba mươi ba phút. Nhưng em xin **không
dùng số này để kết luận hệ nào nhanh hơn**, vì hai bên chạy với số luồng khác nhau và đều bị hạn mức
tài khoản làm chậm.

Ở APEX-MEM, tám mươi tám phần trăm token nằm ở bước dựng. Còn LightMem chưa có số token và số lời
gọi, vì script không ghi lại, và router chèn thêm khoảng hai nghìn năm trăm token vào mỗi lời gọi nên
số đếm qua router bị phình. Muốn so trục này phải sửa script rồi chạy lại.

↳ *Chỉ gạch đầu dòng cuối.* APEX-MEM phục vụ đúng model: ba nghìn chín trăm chín mươi tám lời gọi
luna và đúng một trăm năm mươi lời gọi chấm, không có model nào bị đổi lén.

---

## Slide 11 · Sự cố kỹ thuật (0:50)

Em ghi lại để tuần sau không vấp lại. Đáng kể nhất là dòng thứ năm: các tài khoản đều là gói miễn phí,
chạy tám luồng thì sáu tài khoản hết hạn mức gần như cùng lúc, rồi hai tài khoản bị thu hồi token.
Nguyên nhân thu hồi nhóm chưa xác định được. Đây là rủi ro cho tuần bảy, em nói ở phần câu hỏi.

---

## Slide 12 · Tổng kết (1:00)

↳ *Chỉ cột trái.* Tóm lại: chưa có bằng chứng APEX-MEM hơn LightMem. Tám mươi tư phẩy bảy so với tám
mươi mốt phẩy ba, p bằng không phẩy năm. Chênh lệch nằm ở loại lượt trợ lý, và nguyên nhân nghi là
cấu hình. Cả hai hệ truy xuất gần như không sai, lỗi nằm ở trích xuất và suy luận.

↳ *Chỉ cột phải.* Việc tiếp theo, theo thứ tự ưu tiên. Một, chạy lại LightMem loại lượt trợ lý với
cấu hình lưu cả lượt trợ lý, mười bảy câu, để so công bằng. Hai, chấm ba lần lấy trung bình cho cả
hai hệ. Ba, soi ba mươi lăm câu hai hệ trả lời khác nhau để biết mỗi hệ mạnh ở đâu. Bốn là việc em
xin ý kiến anh.

---

## Câu muốn xin ý kiến mentor

**Về khối lượng chạy tập test ở tuần 7 và hạn mức tài khoản.**

Tập dev một trăm năm mươi câu đã gần như cạn hạn mức các tài khoản miễn phí, và hai tài khoản bị thu
hồi token. Tập test ba trăm năm mươi câu lớn hơn hơn hai lần, và phải chạy cho cả hai hệ. Nhóm xin ý
kiến anh: nên chạy toàn bộ tập test hay chỉ một mẫu con có phân tầng, ví dụ một trăm câu, báo cáo kèm
khoảng tin cậy? Và nhóm nên dùng nguồn LLM nào cho việc này?

---

## Chuẩn bị cho câu hỏi anh có thể hỏi

**"Vậy APEX-MEM có tốt hơn LightMem không?"**
Chưa kết luận được. Gộp chung APEX-MEM hơn năm câu trên một trăm năm mươi, nhưng kiểm định cặp cho p
bằng không phẩy năm. Và toàn bộ chênh lệch nằm ở loại lượt trợ lý, nơi hai hệ cấu hình khác nhau.
Ở năm loại còn lại LightMem hơn nhẹ.

**"Sao không dùng GPT-5.5 như kế hoạch?"**
Tài khoản không có quyền model đó, router báo lỗi 404, kể cả bản review. Quan trọng là cả hai hệ chạy
cùng gpt-5.6-luna và cùng model chấm nên so được.

**"Chênh lệch ở loại lượt trợ lý là do đồ thị hay do cấu hình?"**
Nhóm nghi do cấu hình, vì LightMem không lưu lời trợ lý và sáu trên mười câu sai hệ nói thẳng là không
có thông tin. Nhưng chưa kiểm chứng. Việc đầu tiên tuần sau là chạy lại mười bảy câu đó với cấu hình
lưu cả lượt trợ lý.

**"Một lần chấm có đủ tin không?"**
Chưa. Kế hoạch là ba lần lấy trung bình, hiện mới chấm một lần. Nhóm có soi tay hai mươi tám câu bị
chấm sai và thấy hai câu đáng ngờ, nên model chấm hơi khắt khe, khoảng một phẩy ba điểm.

**"Tại sao tin được kết luận truy xuất không phải nút thắt?"**
Phép đo dựa trên dữ liệu có sẵn của benchmark chứ không phải phán đoán. Nhưng em nhắc lại giới hạn:
nó chỉ chứng minh lấy đúng phiên, chưa chứng minh giữ đúng chi tiết. Có hai câu nhập nhằng về mốc thời gian.

**"APEX-MEM nhanh hơn hay rẻ hơn LightMem?"**
Chưa so được. Thời gian đo ở điều kiện chạy khác nhau, và LightMem chưa ghi token. APEX-MEM tốn khoảng
chín mươi nghìn token để dựng mỗi câu, tám mươi tám phần trăm tổng chi phí.

**"Sao 8 tài khoản mà vẫn hết?"**
Đều là gói miễn phí, hạn mức thấp. Chạy tám luồng song song thì cạn gần như cùng lúc. Nhóm sẽ giảm số
luồng, và cần quyết định nguồn LLM cho tuần bảy.
