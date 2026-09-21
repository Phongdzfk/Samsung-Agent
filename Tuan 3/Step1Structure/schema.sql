-- ltm/store/schema.sql — SỔ CÁI (ledger), nguồn sự thật duy nhất của hệ bộ nhớ.
--
-- Nguyên tắc 2 của bản thiết kế: Chroma và BM25 là chỉ mục DẪN XUẤT.
-- Xóa toàn bộ chỉ mục rồi dựng lại từ file DB này phải ra kết quả y hệt.
-- Vì vậy: không có trường nào chỉ tồn tại ở Chroma mà không có ở đây.
--
-- Quy ước:
--   * Mọi mốc thời gian là chuỗi ISO-8601 UTC, ví dụ '2026-09-21T03:04:05Z'.
--     SQLite không có kiểu DATETIME; lưu TEXT thì so sánh chuỗi = so sánh thời gian.
--   * `attribute` luôn tiếng Anh snake_case. SQLite không có regex nên ràng buộc
--     thật nằm ở ledger.py (_ATTR_RE); ở đây chỉ chặn NULL và chuỗi rỗng.
--   * `seq` tăng đơn điệu TOÀN CỤC, cấp phát trong transaction (bảng `counter`).
--     Toàn cục chứ không theo slot, để còn so được độ mới giữa hai slot khác nhau
--     khi làm suy luận thời gian ở tuần 5.
--
-- File này chỉ chứa DDL. Các PRAGMA theo-kết-nối (foreign_keys, WAL, busy_timeout)
-- được bật trong ledger.py — bật ở đây không có tác dụng cho các kết nối sau.

-- ---------------------------------------------------------------------------
-- 1. Bộ cấp phát seq
-- ---------------------------------------------------------------------------
-- Vì sao không dùng `SELECT max(seq)+1`: hai tiến trình eval chạy song song sẽ
-- đọc cùng một max và cấp trùng seq. UPDATE ... RETURNING là một thao tác
-- nguyên tử, không có khe hở đó. (Cần SQLite >= 3.35; Python 3.11 đạt.)
CREATE TABLE IF NOT EXISTS counter (
  name  TEXT PRIMARY KEY,
  value INTEGER NOT NULL
);
INSERT OR IGNORE INTO counter(name, value) VALUES ('seq', 0);

-- ---------------------------------------------------------------------------
-- 2. Ký ức
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS memory (
  id            INTEGER PRIMARY KEY,

  -- Nhận dạng slot: (subject, attribute) -> value
  subject       TEXT NOT NULL CHECK (length(subject)   > 0),
  attribute     TEXT NOT NULL CHECK (length(attribute) > 0),
  value         TEXT,
  value_canon   TEXT,                       -- giá trị đã chuẩn hóa (mục 3.3)

  -- Văn bản song ngữ
  text          TEXT NOT NULL,              -- nguyên văn, giữ ngôn ngữ gốc
  text_canon    TEXT NOT NULL,              -- bản tiếng Anh — ĐÂY là thứ được nhúng
  lang          TEXT NOT NULL CHECK (lang IN ('vi', 'en')),

  -- Độ mới
  seq           INTEGER NOT NULL UNIQUE,
  status        TEXT NOT NULL DEFAULT 'active'
                  CHECK (status IN ('active', 'pending', 'superseded', 'deleted')),
  superseded_by INTEGER REFERENCES memory(id) ON DELETE SET NULL,

  -- Thời gian (tuần 5 mới khai thác, tuần 3 cứ ghi cho đủ)
  valid_from     TEXT,
  invalidated_at TEXT,
  event_time     TEXT,

  -- Phân loại
  memory_type   TEXT NOT NULL DEFAULT 'semantic'
                  CHECK (memory_type IN ('semantic', 'preference', 'episodic', 'procedural')),
  pinned        INTEGER NOT NULL DEFAULT 0 CHECK (pinned IN (0, 1)),

  -- Nguồn gốc (mục 6) — cổng chặn ảo giác tự củng cố
  speaker       TEXT NOT NULL CHECK (speaker IN ('user', 'assistant')),
  confirmed     INTEGER NOT NULL DEFAULT 0 CHECK (confirmed IN (0, 1)),
  needs_review  INTEGER NOT NULL DEFAULT 0 CHECK (needs_review IN (0, 1)),

  -- Truy vết
  session_id    TEXT NOT NULL,
  turn_id       TEXT NOT NULL,
  source_text   TEXT,                       -- lượt gốc. KHÔNG nhúng, chỉ để debug.
  created_at    TEXT NOT NULL,

  -- Bất biến: một bản đã bị thay thế thì phải trỏ tới bản thay nó, và ngược lại.
  CHECK ((status = 'superseded') = (superseded_by IS NOT NULL))
);

-- Chỉ mục phục vụ truy vấn nóng nhất: "bản mới nhất còn hiệu lực của slot này".
CREATE INDEX IF NOT EXISTS ix_memory_slot
  ON memory (subject, attribute, status, seq DESC);

CREATE INDEX IF NOT EXISTS ix_memory_session ON memory (session_id, turn_id);
CREATE INDEX IF NOT EXISTS ix_memory_pinned  ON memory (pinned) WHERE pinned = 1;

-- ---------------------------------------------------------------------------
-- 3. Nhật ký vết
-- ---------------------------------------------------------------------------
-- Mỗi lượt ghi một dòng JSON. Không có bảng này thì tuần 7 không trả lời được
-- câu "vì sao câu 47 sai" — mà đó mới là phần đáng viết trong báo cáo.
CREATE TABLE IF NOT EXISTS trace (
  id         INTEGER PRIMARY KEY,
  ts         TEXT NOT NULL,
  kind       TEXT NOT NULL,          -- 'ingest' | 'retrieve' | 'answer' | 'extract_reject' | ...
  session_id TEXT,
  turn_id    TEXT,
  payload    TEXT NOT NULL,          -- JSON

  -- Cột sinh: rút sẵn con số hay tra nhất ra khỏi JSON, không tốn chỗ lưu.
  total_ms   REAL GENERATED ALWAYS AS (json_extract(payload, '$.latency_ms.total')) VIRTUAL
);

CREATE INDEX IF NOT EXISTS ix_trace_kind    ON trace (kind, ts);
CREATE INDEX IF NOT EXISTS ix_trace_session ON trace (session_id, turn_id);
