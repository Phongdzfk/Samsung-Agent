"""LightMem baseline on LongMemEval-S, cấu hình qua biến môi trường.

Bọc quanh code gốc của LightMem (baselines/LightMem, không sửa file nào trong đó):
- LLM (trích xuất bộ nhớ, trả lời, chấm) đi qua endpoint tương thích OpenAI (9router).
- Prompt chấm và hàm đọc yes/no lấy nguyên từ experiments/longmemeval/run_lightmem_gpt.py.
- Chạy được trên một tập con qid (tập dev của nhóm), có resume, mỗi câu một file kết quả.

Chạy (từ thư mục baselines, dùng python của LightMem/.venv):
    LightMem/.venv/Scripts/python.exe run_lightmem.py --n 3 --workers 5

Với --workers > 1: mỗi luồng tự dựng một LightMemory riêng (embedder + llmlingua-2 riêng),
nên chạy trên CPU để tránh tràn VRAM 4GB khi có nhiều bản nạp cùng lúc. Việc chậm ở đây là
chờ mạng gọi LLM qua 9router, không phải tính toán trên embedder/llmlingua, nên CPU không
phải là nút thắt.
"""
import argparse
import gc
import json
import os
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from openai import OpenAI
from tqdm import tqdm

HERE = Path(__file__).resolve().parent
UPSTREAM = HERE / "LightMem" / "experiments" / "longmemeval" / "run_lightmem_gpt.py"


def _load_upstream_judge():
    """Lấy nguyên văn get_anscheck_prompt và true_or_false từ script gốc.

    Không ast.parse cả file: script gốc dùng cú pháp f-string của Python 3.12, không parse được trên 3.11.
    """
    src = UPSTREAM.read_text(encoding="utf-8")
    chunk = src[src.index("def get_anscheck_prompt"): src.index("class LLMModel")]
    ns: dict = {}
    exec(compile(chunk, str(UPSTREAM), "exec"), ns)
    return ns["get_anscheck_prompt"], ns["true_or_false"]


get_anscheck_prompt, true_or_false = _load_upstream_judge()


def _env(name, default=None, required=False):
    v = os.getenv(name, default)
    if required and not v:
        raise SystemExit(f"Thiếu biến môi trường {name}")
    return v


class Chat:
    """Client OpenAI-compatible. GPT-5.x không nhận temperature/top_p/max_tokens -> đổi tham số."""

    def __init__(self, model, api_key, base_url, max_tokens=2000):
        self.model, self.max_tokens = model, max_tokens
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0}
        self._lock = threading.Lock()

    def call(self, messages, retries=3):
        for attempt in range(retries):
            try:
                r = self.client.chat.completions.create(
                    model=self.model, messages=messages, max_completion_tokens=self.max_tokens
                )
                if r.usage:
                    with self._lock:
                        self.usage["prompt_tokens"] += r.usage.prompt_tokens
                        self.usage["completion_tokens"] += r.usage.completion_tokens
                        self.usage["calls"] += 1
                return r.choices[0].message.content
            except Exception as e:  # noqa: BLE001
                print(f"[retry {attempt + 1}/{retries}] {type(e).__name__}: {e}")
                if attempt == retries - 1:
                    raise
                time.sleep(2 ** attempt)


def patch_manager_client(lightmem, model_kw_fix=True):
    """Bộ quản lý bộ nhớ của LightMem gửi temperature/top_p/max_tokens; chuyển sang dạng GPT-5 chấp nhận."""
    client = lightmem.manager.client
    orig = client.chat.completions.create

    def create(**kw):
        kw.pop("temperature", None)
        kw.pop("top_p", None)
        if "max_tokens" in kw:
            kw["max_completion_tokens"] = kw.pop("max_tokens")
        return orig(**kw)

    client.chat.completions.create = create


_TLS = threading.local()


def install_model_cache():
    """Mỗi luồng chỉ nạp llmlingua-2 và embedder MỘT lần, dùng lại cho mọi câu hỏi mà luồng đó xử lý.

    Mặc định LightMemory nạp lại cả hai model (~1GB) cho từng câu hỏi; các bản cũ không được giải phóng
    kịp nên sau vài giờ RAM/pagefile cạn ("paging file is too small", "memory allocation failed").
    Cache theo luồng (không dùng chung giữa các luồng) để không phải lo tính an toàn luồng của model.
    """
    from lightmem.factory.pre_compressor.factory import PreCompressorFactory
    from lightmem.factory.text_embedder.factory import TextEmbedderFactory

    for factory in (PreCompressorFactory, TextEmbedderFactory):
        orig = factory.from_config.__func__

        def cached(cls, config, _orig=orig, _name=factory.__name__):
            cache = _TLS.__dict__.setdefault("cache", {})
            if _name not in cache:
                cache[_name] = _orig(cls, config)
            return cache[_name]

        factory.from_config = classmethod(cached)


# accelerate/transformers dùng device_map="cpu"/"cuda" để nạp model qua "meta tensor"
# (khởi tạo trọng số rỗng rồi lấp dữ liệu sau) - cơ chế này monkeypatch tạm thời một số
# hàm torch toàn cục. Hai luồng cùng gọi from_pretrained() một lúc thì việc patch/unpatch
# đụng nhau, lỗi "Cannot copy out of meta tensor; no data!". Khoá lại để chỉ một luồng
# nạp model tại một thời điểm; suy luận (forward) sau khi nạp xong vẫn chạy song song bình thường.
_LOAD_LOCK = threading.Lock()


def build_lightmem(qid, out_dir, api_key, base_url, model, device):
    from lightmem.memory.lightmem import LightMemory

    models = HERE / "models"
    qdrant_path = str(out_dir / "qdrant" / qid)
    config = {
        "pre_compress": True,
        "pre_compressor": {
            "model_name": "llmlingua-2",
            "configs": {"llmlingua_config": {
                "model_name": str(models / "llmlingua-2-bert-base-multilingual-cased-meetingbank"),
                "device_map": device,
                "use_llmlingua2": True,
            }},
        },
        "topic_segment": True,
        "precomp_topic_shared": True,
        "topic_segmenter": {"model_name": "llmlingua-2"},
        "messages_use": "user_only",
        "metadata_generate": True,
        "text_summary": True,
        "memory_manager": {
            "model_name": "openai",
            "configs": {"model": model, "api_key": api_key, "max_tokens": 16000, "openai_base_url": base_url},
        },
        "extract_threshold": 0.1,
        "index_strategy": "embedding",
        "text_embedder": {
            "model_name": "huggingface",
            "configs": {"model": str(models / "all-MiniLM-L6-v2"), "embedding_dims": 384,
                        "model_kwargs": {"device": device}},
        },
        "retrieve_strategy": "embedding",
        "embedding_retriever": {
            "model_name": "qdrant",
            "configs": {"collection_name": qid, "embedding_model_dims": 384, "path": qdrant_path},
        },
        "update": "offline",
    }
    with _LOAD_LOCK:
        lm = LightMemory.from_config(config)
    patch_manager_client(lm)
    return lm


def process_case(item, out, api_key, base_url, llm, judge, llm_model, judge_model, topk, device, keep_qdrant):
    qid = item["question_id"]
    dest = out / "cases" / f"{qid}.json"
    if dest.exists():
        return None

    lm = build_lightmem(qid, out, api_key, base_url, llm_model, device)
    sessions, dates = item["haystack_sessions"], item["haystack_dates"]

    t0 = time.time()
    for session, ts in zip(sessions, dates):
        while session and session[0]["role"] != "user":
            session.pop(0)
        n_turns = len(session) // 2
        for i in range(n_turns):
            msgs = session[i * 2: i * 2 + 2]
            if len(msgs) < 2 or msgs[0]["role"] != "user" or msgs[1]["role"] != "assistant":
                continue
            for m in msgs:
                m["time_stamp"] = ts
            last = session is sessions[-1] and i == n_turns - 1
            lm.add_memory(messages=msgs, force_segment=last, force_extract=last)
    t_build = time.time() - t0

    t0 = time.time()
    memories = lm.retrieve(item["question"], limit=topk)
    t_retrieve = time.time() - t0

    mem_text = "\n".join(memories)
    t0 = time.time()
    answer = llm.call([
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": f"Question time:{item['question_date']} and question:{item['question']}\n"
                                    f"Please answer the question based on the following memories: {mem_text}"},
    ])
    t_answer = time.time() - t0

    prompt = get_anscheck_prompt(item["question_type"], item["question"], item["answer"], answer,
                                 abstention="_abs" in qid)
    verdict = judge.call([{"role": "user", "content": prompt}])

    dest.write_text(json.dumps({
        "question_id": qid,
        "question_type": item["question_type"],
        "question": item["question"],
        "ground_truth": item["answer"],
        "generated_answer": answer,
        "judge_verdict": verdict,
        "correct": int(true_or_false(verdict)),
        "retrieved_memories": memories,
        "answer_session_ids": item.get("answer_session_ids"),
        "time_build_s": t_build, "time_retrieve_s": t_retrieve, "time_answer_s": t_answer,
        "llm_model": llm_model, "judge_model": judge_model,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    del lm
    gc.collect()
    if not keep_qdrant:
        shutil.rmtree(out / "qdrant" / qid, ignore_errors=True)
    return qid


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=_env("LME_DATA", str(HERE / "data" / "longmemeval_s.json")))
    ap.add_argument("--ids", default=_env("LME_IDS", str(HERE / "data" / "split.json")), help="file json/txt chứa danh sách question_id (tập dev)")
    ap.add_argument("--n", type=int, default=0, help="chỉ chạy n câu đầu (0 = tất cả)")
    ap.add_argument("--topk", type=int, default=20)
    ap.add_argument("--out", default=str(HERE / "results" / "lightmem"))
    ap.add_argument("--keep-qdrant", action="store_true")
    ap.add_argument("--workers", type=int, default=1,
                     help="số câu chạy song song. >1 -> embedder/llmlingua chạy CPU (tránh tràn VRAM)")
    ap.add_argument("--device", default=None, help="ép cuda/cpu cho embedder+llmlingua; mặc định cuda khi workers=1, cpu khi workers>1")
    args = ap.parse_args()

    api_key = _env("NINEROUTER_API_KEY", required=True)
    base_url = _env("NINEROUTER_BASE_URL", required=True)
    llm_model = _env("LLM_MODEL", "gpt-5.5")
    judge_model = _env("JUDGE_MODEL", "gpt-4o")
    install_model_cache()
    device = args.device or ("cuda" if args.workers <= 1 else "cpu")

    data = json.load(open(args.data, encoding="utf-8"))
    if args.ids:
        p = Path(args.ids)
        ids = json.loads(p.read_text(encoding="utf-8")) if p.suffix == ".json" else p.read_text().split()
        if isinstance(ids, dict):
            ids = ids.get("dev", ids)
        data = [d for d in data if d["question_id"] in set(ids)]
    if args.n:
        data = data[: args.n]

    out = Path(args.out)
    (out / "cases").mkdir(parents=True, exist_ok=True)
    llm = Chat(llm_model, api_key, base_url)
    judge = Chat(judge_model, api_key, base_url, max_tokens=50)

    pending = [it for it in data if not (out / "cases" / f"{it['question_id']}.json").exists()]
    # ưu tiên loại câu hỏi còn ít kết quả nhất (chưa chạy loại nào thì chạy trước), để nếu bị ngắt giữa chừng
    # thì bảng kết quả vẫn phủ được nhiều loại
    done_by_type: dict = {}
    for it in data:
        if it not in pending:
            done_by_type[it["question_type"]] = done_by_type.get(it["question_type"], 0) + 1
    pending.sort(key=lambda it: done_by_type.get(it["question_type"], 0))
    print(f"{len(data)} câu, {len(data) - len(pending)} đã có kết quả, còn {len(pending)} cần chạy, workers={args.workers}, device={device}")

    errors = []
    if args.workers <= 1:
        for item in tqdm(pending):
            try:
                process_case(item, out, api_key, base_url, llm, judge, llm_model, judge_model,
                             args.topk, device, args.keep_qdrant)
            except Exception as e:  # noqa: BLE001
                errors.append((item["question_id"], str(e)))
                print(f"[LỖI] {item['question_id']}: {e}")
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {
                ex.submit(process_case, item, out, api_key, base_url, llm, judge, llm_model, judge_model,
                          args.topk, device, args.keep_qdrant): item["question_id"]
                for item in pending
            }
            for fut in tqdm(as_completed(futs), total=len(futs)):
                qid = futs[fut]
                try:
                    fut.result()
                except Exception as e:  # noqa: BLE001
                    errors.append((qid, str(e)))
                    print(f"[LỖI] {qid}: {e}")

    if errors:
        print(f"\n{len(errors)} câu lỗi, chưa có file kết quả (chạy lại lệnh này sẽ tự bỏ qua câu đã xong):")
        for qid, msg in errors:
            print(f"  {qid}: {msg}")

    # bảng accuracy theo loại câu hỏi (macro-average, đúng quy ước báo cáo của nhóm)
    rows = [json.loads(f.read_text(encoding="utf-8")) for f in (out / "cases").glob("*.json")]
    by: dict = {}
    for r in rows:
        by.setdefault(r["question_type"], []).append(r["correct"])
        if "_abs" in r["question_id"]:
            by.setdefault("_abs", []).append(r["correct"])
    print(f"\n{'type':32s}{'n':>5s}{'acc':>8s}")
    for k, v in sorted(by.items()):
        print(f"{k:32s}{len(v):5d}{sum(v) / len(v):8.1%}")
    types = [k for k in by if k != "_abs"]
    if types:
        print(f"{'macro-avg':32s}{'':5s}{sum(sum(by[k]) / len(by[k]) for k in types) / len(types):8.1%}")
    print(f"LLM usage: {llm.usage}  judge usage: {judge.usage}")


if __name__ == "__main__":
    main()
