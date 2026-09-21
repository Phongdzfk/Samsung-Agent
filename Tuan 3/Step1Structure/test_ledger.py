"""Test cho sổ cái. Chạy offline, không gọi LLM, không tốn hạn mức.

Mỗi test dưới đây tương ứng một BẤT BIẾN đã cam kết trong tài liệu kiến trúc.
Test hỏng nghĩa là kiến trúc bị vi phạm, không phải "code lỗi vặt".

    pytest -q tests/test_ledger.py
"""

from __future__ import annotations

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
