-- Lược đồ bộ nhớ theo APEX-MEM (Banerjee et al., ACL 2026, §3–4).
-- Tên 7 bảng theo bài báo; cột là thiết kế của nhóm từ định nghĩa hình thức ở §3.1.
-- PRAGMA foreign_keys KHÔNG đặt ở đây: nó mặc định tắt và phải bật cho TỪNG kết nối
-- (xem GraphDB._configure).

-- ---------- 1. Lượt hội thoại gốc ----------
CREATE TABLE IF NOT EXISTS turns (
    turn_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT    NOT NULL,
    turn_index   INTEGER NOT NULL,
    speaker      TEXT    NOT NULL CHECK (speaker IN ('user', 'assistant')),
    text         TEXT    NOT NULL,
    session_date TEXT    NOT NULL,            -- ISO 8601, đã chuẩn hóa
    UNIQUE (session_id, turn_index)
);

-- ---------- 2. Thực thể ----------
CREATE TABLE IF NOT EXISTS entities (
    entity_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,
    type         TEXT NOT NULL,               -- lớp ontology, kiểm tra ở tầng Python
    role         TEXT NOT NULL CHECK (role IN ('Speaker', 'Listener', 'Agent', 'Mentioned')),
    aliases_json TEXT NOT NULL DEFAULT '[]'
);

-- ---------- 3. Thuộc tính ----------
CREATE TABLE IF NOT EXISTS properties (
    property_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE
                CHECK (name GLOB '[a-z]*' AND NOT name GLOB '*[^a-z0-9_]*'),
    dtype       TEXT NOT NULL
                CHECK (dtype IN ('str','int','float','bool','date','datetime','enum','url','list'))
);

-- ---------- 4. Sự kiện ----------
CREATE TABLE IF NOT EXISTS events (
    event_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    type            TEXT NOT NULL,
    anchor_datetime TEXT NOT NULL,            -- ISO 8601
    location        TEXT,
    session_id      TEXT
);

-- ---------- 5. Người tham gia sự kiện ----------
CREATE TABLE IF NOT EXISTS event_participants (
    event_id  INTEGER NOT NULL REFERENCES events(event_id),
    entity_id INTEGER NOT NULL REFERENCES entities(entity_id),
    PRIMARY KEY (event_id, entity_id)
);

-- ---------- 6. Fact: (chủ thể, thuộc tính, giá trị) + khoảng hiệu lực ----------
CREATE TABLE IF NOT EXISTS facts (
    fact_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id  INTEGER NOT NULL REFERENCES entities(entity_id),
    property_id INTEGER NOT NULL REFERENCES properties(property_id),
    value_json  TEXT    NOT NULL,
    dtype       TEXT    NOT NULL,
    t_from      TEXT,
    t_to        TEXT,
    confidence  REAL    NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    event_id    INTEGER NOT NULL REFERENCES events(event_id),
    created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now')),
    CHECK (t_from IS NULL OR t_to IS NULL OR julianday(t_from) <= julianday(t_to))
);

-- ---------- 7. Bằng chứng: nối fact về đúng lượt gốc ----------
CREATE TABLE IF NOT EXISTS evidence (
    evidence_id INTEGER PRIMARY KEY AUTOINCREMENT,
    fact_id     INTEGER NOT NULL REFERENCES facts(fact_id),
    event_id    INTEGER NOT NULL REFERENCES events(event_id),
    turn_id     INTEGER NOT NULL REFERENCES turns(turn_id),
    span        TEXT
);

CREATE INDEX IF NOT EXISTS ix_facts_subject_prop ON facts(subject_id, property_id);
CREATE INDEX IF NOT EXISTS ix_evidence_fact     ON evidence(fact_id);
CREATE INDEX IF NOT EXISTS ix_evidence_turn     ON evidence(turn_id);
CREATE INDEX IF NOT EXISTS ix_events_anchor     ON events(anchor_datetime);
CREATE INDEX IF NOT EXISTS ix_turns_session     ON turns(session_id);

-- ---------- Append-only: chặn UPDATE/DELETE ngay trong DB ----------
-- entities là ngoại lệ: aliases được bổ sung khi giải quyết thực thể.
CREATE TRIGGER IF NOT EXISTS ao_facts_upd  BEFORE UPDATE ON facts  BEGIN SELECT RAISE(ABORT, 'append_only: facts'); END;
CREATE TRIGGER IF NOT EXISTS ao_facts_del  BEFORE DELETE ON facts  BEGIN SELECT RAISE(ABORT, 'append_only: facts'); END;
CREATE TRIGGER IF NOT EXISTS ao_evid_upd   BEFORE UPDATE ON evidence BEGIN SELECT RAISE(ABORT, 'append_only: evidence'); END;
CREATE TRIGGER IF NOT EXISTS ao_evid_del   BEFORE DELETE ON evidence BEGIN SELECT RAISE(ABORT, 'append_only: evidence'); END;
CREATE TRIGGER IF NOT EXISTS ao_events_upd BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT, 'append_only: events'); END;
CREATE TRIGGER IF NOT EXISTS ao_events_del BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT, 'append_only: events'); END;
CREATE TRIGGER IF NOT EXISTS ao_turns_upd  BEFORE UPDATE ON turns  BEGIN SELECT RAISE(ABORT, 'append_only: turns'); END;
CREATE TRIGGER IF NOT EXISTS ao_turns_del  BEFORE DELETE ON turns  BEGIN SELECT RAISE(ABORT, 'append_only: turns'); END;

-- ---------- Chỉ mục từ khóa (FTS5), rowid = id của bảng gốc ----------
CREATE VIRTUAL TABLE IF NOT EXISTS turns_fts    USING fts5(text, tokenize = 'unicode61 remove_diacritics 2');
CREATE VIRTUAL TABLE IF NOT EXISTS entities_fts USING fts5(name, aliases, tokenize = 'unicode61 remove_diacritics 2');
CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts    USING fts5(content, tokenize = 'unicode61 remove_diacritics 2');

-- ---------- Nhật ký vết (không thuộc đồ thị, GraphSQL không đọc được) ----------
CREATE TABLE IF NOT EXISTS trace (
    trace_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    kind         TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now'))
);