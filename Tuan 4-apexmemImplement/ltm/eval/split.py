"""Chia dev/test phân tầng:  python -m ltm.eval.split [--seed 42] [--dev-size 150]

Nếu nhóm đã có danh sách dev/test từ notebook 01, chỉ cần chép vào data/splits/dev.txt và
data/splits/test.txt (mỗi dòng một question_id) — không cần chạy lệnh này.
"""
from __future__ import annotations

import argparse
from collections import Counter

from ..config import load_config, resolve_path
from .datasets import index_meta, make_split

if __name__ == "__main__":
    cfg = load_config()
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=cfg.eval.split_seed)
    ap.add_argument("--dev-size", type=int, default=cfg.eval.dev_size)
    a = ap.parse_args()
    path = resolve_path(cfg.eval.dataset_path)
    dev, test = make_split(path, resolve_path(cfg.eval.splits_dir), a.seed, a.dev_size)
    qt = dict(index_meta(path))
    print(f"dev={len(dev)} test={len(test)}")
    print("dev theo loại:", dict(Counter(qt[q] for q in dev)))
