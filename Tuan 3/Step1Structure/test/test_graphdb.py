"""Mỗi test ứng với một bất biến đã cam kết trong thiết kế. Test hỏng = kiến trúc bị vi phạm."""
import sqlite3

import pytest

from ltm.store.graphdb import GraphDB, ReadOnlySQLError, ValidationError, fts_query


@pytest.fixture
def db(tmp_path):
    g = GraphDB(tmp_path / "mem.db")
    yield g
    g.close()


@pytest.fixture
def world(db):
    """Người dùng đổi trình độ tiếng Nhật N5 → N4 qua hai phiên."""
    t1 = db.add_turn("s1", 0, "user", "I just passed JLPT N5!", "2023-03-10")
    t2 = db.add_turn("s2", 0, "user", "Good news, I'm N4 now. Class E22TTNT starts soon.", "2024-01-22")
    user = db.add_entity("User", "Person", role="Speaker")
    level = db.add_property("japanese_level", "enum")
    e1 = db.add_event("exam_result", "2023-03-10", session_id="s1", participants=[user])
    e2 = db.add_event("exam_result", "2024-01-22", session_id="s2", participants=[user])
    f1 = db.add_fact(user, level, "N5", event_id=e1, confidence=0.95, evidence=[(t1, "JLPT N5")],
                     t_from="2023-03-10")
    f2 = db.add_fact(user, level, "N4", event_id=e2, confidence=0.9, evidence=[(t2, "N4")],
                     t_from="2024-01-22")
    return dict(user=user, level=level, e1=e1, e2=e2, f1=f1, f2=f2, t1=t1, t2=t2)


# ---------------------------------------------------------------- toàn vẹn

def test_foreign_keys_on_for_every_connection(db):
    assert db.conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    ro = db._connect(readonly=True)
    assert ro.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    ro.close()


def test_fact_with_unknown_subject_rejected(db):
    t = db.add_turn("s", 0, "user", "hi", "2024-01-01")
    p = db.add_property("city", "str")
    e = db.add_event("chat", "2024-01-01")
    with pytest.raises(sqlite3.IntegrityError):
        db.add_fact(999, p, "Hanoi", event_id=e, confidence=0.5, evidence=[(t, None)])


def test_fact_and_evidence_are_atomic(db):
    user = db.add_entity("User", "Person", role="Speaker")
    p = db.add_property("city", "str")
    e = db.add_event("chat", "2024-01-01")
    with pytest.raises(sqlite3.IntegrityError):          # turn 999 không tồn tại
        db.add_fact(user, p, "Hanoi", event_id=e, confidence=0.5, evidence=[(999, None)])
    assert db.conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0] == 0
    assert db.conn.execute("SELECT COUNT(*) FROM facts_fts").fetchone()[0] == 0


def test_fact_requires_evidence(db):
    user = db.add_entity("User", "Person")
    p = db.add_property("city", "str")
    e = db.add_event("chat", "2024-01-01")
    with pytest.raises(ValidationError) as ex:
        db.add_fact(user, p, "Hanoi", event_id=e, confidence=0.5, evidence=[])
    assert ex.value.reason == "missing_evidence"


# ---------------------------------------------------------------- append-only

@pytest.mark.parametrize("sql", [
    "UPDATE facts SET value_json='\"N3\"'",
    "DELETE FROM facts",
    "UPDATE evidence SET span='x'",
    "DELETE FROM evidence",
    "UPDATE events SET type='x'",
    "DELETE FROM turns",
])
def test_append_only_enforced_in_db(db, world, sql):
    with pytest.raises(sqlite3.DatabaseError, match="append_only"):
        with db.conn:
            db.conn.execute(sql)


# ---------------------------------------------------------------- chuẩn hóa & kiểm tra

@pytest.mark.parametrize("name,reason", [
    ("trình_độ_tiếng_nhật", "property_not_ascii"),
    ("Japanese Level", "property_bad_format"),
    ("2nd_language", "property_bad_format"),
    ("japanese-level", "property_bad_format"),
])
def test_property_name_must_be_snake_case(db, name, reason):
    with pytest.raises(ValidationError) as ex:
        db.add_property(name, "str")
    assert ex.value.reason == reason


def test_property_is_reused_and_dtype_conflict_detected(db):
    a = db.add_property("home_city", "str")
    assert db.add_property("home_city", "str") == a
    with pytest.raises(ValidationError) as ex:
        db.add_property("home_city", "int")
    assert ex.value.reason == "property_dtype_conflict"


@pytest.mark.parametrize("dtype,value", [
    ("int", "3"), ("int", True), ("bool", 1), ("date", "2024/01/22"),
    ("url", "example.com"), ("list", "a,b"),
])
def test_value_must_match_property_dtype(db, dtype, value):
    user = db.add_entity("User", "Person")
    t = db.add_turn("s", 0, "user", "x", "2024-01-01")
    e = db.add_event("chat", "2024-01-01")
    p = db.add_property(f"p_{dtype}", dtype)
    with pytest.raises(ValidationError) as ex:
        db.add_fact(user, p, value, event_id=e, confidence=0.5, evidence=[(t, None)])
    assert ex.value.reason == "value_dtype_mismatch"


def test_entity_type_and_role_validated(db):
    with pytest.raises(ValidationError) as ex:
        db.add_entity("Tokyo", "City")                    # không có trong ontology
    assert ex.value.reason == "unknown_entity_type"
    with pytest.raises(ValidationError) as ex:
        db.add_entity("Tokyo", "Place", role="Owner")
    assert ex.value.reason == "unknown_role"


@pytest.mark.parametrize("value,reason", [
    ("2023/05/20 (Sat) 02:21", "bad_datetime"),           # định dạng gốc của LongMemEval: loader phải chuẩn hóa trước
    ("2024-01-22T10:00:00+07:00", "tz_not_allowed"),
    ("last month", "bad_datetime"),
])
def test_datetimes_must_be_normalized_iso(db, value, reason):
    with pytest.raises(ValidationError) as ex:
        db.add_event("chat", value)
    assert ex.value.reason == reason


def test_datetime_normalized_on_write(db):
    e = db.add_event("chat", "2024-01-22T10:00:00.123456")
    assert db.conn.execute("SELECT anchor_datetime FROM events WHERE event_id=?", (e,)).fetchone()[0] \
        == "2024-01-22T10:00:00"


def test_bad_interval_and_confidence_rejected(db, world):
    t = world["t1"]
    with pytest.raises(ValidationError, match="bad_interval"):
        db.add_fact(world["user"], world["level"], "N3", event_id=world["e2"], confidence=0.5,
                    evidence=[(t, None)], t_from="2025-01-01", t_to="2024-01-01")
    with pytest.raises(ValidationError, match="bad_confidence"):
        db.add_fact(world["user"], world["level"], "N3", event_id=world["e2"], confidence=1.5,
                    evidence=[(t, None)])


# ---------------------------------------------------------------- đọc: giải quyết lúc đọc

def test_latest_fact_is_newest_by_validity_time(db, world):
    [f] = db.latest_facts(world["user"], world["level"])
    assert f.value == "N4"
    assert [h.value for h in db.fact_history(world["user"], world["level"])] == ["N5", "N4"]


def test_latest_ignores_insertion_order(db):
    """Ghi N4 (2024) trước, N5 (2023) sau — vẫn phải ra N4. Đây là khác biệt với max(seq)."""
    user = db.add_entity("User", "Person")
    p = db.add_property("japanese_level", "enum")
    t = db.add_turn("s", 0, "user", "x", "2024-02-01")
    e = db.add_event("recall", "2024-02-01")
    db.add_fact(user, p, "N4", event_id=e, confidence=0.9, evidence=[(t, None)], t_from="2024-01-22")
    db.add_fact(user, p, "N5", event_id=e, confidence=0.9, evidence=[(t, None)], t_from="2023-03-10")
    assert db.latest_facts(user, p)[0].value == "N4"


def test_latest_as_of_answers_past_questions(db, world):
    [f] = db.latest_facts(world["user"], world["level"], as_of="2023-12-31")
    assert f.value == "N5"
    assert db.latest_facts(world["user"], world["level"], as_of="2022-01-01") == []


def test_latest_falls_back_to_event_anchor(db):
    user = db.add_entity("User", "Person")
    p = db.add_property("favorite_food", "str")
    t = db.add_turn("s", 0, "user", "x", "2024-01-01")
    e_old = db.add_event("chat", "2023-01-01")
    e_new = db.add_event("chat", "2024-01-01")
    db.add_fact(user, p, "phở", event_id=e_new, confidence=0.8, evidence=[(t, None)])
    db.add_fact(user, p, "sushi", event_id=e_old, confidence=0.8, evidence=[(t, None)])
    assert db.latest_facts(user, p)[0].value == "phở"


def test_get_facts_by_ids_preserves_input_order(db, world):
    got = db.get_facts_by_ids([world["f2"], 12345, world["f1"]])
    assert [f.fact_id for f in got] == [world["f2"], world["f1"]]


def test_evidence_links_back_to_source_turn(db, world):
    [row] = db.evidence_turns(world["f2"])
    assert row["session_id"] == "s2" and row["span"] == "N4"


# ---------------------------------------------------------------- unicode & vết

def test_unicode_not_escaped_in_json(db):
    user = db.add_entity("User", "Person")
    p = db.add_property("home_city", "str")
    t = db.add_turn("s", 0, "user", "Tôi sống ở Hà Nội", "2024-01-01")
    e = db.add_event("chat", "2024-01-01")
    fid = db.add_fact(user, p, "Hà Nội", event_id=e, confidence=0.9, evidence=[(t, None)])
    raw = db.conn.execute("SELECT value_json FROM facts WHERE fact_id=?", (fid,)).fetchone()[0]
    assert raw == '"Hà Nội"'
    tid = db.log_trace("ingest", {"text": "Hà Nội"})
    assert "Hà Nội" in db.conn.execute("SELECT payload_json FROM trace WHERE trace_id=?", (tid,)).fetchone()[0]


# ---------------------------------------------------------------- tìm kiếm từ khóa

def test_lexical_search_finds_exact_codes(db, world):
    hits = db.search_lexical("turns", "What class code E22TTNT?")
    assert hits and hits[0][0] == world["t2"]


def test_lexical_search_survives_fts_special_chars(db, world):
    for q in ['what\'s "N4"?', "N4 AND OR NOT", "level: N5*", "(", ""]:
        db.search_lexical("facts", q)                        # không được ném lỗi cú pháp FTS5
    assert fts_query("?!") is None


def test_entity_found_by_alias(db):
    eid = db.add_entity("Mai", "Person")
    db.add_alias(eid, "my sister")
    db.add_alias(eid, "my sister")                          # thêm trùng không sinh bản ghi thừa
    assert db.search_lexical("entities", "sister")[0][0] == eid
    assert db.conn.execute("SELECT COUNT(*) FROM entities_fts").fetchone()[0] == 1


def test_iter_for_index_covers_all_kinds(db, world):
    kinds = {d["kind"] for d in db.iter_for_index()}
    assert kinds == {"entity", "property", "fact", "turn"}
    facts = [d for d in db.iter_for_index() if d["kind"] == "fact"]
    assert any("japanese level N4" in d["text"] for d in facts)


# ---------------------------------------------------------------- GraphSQL chỉ-đọc

def test_graphsql_temporal_query_from_paper(db, world):
    """Bản rút gọn truy vấn TEMPORAL ở Bảng 8 của bài báo."""
    sql = """
        SELECT json_extract(f.value_json, '$') AS level,
               CAST(julianday(:q) - julianday(f.t_from) AS INTEGER) AS days_ago
        FROM facts f JOIN properties p ON p.property_id = f.property_id
        WHERE f.subject_id = :u AND p.name = 'japanese_level'
        ORDER BY julianday(f.t_from) DESC LIMIT 1
    """
    out = db.run_readonly_sql(sql, {"q": "2024-02-01", "u": world["user"]})
    assert out["columns"] == ["level", "days_ago"]
    assert out["rows"] == [("N4", 10)]


def test_graphsql_allows_cte(db, world):
    out = db.run_readonly_sql(
        "WITH x AS (SELECT fact_id FROM facts) SELECT COUNT(*) FROM x")
    assert out["rows"] == [(2,)]


@pytest.mark.parametrize("sql,reason", [
    ("INSERT INTO facts(subject_id) VALUES (1)", "not_select"),
    ("DROP TABLE facts", "not_select"),
    ("PRAGMA foreign_keys = OFF", "not_select"),
    ("SELECT 1; DELETE FROM facts", "multiple_statements"),
    ("SELECT * FROM trace", "not_authorized"),              # ngoài danh sách bảng
    ("SELECT * FROM sqlite_master", "not_authorized"),
    ("SELECT * FROM facts_fts", "not_authorized"),
    ("WITH x AS (SELECT 1) DELETE FROM facts", "not_authorized"),
    ("", "not_select"),
])
def test_graphsql_rejects_everything_but_whitelisted_reads(db, world, sql, reason):
    with pytest.raises(ReadOnlySQLError) as ex:
        db.run_readonly_sql(sql)
    assert ex.value.reason == reason
    assert db.conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0] == 2


def test_graphsql_truncates_large_results(db, world):
    out = db.run_readonly_sql("SELECT turn_id FROM turns", max_rows=1)
    assert len(out["rows"]) == 1 and out["truncated"] is True


def test_memory_db_rejected():
    with pytest.raises(ValueError):
        GraphDB(":memory:")