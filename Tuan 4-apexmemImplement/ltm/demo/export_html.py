"""Xuất kết quả chạy thành MỘT file HTML tự chứa — mở bằng trình duyệt, không cần Python.

    python -m ltm.demo.export_html data/runs/full/dev [data/runs/a1/dev] -o demo.html

Dùng khi demo trên máy không chạy được Python: xem từng câu hỏi, câu trả lời, phán quyết, và
từng bước agent gọi công cụ (tham số + kết quả trả về).
"""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

from ..eval.report import load, report

PAGE = r"""<!doctype html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>APEX-MEM demo</title><style>
:root{--bg:#fafaf8;--fg:#1d1d1b;--mut:#6b6b66;--line:#e3e2dc;--card:#fff;--ok:#1f7a4d;--bad:#b3261e;--acc:#2f5bd3}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--fg:#ecebe6;--mut:#9d9c96;--line:#2f2f2c;--card:#1e1e1c;--ok:#5cc28f;--bad:#f08a80;--acc:#8aa7ff}}
*{box-sizing:border-box}body{margin:0;font:14px/1.5 system-ui,Segoe UI,sans-serif;background:var(--bg);color:var(--fg)}
header{padding:16px;border-bottom:1px solid var(--line)}h1{font-size:18px;margin:0 0 4px}
.wrap{display:grid;grid-template-columns:minmax(260px,380px) 1fr;height:calc(100vh - 110px)}
@media(max-width:800px){.wrap{grid-template-columns:1fr;height:auto}}
#list{overflow:auto;border-right:1px solid var(--line)}#detail{overflow:auto;padding:16px}
.item{padding:8px 12px;border-bottom:1px solid var(--line);cursor:pointer}.item:hover,.item.sel{background:var(--card)}
.tag{font-size:11px;padding:1px 6px;border-radius:9px;border:1px solid var(--line);color:var(--mut);margin-right:4px}
.ok{color:var(--ok);font-weight:600}.bad{color:var(--bad);font-weight:600}
.bar{display:flex;gap:8px;flex-wrap:wrap;padding:8px 16px;border-bottom:1px solid var(--line)}
select,input{font:inherit;padding:4px 6px;background:var(--card);color:var(--fg);border:1px solid var(--line);border-radius:6px}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px;margin:10px 0}
pre{white-space:pre-wrap;word-break:break-word;font:12px/1.45 ui-monospace,Consolas,monospace;margin:6px 0 0;max-height:360px;overflow:auto}
.k{color:var(--mut);font-size:12px}details summary{cursor:pointer}
</style></head><body>
<header><h1>APEX-MEM · bộ nhớ dài hạn trên LongMemEval-S</h1><div class="k" id="sum"></div></header>
<div class="bar"><select id="run"></select><select id="qt"><option value="">mọi loại</option></select>
<select id="vd"><option value="">đúng + sai</option><option value="1">chỉ đúng</option><option value="0">chỉ sai</option></select>
<input id="q" placeholder="tìm trong câu hỏi…"><details><summary>Bảng tổng hợp</summary><pre id="rep"></pre></details></div>
<div class="wrap"><div id="list"></div><div id="detail"><p class="k">Chọn một câu hỏi bên trái.</p></div></div>
<script>
const DATA=__DATA__, REPORT=__REPORT__;
const $=id=>document.getElementById(id), esc=s=>String(s??"").replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));
$("rep").textContent=REPORT;
Object.keys(DATA).forEach(r=>$("run").add(new Option(r,r)));
[...new Set(Object.values(DATA).flat().map(x=>x.question_type))].sort().forEach(t=>$("qt").add(new Option(t,t)));
function rows(){const r=DATA[$("run").value]||[],qt=$("qt").value,vd=$("vd").value,q=$("q").value.toLowerCase();
 return r.filter(x=>(!qt||x.question_type==qt)&&(vd===""||(x.score>=.5)==(vd=="1"))&&(!q||x.question.toLowerCase().includes(q)))}
function draw(){const rs=rows(),all=DATA[$("run").value]||[];const ok=all.filter(x=>x.score>=.5).length;
 $("sum").textContent=`${$("run").value}: ${ok}/${all.length} đúng (${(100*ok/Math.max(1,all.length)).toFixed(1)}%) · đang lọc ${rs.length} câu`;
 $("list").innerHTML=rs.map((x,i)=>`<div class="item" data-i="${i}"><span class="${x.score>=.5?"ok":"bad"}">${x.score>=.5?"✓":"✗"}</span> ${esc(x.question)}<br><span class="tag">${x.question_type}</span>${x.is_abs?'<span class="tag">_abs</span>':""}<span class="tag">${x.n_tool_calls} công cụ</span></div>`).join("");
 document.querySelectorAll(".item").forEach(el=>el.onclick=()=>{document.querySelectorAll(".item").forEach(e=>e.classList.remove("sel"));el.classList.add("sel");show(rs[+el.dataset.i])})}
function show(x){const steps=(x.steps||[]).map((s,i)=>`<div class="card"><b>Bước ${i+1}: ${esc(s.tool)}</b> <span class="k">${s.ms??""} ms</span>${s.thought?`<div class="k">${esc(s.thought)}</div>`:""}<pre>${esc(JSON.stringify(s.args,null,1))}</pre><details><summary>kết quả công cụ</summary><pre>${esc(s.output)}</pre></details></div>`).join("");
 $("detail").innerHTML=`<div class="k">${x.question_id} · ${x.question_type} · ngày hỏi ${esc(x.question_date)}</div><h2 style="font-size:17px">${esc(x.question)}</h2>
 <div class="card"><div class="k">Đáp án chuẩn</div>${esc(x.gold)}</div>
 <div class="card"><div class="k">Câu trả lời của hệ — <span class="${x.score>=.5?"ok":"bad"}">${x.score>=.5?"ĐÚNG":"SAI"}</span>${x.error_class?` · lỗi: ${x.error_class}`:""}</div>${esc(x.hypothesis)}</div>
 <div class="k">recall bộ lọc: ${x.filter_recall??"–"} · recall công cụ: ${x.tool_recall??"–"} · phiên bằng chứng: ${esc((x.answer_session_ids||[]).join(", "))} · trả lời ${(x.answer_ms/1000).toFixed(1)} s</div>
 <h3 style="font-size:15px">Các bước của agent (${(x.steps||[]).length})</h3>${steps||'<p class="k">Không gọi công cụ.</p>'}`}
["run","qt","vd"].forEach(i=>$(i).onchange=draw);$("q").oninput=draw;draw();
</script></body></html>"""

KEEP = ("question_id", "question_type", "is_abs", "question", "gold", "question_date", "hypothesis",
        "score", "steps", "n_tool_calls", "error_class", "filter_recall", "tool_recall",
        "answer_session_ids", "answer_ms")


def export(run_dirs: list[Path], out: Path) -> Path:
    data = {}
    for d in run_dirs:
        name = f"{d.parent.name}/{d.name}"
        data[name] = [{k: r.get(k) for k in KEEP} for r in load(d)]
    rep = report(run_dirs)
    page = PAGE.replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/")) \
               .replace("__REPORT__", json.dumps(rep, ensure_ascii=False).replace("</", "<\\/"))
    out.write_text(page, encoding="utf-8")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("-o", "--out", default="demo.html")
    a = ap.parse_args()
    p = export([Path(r) for r in a.runs], Path(a.out))
    print(f"Đã ghi {p} — mở bằng trình duyệt bất kỳ.")


if __name__ == "__main__":
    main()
