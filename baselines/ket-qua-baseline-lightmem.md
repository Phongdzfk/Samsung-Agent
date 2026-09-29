# Kết quả baseline LightMem trên LongMemEval-S

**Trạng thái:** số liệu sơ bộ trên 125/150 câu tập dev. Tập test 350 câu vẫn khóa đến tuần 7.
**Cập nhật:** 29/09/2026.

Tài liệu này ghi lại cách chạy, số liệu, và những gì kiểm chứng được. Slide tóm tắt cùng nội
dung nằm ở `bao-cao-lightmem-baseline.pptx`.

---

## 1. Thiết lập

| Hạng mục | Giá trị |
|---|---|
| Dữ liệu | LongMemEval-S, 500 câu, mỗi câu một haystack khoảng 115K token |
| Chia tập | Dev 150 / test 350, phân tầng theo loại câu hỏi, seed 42 |
| LLM trích xuất và trả lời | `cx/gpt-5.6-luna` qua 9router |
| Model chấm | `cx/gpt-5.6-terra`, khác model trả lời |
| Prompt chấm | Nguyên văn prompt chính thức của LongMemEval, tách theo loại câu hỏi |
| Truy xuất | Top-20 ký ức, embedding all-MiniLM-L6-v2, Qdrant |
| Cấu hình LightMem | Nguyên bản từ `experiments/longmemeval/run_lightmem_gpt.py` |

**Một sai lệch so với kế hoạch:** kế hoạch tuần 3 ghi dùng GPT-5.5, nhưng tài khoản nối vào
9router không có quyền model đó (lỗi 404). Nhóm chuyển sang `gpt-5.6-luna`. Hệ APEX-MEM phải
chạy đúng model này thì so sánh mới công bằng.

**Chia dev/test đã đối chiếu:** bản `data/split.json` trong repo được sinh lại bằng đúng đoạn
mã trong notebook khảo sát của nhóm, và đã so khớp 100% với file gốc xuất ra từ Kaggle.

---

## 2. Độ chính xác

| Loại câu hỏi | Đã chạy / tổng dev | Đúng | Accuracy |
|---|---|---|---|
| Đơn phiên · người dùng | 21/21 | 21 | 100% |
| Cập nhật kiến thức | 16/23 | 15 | 93,8% |
| Suy luận thời gian | 30/40 | 26 | 86,7% |
| Đa phiên | 40/40 | 33 | 82,5% |
| Đơn phiên · sở thích | 9/9 | 7 | 77,8% |
| **Đơn phiên · trợ lý** | **9/17** | **3** | **33,3%** |

- **Macro-average (trung bình theo loại): 79,0%**
- Gộp chung 125 câu (micro): 84,0%
- Nhóm câu từ chối `_abs`: mới có 1 câu, trả lời đúng.

Báo cáo dùng macro-average vì số câu giữa các loại chênh nhau nhiều (9 đến 40 câu), gộp chung
sẽ để loại đông câu lấn át.

---

## 3. Phát hiện 1: loại "lượt trợ lý" thấp là do cấu hình, không phải do hệ yếu

33,3% của loại `single-session-assistant` thấp hơn hẳn năm loại còn lại (77,8%–100%). Nguyên
nhân xác định được, không phải suy đoán:

Cấu hình gốc của LightMem đặt `messages_use = "user_only"`, tức **chỉ lượt của người dùng mới
được đưa vào bộ nhớ**. Loại câu hỏi này lại hỏi đúng về những gì trợ lý đã nói ("trước đây bạn
gợi ý trang web nào", "bạn đề xuất chai thứ năm là gì").

Bằng chứng: trong 6 câu sai của loại này, **4 câu hệ trả lời thẳng là không tìm thấy thông tin
trong bộ nhớ** (dạng "I don't have the specific … in the available memories"). Hai câu còn lại
hệ bịa ra đáp án.

**Việc cần làm:** chạy lại LightMem với `messages_use = "user_assistant"` để đo mức cải thiện.
Lưu ý khi đó số liệu không còn so được với bài báo gốc, nên phải báo cáo cả hai cấu hình.

---

## 4. Phát hiện 2: nút thắt không nằm ở khâu tìm kiếm

Đây là phép đo mà kế hoạch tuần 3 yêu cầu — tách lỗi "không tìm thấy" khỏi lỗi "tìm thấy nhưng
suy luận sai".

**Cách đo.** Mỗi ký ức LightMem trả về đều mở đầu bằng mốc thời gian của phiên chứa nó (ví dụ
`2023-05-22T23:10:00.000 Mon`). Bộ dữ liệu cho biết ngày của từng phiên (`haystack_dates`), id
phiên (`haystack_session_ids`) và phiên nào chứa bằng chứng (`answer_session_ids`). Khớp mốc
thời gian là biết ký ức đến từ phiên nào. Trong 125 câu không có trường hợp nào hai phiên trùng
mốc thời gian, nên phép khớp này không nhập nhằng.

**Kết quả.**

| Chỉ số | Giá trị |
|---|---|
| Câu có ít nhất một ký ức đến từ phiên chứa bằng chứng | 124/125 (99,2%) |
| Trong 20 câu sai: đã truy xuất được bằng chứng | 19 |
| Trong 20 câu sai: không truy xuất được bằng chứng | 1 |

Câu duy nhất không truy xuất được thuộc loại lượt trợ lý, tức vẫn quy về nguyên nhân ở mục 3.

**Giới hạn của phép đo này:** "trúng phiên" không đồng nghĩa với "giữ được chi tiết cần thiết".
LightMem nén và tóm tắt trước khi lưu, nên một ký ức đến từ đúng phiên vẫn có thể đã mất chi
tiết cần cho câu trả lời. Vì vậy 19 câu kia là **lỗi trích xuất hoặc lỗi suy luận**, phép đo
hiện tại chưa tách được hai loại đó.

**Ví dụ cho thấy có lỗi suy luận thật:** một câu hỏi khoảng cách giữa hai ngày, hệ nêu đúng cả
hai mốc 22/03/2023 và 15/04/2023 — khớp đáp án gốc — nhưng tính ra 18 ngày trong khi thực tế là
24 ngày. Ký ức lấy đúng, phép trừ ngày sai.

**Ý nghĩa cho hệ APEX-MEM:** trên bộ dữ liệu này, đầu tư thêm vào khâu tìm kiếm gần như không
còn dư địa. Điểm số phụ thuộc vào việc trích xuất giữ được bao nhiêu chi tiết và mô hình suy
luận ra sao.

---

## 5. Phân bố lỗi

20 câu sai trong 125 câu đã chạy:

| Loại | Số câu sai |
|---|---|
| Đa phiên | 7 |
| Đơn phiên · trợ lý | 6 |
| Suy luận thời gian | 4 |
| Đơn phiên · sở thích | 2 |
| Cập nhật kiến thức | 1 |

Hai kiểu lỗi chiếm đa số:

1. **Câu đếm qua nhiều phiên** (7 câu đa phiên, hầu hết dạng "bao nhiêu…"): hệ đếm thiếu hoặc
   thừa. Ví dụ: đáp án 4 loại ẩm thực, hệ trả lời 6; đáp án 23 bài viết, hệ trả lời 25.
2. **Câu hỏi về lời trợ lý** (6 câu): đã giải thích ở mục 3.

---

## 6. Độ tin cậy của model chấm

Toàn bộ con số accuracy phụ thuộc vào model chấm, nên nhóm soi tay để kiểm tra.

| Mẫu soi | Số câu | Kết quả |
|---|---|---|
| Câu được chấm **đúng** (chọn ngẫu nhiên, seed 7) | 12 | 0 câu được cho điểm oan |
| Câu bị chấm **sai** (soi toàn bộ) | 20 | 2 câu nhóm cho rằng đáng lẽ nên tính đúng |

Hai câu đáng ngờ:

- **Câu sở thích về hắt hơi.** Đáp án gốc là một rubric yêu cầu câu trả lời phải xét tới con mèo
  và việc nó rụng lông. Hệ trả lời "Your cat sheds heavily, so the living room may contain cat
  hair and dander…", tức đã đáp ứng rubric, nhưng vẫn bị chấm sai.
- **Câu tính ngày ra mắt website.** Đáp án gốc "19 days ago". Hệ trả lời có nêu đúng "19 days
  before", nhưng nói thêm "As of March 25, 2023, that launch was 43 days ago" ở cuối nên có thể
  bị hiểu là đáp án cuối cùng là 43. Trường hợp này thật sự mập mờ.

**Kết luận:** model chấm không cho điểm oan, nhưng hơi khắt khe. Accuracy thật có thể cao hơn
khoảng 1,6 điểm. Cách xử lý: giữ kế hoạch chấm 3 lần lấy trung bình, và dùng đúng một model
chấm cho cả LightMem lẫn APEX-MEM để sai lệch này triệt tiêu khi so sánh.

Chi tiết bản soi tay nằm trong `report/manual_review.json`. File đó là kết quả **soi tay**, chạy
thêm câu thì phải soi lại và cập nhật.

---

## 7. Chi phí và thời gian

| Pha | Thời gian |
|---|---|
| Dựng bộ nhớ mỗi câu | trung vị 33 phút, trung bình 37 phút, chậm nhất 61 phút |
| Truy xuất | 0,18 giây |
| Sinh câu trả lời | 4,1 giây |

Dựng bộ nhớ chiếm gần như toàn bộ thời gian. Lý do: mỗi câu có haystack dài, bị chia thành hàng
trăm topic, mỗi topic lại tốn lời gọi LLM để trích fact và sinh metadata. Một câu tốn hàng trăm
lời gọi LLM.

Chạy 5–9 luồng song song, cả tập dev cần vài chục giờ.

**Chưa đo được số token.** 9router chèn khoảng 2.500 token system prompt vào mỗi lời gọi, nên
token đếm qua router bị phình so với thực tế. Muốn báo cáo trục chi phí token thì phải đo riêng,
trừ phần này ra.

**Rủi ro cho tuần 7:** tài khoản ChatGPT có trần sử dụng và đã chạm giới hạn (lỗi 429) nhiều lần
khi chạy. Với tốc độ 10–14 câu/giờ, chạy 350 câu test tốn khoảng 25–30 giờ cho **mỗi hệ**. Hai
hệ là 50–60 giờ chạy liên tục. Đây là việc cần chốt với mentor: chạy toàn bộ tập test cho
baseline, hay chỉ chạy một mẫu con có phân tầng.

---

## 8. Sự cố kỹ thuật đã gặp

| Sự cố | Nguyên nhân | Cách xử lý |
|---|---|---|
| Script gốc không chạy | Dùng cú pháp f-string của Python 3.12, môi trường là 3.11 | Viết script bọc ngoài, không sửa mã gốc |
| Lỗi "meta tensor" khi chạy song song | Nhiều luồng cùng gọi `from_pretrained`, đụng cơ chế nạp model của accelerate | Khóa phần nạp model, mỗi luồng nạp một lần |
| Cạn RAM sau vài giờ | Mỗi câu nạp lại model mới, bản cũ không được giải phóng kịp | Cache model theo luồng, dọn bộ nhớ sau mỗi câu |
| Windows chặn Python | Smart App Control chặn file thực thi chưa ký số | Bật/tắt lại Smart App Control |
| Lỗi 429 | Hết hạn mức tài khoản | Chờ mở lại hoặc thêm tài khoản |

---

## 9. Việc còn lại

1. Chạy nốt 25 câu dev còn lại (trợ lý 9/17, thời gian 30/40, cập nhật kiến thức 16/23), nhất là
   để có đủ nhóm `_abs`.
2. Chạy hệ APEX-MEM cùng model và cùng model chấm. Hiện baseline chưa có gì để so.
3. Chạy lại LightMem với `messages_use = "user_assistant"` để tách phần thiệt do cấu hình.
4. Chốt với mentor về khối lượng chạy tập test ở tuần 7.
5. Chấm 3 lần lấy trung bình, đúng kế hoạch đánh giá.
