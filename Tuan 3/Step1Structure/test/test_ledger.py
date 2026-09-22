"""Test cho sổ cái. Chạy offline, không gọi LLM, không tốn hạn mức.

Mỗi test dưới đây tương ứng một BẤT BIẾN đã cam kết trong tài liệu kiến trúc.
Test hỏng nghĩa là kiến trúc bị vi phạm, không phải "code lỗi vặt".

    pytest -q tests/test_ledger.py
"""

from __future__ import annotations

import json
import multiprocessing as mp
import sqlite3

import pytest

from ltm.store.ledger import (
    WEEK4_ACTIVE_SLOT_CONSTRAINT,
    Fact,
    Ledger,
)


@pytest.fixture()
def led(tmp_path):
    with Ledger(tmp_path / "t.db") as l:
        yield l


def f(attribute="japanese_level", value="N4", speaker="user", lang="vi", **kw) -> Fact:
    return Fact(
        subject="user",
        attribute=attribute,
        value=value,
        value_canon=value,
        text=f"Trình độ tiếng Nhật của mình là {value}",
        text_canon=f"My Japanese level is {value}",
        lang=lang,
        speaker=speaker,
        **kw,
    )


def add(led, *facts, session="s1", turn="t1"):
    return led.add_facts(list(facts), session_id=session, turn_id=turn)


# -- hạ tầng ----------------------------------------------------------------
def test_migrate_idempotent(tmp_path):
    p = tmp_path / "t.db"
    Ledger(p).close()
    l2 = Ledger(p)                       # mở lại không được dựng lại schema
    assert l2.conn.execute("PRAGMA user_version").fetchone()[0] == 1
    l2.close()


def test_foreign_keys_enforced(led):
    """PRAGMA foreign_keys phải bật cho từng kết nối — mặc định của SQLite là TẮT."""
    ids = add(led, f()).inserted
    with pytest.raises(sqlite3.IntegrityError):
        led.conn.execute(
            "UPDATE memory SET status='superseded', superseded_by=99999 WHERE id=?",
            (ids[0],),
        )


# -- seq --------------------------------------------------------------------
def test_seq_monotonic_and_unique(led):
    add(led, f(value="N5"), f(attribute="city", value="Hanoi"))
    add(led, f(value="N4"), session="s2", turn="t1")
    seqs = [r[0] for r in led.conn.execute("SELECT seq FROM memory ORDER BY id")]
    assert seqs == sorted(seqs) == [1, 2, 3]


# -- cổng nguồn gốc (mục 6) --------------------------------------------------
def test_assistant_fact_is_pending_and_invisible(led):
    add(led, f(speaker="assistant", value="N3"))
    assert led.active_slots() == []          # không được truy xuất
    assert led.stats()["by_status"] == {"pending": 1}


def test_confirm_promotes_pending(led):
    mid = add(led, f(speaker="assistant", value="N3")).inserted[0]
    led.confirm(mid)
    rows = led.active_slots()
    assert len(rows) == 1 and rows[0]["confirmed"] == 1


# -- lọc bản cũ --------------------------------------------------------------
def test_active_slots_keeps_max_seq_per_slot(led):
    add(led, f(value="N5"))
    add(led, f(value="N4"), session="s2")                 # cùng slot, mới hơn
    add(led, f(attribute="city", value="Hanoi"), session="s3")
    rows = {r["attribute"]: r["value"] for r in led.active_slots()}
    assert rows == {"japanese_level": "N4", "city": "Hanoi"}


def test_active_slots_excludes_deleted(led):
    ids = add(led, f(value="N5")).inserted
    led.conn.execute("UPDATE memory SET status='deleted' WHERE id=?", (ids[0],))
    assert led.active_slots() == []


# -- khóa slot phải là tiếng Anh (mục 3.2) -----------------------------------
@pytest.mark.parametrize(
    "attr, reason",
    [
        ("trình_độ_tiếng_nhật", "attribute_not_ascii"),   # LLM trả khóa tiếng Việt
        ("Japanese Level", "attribute_bad_format"),       # có hoa và khoảng trắng
        ("2nd_language", "attribute_bad_format"),         # mở đầu bằng số
        ("japanese_level", None),
    ],
)
def test_attribute_gate(led, attr, reason):
    res = add(led, f(attribute=attr))
    if reason is None:
        assert res.inserted and not res.rejected
    else:
        assert not res.inserted
        assert res.rejected[0][1] == reason
        assert res.reject_rate == 1.0


def test_reject_is_traced_for_the_weekly_number(led):
    add(led, f(attribute="trình_độ"), f(attribute="city", value="Hanoi"))
    assert led.stats()["rejects"] == {"attribute_not_ascii": 1}


# -- giao diện với tầng chỉ mục ---------------------------------------------
def test_get_by_ids_preserves_rerank_order(led):
    a, b, c = add(led, f(attribute="a"), f(attribute="b"), f(attribute="c")).inserted
    assert [r["id"] for r in led.get_by_ids([c, a, b])] == [c, a, b]


def test_index_source_embeds_text_canon(led):
    add(led, f())
    batch = next(led.iter_for_index())
    assert batch[0]["document"].startswith("My Japanese level")   # tiếng Anh, không phải bản gốc
    assert batch[0]["metadata"]["lang"] == "vi"                   # vẫn biết gốc là tiếng Việt


def test_pending_never_reaches_the_index(led):
    add(led, f(speaker="assistant"))
    assert list(led.iter_for_index()) == []


# -- ràng buộc của tuần 4 ----------------------------------------------------
def test_week4_constraint_would_catch_a_broken_updater(led):
    """Chứng minh ràng buộc bắt đúng lỗi, và giải thích vì sao tuần 3 chưa bật."""
    add(led, f(value="N5"))
    led.conn.executescript(WEEK4_ACTIVE_SLOT_CONSTRAINT)
    with pytest.raises(sqlite3.IntegrityError):
        add(led, f(value="N4"), session="s2")    # quên hạ bản cũ xuống 'superseded'


# ===========================================================================
# Nhóm dưới đây bịt bốn lỗ hổng: những bất biến đã CAM KẾT trong docstring
# nhưng trước đó không test nào chạm tới. Một lời hứa không có test là một
# lời hứa sẽ bị ai đó vô tình xóa trong lần refactor tuần 4.
# ===========================================================================

def test_transaction_rolls_back_the_whole_turn(led):
    """`add_facts` hứa: hoặc cả lượt vào, hoặc không gì vào.

    Ca lỗi thật: LLM trả `"value": ["N4","N5"]` (list thay vì chuỗi). Nó qua
    được `validate()` vì validate không xét kiểu của `value`, rồi chết ở INSERT.
    Nếu rollback hỏng, fact đầu đã nằm trong DB còn fact sau thì không — một
    lượt nạp nửa vời mà nhật ký vết không mô tả được.
    """
    good = f(attribute="city", value="Hanoi")
    broken = f(attribute="japanese_level")
    broken.value = ["N4", "N5"]                  # kiểu SQLite không ghi được

    with pytest.raises(sqlite3.Error):
        add(led, good, broken)

    assert led.stats()["total"] == 0             # fact hợp lệ cũng KHÔNG được lọt
    assert led.stats()["max_seq"] == 0           # bộ đếm seq cũng hoàn nguyên


def _concurrent_writer(db_path: str, n: int, tag: str) -> None:
    """Chạy ở tiến trình riêng — phải ở cấp module để pickle được."""
    l = Ledger(db_path)
    for i in range(n):
        l.add_facts(
            [Fact(subject="user", attribute=f"attr_{tag}_{i}", value="v", value_canon="v",
                  text="t", text_canon="c", lang="en", speaker="user")],
            session_id="s", turn_id=f"t{i}",
        )
    l.close()


def test_seq_stays_unique_under_concurrent_writers(tmp_path):
    """Lý do dùng `UPDATE ... RETURNING` thay cho `SELECT max(seq)+1`.

    Test `seq` đơn điệu ở trên chỉ chèn 3 bản trong MỘT tiến trình — nó không
    hề chạm vào tình huống đã thúc đẩy thiết kế này. Ở đây 3 tiến trình ghi
    đồng thời; `max(seq)+1` sẽ cấp trùng và bản ghi bị mất.
    """
    db = str(tmp_path / "conc.db")
    Ledger.fresh(db).close()

    procs = [mp.Process(target=_concurrent_writer, args=(db, 30, f"p{i}")) for i in range(3)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=60)

    l = Ledger(db)
    total, distinct, lo, hi = l.conn.execute(
        "SELECT COUNT(*), COUNT(DISTINCT seq), MIN(seq), MAX(seq) FROM memory"
    ).fetchone()
    l.close()
    assert total == 90
    assert distinct == 90, "seq bị cấp trùng — bộ cấp phát không nguyên tử"
    assert (lo, hi) == (1, 90), "seq có lỗ hổng — có bản ghi đã mất"


def test_fresh_wipes_the_previous_case(tmp_path):
    """`fresh()` là thứ ngăn fact của câu 7 nhiễm vào câu 200 khi chạy eval.

    Đây là hàm được thêm vào để VÁ một lỗi nhiễm dữ liệu — mà lại chưa có test.
    """
    db = tmp_path / "case.db"
    l1 = Ledger.fresh(db)
    add(l1, f(), f(attribute="city", value="Hanoi"))
    assert l1.stats()["total"] == 2
    l1.close()

    l2 = Ledger.fresh(db)                        # case tiếp theo
    assert l2.stats()["total"] == 0
    assert l2.stats()["max_seq"] == 0, "seq phải đếm lại từ đầu cho mỗi case"
    l2.close()


def test_turn_time_overrides_wall_clock(led):
    """Nạp haystack của LongMemEval: `valid_from` phải là ngày của PHIÊN.

    Lấy giờ hệ thống thì mọi fact mang ngày hôm nay, năng lực 3 sai toàn bộ mà
    không có lỗi nào hiện ra.
    """
    led.add_facts([f()], session_id="s", turn_id="t", turn_time="2025-01-15T09:00:00Z")
    assert led.active_slots()[0]["valid_from"] == "2025-01-15T09:00:00Z"


def test_drop_stale_pending(led):
    """Quá hạn không ai nhắc lại thì bản `pending` bị bỏ (mục 6)."""
    add(led, f(speaker="assistant", value="N3"))          # seq = 1
    add(led, f(attribute="city", value="Hanoi"), session="s2")   # seq = 2

    assert led.drop_stale_pending("s1", older_than_seq=2) == 1
    assert led.stats()["by_status"] == {"deleted": 1, "active": 1}

    indexed = [it["metadata"]["attribute"] for b in led.iter_for_index() for it in b]
    assert indexed == ["city"]                            # bản deleted không vào chỉ mục


def test_pinned_returns_only_active_pinned(led):
    """Ký ức `pinned` có hạn ngạch riêng ở ContextAssembler — phải lọc đúng."""
    add(led,
        f(attribute="reply_language", value="vi", memory_type="preference", pinned=True),
        f(attribute="city", value="Hanoi"),                         # không pinned
        f(attribute="tone", value="ngan gon", speaker="assistant", pinned=True))  # pending
    rows = led.pinned()
    assert [r["attribute"] for r in rows] == ["reply_language"]


def test_trace_keeps_vietnamese_readable(led):
    """`ensure_ascii=False`: log phải đọc được bằng mắt lúc phân tích lỗi."""
    led.log_trace("answer", {"kind": "answer", "note": "trả lời sai vì thiếu bằng chứng"})
    raw = led.conn.execute("SELECT payload FROM trace WHERE kind='answer'").fetchone()[0]
    assert "trả lời sai" in raw, "JSON bị escape thành \\uXXXX, không ai đọc nổi"
    assert json.loads(raw)["note"].startswith("trả lời")