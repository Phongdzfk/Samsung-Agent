# Kết quả baseline LightMem và so sánh với APEX-MEM trên LongMemEval-S

**Trạng thái:** cả hai hệ đã chạy đủ **150/150 câu tập dev**. Tập test 350 câu vẫn khóa đến tuần 7.
**Cập nhật:** 01/10/2026.

Tài liệu ghi lại cách chạy, số liệu, những gì kiểm chứng được và giới hạn của từng phép đo. Slide
tóm tắt cùng nội dung nằm ở `bao-cao-lightmem-baseline.pptx`; số liệu thô nằm trong `results/`.

---

## 1. Thiết lập

| Hạng mục | Giá trị (cả hai hệ, trừ khi ghi khác) |
|---|---|
| Dữ liệu | LongMemEval-S, 500 câu, mỗi câu một haystack khoảng 115K token |
| Chia tập | Dev 150 / test 350, phân tầng theo loại câu hỏi, seed 42 |
| Model trả lời và trích xuất | `cx/gpt-5.6-luna` qua 9router |
| Model chấm | `cx/gpt-5.6-terra`, khác model trả lời |
| Prompt chấm | Nguyên văn prompt chính thức của LongMemEval, tách theo loại câu hỏi |
| Số lần chấm | 1 lần (kế hoạch là 3 lần, xem mục 9) |
| LightMem | Cấu hình gốc của bài báo: top-20 ký ức, MiniLM, `messages_use = user_only` |
| APEX-MEM | Đồ thị SQLite, agent ReAct tối đa 20 bước, BGE-M3, lưu cả lượt trợ lý |

**Sai lệch so với kế hoạch:** kế hoạch ghi dùng GPT-5.5, nhưng tài khoản nối vào 9router không có
quyền model đó (lỗi 404), nên cả hai hệ chạy bằng `gpt-5.6-luna`.

**Chia dev/test đã đối chiếu:** `data/split.json` được sinh lại bằng đúng đoạn mã trong notebook
khảo sát của nhóm, và đã so khớp 100% với file gốc xuất ra từ Kaggle.

**Tính hợp lệ của phép so sánh:** báo cáo của APEX-MEM xác nhận mô hình thực sự phục vụ là
3.998 lời gọi `gpt-5.6-luna` và 150 lời gọi `gpt-5.6-terra` (một lần chấm mỗi câu), không có model
nào bị 9router đổi lén. Phía LightMem, mỗi file kết quả ghi tên model yêu cầu.

---

## 2. Độ chính xác trên 150 câu

| Loại câu hỏi | n | APEX-MEM | LightMem |
|---|---|---|---|
| Đơn phiên · người dùng | 21 | 20 (95,2%) | **21 (100%)** |
| Đơn phiên · trợ lý | 17 | **14 (82,4%)** | 7 (41,2%) |
| Đơn phiên · sở thích | 9 | 7 (77,8%) | 7 (77,8%) |
| Đa phiên | 40 | 32 (80,0%) | 33 (82,5%) |
| Suy luận thời gian | 40 | 34 (85,0%) | 34 (85,0%) |
| Cập nhật kiến thức | 23 | 20 (87,0%) | 20 (87,0%) |
| **Gộp chung (micro)** | **150** | **127 (84,7%)** | **122 (81,3%)** |
| **Trung bình theo loại (macro)** | | **84,6%** | **78,9%** |

Khoảng tin cậy 95% (Wilson) của tỉ lệ gộp chung: APEX-MEM 78–90%, LightMem 74–87%. Hai khoảng
chồng lên nhau gần hết.

Nhóm câu từ chối `_abs` chỉ có **4 câu** (APEX-MEM đúng 3, LightMem đúng 2), quá ít để nói về năng
lực biết từ chối.

Báo cáo dùng trung bình theo loại bên cạnh số gộp chung vì số câu giữa các loại chênh nhau nhiều
(9 đến 40 câu), gộp chung sẽ để loại đông câu lấn át.

---

## 3. Phát hiện 1: hai hệ chưa khác biệt rõ

Kiểm định trên cặp câu hỏi (cùng 150 câu, hai hệ):

| | Số câu |
|---|---|
| Cả hai đúng | 107 |
| Chỉ APEX-MEM đúng | 20 |
| Chỉ LightMem đúng | 15 |
| Cả hai sai | 8 |

Kiểm định McNemar chính xác hai phía cho p = **0,50**. Tức là không có bằng chứng thống kê rằng
một hệ tốt hơn hệ kia trên tập dev này.

---

## 4. Phát hiện 2: toàn bộ chênh lệch nằm ở một loại câu hỏi

Chênh lệch gộp chung là +5 câu cho APEX-MEM. Tách theo loại:

| | APEX-MEM | LightMem | Chênh |
|---|---|---|---|
| Loại lượt trợ lý (17 câu) | 14 | 7 | **+7** |
| Năm loại còn lại (133 câu) | 113 (85,0%) | 115 (86,5%) | **−2** |

Nghĩa là toàn bộ lợi thế của APEX-MEM đến từ loại câu hỏi về lời trợ lý, và ở năm loại còn lại
LightMem hơn nhẹ (không có ý nghĩa thống kê).

**Nguyên nhân nghi ngờ là cấu hình, chưa phải đồ thị.** LightMem mặc định `messages_use =
"user_only"`, tức chỉ lượt của người dùng được lưu. APEX-MEM lưu cả lượt trợ lý
(`include_assistant: true`). Loại câu hỏi này hỏi đúng về những gì trợ lý đã nói ("trước đây bạn
gợi ý trang web nào").

Bằng chứng ủng hộ giả thuyết: trong 10 câu LightMem sai ở loại này, **6 câu hệ trả lời thẳng là
không tìm thấy thông tin trong bộ nhớ**; 4 câu còn lại hệ đưa ra đáp án sai một cách tự tin.

**Giả thuyết này chưa được kiểm chứng.** Muốn kiểm chứng phải chạy lại LightMem loại này với
`messages_use = "user_assistant"`. Khi đó số liệu không còn so được với bài báo gốc nên phải báo cả
hai cấu hình. Lệnh chạy: `run_lightmem.py --qtype single-session-assistant --messages-use
user_assistant --out results/assistant-user-assistant` (17 câu).

---

## 5. Phát hiện 3: truy xuất gần như không sai ở cả hai hệ

**LightMem.** Mỗi ký ức trả về mở đầu bằng mốc thời gian của phiên chứa nó (ví dụ
`2023-05-22T23:10:00.000 Mon`). Bộ dữ liệu cho ngày của từng phiên (`haystack_dates`), id phiên
(`haystack_session_ids`) và phiên nào chứa bằng chứng (`answer_session_ids`). Khớp mốc thời gian
cho biết ký ức đến từ phiên nào.

| Chỉ số (LightMem) | Giá trị |
|---|---|
| Câu có ít nhất một ký ức đến từ phiên chứa bằng chứng | 149/150 (99,3%) |
| Trong 28 câu sai: đã truy xuất được bằng chứng | 27 |
| Trong 28 câu sai: không truy xuất được | 1 |

**Giới hạn:** có **2 câu** trong đó phiên chứa bằng chứng trùng mốc thời gian với một phiên khác,
nên việc khớp không chắc chắn. Và "trúng phiên" không đồng nghĩa với "giữ được chi tiết cần
thiết", vì LightMem nén và tóm tắt trước khi lưu.

**APEX-MEM** (số do chính hệ đo, từ nhãn `answer_session_ids`): recall bộ lọc phiên 98,5%, recall
phiên mà công cụ của agent chạm tới 99,6%, 98,0% số câu có ít nhất một fact từ đúng lượt chứa đáp
án. Hai thước đo này khác thước đo của LightMem nên không đặt cạnh nhau như cùng một chỉ số.

**Kết luận:** ở cả hai hệ, phần lớn câu sai là câu đã có bằng chứng trong tay mà vẫn trả lời sai.
Nghĩa là lỗi nằm ở trích xuất (mất chi tiết) hoặc suy luận (đếm, tính ngày), không phải ở khâu tìm
kiếm. Phép đo hiện tại chưa tách được hai loại lỗi đó.

Ví dụ có lỗi suy luận thật: một câu hỏi khoảng cách giữa hai ngày, LightMem nêu đúng cả hai mốc
22/03/2023 và 15/04/2023 nhưng tính ra 18 ngày trong khi thực tế là 24 ngày.

APEX-MEM phân loại 23 câu sai của mình: 21 `reasoning`, 1 `abstention_fail`, 1 `filtered_out`.

---

## 6. Phân bố lỗi của LightMem

28 câu sai trong 150 câu:

| Loại | Số câu sai |
|---|---|
| Đơn phiên · trợ lý | 10 |
| Đa phiên | 7 |
| Suy luận thời gian | 6 |
| Cập nhật kiến thức | 3 |
| Đơn phiên · sở thích | 2 |

Hai kiểu lỗi chiếm đa số:

1. **Câu hỏi về lời trợ lý** (10 câu): đã giải thích ở mục 4.
2. **Câu đếm qua nhiều phiên** (đa phiên, hầu hết dạng "bao nhiêu…"): hệ đếm thiếu hoặc thừa. Ví
   dụ đáp án là 4 loại ẩm thực, hệ trả lời 6; đáp án là 23 bài viết, hệ trả lời 25.

---

## 7. Độ tin cậy của model chấm

Toàn bộ con số accuracy phụ thuộc vào model chấm, nên nhóm soi tay các kết quả của LightMem.

| Mẫu soi | Số câu | Kết quả |
|---|---|---|
| Câu được chấm **đúng** (chọn ngẫu nhiên, seed 7) | 20 | 0 câu được cho điểm oan |
| Câu bị chấm **sai** (soi toàn bộ) | 28 | 2 câu nhóm cho rằng đáng lẽ nên tính đúng |

Hai câu đáng ngờ:

- **Câu sở thích về hắt hơi.** Đáp án gốc là một rubric yêu cầu câu trả lời xét tới con mèo và việc
  nó rụng lông. Hệ trả lời "Your cat sheds heavily, so the living room may contain cat hair and
  dander…", tức đã đáp ứng rubric, nhưng vẫn bị chấm sai.
- **Câu tính ngày ra mắt website.** Đáp án gốc "19 days ago". Hệ nêu đúng "19 days before" nhưng
  nói thêm "43 days ago" ở cuối, nên có thể bị hiểu là đáp án cuối cùng là 43. Trường hợp mập mờ.

**Kết luận:** model chấm không cho điểm oan, nhưng hơi khắt khe. Accuracy thật của LightMem có thể
cao hơn khoảng 1,3 điểm (2/150).

**Giới hạn:** mới soi kết quả của LightMem. Kết quả của APEX-MEM chưa được soi tay độc lập (deck
tuần 4 của nhóm có đối chiếu bằng một model chấm khác, trùng 20/20 trên 20 câu). Vì cùng một model
chấm cho cả hai hệ nên sai lệch này nhiều khả năng ảnh hưởng hai bên tương tự, nhưng chưa kiểm chứng.

Chi tiết nằm trong `report/manual_review.json`. File đó là kết quả **soi tay**, chạy lại hoặc thêm
câu thì phải soi lại.

---

## 8. Chi phí và thời gian

| Mỗi câu hỏi | LightMem | APEX-MEM |
|---|---|---|
| Dựng bộ nhớ, trung vị | 33 phút | 7,1 phút |
| Dựng bộ nhớ, p95 | 57 phút | 23,1 phút |
| Trả lời, trung vị | 3,3 giây | 33,2 giây |
| Lời gọi LLM khi dựng | chưa ghi | 22,4 |
| Token khi dựng | chưa ghi | 89.172 (88,1% tổng) |
| Token khi trả lời | chưa ghi | 12.036 |

**Không dùng bảng này để kết luận hệ nào nhanh hơn.** Thời gian đo khi chạy song song với số luồng
khác nhau (LightMem 3–9 luồng, APEX-MEM 2–8 luồng) và bị hạn mức tài khoản làm chậm, nên chỉ để
tham khảo.

**LightMem chưa có số token và số lời gọi LLM:** script không ghi lại, và 9router chèn thêm khoảng
2.500 token vào mỗi lời gọi nên số đếm qua router bị phình. Muốn so trục chi phí này phải sửa script
LightMem để ghi lại rồi chạy lại.

Ở APEX-MEM, bước dựng chiếm 88,1% token, trong đó trích xuất chiếm 67,8% và giải quyết thực thể
chiếm 32,2% token dựng (đo trên 63 câu đầu).

---

## 9. Hạn mức tài khoản: rủi ro lớn nhất cho tuần 7

Trong lúc chạy, các tài khoản ChatGPT nối vào 9router (đều là gói **free**) lần lượt bị giới hạn:

- 6 tài khoản hết hạn mức (lỗi 429) gần như cùng lúc khi chạy 8 luồng song song.
- 2 tài khoản bị thu hồi token OAuth (lỗi 401 `token_revoked`) trong vòng 5 phút sau đó.
- Khi cả hai hệ cùng dừng, không còn tài khoản nào dùng được, và lần đăng nhập lại báo "Token
  invalid or revoked".

Nguyên nhân thu hồi token chưa xác định được (có thể do đăng nhập nơi khác, hoặc do nhà cung cấp chặn
sau khi dùng nặng và song song). Việc dùng nhiều tài khoản miễn phí để vượt hạn mức cũng có nguy cơ
vi phạm điều khoản sử dụng.

**Hệ quả cho kế hoạch:** tập dev 150 câu đã gần như cạn hạn mức. Tập test lớn hơn gấp hơn hai lần,
và phải chạy cho cả hai hệ. Đây là việc cần chốt với mentor trước tuần 7: chạy toàn bộ 350 câu hay
chỉ một mẫu con có phân tầng, và dùng nguồn LLM nào.

---

## 10. Sự cố kỹ thuật đã gặp

| Sự cố | Nguyên nhân | Cách xử lý |
|---|---|---|
| Script gốc không chạy | Dùng cú pháp f-string của Python 3.12, môi trường là 3.11 | Viết script bọc ngoài, không sửa mã gốc |
| Lỗi "meta tensor" khi chạy song song | Nhiều luồng cùng gọi `from_pretrained`, đụng cơ chế nạp model của accelerate | Khóa phần nạp model, mỗi luồng nạp một lần |
| Cạn RAM sau vài giờ | Mỗi câu nạp lại model mới, bản cũ không được giải phóng kịp | Cache model theo luồng, dọn bộ nhớ sau mỗi câu |
| Windows chặn Python | Smart App Control chặn file thực thi chưa ký số | Bật/tắt lại Smart App Control |
| Hết hạn mức (429), rồi token bị thu hồi (401) | Tài khoản gói free, chạy 8 luồng | Giảm số luồng, đăng nhập lại từ đầu, chờ hạn mức |
| 9router tắt giữa chừng | Chưa xác định chắc (nghi máy ngủ hoặc tiến trình bị đóng) | Chạy 9router trong terminal riêng; chạy lại lệnh cũ để tiếp tục |

---

## 11. Việc còn lại

1. Chạy lại LightMem loại lượt trợ lý (17 câu) với `messages_use = user_assistant` để kiểm chứng
   giả thuyết ở mục 4. Đây là việc quan trọng nhất để phép so sánh công bằng.
2. Chấm 3 lần lấy trung bình cho cả hai hệ, đúng kế hoạch đánh giá (hiện mới chấm 1 lần).
3. Soi 35 câu hai hệ trả lời khác nhau (20 chỉ APEX-MEM đúng, 15 chỉ LightMem đúng) để biết mỗi hệ
   mạnh ở đâu. Danh sách nằm trong `report/compare.json`.
4. Sửa script LightMem để ghi số token và số lời gọi, nếu muốn so trục chi phí.
5. Chốt với mentor về khối lượng chạy tập test ở tuần 7 (mục 9).
