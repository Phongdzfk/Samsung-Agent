1. Mạch câu chuyện cốt lõi (nắm được cái này là nắm được đề tài)
Vấn đề gốc: LLM về bản chất là stateless — mỗi lần gọi API là một lần "mất trí nhớ". Thứ duy nhất mô hình "thấy" là context window (cửa sổ ngữ cảnh): số token tối đa đưa vào mỗi lần. Cửa sổ này hữu hạn và tính tiền theo token, nên không thể nhồi toàn bộ lịch sử nhiều tháng vào prompt.
Ý tưởng giải quyết: Tách bộ nhớ thành hai tầng:
Ngắn hạn = context window (có sẵn).
Dài hạn = lưu ra ngoài (database), rồi mỗi lượt hội thoại chỉ truy xuất đúng mẩu ký ức liên quan và chèn vào prompt.
Kỹ thuật để làm việc "truy xuất theo nghĩa" đó chính là RAG (Retrieval-Augmented Generation), dựa trên embedding (biến câu chữ thành vector; câu gần nghĩa → vector gần nhau) và vector database (kho tìm kiếm theo độ tương đồng).
Điểm mấu chốt để nói với mentor: Đề tài không huấn luyện mô hình mới. Giá trị nằm ở lớp quản lý bộ nhớ bao quanh LLM — nó quyết định nhớ gì, khi nào truy xuất, và cập nhật ra sao.
2. Bốn khái niệm dễ bị hỏi sâu
Embedding vs. token: token là đơn vị chia nhỏ văn bản để mô hình xử lý; embedding là vector số biểu diễn ý nghĩa. Truy xuất ký ức dựa trên khoảng cách giữa các embedding (thường dùng cosine similarity).
RAG khác gì fine-tuning: fine-tuning "nướng" kiến thức vào trọng số mô hình (tốn kém, khó cập nhật); RAG giữ kiến thức bên ngoài, cập nhật/xóa dễ dàng → phù hợp bộ nhớ hội thoại luôn thay đổi.
Phân loại bộ nhớ (khung Tulving từ khoa học nhận thức): Episodic = "chuyện đã xảy ra" (log/tóm tắt hội thoại); Semantic = "sự thật/sở thích" (hồ sơ người dùng); Procedural = "cách làm việc" (chỉ dẫn hệ thống). Trọng tâm đồ án nên là Episodic + Semantic.
Cơ chế cập nhật: ký ức không chỉ thêm mà phải ADD / UPDATE / DELETE (ý tưởng từ Mem0) để tránh mâu thuẫn khi thông tin thay đổi (vd người dùng lên N4).
3. Câu hỏi mentor hay hỏi — chuẩn bị sẵn
"Sao không nhồi hết lịch sử vào context window dài (128k+)?" → Tốn kém tuyến tính theo token, chậm, và mô hình bị "lost in the middle" (bỏ sót thông tin ở giữa ngữ cảnh dài). Truy xuất chọn lọc chính xác và rẻ hơn.
"Đánh giá bằng gì cho khách quan?" → Dùng benchmark chuẩn LoCoMo hoặc LongMemEval, hoặc bộ kịch bản tự xây đo 3 trục: độ chính xác (trả lời đúng?), tính nhất quán (không tự mâu thuẫn?), hiệu năng (độ trễ, chi phí truy xuất).
"Vector search có đủ không?" → Không phải lúc nào cũng đủ với câu hỏi đa bước/theo thời gian → đó là lý do có hướng knowledge graph (Zep, Mem0g). Nêu đây là phần mở rộng.
A. NỘI DUNG CÁC HỆ THỐNG BỘ NHỚ
A1. MemGPT (2023) — ý tưởng "LLM như hệ điều hành"
Vấn đề nó giải: context window hữu hạn, nhưng hội thoại thì vô hạn.
Ý tưởng cốt lõi: mượn nguyên cơ chế bộ nhớ ảo của hệ điều hành. Giống như OS tạo ảo giác có nhiều bộ nhớ hơn thực tế bằng cách đẩy dữ liệu tràn xuống đĩa rồi nạp lại khi cần (page fault), MemGPT cho phép chính LLM quản lý cái gì được đặt vào context của nó.
Kiến trúc 2 tầng:
Main context (= RAM): phần LLM thực sự nhìn thấy. Gồm system instructions, working context (vùng ghi tạm), và một hàng đợi FIFO chứa hội thoại gần đây.
External context (= đĩa): nằm ngoài context window, chia thành recall storage (lịch sử tin nhắn) và archival storage (kho văn bản dài hạn tìm kiếm được).
Điểm hay nhất để học: Agent tự di chuyển dữ liệu giữa hai tầng bằng function call do chính LLM sinh ra — tức là mô hình tự quyết định "cần lục lại ký ức nào", không cần luật cứng. Hệ thống cảnh báo khi context đầy ~70% và buộc dọn ở 100%, sinh một bản tóm tắt đệ quy các tin nhắn bị đẩy ra để không mất trắng thông tin. Beancount
Nhược điểm cần biết: cơ chế nén là "thêm rồi tóm tắt" — tóm tắt chồng tóm tắt, dễ mất chi tiết dần. Và mỗi thao tác bộ nhớ đều tốn một lượt gọi LLM → chậm, tốn tiền.
A2. Mem0 (2025) — bộ nhớ thực dụng, hướng sản phẩm
Vấn đề nó giải: các phương án trước hoặc chưa đủ chính xác, hoặc xây graph quá chậm; mục tiêu của Mem0 là đạt độ chính xác gần mức full-context nhưng với độ trễ dưới một giây và ngân sách token chấp nhận được. GitHub
Pipeline 2 pha — đây là phần bạn nên mô phỏng lại cho đồ án:
Pha 1 — Extraction (khi ghi): Mỗi cặp tin nhắn mới đưa vào, LLM đọc bản tóm tắt hội thoại + m tin nhắn gần nhất (m=10) để rút ra các "fact" ứng viên. GitHub
Pha 2 — Update (khi cập nhật): Lấy top-s ký ức tương đồng nhất (s=10) rồi để LLM dùng tool-call chọn một trong bốn thao tác: ADD / UPDATE / DELETE / NOOP. Đây chính là chỗ giải quyết bài toán xung đột — thông tin cũ bị ghi đè thay vì cứ chất đống lên nhau. GitHub
Biến thể Mem0ᵍ: chuyển fact thành bộ ba (thực thể, quan hệ, thực thể) lưu vào Neo4j; pha trích xuất tách thành entity extractor + relations generator, pha cập nhật thêm conflict detector + update resolver. GitHub
Kết quả (rất đáng trích khi báo cáo):
Trên LOCOMO, Mem0 cao hơn 26% tương đối so với tính năng memory của OpenAI theo điểm LLM-as-a-Judge (66,9% so với 52,9%) Mem0
Giảm 91% độ trễ p95 và tiết kiệm hơn 90% chi phí token arXiv
Về token: Mem0 trung bình ~1,7k token/hội thoại, Mem0ᵍ ~3,6k, trong khi full-context tốn ~26k — chênh khoảng 20 lần GitHub
Mem0 dẫn đầu ở câu hỏi single-hop và multi-hop; Mem0ᵍ mạnh nhất ở nhóm temporal và open-domain GitHub
A3. Zep (2025) — bộ nhớ dạng đồ thị tri thức có thời gian
Ý tưởng: RAG truyền thống chỉ truy xuất tài liệu tĩnh, trong khi ứng dụng thực tế cần tích hợp tri thức động từ hội thoại đang diễn ra và dữ liệu nghiệp vụ. Zep lưu thực thể + quan hệ + dấu thời gian, cho phép truy xuất theo ngữ cảnh thời gian. huggingface
Đánh đổi: mạnh về suy luận thời gian và đa bước, nhưng tốn khoảng 600k token mỗi hội thoại và cần hàng giờ xây dựng nền ở chế độ nền. → Với đồ án 2 tháng, đây là hướng mở rộng, không nên làm trục chính. GitHub
A4. Các hệ khác (biết tên là đủ)
A-MEM (2025): bộ nhớ "agentic" — các mẩu ký ức tự liên kết với nhau. Kho bộ nhớ lớn nên chi phí tìm kiếm cao (p50 ~0,668s, tổng ~1,410s). arXiv
LangMem (LangChain): hỗ trợ ba loại bộ nhớ — episodic, semantic, procedural (agent tự sửa chỉ dẫn của chính nó). Nhưng độ trễ tìm kiếm rất cao (p50 ~18s, p95 ~60s), khó dùng cho ứng dụng tương tác. AtlanarXiv
MemOS (2025): coi bộ nhớ như tài nguyên hệ thống có thể lập lịch, gói trong đơn vị chuẩn "MemCube", có scheduler và lifecycle manager.
A5. Rút ra — mô hình chung của mọi hệ thống
Đọc hết thì thấy tất cả đều quy về 3 giai đoạn (khung này lấy từ LongMemEval, rất tiện để trình bày kiến trúc):
Giai đoạn
Câu hỏi thiết kế
Lựa chọn thực tế
Indexing (ghi)
Lưu gì? Lưu ở dạng nào?
Raw log · tóm tắt phiên · fact rời · bộ ba đồ thị
Retrieval (đọc)
Tìm bằng gì?
Vector similarity · keyword · entity · lọc theo thời gian
Reading (dùng)
Đưa vào prompt ra sao?
Top-k thô · sắp lại theo thời gian · chain-of-note

LongMemEval phân tích các lựa chọn thiết kế theo ba giai đoạn này cùng bốn điểm điều khiển: value, key, query và chiến lược đọc. ResearchGate

B. PHẦN ĐÁNH GIÁ
B1. Ba trục phải đo — không được chỉ đo độ chính xác
Đánh giá một hệ bộ nhớ quy về ba tham số: độ chính xác (benchmark đo), chi phí (số token ngữ cảnh mỗi truy vấn), và hiệu năng (độ trễ). Tối ưu một cái thì dễ, cân bằng cả ba mới là bài toán thật. Mem0
Đây chính là điểm khớp với tiêu chí đề tài của bạn ("độ chính xác, tính nhất quán và hiệu năng"). Bảng đo đề xuất:
Trục
Chỉ số cụ thể
Độ chính xác
Tỉ lệ trả lời đúng theo từng loại câu hỏi; F1; LLM-as-a-Judge
Tính nhất quán
Tỉ lệ dùng đúng fact mới sau khi cập nhật; tỉ lệ tự mâu thuẫn; tỉ lệ biết từ chối khi không có dữ liệu
Hiệu năng
Độ trễ p50/p95 (tách riêng: pha tìm kiếm vs. tổng); token/truy vấn; kích thước kho bộ nhớ

Lưu ý cách đo độ trễ trong paper Mem0: tách riêng thời gian tìm kiếm và thời gian tổng, và báo cả p50 lẫn p95 (p95 mới lộ ra trường hợp xấu). Nhóm bạn nên bắt chước cách này.
B2. Hai benchmark chuẩn
LoCoMo (ACL 2024)
Sinh bằng pipeline máy–người: mỗi nhân vật ảo có persona và một đồ thị sự kiện đời sống có quan hệ nhân quả, sau đó người thật kiểm tra và chỉnh sửa để đảm bảo nhất quán dài hạn Emergent Mind
Quy mô: 50 hội thoại, mỗi cái tới 35 phiên, trung bình ~300 lượt, kèm khoảng 200 cặp hỏi-đáp arxiv
Câu hỏi chia 5 loại: single-hop, multi-hop, temporal reasoning, open-domain, và adversarial Emergent Mind
Thông lệ chung là bỏ nhóm adversarial khi so sánh, theo cách làm của Mem0 và A-MEM arxiv
Ngoài QA còn có nhiệm vụ tóm tắt sự kiện và sinh hội thoại đa phương thức — hai cái này bạn có thể bỏ qua Emergent Mind
LongMemEval (ICLR 2025)
500 câu hỏi được cài vào lịch sử hội thoại có thể co giãn độ dài tùy ý arXiv
Đo 5 năng lực: trích xuất thông tin, suy luận đa phiên, suy luận thời gian, cập nhật kiến thức, và biết từ chối (abstention) arXiv
Bản LongMemEval-S: ~500 câu, mỗi câu kèm lịch sử ~115K token; bản M lên tới 500 phiên, khoảng 1,5 triệu token arXiv
Chọn cái nào? LoCoMo dễ chạy hơn, thiên về chiều sâu suy luận. LongMemEval khắt khe hơn về cập nhật và nhất quán — chính là điểm yếu mà đồ án bạn muốn giải. Gợi ý: chạy LoCoMo làm chính, mượn khung 5 năng lực của LongMemEval để tự thiết kế bộ test tiếng Việt.
B3. Ba con số đắt giá để mở đầu buổi báo cáo
Trợ lý thương mại và LLM ngữ cảnh dài đều tụt khoảng 30% độ chính xác khi phải nhớ thông tin qua tương tác kéo dài → chứng minh vấn đề là thật. arXiv
Trong bài LongMemEval, các LLM ngữ cảnh dài giảm 30–60% hiệu năng khi phải đọc toàn bộ lịch sử; và lịch sử ở đó mới chỉ ~50 phiên, càng dài thì càng tệ hơn → chứng minh "cứ nhồi hết vào context" không phải lời giải. arXiv
Mem0 giảm 91% độ trễ p95 và trên 90% chi phí token → chứng minh bộ nhớ chọn lọc là lời giải đúng hướng. arXiv
Ba con số này ghép lại thành đúng mạch lập luận của đề tài: vấn đề có thật → giải pháp ngây thơ không đủ → cần lớp bộ nhớ có chọn lọc.
B4. Cảnh báo về đánh giá (nên nói ra để ghi điểm với mentor)
Các benchmark nhỏ như LoCoMo và LongMemEval có thể được cải thiện đáng kể chỉ bằng chiến lược truy xuất mạnh tay, context window lớn hơn, hoặc mô hình mạnh hơn — điều đó không có nghĩa là hệ thống bộ nhớ đã tốt lên. Vì vậy nhóm nên cố định điều kiện thí nghiệm (cùng LLM, cùng ngân sách token, cùng k) khi so sánh các cấu hình bộ nhớ với nhau. Đây là lỗi rất phổ biến trong đồ án sinh viên. Mem0
Ngoài ra, có kết quả đánh giá độc lập cho Mem0 khoảng 49,0% trên LongMemEval, thấp hơn nhiều so với các hệ chuyên biệt khác, và kết quả LOCOMO do chính họ công bố cũng bị đối thủ phản bác. → Khi trích số liệu, nên nói rõ "theo công bố của tác giả", đừng coi là chân lý.

