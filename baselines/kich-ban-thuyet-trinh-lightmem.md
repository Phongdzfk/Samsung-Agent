# KỊCH BẢN THUYẾT TRÌNH — BASELINE LIGHTMEM (11 slide, khoảng 9–10 phút)

> Toàn bộ số trong kịch bản lấy từ 125/150 câu tập dev đã chạy xong. Chạy thêm câu thì số đổi,
> nhớ sửa lại kịch bản cho khớp slide.
> Dấu **↳** là gợi ý thao tác: chỉ vào đâu trên slide.

---

## Slide 1 · Tiêu đề (0:15)

Phần này em xin báo cáo về đường cơ sở, tức baseline, mà nhóm dùng để so sánh với hệ thống
APEX-MEM. Nhóm chọn LightMem, một bài đã bình duyệt ở ICLR 2026, có sẵn mã nguồn mở.

Số liệu hôm nay là số sơ bộ trên 125 trong 150 câu tập dev. Em sẽ nói rõ chỗ nào chưa đủ dữ liệu.

---

## Slide 2 · LightMem hoạt động thế nào (0:50)

↳ *Chỉ lần lượt năm thẻ.* LightMem chạy qua năm bước. Nén hội thoại bằng LLMLingua-2 để bỏ bớt
token ít thông tin. Chia hội thoại thành các chủ đề. Với mỗi chủ đề, gọi LLM để rút ra fact và
metadata. Nhúng bằng MiniLM rồi lưu vào Qdrant. Khi hỏi thì lấy hai mươi ký ức gần nhất đưa cho
LLM trả lời.

↳ *Chỉ ô "Giới hạn quan trọng".* Có một điểm em xin nhấn mạnh từ đầu, vì nó giải thích phần lớn
kết quả sau này: cấu hình gốc của LightMem chỉ lưu lượt của người dùng. Những gì trợ lý nói
không vào bộ nhớ.

Lý do nhóm chọn bài này làm baseline: đã bình duyệt, có mã nguồn chạy được trên đúng benchmark
nhóm dùng, và cách lưu ký ức khác hẳn hướng đồ thị của APEX-MEM nên đối chứng có ý nghĩa.

---

## Slide 3 · Thiết lập thực nghiệm (1:00)

↳ *Chỉ bảng bên trái.* Dữ liệu là LongMemEval-S, năm trăm câu, mỗi câu có một kho hội thoại
riêng khoảng một trăm mười lăm nghìn token.

Về chia tập: nhóm chia một trăm năm mươi câu dev và ba trăm năm mươi câu test, phân tầng theo
loại câu hỏi, seed bốn mươi hai. File chia này nhóm đã đối chiếu với bản gốc xuất ra từ Kaggle,
trùng khớp một trăm phần trăm.

Có một điểm em xin báo cáo thẳng: kế hoạch tuần trước ghi dùng GPT-5.5, nhưng tài khoản nối vào
router không có quyền dùng model đó, báo lỗi 404. Nhóm chuyển sang gpt-5.6-luna. Hệ APEX-MEM sẽ
phải chạy đúng model này thì so sánh mới công bằng.

Model chấm là một model khác với model trả lời, và prompt chấm lấy nguyên văn prompt chính thức
của LongMemEval, tách theo từng loại câu hỏi, để điểm số so được với các bài báo khác.

↳ *Chỉ hai số bên phải.* Một trăm năm mươi câu dev để chạy và chỉnh. Ba trăm năm mươi câu test
nhóm khóa lại, đến tuần bảy mới mở.

---

## Slide 4 · Tiến độ chạy (0:30)

↳ *Chỉ các thanh màu nhạt.* Slide này để anh thấy phần nào còn thiếu. Ba loại chưa chạy hết:
đơn phiên trợ lý mới chín trên mười bảy câu, suy luận thời gian ba mươi trên bốn mươi, cập nhật
kiến thức mười sáu trên hai mươi ba.

Nguyên nhân chậm em sẽ nói ở slide chi phí. Ngắn gọn là mỗi câu tốn hơn nửa tiếng.

---

## Slide 5 · Kết quả theo loại (1:30)

Đây là slide chính.

↳ *Chỉ biểu đồ.* Trung bình theo loại là bảy mươi chín phẩy không phần trăm. Gộp chung một trăm
hai mươi lăm câu thì được tám mươi tư phần trăm. Nhóm báo cáo trung bình theo loại vì số câu
giữa các loại chênh nhau nhiều, từ chín đến bốn mươi câu, gộp chung thì loại đông câu sẽ lấn át.

↳ *Chỉ cột thấp nhất.* Điều đáng chú ý nhất là loại đơn phiên trợ lý chỉ đạt ba mươi ba phẩy ba
phần trăm, trong khi năm loại còn lại đều từ bảy mươi tám đến một trăm.

↳ *Chỉ ô đỏ bên phải.* Và nguyên nhân không phải ngẫu nhiên. Đây đúng là hệ quả của cấu hình em
nói ở slide hai: LightMem không lưu lời trợ lý, mà loại câu hỏi này lại hỏi đúng về những gì trợ
lý đã nói trước đó. Bằng chứng ở slide sau.

↳ *Chỉ dải cảnh báo dưới cùng.* Em xin lưu ý đây là số sơ bộ. Ba loại chưa chạy đủ, và nhóm câu
từ chối mới có đúng một câu, chưa đủ để nói gì về năng lực biết từ chối.

---

## Slide 6 · Hai kiểu lỗi (1:15)

Hai mươi câu sai trong một trăm hai mươi lăm câu đã chạy, tập trung vào hai kiểu.

↳ *Chỉ danh sách bên trái.* Kiểu thứ nhất là câu đếm qua nhiều phiên, bảy câu. Toàn dạng "bao
nhiêu". Hệ đếm thiếu hoặc thừa. Anh xem hai dòng đầu bảng: đáp án là bốn loại ẩm thực thì hệ trả
lời sáu; đáp án hai mươi ba bài viết thì hệ trả lời hai mươi lăm.

Kiểu thứ hai là câu hỏi về lời trợ lý, sáu câu.

↳ *Chỉ hai dòng cuối bảng.* Hai dòng này cho thấy hai cách hệ sai. Dòng trên, hệ bịa ra một trang
web khác. Dòng dưới, hệ nói thẳng là không có trong bộ nhớ.

↳ *Chỉ dải xanh dưới cùng.* Và đây là bằng chứng: bốn trên sáu câu sai loại này, hệ trả lời thẳng
là không tìm thấy thông tin trong bộ nhớ. Khớp đúng với cấu hình chỉ lưu lượt người dùng.

Khác biệt quan trọng giữa hai kiểu: kiểu hai là lỗi cấu hình, sửa được bằng một dòng config.
Kiểu một là hạn chế thật của cách lưu ký ức.

---

## Slide 7 · Lỗi nằm ở đâu (1:45)

Slide này trả lời câu hỏi mà bản kế hoạch tuần ba đặt ra: sai là do không tìm thấy bằng chứng,
hay tìm thấy rồi mà vẫn suy luận sai?

↳ *Chỉ ô "Đo thế nào".* Cách đo như sau. Mỗi ký ức LightMem trả về đều mở đầu bằng mốc thời gian
của phiên chứa nó. Bộ dữ liệu thì cho biết ngày của từng phiên và phiên nào chứa bằng chứng. Khớp
hai mốc thời gian đó là biết ký ức được lấy về đến từ phiên nào. Trong một trăm hai mươi lăm câu
không có trường hợp nào hai phiên trùng mốc, nên phép khớp này không nhập nhằng.

↳ *Chỉ số 99,2%.* Kết quả: truy xuất trúng phiên chứa bằng chứng ở một trăm hai mươi bốn trên một
trăm hai mươi lăm câu.

↳ *Chỉ ô số 19.* Và trong hai mươi câu sai, mười chín câu đã có bằng chứng trong hai mươi ký ức
lấy về mà vẫn trả lời sai.

Ví dụ rõ nhất nằm trong ô đó: một câu hỏi khoảng cách giữa hai ngày. Hệ nêu đúng cả hai mốc, hai
mươi hai tháng ba và mười lăm tháng tư, đúng như đáp án gốc, nhưng tính ra mười tám ngày trong
khi thực tế là hai mươi bốn. Ký ức lấy đúng, phép trừ ngày sai.

Em xin nói rõ giới hạn của phép đo này: trúng phiên không đồng nghĩa với giữ được chi tiết cần
thiết, vì LightMem có nén và tóm tắt trước khi lưu. Nên mười chín câu kia là lỗi trích xuất hoặc
lỗi suy luận, phép đo hiện tại chưa tách được hai loại đó.

↳ *Chỉ dải vàng dưới cùng.* Ý nghĩa cho hệ của nhóm: trên bộ dữ liệu này, đầu tư thêm vào khâu
tìm kiếm gần như không còn dư địa. Điểm số sẽ phụ thuộc vào trích xuất giữ được bao nhiêu chi
tiết và mô hình suy luận ra sao.

---

## Slide 8 · Model chấm có đáng tin không (1:00)

Toàn bộ con số accuracy vừa rồi đều do một model chấm quyết định, nên nhóm kiểm tra lại nó bằng
tay.

↳ *Chỉ ô bên trái.* Soi mười hai câu được chấm đúng, chọn ngẫu nhiên. Không có câu nào được cho
điểm oan.

↳ *Chỉ ô bên phải.* Soi toàn bộ hai mươi câu bị chấm sai. Hai câu nhóm cho rằng đáng lẽ nên tính
đúng.

↳ *Chỉ bảng.* Câu thứ nhất, đáp án gốc là một rubric yêu cầu xét tới con mèo và việc nó rụng
lông; hệ đã nói đúng chuyện đó nhưng vẫn bị chấm sai. Câu thứ hai mập mờ hơn: hệ nêu đúng con số
mười chín ngày nhưng nói thêm một con số khác ở cuối, nên có thể bị hiểu nhầm.

Kết luận: model chấm không rộng tay, nhưng hơi khắt khe. Accuracy thật có thể cao hơn khoảng một
phẩy sáu điểm.

↳ *Chỉ dải dưới cùng.* Cách xử lý: giữ kế hoạch chấm ba lần lấy trung bình, và quan trọng hơn là
dùng đúng một model chấm cho cả LightMem lẫn APEX-MEM, để sai lệch này triệt tiêu khi so sánh hai
hệ.

---

## Slide 9 · Chi phí và thời gian (0:50)

↳ *Chỉ ba ô số.* Dựng bộ nhớ mỗi câu tốn trung vị ba mươi ba phút, chậm nhất sáu mươi mốt phút.
Trong khi truy xuất chỉ mất không phẩy mười tám giây và sinh câu trả lời bốn phẩy một giây. Tức
là dựng bộ nhớ chiếm gần như toàn bộ thời gian.

Lý do là mỗi câu có kho hội thoại rất dài, bị chia thành hàng trăm chủ đề, mỗi chủ đề lại tốn
lời gọi LLM riêng. Một câu tốn hàng trăm lời gọi.

↳ *Chỉ gạch đầu dòng thứ ba.* Một điểm em phải nói rõ: router mà nhóm dùng chèn thêm khoảng hai
nghìn năm trăm token vào mỗi lời gọi. Nên nhóm **chưa** báo cáo trục chi phí token, vì số đếm qua
router không phản ánh đúng. Muốn có số đó thì phải đo riêng, trừ phần này ra.

---

## Slide 10 · Sự cố kỹ thuật (0:40)

Slide này em ghi lại để tuần sau chạy APEX-MEM không vấp lại. Năm sự cố, tất cả đều nằm ở môi
trường chạy chứ không phải ở thiết kế.

Đáng kể nhất là hai cái giữa: chạy song song nhiều luồng thì các luồng đụng nhau lúc nạp model,
và chạy vài giờ thì cạn RAM vì mỗi câu nạp lại model mới. Cả hai đã sửa trong script, và script
có cơ chế chạy tiếp nên bị ngắt giữa chừng không mất kết quả đã có.

---

## Slide 11 · Tổng kết (1:00)

↳ *Chỉ cột trái.* Tóm lại: baseline đã chạy được đầu cuối. Số sơ bộ là bảy mươi chín phần trăm
trung bình theo loại. Điểm yếu rõ nhất là loại lượt trợ lý, và nguyên nhân là cấu hình chứ không
phải hệ kém. Truy xuất gần như không sai, nên lỗi nằm ở trích xuất và suy luận.

↳ *Chỉ cột phải.* Việc tiếp theo, xếp theo thứ tự ưu tiên. Chạy nốt hai mươi lăm câu dev còn lại.
Dựng và chạy hệ APEX-MEM cùng model và cùng model chấm, vì hiện baseline chưa có gì để so. Chạy
lại LightMem với cấu hình lưu cả lượt trợ lý để tách phần thiệt do cấu hình.

Và có một việc em muốn xin ý kiến anh, ở mục bốn.

---

## Câu hỏi muốn xin ý kiến mentor

**Câu chính — về khối lượng chạy tập test ở tuần 7.**

Tốc độ đo được là mười đến mười bốn câu một giờ. Chạy ba trăm năm mươi câu test tốn khoảng hai
mươi lăm đến ba mươi giờ cho **mỗi hệ**. Hai hệ là năm mươi đến sáu mươi giờ chạy liên tục, chưa
kể tài khoản có trần sử dụng và đã chạm giới hạn nhiều lần.

Nhóm muốn hỏi anh nên chạy toàn bộ tập test cho baseline, hay chỉ chạy một mẫu con có phân tầng,
ví dụ một trăm câu, rồi báo cáo kèm khoảng tin cậy?

---

## Chuẩn bị cho câu hỏi anh có thể hỏi

**"Sao không dùng GPT-5.5 như kế hoạch?"**
Tài khoản không có quyền model đó, router báo lỗi 404. Nhóm đã thử cả bản gpt-5.5-review, cũng
404. Quan trọng là hệ APEX-MEM sẽ chạy đúng model gpt-5.6-luna này để so sánh công bằng.

**"79% so với bài báo LightMem thì thế nào?"**
Chưa so được. Bài báo báo cáo trên LongMemEval với model nền khác, và repo không công bố bảng số
cho LongMemEval, chỉ có cho LoCoMo. Muốn so thì phải chạy lại bằng model nền của họ. Nhóm cho
rằng việc đó không cần thiết, vì cái nhóm cần là so LightMem với APEX-MEM trên cùng điều kiện,
chứ không phải tái hiện đúng con số của bài báo.

**"Sao loại lượt trợ lý thấp thế, có phải chạy sai không?"**
Không. Đó là cấu hình gốc của chính bài báo, `messages_use = user_only`. Nhóm giữ nguyên để số
liệu so được với bài báo. Bằng chứng là bốn trên sáu câu sai loại này hệ trả lời thẳng là không
có dữ liệu trong bộ nhớ. Tuần sau nhóm sẽ chạy thêm cấu hình lưu cả lượt trợ lý để đo phần chênh.

**"Số này có dùng để kết luận được chưa?"**
Chưa. Ba lý do. Một, mới một trăm hai mươi lăm trên một trăm năm mươi câu, và ba loại chưa chạy
đủ. Hai, nhóm câu từ chối mới có một câu. Ba, chưa có hệ APEX-MEM để đối chứng, mà baseline đứng
một mình thì không nói lên điều gì.

**"Sao chậm thế, ba mươi ba phút một câu?"**
Vì mỗi câu LightMem phải dựng lại toàn bộ bộ nhớ từ kho hội thoại riêng của câu đó, chia thành
hàng trăm chủ đề, mỗi chủ đề một lời gọi LLM trở lên. Đây là đặc tính của LightMem trên dữ liệu
hội thoại dài, không phải do máy yếu hay code chậm. Nút thắt là độ trễ gọi API.

**"Tại sao tin được kết luận truy xuất không phải nút thắt?"**
Vì phép đo dựa trên dữ liệu có sẵn của benchmark, không phải phán đoán: mỗi ký ức có mốc thời
gian phiên, benchmark có danh sách phiên chứa bằng chứng, khớp hai thứ đó lại. Nhưng em xin nhắc
lại giới hạn: phép đo này chỉ chứng minh lấy đúng *phiên*, chưa chứng minh giữ được đúng *chi
tiết*.
