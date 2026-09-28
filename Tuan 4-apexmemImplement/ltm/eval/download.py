"""Tải LongMemEval-S (bản cleaned) về data/longmemeval/:  python -m ltm.eval.download"""
from __future__ import annotations

import shutil
import urllib.request

from ..config import load_config, resolve_path

URL = ("https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned/resolve/main/"
       "longmemeval_s_cleaned.json")

if __name__ == "__main__":
    dst = resolve_path(load_config().eval.dataset_path)
    if dst.exists():
        print(f"Đã có {dst}")
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_suffix(".part")
        print(f"Tải {URL}\n → {dst} (~265 MB)")
        with urllib.request.urlopen(URL) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f, length=1 << 20)
        tmp.rename(dst)
        print("Xong.")
