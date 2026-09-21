"""Sổ cái của hệ bộ nhớ dài hạn — nguồn sự thật duy nhất.

Vì sao module này đáng làm kỹ trước mọi thứ khác:

1. Nó là nơi DUY NHẤT trong hệ thống không được phép sai. Chroma trả về nhầm
   một ứng viên thì reranker còn vớt lại được; sổ cái ghi sai một bản `active`
   thì mọi thứ phía sau đều sai và không có cách nào biết.
2. Nó không gọi LLM, nên test được 100% offline, không tốn hạn mức Gemini.
3. Toàn bộ logic cập nhật của tuần 4 (ADD/UPDATE/DELETE/CONFLICT) chỉ là các
   phép ghi lên đúng cái bảng này. Schema đúng từ tuần 3 thì tuần 4 không phải
   nhập lại dữ liệu.

Hợp đồng với tầng chỉ mục (quan trọng, đừng phá):

    Chroma chỉ lưu  id + vector + vài metadata để lọc.
    Nội dung trả cho LLM LUÔN được nạp lại từ đây qua `get_by_ids()`.

    Nhờ vậy chỉ mục và sổ cái không bao giờ bất đồng về nội dung — cùng lắm là
    chỉ mục cũ, và `rebuild` sửa được.

Chỉ dùng thư viện chuẩn. Python 3.11+.
"""

from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Sequence

SCHEMA_VERSION = 1
_SCHEMA_PATH = Path(__file__).with_name("schema.sql")

# Lớp bảo vệ số 2 của mục 3.2: khóa slot phải là tiếng Anh, snake_case, không dấu.
# Bắt đầu bằng chữ cái để khóa kiểu "2nd_language" không lọt qua.
_ATTR_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

_MEMORY_COLS = (
    "id subject attribute value value_canon text text_canon lang seq status "
    "superseded_by valid_from invalidated_at event_time memory_type pinned "
    "speaker confirmed needs_review session_id turn_id source_text created_at"
).split()


def utcnow() -> str:
    """Mốc thời gian ISO-8601 UTC. Dùng một hàm duy nhất cho cả hệ để các mốc
    còn so sánh được với nhau bằng phép so chuỗi."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class InvalidFact(ValueError):
    """Fact không đạt ràng buộc tầng ghi."""


# ---------------------------------------------------------------------------
# Fact — thứ `FactExtractor` sinh ra, khớp 1-1 với JSON mà prompt yêu cầu
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class Fact:
    subject: str
    attribute: str
    text: str
    text_canon: str
    lang: str
    speaker: str
    value: str | None = None
    value_canon: str | None = None
    memory_type: str = "semantic"
    pinned: bool = False
    event_time: str | None = None
    valid_from: str | None = None

    def validate(self) -> str | None:
        """Trả về lý do bị từ chối, hoặc None nếu hợp lệ.

        Trả lý do thay vì ném ngoại lệ, vì bên gọi cần con số "tỉ lệ khóa hỏng"
        để đưa vào báo cáo — chứ không phải một cú crash giữa lúc chạy eval.
        """
        if not _ATTR_RE.match(self.attribute):
            # Phân biệt hai ca khác nhau: LLM trả khóa tiếng Việt (lỗi prompt,
            # sửa được) và khóa lạ ký tự (lỗi parse). Báo cáo tách hai loại này.
            if any(unicodedata.combining(c) or ord(c) > 127
                   for c in unicodedata.normalize("NFD", self.attribute)):
                return "attribute_not_ascii"
            return "attribute_bad_format"
        if self.lang not in ("vi", "en"):
            return "bad_lang"
        if self.speaker not in ("user", "assistant"):
            return "bad_speaker"
        if self.memory_type not in ("semantic", "preference", "episodic", "procedural"):
            return "bad_memory_type"
        if not self.subject.strip():
            return "empty_subject"
        if not self.text.strip() or not self.text_canon.strip():
            return "empty_text"
        return None


@dataclass(slots=True)
class IngestResult:
    inserted: list[int] = field(default_factory=list)
    rejected: list[tuple[Fact, str]] = field(default_factory=list)

    @property
    def reject_rate(self) -> float:
        total = len(self.inserted) + len(self.rejected)
        return len(self.rejected) / total if total else 0.0


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------
class Ledger:
    """Bọc một file SQLite. Mở một lần, dùng suốt phiên."""

    def __init__(self, path: str | Path = "ltm.db") -> None:
        self.path = str(path)
        self.conn = sqlite3.connect(self.path, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self._configure()
        self._migrate()

    # -- hạ tầng ------------------------------------------------------------
    def _configure(self) -> None:
        """PRAGMA phải đặt cho TỪNG kết nối — đặt trong schema.sql là vô hiệu.

        Đây là lỗi kinh điển: `foreign_keys` mặc định TẮT trong SQLite, nên
        `superseded_by` trỏ vào id không tồn tại vẫn ghi được, im lặng.
        """
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")   # đọc và ghi song song khi chạy eval
        self.conn.execute("PRAGMA synchronous = NORMAL")
        self.conn.execute("PRAGMA busy_timeout = 5000")

    def _migrate(self) -> None:
        cur = self.conn.execute("PRAGMA user_version")
        current = cur.fetchone()[0]
        if current >= SCHEMA_VERSION:
            return
        self.conn.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))
        self.conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Ledger":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _next_seq(self) -> int:
        """Cấp phát nguyên tử. Phải gọi bên trong một transaction đang mở."""
        row = self.conn.execute(
            "UPDATE counter SET value = value + 1 WHERE name = 'seq' RETURNING value"
        ).fetchone()
        return int(row[0])

    # -- ghi ----------------------------------------------------------------
    def add_facts(
        self,
        facts: Sequence[Fact],
        *,
        session_id: str,
        turn_id: str,
        source_text: str | None = None,
    ) -> IngestResult:
        """Ghi các fact của MỘT lượt hội thoại, trong một transaction.

        Hoặc cả lượt vào, hoặc không gì vào. Nửa vời là trạng thái không thể
        dò lại được từ nhật ký vết.

        Cổng nguồn gốc (mục 6): fact trích từ lượt của TRỢ LÝ vào `pending` và
        không được truy xuất, tới khi người dùng xác nhận ở lượt sau. Đây là
        thứ ngăn hệ tự ghi lại ảo giác của chính nó rồi coi đó là sự thật.
        """
        result = IngestResult()
        now = utcnow()

        self.conn.execute("BEGIN IMMEDIATE")
        try:
            for f in facts:
                reason = f.validate()
                if reason is not None:
                    result.rejected.append((f, reason))
                    continue

                seq = self._next_seq()
                status = "pending" if f.speaker == "assistant" else "active"
                cur = self.conn.execute(
                    """
                    INSERT INTO memory (
                        subject, attribute, value, value_canon,
                        text, text_canon, lang, seq, status,
                        valid_from, event_time, memory_type, pinned,
                        speaker, confirmed, needs_review,
                        session_id, turn_id, source_text, created_at
                    ) VALUES (?,?,?,?, ?,?,?,?,?, ?,?,?,?, ?,?,?, ?,?,?,?)
                    """,
                    (
                        f.subject, f.attribute, f.value, f.value_canon,
                        f.text, f.text_canon, f.lang, seq, status,
                        f.valid_from or now, f.event_time, f.memory_type, int(f.pinned),
                        f.speaker, 0, 0,
                        session_id, turn_id, source_text, now,
                    ),
                )
                result.inserted.append(int(cur.lastrowid))

            # Ghi vết NGAY trong cùng transaction: nếu commit hỏng thì vết cũng
            # biến mất, không để lại dòng nhật ký nói về dữ liệu không tồn tại.
            self._log_trace_nocommit(
                kind="ingest",
                session_id=session_id,
                turn_id=turn_id,
                payload={
                    "kind": "ingest",
                    "n_in": len(facts),
                    "n_inserted": len(result.inserted),
                    "rejected": [
                        {"attribute": f.attribute, "reason": r} for f, r in result.rejected
                    ],
                },
            )
            self.conn.execute("COMMIT")
        except Exception:
            self.conn.execute("ROLLBACK")
            raise
        return result

    def confirm(self, memory_id: int) -> None:
        """Người dùng đã xác nhận một fact `pending` → cho nó vào lưu thông."""
        self.conn.execute(
            "UPDATE memory SET status='active', confirmed=1 "
            "WHERE id=? AND status='pending'",
            (memory_id,),
        )

    def drop_stale_pending(self, session_id: str, *, older_than_seq: int) -> int:
        """Quá 3 lượt không ai nhắc lại thì bản `pending` bị bỏ (mục 6)."""
        cur = self.conn.execute(
            "UPDATE memory SET status='deleted' "
            "WHERE status='pending' AND session_id=? AND seq < ?",
            (session_id, older_than_seq),
        )
        return cur.rowcount

    # -- đọc ----------------------------------------------------------------
    def active_slots(self, subject: str | None = None) -> list[sqlite3.Row]:
        """Mỗi slot đúng một bản: bản `active` có `seq` lớn nhất.

        Lọc này chạy bằng SQL chứ không bằng LLM — đúng nguyên tắc 1. Một câu
        window function thì tất định và giải thích được; nhờ LLM "chọn bản mới
        nhất" thì không, và đó chính là cấu hình đối chứng `llm-judge`.
        """
        sql = """
            SELECT * FROM (
              SELECT *, ROW_NUMBER() OVER (
                         PARTITION BY subject, attribute ORDER BY seq DESC
                       ) AS rn
              FROM memory
              WHERE status = 'active' AND (? IS NULL OR subject = ?)
            ) WHERE rn = 1
            ORDER BY seq DESC
        """
        return self.conn.execute(sql, (subject, subject)).fetchall()

    def get_by_ids(self, ids: Sequence[int]) -> list[sqlite3.Row]:
        """Nạp nội dung thật từ sổ cái, GIỮ NGUYÊN thứ tự do reranker đưa vào.

        `WHERE id IN (...)` trả về theo thứ tự rowid, không theo thứ tự hỏi —
        nếu bê thẳng ra thì thứ hạng của reranker bị xóa sạch một cách âm thầm.
        """
        if not ids:
            return []
        marks = ",".join("?" * len(ids))
        rows = self.conn.execute(
            f"SELECT * FROM memory WHERE id IN ({marks})", tuple(ids)
        ).fetchall()
        by_id = {r["id"]: r for r in rows}
        return [by_id[i] for i in ids if i in by_id]

    def pinned(self, subject: str | None = None) -> list[sqlite3.Row]:
        """Ký ức luôn có mặt trong ngữ cảnh — hạn ngạch riêng ở ContextAssembler."""
        return self.conn.execute(
            "SELECT * FROM memory WHERE pinned=1 AND status='active' "
            "AND (? IS NULL OR subject=?) ORDER BY seq DESC",
            (subject, subject),
        ).fetchall()

    # -- chỉ mục dẫn xuất ---------------------------------------------------
    def iter_for_index(self, batch: int = 512) -> Iterator[list[dict[str, Any]]]:
        """Nguồn dữ liệu để dựng lại Chroma/BM25 từ số không.

        Nhúng `text_canon` chứ không phải `text` (mục 3.4): mọi bản ghi đã quy
        về tiếng Anh ở tầng ghi, nên chỉ mục trên thực tế là đơn ngữ.

        Có `superseded` trong chỉ mục là cố ý — câu hỏi thời gian ở tuần 5
        ("trước đó trình độ là gì") cần chạm tới bản cũ. Việc lọc là của tầng
        truy xuất, không phải của chỉ mục.
        """
        sql = (
            "SELECT id, text_canon, subject, attribute, lang, memory_type, "
            "pinned, seq, status, session_id FROM memory "
            "WHERE status IN ('active','superseded') ORDER BY id"
        )
        cur = self.conn.execute(sql)
        while rows := cur.fetchmany(batch):
            yield [
                {
                    "id": str(r["id"]),
                    "document": r["text_canon"],
                    "metadata": {
                        k: r[k] for k in
                        ("subject", "attribute", "lang", "memory_type",
                         "pinned", "seq", "status", "session_id")
                    },
                }
                for r in rows
            ]

    # -- nhật ký vết --------------------------------------------------------
    def _log_trace_nocommit(
        self, *, kind: str, payload: dict[str, Any],
        session_id: str | None = None, turn_id: str | None = None,
    ) -> None:
        self.conn.execute(
            "INSERT INTO trace (ts, kind, session_id, turn_id, payload) VALUES (?,?,?,?,?)",
            (utcnow(), kind, session_id, turn_id,
             json.dumps(payload, ensure_ascii=False)),
        )

    def log_trace(self, kind: str, payload: dict[str, Any], **ids: str | None) -> None:
        """`ensure_ascii=False` là bắt buộc: nếu không, mọi vết tiếng Việt biến
        thành `\\u1ea1...` và không ai đọc nổi log lúc phân tích lỗi."""
        self._log_trace_nocommit(kind=kind, payload=payload, **ids)

    # -- số liệu cho báo cáo tuần -------------------------------------------
    def stats(self) -> dict[str, Any]:
        q = self.conn.execute
        by = lambda sql: {r[0]: r[1] for r in q(sql).fetchall()}  # noqa: E731
        rejects = q(
            "SELECT json_extract(value, '$.reason') AS reason, COUNT(*) "
            "FROM trace, json_each(json_extract(trace.payload, '$.rejected')) "
            "WHERE trace.kind='ingest' GROUP BY reason"
        ).fetchall()
        return {
            "total": q("SELECT COUNT(*) FROM memory").fetchone()[0],
            "by_status": by("SELECT status, COUNT(*) FROM memory GROUP BY status"),
            "by_lang": by("SELECT lang, COUNT(*) FROM memory GROUP BY lang"),
            "by_type": by("SELECT memory_type, COUNT(*) FROM memory GROUP BY memory_type"),
            "slots": q(
                "SELECT COUNT(*) FROM (SELECT DISTINCT subject, attribute FROM memory)"
            ).fetchone()[0],
            "max_seq": q("SELECT value FROM counter WHERE name='seq'").fetchone()[0],
            "rejects": {r[0]: r[1] for r in rejects},
            "traces": by("SELECT kind, COUNT(*) FROM trace GROUP BY kind"),
        }


# ---------------------------------------------------------------------------
# Ràng buộc để BẬT Ở TUẦN 4, không phải tuần 3
# ---------------------------------------------------------------------------
# Tuần 3 chỉ có thao tác ADD. Nạp LongMemEval, một người nói N5 rồi sau đó nói
# N4 sẽ sinh hai bản `active` cùng slot — đúng như thiết kế, vì `MemoryUpdater`
# chưa tồn tại. Bật ràng buộc này bây giờ là tự làm vỡ pipeline.
#
# Tuần 4, sau khi có UPDATE, chạy đúng một dòng dưới đây. Từ lúc đó mọi lỗi
# logic cập nhật sẽ NỔ NGAY tại chỗ thay vì âm thầm làm hỏng số liệu:
WEEK4_ACTIVE_SLOT_CONSTRAINT = """
CREATE UNIQUE INDEX IF NOT EXISTS ux_active_slot
  ON memory (subject, attribute) WHERE status = 'active';
"""
