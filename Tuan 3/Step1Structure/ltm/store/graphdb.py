"""Đồ thị bộ nhớ trên SQLite theo APEX-MEM.

Ba bất biến chính:
  1. Append-only: facts / evidence / events / turns không bao giờ bị sửa hay xóa
     (trigger trong DB chặn, không chỉ dựa vào code Python).
  2. Mọi fact có ít nhất một bằng chứng trỏ về lượt gốc; fact + evidence ghi trong
     cùng một giao dịch.
  3. "Giá trị mới nhất" được quyết định LÚC ĐỌC theo thời gian hiệu lực, không phải
     theo thứ tự ghi.
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Iterator

SCHEMA_PATH = Path(__file__).with_name("schema.sql")

# 26 lớp được nêu trong §3.1 của bài; bài có 35 lớp, phần còn lại ở Phụ lục I.
DEFAULT_ONTOLOGY = frozenset({
    "Person", "Organization", "Corporation", "Animal", "Plant", "Taxonomy",
    "Place", "Event", "Time", "Product", "Device", "Vehicle", "Software",
    "Dataset", "Service", "CreativeWork", "Document", "Message", "Stock",
    "Contract", "Food", "Medication", "Disease", "Topic", "Metric", "Task",
})
ROLES = frozenset({"Speaker", "Listener", "Agent", "Mentioned"})
DTYPES = frozenset({"str", "int", "float", "bool", "date", "datetime", "enum", "url", "list"})
PROPERTY_RE = re.compile(r"^[a-z][a-z0-9_]*$")

# Bảng mà GraphSQL (công cụ của agent) được phép đọc — đúng danh sách ở §4.3.
GRAPHSQL_TABLES = frozenset({
    "events", "facts", "evidence", "entities", "event_participants", "properties", "turns",
})
FTS_TABLES = {"turns": "turns_fts", "entities": "entities_fts", "facts": "facts_fts"}


class ValidationError(ValueError):
    """Lỗi dữ liệu đầu vào, kèm mã lý do để thống kê trong nhật ký vết."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason


class ReadOnlySQLError(RuntimeError):
    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason


@dataclass(frozen=True)
class Fact:
    fact_id: int
    subject_id: int
    property_id: int
    property_name: str
    value: Any
    dtype: str
    t_from: str | None
    t_to: str | None
    confidence: float
    event_id: int
    anchor_datetime: str


# ---------------------------------------------------------------- chuẩn hóa

def normalize_iso(value: str | None, field: str) -> str | None:
    """Chỉ nhận ngày 'YYYY-MM-DD' hoặc datetime KHÔNG có múi giờ.

    Mọi mốc thời gian đều qua đây để julianday() so sánh nhất quán.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValidationError("bad_datetime", f"{field}={value!r}")
    try:
        if len(value) == 10:
            return date.fromisoformat(value).isoformat()
        dt = datetime.fromisoformat(value)
    except ValueError:
        raise ValidationError("bad_datetime", f"{field}={value!r}") from None
    if dt.tzinfo is not None:
        raise ValidationError("tz_not_allowed", f"{field}={value!r}")
    return dt.replace(microsecond=0).isoformat()


def check_value(value: Any, dtype: str) -> None:
    ok = {
        "str": lambda v: isinstance(v, str),
        "enum": lambda v: isinstance(v, str),
        "int": lambda v: isinstance(v, int) and not isinstance(v, bool),
        "float": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
        "bool": lambda v: isinstance(v, bool),
        "list": lambda v: isinstance(v, list),
        "url": lambda v: isinstance(v, str) and v.startswith(("http://", "https://")),
        "date": lambda v: isinstance(v, str) and len(v) == 10 and bool(normalize_iso(v, "value")),
        "datetime": lambda v: isinstance(v, str) and bool(normalize_iso(v, "value")),
    }[dtype]
    try:
        good = ok(value)
    except ValidationError:
        good = False
    if not good:
        raise ValidationError("value_dtype_mismatch", f"{value!r} is not {dtype}")


def fts_query(text: str) -> str | None:
    """Biến câu tự do thành truy vấn FTS5 an toàn: mỗi từ được bọc nháy kép, nối bằng OR.

    Truyền thẳng câu hỏi vào MATCH sẽ nổ với các ký tự như ', ", ?, -, :, *.
    """
    tokens = re.findall(r"\w+", text, flags=re.UNICODE)
    return " OR ".join(f'"{t}"' for t in tokens) if tokens else None


def _dumps(obj: Any) -> str:
    # ensure_ascii=False: giữ nguyên chữ có dấu, không thành \u1ea1... khi đọc log
    return json.dumps(obj, ensure_ascii=False)


# ---------------------------------------------------------------- GraphDB

class GraphDB:
    def __init__(self, path: str | Path, ontology: Iterable[str] = DEFAULT_ONTOLOGY):
        self.path = str(path)
        if self.path == ":memory:":
            raise ValueError("GraphDB cần file thật: GraphSQL mở kết nối chỉ-đọc riêng")
        self.ontology = frozenset(ontology)
        self.conn = self._connect()
        self.conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))

    # ---- kết nối
    def _connect(self, readonly: bool = False) -> sqlite3.Connection:
        if readonly:
            conn = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
        else:
            conn = sqlite3.connect(self.path)
        self._configure(conn, readonly)
        return conn

    @staticmethod
    def _configure(conn: sqlite3.Connection, readonly: bool) -> None:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")      # mặc định TẮT, phải bật mỗi kết nối
        conn.execute("PRAGMA busy_timeout = 5000")
        if readonly:
            conn.execute("PRAGMA query_only = ON")

    def close(self) -> None:
        self.conn.close()

    # ---- ghi: turns
    def add_turn(self, session_id: str, turn_index: int, speaker: str, text: str,
                 session_date: str) -> int:
        session_date = normalize_iso(session_date, "session_date")
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO turns(session_id, turn_index, speaker, text, session_date) "
                "VALUES (?,?,?,?,?)", (session_id, turn_index, speaker, text, session_date))
            tid = cur.lastrowid
            self.conn.execute("INSERT INTO turns_fts(rowid, text) VALUES (?,?)", (tid, text))
        return tid

    # ---- ghi: entities (không append-only: aliases được bổ sung)
    def add_entity(self, name: str, type: str, role: str = "Mentioned",
                   aliases: Iterable[str] = ()) -> int:
        if type not in self.ontology:
            raise ValidationError("unknown_entity_type", type)
        if role not in ROLES:
            raise ValidationError("unknown_role", role)
        aliases = sorted(set(aliases) - {name})
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO entities(name, type, role, aliases_json) VALUES (?,?,?,?)",
                (name, type, role, _dumps(aliases)))
            eid = cur.lastrowid
            self.conn.execute("INSERT INTO entities_fts(rowid, name, aliases) VALUES (?,?,?)",
                              (eid, name, " ".join(aliases)))
        return eid

    def add_alias(self, entity_id: int, alias: str) -> None:
        row = self.conn.execute("SELECT name, aliases_json FROM entities WHERE entity_id=?",
                                (entity_id,)).fetchone()
        if row is None:
            raise ValidationError("unknown_entity", str(entity_id))
        aliases = set(json.loads(row["aliases_json"]))
        if alias == row["name"] or alias in aliases:
            return
        aliases = sorted(aliases | {alias})
        with self.conn:
            self.conn.execute("UPDATE entities SET aliases_json=? WHERE entity_id=?",
                              (_dumps(aliases), entity_id))
            self.conn.execute("DELETE FROM entities_fts WHERE rowid=?", (entity_id,))
            self.conn.execute("INSERT INTO entities_fts(rowid, name, aliases) VALUES (?,?,?)",
                              (entity_id, row["name"], " ".join(aliases)))

    # ---- ghi: properties
    def add_property(self, name: str, dtype: str) -> int:
        if not name.isascii():
            raise ValidationError("property_not_ascii", name)
        if not PROPERTY_RE.match(name):
            raise ValidationError("property_bad_format", name)
        if dtype not in DTYPES:
            raise ValidationError("unknown_dtype", dtype)
        existing = self.conn.execute("SELECT property_id, dtype FROM properties WHERE name=?",
                                     (name,)).fetchone()
        if existing:
            if existing["dtype"] != dtype:
                raise ValidationError("property_dtype_conflict", f"{name}: {existing['dtype']} vs {dtype}")
            return existing["property_id"]
        with self.conn:
            return self.conn.execute("INSERT INTO properties(name, dtype) VALUES (?,?)",
                                     (name, dtype)).lastrowid

    # ---- ghi: events
    def add_event(self, type: str, anchor_datetime: str, *, location: str | None = None,
                  session_id: str | None = None, participants: Iterable[int] = ()) -> int:
        anchor = normalize_iso(anchor_datetime, "anchor_datetime")
        with self.conn:
            eid = self.conn.execute(
                "INSERT INTO events(type, anchor_datetime, location, session_id) VALUES (?,?,?,?)",
                (type, anchor, location, session_id)).lastrowid
            self.conn.executemany(
                "INSERT INTO event_participants(event_id, entity_id) VALUES (?,?)",
                [(eid, p) for p in set(participants)])
        return eid

    # ---- ghi: facts + evidence, nguyên tử
    def add_fact(self, subject_id: int, property_id: int, value: Any, *, event_id: int,
                 confidence: float, evidence: list[tuple[int, str | None]],
                 t_from: str | None = None, t_to: str | None = None) -> int:
        if not evidence:
            raise ValidationError("missing_evidence")
        if not 0.0 <= confidence <= 1.0:
            raise ValidationError("bad_confidence", str(confidence))
        prop = self.conn.execute("SELECT name, dtype FROM properties WHERE property_id=?",
                                 (property_id,)).fetchone()
        if prop is None:
            raise ValidationError("unknown_property", str(property_id))
        dtype = prop["dtype"]          # một nguồn sự thật cho kiểu dữ liệu
        check_value(value, dtype)
        t_from = normalize_iso(t_from, "t_from")
        t_to = normalize_iso(t_to, "t_to")
        if t_from and t_to and t_from > t_to:
            raise ValidationError("bad_interval", f"{t_from} > {t_to}")

        subj = self.conn.execute("SELECT name FROM entities WHERE entity_id=?",
                                 (subject_id,)).fetchone()
        with self.conn:   # fact và evidence cùng thành công hoặc cùng rollback
            fid = self.conn.execute(
                "INSERT INTO facts(subject_id, property_id, value_json, dtype, t_from, t_to, "
                "confidence, event_id) VALUES (?,?,?,?,?,?,?,?)",
                (subject_id, property_id, _dumps(value), dtype, t_from, t_to, confidence,
                 event_id)).lastrowid
            self.conn.executemany(
                "INSERT INTO evidence(fact_id, event_id, turn_id, span) VALUES (?,?,?,?)",
                [(fid, event_id, turn_id, span) for turn_id, span in evidence])
            self.conn.execute("INSERT INTO facts_fts(rowid, content) VALUES (?,?)",
                              (fid, self._fact_text(subj["name"] if subj else "", prop["name"], value)))
        return fid

    @staticmethod
    def _fact_text(subject: str, prop: str, value: Any) -> str:
        v = " ".join(map(str, value)) if isinstance(value, list) else str(value)
        return f"{subject} {prop.replace('_', ' ')} {v}".strip()

    # ---- đọc
    _FACT_COLS = ("f.fact_id, f.subject_id, f.property_id, p.name AS property_name, f.value_json, "
                  "f.dtype, f.t_from, f.t_to, f.confidence, f.event_id, e.anchor_datetime")
    _FACT_FROM = ("FROM facts f JOIN properties p ON p.property_id = f.property_id "
                  "JOIN events e ON e.event_id = f.event_id ")
    _FACT_SELECT = f"SELECT {_FACT_COLS} {_FACT_FROM}"
    # Thời điểm hiệu lực: t_from nếu có, nếu không thì mốc của sự kiện chứa fact.
    _EFFECTIVE = "julianday(COALESCE(f.t_from, e.anchor_datetime))"

    @staticmethod
    def _to_fact(r: sqlite3.Row) -> Fact:
        return Fact(r["fact_id"], r["subject_id"], r["property_id"], r["property_name"],
                    json.loads(r["value_json"]), r["dtype"], r["t_from"], r["t_to"],
                    r["confidence"], r["event_id"], r["anchor_datetime"])

    def latest_facts(self, subject_id: int, property_id: int | None = None,
                     as_of: str | None = None) -> list[Fact]:
        """Mỗi thuộc tính của chủ thể → bản có thời điểm hiệu lực muộn nhất (≤ as_of nếu có)."""
        where, params = ["f.subject_id = ?"], [subject_id]
        if property_id is not None:
            where.append("f.property_id = ?"); params.append(property_id)
        if as_of is not None:
            where.append(f"{self._EFFECTIVE} <= julianday(?)")
            params.append(normalize_iso(as_of, "as_of"))
        sql = (f"SELECT * FROM (SELECT {self._FACT_COLS}, ROW_NUMBER() OVER ("
               f"PARTITION BY f.property_id ORDER BY {self._EFFECTIVE} DESC, f.fact_id DESC) AS rn "
               f"{self._FACT_FROM} WHERE {' AND '.join(where)}) WHERE rn = 1 ORDER BY property_name")
        return [self._to_fact(r) for r in self.conn.execute(sql, params)]

    def fact_history(self, subject_id: int, property_id: int) -> list[Fact]:
        """Mọi phiên bản của một thuộc tính, theo thứ tự thời gian hiệu lực."""
        sql = (self._FACT_SELECT + "WHERE f.subject_id=? AND f.property_id=? "
               f"ORDER BY {self._EFFECTIVE}, f.fact_id")
        return [self._to_fact(r) for r in self.conn.execute(sql, (subject_id, property_id))]

    def get_facts_by_ids(self, ids: list[int]) -> list[Fact]:
        """Giữ ĐÚNG thứ tự đầu vào. `WHERE id IN (...)` trả theo rowid và sẽ xóa thứ hạng."""
        if not ids:
            return []
        ph = ",".join("?" * len(ids))
        by_id = {r["fact_id"]: self._to_fact(r)
                 for r in self.conn.execute(self._FACT_SELECT + f"WHERE f.fact_id IN ({ph})", ids)}
        return [by_id[i] for i in ids if i in by_id]

    def evidence_turns(self, fact_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT t.*, ev.span FROM evidence ev JOIN turns t ON t.turn_id = ev.turn_id "
            "WHERE ev.fact_id=? ORDER BY t.turn_id", (fact_id,)).fetchall()

    def search_lexical(self, kind: str, query: str, k: int = 10) -> list[tuple[int, float]]:
        """Tìm từ khóa bằng FTS5. Trả (id, điểm) với điểm càng cao càng liên quan."""
        table = FTS_TABLES.get(kind)
        if table is None:
            raise ValueError(f"kind phải thuộc {sorted(FTS_TABLES)}")
        q = fts_query(query)
        if q is None:
            return []
        rows = self.conn.execute(
            f"SELECT rowid, -bm25({table}) AS score FROM {table} WHERE {table} MATCH ? "
            "ORDER BY score DESC LIMIT ?", (q, k))
        return [(r["rowid"], r["score"]) for r in rows]

    def iter_for_index(self) -> Iterator[dict]:
        """Nguồn để dựng lại chỉ mục vector. Chỉ mục là dẫn xuất: xóa đi dựng lại được."""
        for r in self.conn.execute("SELECT entity_id, name, type, aliases_json FROM entities"):
            yield {"kind": "entity", "id": r["entity_id"],
                   "text": " ".join([r["name"], *json.loads(r["aliases_json"])]), "type": r["type"]}
        for r in self.conn.execute("SELECT property_id, name FROM properties"):
            yield {"kind": "property", "id": r["property_id"], "text": r["name"].replace("_", " ")}
        for r in self.conn.execute("SELECT rowid, content FROM facts_fts"):
            yield {"kind": "fact", "id": r["rowid"], "text": r["content"]}
        for r in self.conn.execute("SELECT turn_id, text FROM turns"):
            yield {"kind": "turn", "id": r["turn_id"], "text": r["text"]}

    # ---- GraphSQL: truy vấn chỉ-đọc cho agent
    @staticmethod
    def _authorizer(action, arg1, arg2, dbname, source):
        if action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_FUNCTION,
                      getattr(sqlite3, "SQLITE_RECURSIVE", 33)):
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_READ:
            return sqlite3.SQLITE_OK if arg1 in GRAPHSQL_TABLES else sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_DENY

    def run_readonly_sql(self, sql: str, params: dict | None = None,
                         max_rows: int = 200) -> dict:
        """Ba lớp chặn: kết nối mode=ro + PRAGMA query_only + authorizer theo danh sách bảng."""
        head = sql.lstrip().split(None, 1)[0].upper() if sql.strip() else ""
        if head not in ("SELECT", "WITH"):
            raise ReadOnlySQLError("not_select", head or "<empty>")
        conn = self._connect(readonly=True)
        conn.set_authorizer(self._authorizer)
        try:
            cur = conn.execute(sql, params or {})
            rows = cur.fetchmany(max_rows + 1)
            cols = [d[0] for d in cur.description] if cur.description else []
        except (sqlite3.ProgrammingError, sqlite3.Warning) as e:
            # Python <= 3.11 báo nhiều câu lệnh bằng sqlite3.Warning, từ 3.12 là ProgrammingError
            if "one statement" in str(e):
                raise ReadOnlySQLError("multiple_statements") from None
            raise ReadOnlySQLError("sql_error", str(e)) from None
        except sqlite3.DatabaseError as e:
            # authorizer từ chối → SQLite báo bằng một trong ba thông điệp này
            denied = ("not authorized", "prohibited", "vtable constructor failed")
            reason = "not_authorized" if any(d in str(e) for d in denied) else "sql_error"
            raise ReadOnlySQLError(reason, str(e)) from None
        finally:
            conn.close()
        return {"columns": cols, "rows": [tuple(r) for r in rows[:max_rows]],
                "truncated": len(rows) > max_rows}

    # ---- nhật ký vết
    def log_trace(self, kind: str, payload: dict) -> int:
        with self.conn:
            return self.conn.execute("INSERT INTO trace(kind, payload_json) VALUES (?,?)",
                                     (kind, _dumps(payload))).lastrowid