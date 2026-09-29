"""Nạp config.yaml thành đối tượng truy cập bằng dấu chấm: cfg.llm.model.

Thứ tự ưu tiên: file YAML  <  biến môi trường LTM__MUC__KHOA  <  overrides truyền vào.
"""
from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATH = ROOT / "config.yaml"


class Cfg(dict):
    """dict cho phép cfg.a.b; khóa thiếu → AttributeError rõ ràng."""

    def __getattr__(self, k: str) -> Any:
        try:
            v = self[k]
        except KeyError:
            raise AttributeError(f"config thiếu khóa '{k}'") from None
        return Cfg(v) if isinstance(v, dict) and not isinstance(v, Cfg) else v

    def __setattr__(self, k: str, v: Any) -> None:
        self[k] = v

    def get_path(self, dotted: str, default: Any = None) -> Any:
        cur: Any = self
        for part in dotted.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return default
            cur = cur[part]
        return cur


def _coerce(s: str) -> Any:
    # "10" -> 10, "true" -> True, "[a,b]" -> list ...: YAML làm hộ
    try:
        return yaml.safe_load(s)
    except yaml.YAMLError:
        return s


def deep_merge(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _to_cfg(d: Any) -> Any:
    if isinstance(d, dict):
        return Cfg({k: _to_cfg(v) for k, v in d.items()})
    return d


def load_dotenv(path: Path = ROOT / ".env") -> None:
    """Nạp KEY=VALUE từ .env (nếu có) vào biến môi trường; không ghi đè biến đã đặt."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def load_config(path: str | Path | None = None, overrides: dict | None = None) -> Cfg:
    load_dotenv()
    path = Path(path) if path else DEFAULT_PATH
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    for key, val in os.environ.items():
        if key.startswith("LTM__"):
            parts = [p.lower() for p in key[5:].split("__") if p]
            cur = data
            for p in parts[:-1]:
                cur = cur.setdefault(p, {})
            cur[parts[-1]] = _coerce(val)
    if overrides:
        data = deep_merge(data, overrides)
    return _to_cfg(data)


def resolve_path(p: str | Path) -> Path:
    """Đường dẫn tương đối trong config tính từ thư mục gốc dự án, không phụ thuộc cwd."""
    p = Path(p)
    return p if p.is_absolute() else ROOT / p
