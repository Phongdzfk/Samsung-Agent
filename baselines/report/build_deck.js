// Dựng slide baseline LightMem từ stats.json.  Chạy:  python gen_stats.py && node build_deck.js
const pptxgen = require("pptxgenjs");
const fs = require("fs");
const path = require("path");

const S = JSON.parse(fs.readFileSync(path.join(__dirname, "stats.json"), "utf-8"));
// ket qua soi tay (khong sinh tu dong) — xem ghi chu trong chinh file do
const MR = JSON.parse(fs.readFileSync(path.join(__dirname, "manual_review.json"), "utf-8"));
const CP = JSON.parse(fs.readFileSync(path.join(__dirname, "compare.json"), "utf-8"));   // so sanh APEX-MEM vs LightMem
const OUT = path.join(__dirname, "..", "bao-cao-lightmem-baseline.pptx");

const C = { ink: "10243E", teal: "1F6F8B", mint: "5FB49C", amber: "F2A541", red: "C8553D",
  bg: "F7F9FB", card: "FFFFFF", text: "1B2B3A", mute: "5B6B7A", line: "DCE3EA", pale: "E7F0F4" };
const HF = "Cambria", BF = "Calibri";
const VI = { "single-session-user": "Đơn phiên · người dùng", "single-session-assistant": "Đơn phiên · trợ lý",
  "single-session-preference": "Đơn phiên · sở thích", "multi-session": "Đa phiên",
  "temporal-reasoning": "Suy luận thời gian", "knowledge-update": "Cập nhật kiến thức" };
const pct = (x) => (x == null ? "—" : (x * 100).toFixed(1).replace(".", ",") + "%");
const num1 = (x) => x.toFixed(1).replace(".", ",");
const thou = (x) => Math.round(x).toLocaleString("en-US").replace(/,/g, ".");
const done = S.n_done, total = S.n_dev;
const partial = done < total;

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9";
pres.title = "LightMem và APEX-MEM trên LongMemEval-S";

function base(title, kicker, notes) {
  const s = pres.addSlide();
  s.background = { color: C.bg };
  if (kicker) s.addText(kicker, { x: 0.5, y: 0.3, w: 9, h: 0.3, fontFace: BF, fontSize: 11, bold: true, color: C.teal, isTextBox: true, margin: 0 });
  s.addText(title, { x: 0.5, y: 0.55, w: 9, h: 0.6, fontFace: HF, fontSize: 26, bold: true, color: C.ink, isTextBox: true, margin: 0 });
  if (partial) s.addText(`Số liệu sơ bộ: ${done}/${total} câu dev`, { x: 6.9, y: 0.3, w: 2.6, h: 0.3, align: "right", fontFace: BF, fontSize: 10, color: C.red, bold: true, isTextBox: true, margin: 0 });
  if (notes) s.addNotes(notes);
  return s;
}
const card = (s, x, y, w, h, fill) => s.addShape(pres.shapes.RECTANGLE, { x, y, w, h, fill: { color: fill || C.card }, line: { color: C.line, width: 0.75 } });

// 1 ─ Tiêu đề
{
  const s = pres.addSlide();
  s.background = { color: C.ink };
  s.addText("BASELINE LIGHTMEM · SO SÁNH VỚI APEX-MEM", { x: 0.7, y: 1.2, w: 8.6, h: 0.4, fontFace: BF, fontSize: 14, bold: true, color: C.amber, isTextBox: true, margin: 0 });
  s.addText("LightMem và APEX-MEM trên LongMemEval-S", { x: 0.7, y: 1.65, w: 8.6, h: 1.1, fontFace: HF, fontSize: 34, bold: true, color: "FFFFFF", isTextBox: true, margin: 0 });
  s.addText("Đường cơ sở LightMem và phép so sánh đầu tiên với hệ của nhóm, trên 150 câu dev", { x: 0.7, y: 2.85, w: 8.6, h: 0.5, fontFace: BF, fontSize: 18, color: "CADCFC", isTextBox: true, margin: 0 });
  s.addText(`Tuần 3 · ${partial ? `số liệu sơ bộ ${done}/${total} câu dev` : `đủ ${total} câu dev`} · nhóm 2 thành viên · 09/2026`,
    { x: 0.7, y: 4.6, w: 8.6, h: 0.35, fontFace: BF, fontSize: 13, color: "8FA7C4", isTextBox: true, margin: 0 });
  s.addNotes("Deck tổng hợp baseline LightMem và so sánh với APEX-MEM. Số liệu sinh tự động từ thư mục kết quả; chạy lại gen_stats.py, compare_apex.py và build_deck.js khi có thêm câu.");
}

// 2 ─ LightMem làm gì
{
  const s = base("LightMem lưu và truy xuất ký ức thế nào", "CÁCH HOẠT ĐỘNG",
    "LightMem (ICLR 2026) nén hội thoại trước khi đưa vào LLM để tiết kiệm token. Cấu hình dùng: messages_use=user_only, top-k=20.");
  const steps = [["Nén trước", "LLMLingua-2 bỏ token ít thông tin"], ["Chia chủ đề", "Cắt hội thoại thành các topic"],
    ["Trích fact", "LLM tóm fact + metadata cho mỗi topic"], ["Lập chỉ mục", "Nhúng MiniLM, lưu Qdrant"], ["Truy xuất", "Top-20 ký ức → LLM trả lời"]];
  const w = 1.66, gap = 0.175;
  steps.forEach((st, i) => {
    const x = 0.5 + i * (w + gap);
    card(s, x, 1.55, w, 1.75);
    s.addShape(pres.shapes.OVAL, { x: x + 0.15, y: 1.7, w: 0.42, h: 0.42, fill: { color: i === 2 ? C.amber : C.teal }, line: { color: i === 2 ? C.amber : C.teal, width: 0 } });
    s.addText(String(i + 1), { x: x + 0.15, y: 1.7, w: 0.42, h: 0.42, align: "center", valign: "middle", fontFace: BF, fontSize: 14, bold: true, color: "FFFFFF", isTextBox: true, margin: 0 });
    s.addText(st[0], { x: x + 0.15, y: 2.2, w: w - 0.3, h: 0.35, fontFace: HF, fontSize: 15, bold: true, color: C.ink, isTextBox: true, margin: 0 });
    s.addText(st[1], { x: x + 0.15, y: 2.58, w: w - 0.3, h: 0.65, fontFace: BF, fontSize: 11.5, color: C.mute, valign: "top", isTextBox: true, margin: 0 });
  });
  card(s, 0.5, 3.6, 4.4, 1.4, C.pale);
  s.addText([{ text: "Giới hạn quan trọng", options: { bold: true, breakLine: true, color: C.ink } },
    { text: "Chỉ lưu lượt của người dùng (user_only). Nội dung do trợ lý nói không vào bộ nhớ.", options: { color: C.text } }],
    { x: 0.7, y: 3.7, w: 4.0, h: 1.2, fontFace: BF, fontSize: 12.5, valign: "top", isTextBox: true, margin: 0 });
  card(s, 5.1, 3.6, 4.4, 1.4, C.pale);
  s.addText([{ text: "Vì sao chọn làm baseline", options: { bold: true, breakLine: true, color: C.ink } },
    { text: "Đã bình duyệt, có mã nguồn mở, chạy được trên LongMemEval. Đối chứng tốt cho hệ dựa trên đồ thị của nhóm.", options: { color: C.text } }],
    { x: 5.3, y: 3.7, w: 4.0, h: 1.2, fontFace: BF, fontSize: 12.5, valign: "top", isTextBox: true, margin: 0 });
}

// 3 ─ Thiết lập
{
  const s = base("Thiết lập thực nghiệm", "CÁCH CHẠY",
    "Model: kế hoạch ghi GPT-5.5, nhưng tài khoản ChatGPT nối qua 9router không có quyền model này (lỗi 404). Dùng gpt-5.6-luna. Hệ APEX-MEM của nhóm phải chạy cùng model để so công bằng.");
  const rows = [["Dữ liệu", "LongMemEval-S, 500 câu, mỗi câu một haystack ~115K token"],
    ["Chia tập", "Dev 150 / test 350, phân tầng theo loại, seed 42 (khớp split.json của nhóm)"],
    ["Model trả lời (cả hai hệ)", S.llm || "cx/gpt-5.6-luna"],
    ["Model chấm (cả hai hệ)", (S.judge || "cx/gpt-5.6-terra") + " — khác model trả lời"],
    ["Prompt chấm", "Prompt chính thức của LongMemEval, theo từng loại câu hỏi"],
    ["LightMem", "Top-20 ký ức, MiniLM. Chỉ lưu lượt của người dùng"],
    ["APEX-MEM", "Đồ thị SQLite, agent ReAct ≤ 20 bước, BGE-M3. Lưu cả lượt trợ lý"]];
  rows.forEach((r, i) => {
    const y = 1.3 + i * 0.55;
    s.addText(r[0], { x: 0.5, y, w: 2.3, h: 0.5, fontFace: BF, fontSize: 12, bold: true, color: i >= 5 ? C.amber : C.teal, valign: "middle", isTextBox: true, margin: 0 });
    s.addText(r[1], { x: 2.8, y, w: 4.1, h: 0.5, fontFace: BF, fontSize: 11.5, color: C.text, valign: "middle", isTextBox: true, margin: 0 });
  });
  card(s, 7.1, 1.4, 2.4, 3.5);
  s.addText(String(S.n_dev), { x: 7.1, y: 1.6, w: 2.4, h: 0.9, align: "center", fontFace: HF, fontSize: 54, bold: true, color: C.teal, isTextBox: true, margin: 0 });
  s.addText("câu dev để chạy và chỉnh", { x: 7.1, y: 2.5, w: 2.4, h: 0.4, align: "center", fontFace: BF, fontSize: 12, color: C.mute, isTextBox: true, margin: 0 });
  s.addText(String(S.n_test), { x: 7.1, y: 3.2, w: 2.4, h: 0.9, align: "center", fontFace: HF, fontSize: 54, bold: true, color: C.mute, isTextBox: true, margin: 0 });
  s.addText("câu test, khóa đến tuần 7", { x: 7.1, y: 4.1, w: 2.4, h: 0.4, align: "center", fontFace: BF, fontSize: 12, color: C.mute, isTextBox: true, margin: 0 });
}

// 4 ─ So sánh theo loại
{
  const ci = (c) => `${(c[0] * 100).toFixed(0)}–${(c[1] * 100).toFixed(0)}%`;
  const s = base(`APEX-MEM ${pct(CP.apex.micro)}, LightMem ${pct(CP.lm.micro)}: chưa khác biệt`, "SO SÁNH TRỰC TIẾP",
    `Cùng ${CP.n} câu dev, cùng model trả lời (luna), cùng model chấm (terra). Gộp chung APEX-MEM ${CP.apex.correct}/${CP.n}, LightMem ${CP.lm.correct}/${CP.n}. Hai khoảng tin cậy 95% chồng lên nhau gần hết.`);
  const order = ["single-session-user", "single-session-assistant", "single-session-preference", "multi-session", "temporal-reasoning", "knowledge-update"];
  const labels = order.map((t) => `${VI[t]} (n=${CP.by_type[t].n})`);
  s.addChart(pres.charts.BAR, [
    { name: "APEX-MEM", labels, values: order.map((t) => +(CP.by_type[t].apex_acc * 100).toFixed(1)) },
    { name: "LightMem", labels, values: order.map((t) => +(CP.by_type[t].lm_acc * 100).toFixed(1)) }],
    { x: 0.4, y: 1.2, w: 6.3, h: 3.45, barDir: "col", barGrouping: "clustered", chartColors: [C.teal, C.amber],
      showLegend: true, legendPos: "t", legendFontSize: 11, legendColor: C.mute,
      showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: '0"%"', dataLabelFontSize: 9, dataLabelColor: C.ink,
      valAxisMinVal: 0, valAxisMaxVal: 110, valAxisHidden: true, valGridLine: { style: "none" },
      catAxisLabelColor: C.text, catAxisLabelFontSize: 8.5, catGridLine: { style: "none" } });
  [["APEX-MEM", CP.apex, C.teal], ["LightMem", CP.lm, C.amber]].forEach(([name, d, col], i) => {
    const y = 1.3 + i * 1.7;
    card(s, 6.9, y, 2.6, 1.55);
    s.addText(name, { x: 6.9, y: y + 0.08, w: 2.6, h: 0.3, align: "center", fontFace: BF, fontSize: 12, bold: true, color: col, isTextBox: true, margin: 0 });
    s.addText(pct(d.micro), { x: 6.9, y: y + 0.38, w: 2.6, h: 0.65, align: "center", fontFace: HF, fontSize: 32, bold: true, color: C.ink, isTextBox: true, margin: 0 });
    s.addText(`gộp chung ${d.correct}/${CP.n} · KTC 95% ${ci(d.ci95)}`, { x: 6.9, y: y + 1.0, w: 2.6, h: 0.25, align: "center", fontFace: BF, fontSize: 9.5, color: C.mute, isTextBox: true, margin: 0 });
    s.addText(`theo loại (macro) ${pct(d.macro)}`, { x: 6.9, y: y + 1.24, w: 2.6, h: 0.25, align: "center", fontFace: BF, fontSize: 9.5, color: C.mute, isTextBox: true, margin: 0 });
  });
  card(s, 0.4, 4.8, 9.1, 0.55, "FDF3E1");
  s.addText([{ text: "Đọc đúng mức: ", options: { bold: true, color: C.red } },
    { text: `chênh ${CP.apex.correct - CP.lm.correct} câu trên ${CP.n} câu; nhóm câu từ chối (_abs) chỉ có ${CP.abs.n} câu (APEX-MEM ${CP.abs.apex}, LightMem ${CP.abs.lm}). Cả hai hệ cùng model nên khác biệt đến từ cách lưu và truy xuất ký ức.`, options: { color: C.text } }],
    { x: 0.6, y: 4.83, w: 8.7, h: 0.5, fontFace: BF, fontSize: 10.5, valign: "middle", isTextBox: true, margin: 0 });
}

// 5 ─ Chênh lệch đến từ đâu
{
  const P = CP.paired, bt = CP.by_type;
  const asst = bt["single-session-assistant"];
  const restN = CP.n - asst.n, restA = CP.apex.correct - asst.apex, restL = CP.lm.correct - asst.lm;
  const p = CP.paired.mcnemar_p.toFixed(2).replace(".", ",");
  const s = base("Toàn bộ chênh lệch nằm ở loại lượt trợ lý", "CHÊNH LỆCH ĐẾN TỪ ĐÂU",
    `Kiểm định McNemar trên cặp câu hỏi: APEX-MEM đúng riêng ${P.only_apex} câu, LightMem đúng riêng ${P.only_lm} câu, p = ${p}. Tách theo loại: loại lượt trợ lý APEX-MEM hơn ${asst.apex - asst.lm} câu, năm loại còn lại LightMem hơn ${restL - restA} câu.`);
  const boxes = [[P.both_right, "cả hai đúng", C.teal, C.card], [P.only_apex, "chỉ APEX-MEM đúng", C.teal, "E4F1F5"],
                 [P.only_lm, "chỉ LightMem đúng", C.amber, "FDF3E1"], [P.both_wrong, "cả hai sai", C.mute, C.card]];
  boxes.forEach((b, i) => {
    const x = 0.4 + (i % 2) * 2.35, y = 1.3 + Math.floor(i / 2) * 1.5;
    card(s, x, y, 2.25, 1.4, b[3]);
    s.addText(String(b[0]), { x, y: y + 0.12, w: 2.25, h: 0.75, align: "center", fontFace: HF, fontSize: 38, bold: true, color: b[2], isTextBox: true, margin: 0 });
    s.addText(b[1], { x, y: y + 0.9, w: 2.25, h: 0.3, align: "center", fontFace: BF, fontSize: 11.5, color: C.text, isTextBox: true, margin: 0 });
  });
  s.addText(`McNemar chính xác: p = ${p} (chưa khác biệt)`, { x: 0.4, y: 4.32, w: 4.6, h: 0.3, fontFace: BF, fontSize: 11, bold: true, color: C.ink, isTextBox: true, margin: 0 });

  const rows = [["Loại lượt trợ lý", `${asst.apex}/${asst.n}`, `${asst.lm}/${asst.n}`, `+${asst.apex - asst.lm}`, true],
                ["Năm loại còn lại", `${restA}/${restN}`, `${restL}/${restN}`, `${restA - restL}`, false]];
  const hdr = (t) => ({ text: t, options: { bold: true, color: "FFFFFF", fill: { color: C.teal }, align: "center" } });
  const tb = [[{ text: "", options: { fill: { color: C.teal } } }, hdr("APEX-MEM"), hdr("LightMem"), hdr("Chênh")]];
  rows.forEach((r) => tb.push([{ text: r[0], options: { bold: true } }, { text: r[1], options: { align: "center" } }, { text: r[2], options: { align: "center" } },
    { text: r[3], options: { align: "center", bold: true, color: r[4] ? C.teal : C.red } }]));
  s.addTable(tb, { x: 5.2, y: 1.3, w: 4.3, colW: [1.45, 1.15, 1.0, 0.7], fontFace: BF, fontSize: 11, color: C.text, border: { type: "solid", color: C.line, pt: 0.75 }, valign: "middle", rowH: 0.5 });
  s.addText(`Năm loại còn lại: APEX-MEM ${pct(restA / restN)}, LightMem ${pct(restL / restN)}.`, { x: 5.2, y: 2.95, w: 4.3, h: 0.5, fontFace: BF, fontSize: 11, color: C.text, valign: "top", isTextBox: true, margin: 0 });
  card(s, 5.2, 3.5, 4.3, 1.12, "FBEAE5");
  s.addText([{ text: "Khác biệt cấu hình: ", options: { bold: true, color: C.red } },
    { text: "APEX-MEM lưu cả lượt trợ lý, LightMem mặc định chỉ lưu lượt người dùng. Loại câu hỏi này hỏi đúng về lời trợ lý.", options: { color: C.text } }],
    { x: 5.35, y: 3.55, w: 4.0, h: 1.02, fontFace: BF, fontSize: 10.5, valign: "middle", isTextBox: true, margin: 0 });

  card(s, 0.4, 4.78, 9.1, 0.58, C.pale);
  s.addText([{ text: "Chưa kết luận được: ", options: { bold: true, color: C.ink } },
    { text: "giả thuyết là khác biệt cấu hình, không phải đồ thị, tạo ra chênh lệch. Muốn kiểm chứng phải chạy lại LightMem loại này với messages_use = user_assistant.", options: { color: C.text } }],
    { x: 0.6, y: 4.81, w: 8.7, h: 0.52, fontFace: BF, fontSize: 10.5, valign: "middle", isTextBox: true, margin: 0 });
}

// 5 ─ Kết quả
{
  const asstT = S.types.find((t) => t.type === "single-session-assistant");
  const others = S.types.filter((t) => t.done && t !== asstT).map((t) => t.acc * 100);
  const s = base(`Năm loại đạt ${Math.round(Math.min(...others))}–${Math.round(Math.max(...others))}%, riêng lượt trợ lý ${Math.round(asstT.acc * 100)}%`, "KẾT QUẢ LIGHTMEM",
    `Micro ${pct(S.micro)} trên ${done} câu, macro ${pct(S.macro)} trên 6 loại. Điểm đáng chú ý nhất: loại đơn phiên · trợ lý thấp hẳn, và nguyên nhân nằm ở cấu hình user_only của LightMem chứ không phải ngẫu nhiên.`);
  const ran = S.types.filter((t) => t.done);
  s.addChart(pres.charts.BAR, [{ name: "Accuracy", labels: ran.map((t) => `${VI[t.type]} (n=${t.done})`), values: ran.map((t) => +(t.acc * 100).toFixed(1)) }],
    { x: 0.4, y: 1.25, w: 5.7, h: 3.2, barDir: "col", chartColors: [C.teal], showLegend: false, showValue: true,
      dataLabelPosition: "outEnd", dataLabelFormatCode: '0.0"%"', dataLabelFontSize: 11, dataLabelColor: C.ink,
      valAxisMinVal: 0, valAxisMaxVal: 100,
      catAxisLabelColor: C.text, catAxisLabelFontSize: 9, valAxisLabelColor: C.mute, valAxisLabelFontSize: 10,
      valGridLine: { color: C.line, size: 0.5 }, catGridLine: { style: "none" } });

  card(s, 6.3, 1.25, 3.2, 1.0);
  s.addText(pct(S.macro), { x: 6.3, y: 1.3, w: 3.2, h: 0.62, align: "center", fontFace: HF, fontSize: 32, bold: true, color: C.teal, isTextBox: true, margin: 0 });
  s.addText(`macro-average, 6/6 loại · micro ${pct(S.micro)}`, { x: 6.3, y: 1.9, w: 3.2, h: 0.3, align: "center", fontFace: BF, fontSize: 10.5, color: C.mute, isTextBox: true, margin: 0 });

  const asst = asstT;
  card(s, 6.3, 2.45, 3.2, 2.0, "FBEAE5");
  s.addText(pct(asst.acc), { x: 6.3, y: 2.55, w: 3.2, h: 0.6, align: "center", fontFace: HF, fontSize: 32, bold: true, color: C.red, isTextBox: true, margin: 0 });
  s.addText(`Đơn phiên · trợ lý (${asst.correct}/${asst.done})`, { x: 6.3, y: 3.15, w: 3.2, h: 0.3, align: "center", fontFace: BF, fontSize: 11, bold: true, color: C.ink, isTextBox: true, margin: 0 });
  s.addText("LightMem chỉ lưu lượt người dùng (user_only), nên câu hỏi “trước đây bạn gợi ý gì” không có bằng chứng nào trong bộ nhớ.",
    { x: 6.5, y: 3.5, w: 2.8, h: 0.85, fontFace: BF, fontSize: 11, color: C.text, valign: "top", isTextBox: true, margin: 0 });

  const inc = S.types.filter((t) => t.done < t.dev);
  card(s, 0.4, 4.65, 9.1, 0.65, "FDF3E1");
  s.addText([{ text: inc.length ? "Số liệu sơ bộ. " : "Đủ 150 câu dev. ", options: { bold: true, color: C.red } },
    { text: `${inc.length ? "Chưa chạy đủ: " + inc.map((t) => `${VI[t.type]} ${t.done}/${t.dev}`).join(" · ") + ". " : ""}Nhóm câu từ chối (_abs) chỉ có ${CP.abs.n} câu, quá ít để nói về năng lực biết từ chối.`, options: { color: C.text } }],
    { x: 0.6, y: 4.7, w: 8.7, h: 0.55, fontFace: BF, fontSize: 11.5, valign: "middle", isTextBox: true, margin: 0 });
}

// 6 ─ Phân tích lỗi
{
  const w = S.wrong;
  const s = base(`Hai kiểu lỗi chính trong ${w.length} câu sai`, "PHÂN TÍCH LỖI",
    "Kiểu 1: câu đếm qua nhiều phiên, hệ đếm thiếu hoặc thừa. Kiểu 2: câu hỏi về lời trợ lý, hệ không có dữ liệu vì cấu hình user_only. Kiểu 2 là lỗi cấu hình, sửa được; kiểu 1 là hạn chế thật của cách lưu ký ức.");
  const byT = {};
  w.forEach((x) => (byT[x.type] = (byT[x.type] || 0) + 1));
  const sorted = Object.entries(byT).sort((a, b) => b[1] - a[1]);

  card(s, 0.4, 1.3, 2.9, 3.6);
  s.addText(String(w.length), { x: 0.4, y: 1.45, w: 2.9, h: 0.85, align: "center", fontFace: HF, fontSize: 46, bold: true, color: C.red, isTextBox: true, margin: 0 });
  s.addText(`câu sai trong ${done} câu đã chạy`, { x: 0.5, y: 2.3, w: 2.7, h: 0.3, align: "center", fontFace: BF, fontSize: 11.5, color: C.mute, isTextBox: true, margin: 0 });
  sorted.forEach(([t, n], i) => {
    const y = 2.8 + i * 0.4;
    s.addText(VI[t], { x: 0.65, y, w: 2.0, h: 0.34, fontFace: BF, fontSize: 11.5, color: C.text, valign: "middle", isTextBox: true, margin: 0 });
    s.addText(String(n), { x: 2.65, y, w: 0.45, h: 0.34, align: "right", fontFace: BF, fontSize: 11.5, bold: true, color: i < 2 ? C.red : C.mute, valign: "middle", isTextBox: true, margin: 0 });
  });

  const hdr = (t) => ({ text: t, options: { bold: true, color: "FFFFFF", fill: { color: C.teal } } });
  const cut = (t, n) => (t.length > n ? t.slice(0, n - 1).trimEnd() + "…" : t);
  // voi loai luot tro ly, lay mot vi du bia ra va mot vi du tra loi "khong co trong bo nho"
  const asstW = w.filter((x) => x.type === "single-session-assistant");
  const norm = (t) => t.replace(/[‘’]/g, "'");            // nhay cong -> nhay thang
  const noData = (x) => /don't|doesn't|can't|couldn't|not (found|available|specified)|memories don/i.test(norm(x.pred));
  const pick = [...w.filter((x) => x.type === "multi-session").slice(0, 2),
    ...asstW.filter((x) => !noData(x)).slice(0, 1), ...asstW.filter(noData).slice(0, 1)];
  const kind = { "multi-session": "Đếm đa phiên", "single-session-assistant": "Lượt trợ lý" };
  const rowsT = [[hdr("Kiểu lỗi"), hdr("Câu hỏi"), hdr("Đáp án"), hdr("Hệ trả lời")]];
  pick.forEach((x) => rowsT.push([
    { text: kind[x.type], options: { bold: true, color: x.type === "multi-session" ? C.teal : C.red } },
    cut(x.q, 62), cut(x.gold, 16), cut(x.pred.replace(/\*\*/g, ""), 44)]));
  s.addTable(rowsT, { x: 3.6, y: 1.3, w: 5.9, colW: [0.95, 2.35, 0.7, 1.9], fontFace: BF, fontSize: 9,
    color: C.text, border: { type: "solid", color: C.line, pt: 0.75 }, valign: "middle", rowH: 0.62 });

  const nAsstNoData = asstW.filter(noData).length;
  card(s, 3.6, 4.55, 5.9, 0.75, C.pale);
  s.addText([{ text: "Bằng chứng: ", options: { bold: true, color: C.ink } },
    { text: `${nAsstNoData}/${asstW.length} câu sai loại lượt trợ lý, hệ trả lời thẳng là không tìm thấy thông tin trong bộ nhớ, khớp với cấu hình user_only.`, options: { color: C.text } }],
    { x: 3.8, y: 4.6, w: 5.5, h: 0.65, fontFace: BF, fontSize: 10.5, valign: "middle", isTextBox: true, margin: 0 });
}

// 7 ─ Truy xuất có trúng bằng chứng không
{
  const R = S.retrieval, nw = R.wrong_with_evidence + R.wrong_without_evidence;
  const s = base("Lỗi không nằm ở khâu tìm kiếm", "TÁCH NGUỒN LỖI",
    `Truy xuất trúng phiên chứa bằng chứng ở ${R.hit}/${R.n} câu. Trong ${nw} câu sai, ${R.wrong_with_evidence} câu đã có bằng chứng trong 20 ký ức lấy về mà vẫn trả lời sai. Lưu ý: "trúng phiên" chưa chắc là "giữ được chi tiết cần thiết", vì LightMem nén và tóm tắt trước khi lưu.`);

  card(s, 0.4, 1.3, 2.9, 3.2);
  s.addText(pct(R.hit / R.n), { x: 0.4, y: 1.45, w: 2.9, h: 0.8, align: "center", fontFace: HF, fontSize: 40, bold: true, color: C.teal, isTextBox: true, margin: 0 });
  s.addText(`truy xuất trúng phiên chứa bằng chứng (${R.hit}/${R.n} câu)`,
    { x: 0.6, y: 2.25, w: 2.5, h: 0.6, align: "center", fontFace: BF, fontSize: 12, color: C.mute, valign: "top", isTextBox: true, margin: 0 });
  s.addText([{ text: "Đo thế nào", options: { bold: true, breakLine: true, color: C.ink } },
    { text: "Mỗi ký ức LightMem trả về đều mở đầu bằng mốc thời gian của phiên. Khớp mốc đó với haystack_dates để biết ký ức đến từ phiên nào, rồi so với answer_session_ids của bộ dữ liệu." + (R.ambiguous ? ` Có ${R.ambiguous} câu có phiên trùng mốc với phiên khác nên khớp chưa chắc chắn.` : ""), options: { color: C.text } }],
    { x: 0.6, y: 2.95, w: 2.5, h: 1.45, fontFace: BF, fontSize: 10.5, valign: "top", isTextBox: true, margin: 0 });

  const boxes = [
    { n: R.wrong_with_evidence, col: C.red, bg: "FBEAE5", y: 1.7, h: 1.75,
      head: "đã có bằng chứng trong ký ức lấy về, vẫn trả lời sai",
      body: "Lỗi nằm ở tầng trích xuất (nén làm mất chi tiết) hoặc tầng suy luận, không phải tầng tìm kiếm. Ví dụ rõ nhất: một câu tính khoảng ngày, hệ nêu đúng cả hai mốc 22/03 và 15/04/2023 nhưng tính ra 18 ngày thay vì 24 — ký ức đúng, phép trừ sai." },
    { n: R.wrong_without_evidence, col: C.mute, bg: C.card, y: 3.6, h: 1.0,
      head: "không truy xuất được bằng chứng",
      body: "Câu duy nhất thuộc loại lượt trợ lý, mà lời trợ lý thì không được lưu do cấu hình user_only." }];
  s.addText(`Trong ${nw} câu sai`, { x: 3.6, y: 1.3, w: 5.9, h: 0.3, fontFace: HF, fontSize: 15, bold: true, color: C.ink, isTextBox: true, margin: 0 });
  boxes.forEach((b) => {
    card(s, 3.6, b.y, 5.9, b.h, b.bg);
    s.addText(String(b.n), { x: 3.75, y: b.y + 0.15, w: 0.95, h: 0.8, align: "center", fontFace: HF, fontSize: 38, bold: true, color: b.col, valign: "middle", isTextBox: true, margin: 0 });
    s.addText(b.head, { x: 4.8, y: b.y + 0.14, w: 4.55, h: 0.42, fontFace: BF, fontSize: 12.5, bold: true, color: C.ink, valign: "middle", isTextBox: true, margin: 0 });
    s.addText(b.body, { x: 4.8, y: b.y + 0.56, w: 4.55, h: b.h - 0.68, fontFace: BF, fontSize: 11, color: C.text, valign: "top", isTextBox: true, margin: 0 });
  });

  card(s, 0.4, 4.75, 9.1, 0.6, "FDF3E1");
  s.addText([{ text: "Ý nghĩa cho hệ của nhóm: ", options: { bold: true, color: C.ink } },
    { text: "trên bộ dữ liệu này, cải thiện khâu tìm kiếm gần như không còn dư địa; điểm số phụ thuộc vào việc trích xuất giữ được bao nhiêu chi tiết và mô hình suy luận ra sao.", options: { color: C.text } }],
    { x: 0.6, y: 4.8, w: 8.7, h: 0.5, fontFace: BF, fontSize: 11.5, valign: "middle", isTextBox: true, margin: 0 });
}

// 8 ─ Soi tay model chấm
{
  const A = MR.mau_cham_dung, W = MR.mau_cham_sai;
  const s = base("Model chấm đáng tin, nhưng hơi khắt khe", "ĐỘ TIN CẬY CỦA PHÉP ĐO",
    `Soi tay ${A.n} câu được chấm đúng và toàn bộ ${W.n} câu bị chấm sai. Không có câu nào được chấm đúng oan; có ${W.so_dang_ngo} câu nhóm cho rằng đáng lẽ nên tính đúng, nên accuracy thật có thể cao hơn khoảng ${num1(W.so_dang_ngo / done * 100)} điểm.`);

  const stats = [[`${A.so_cham_sai}/${A.n}`, C.teal, "câu chấm đúng bị sai", "Soi ngẫu nhiên trong nhóm được chấm đúng. Không có câu nào được cho điểm oan."],
                 [`${W.so_dang_ngo}/${W.n}`, C.amber, "câu chấm sai đáng ngờ", "Soi toàn bộ nhóm bị chấm sai. Hai câu dưới đây nhóm thấy nên tính đúng."]];
  stats.forEach((b, i) => {
    const x = 0.4 + i * 4.65;
    card(s, x, 1.3, 4.45, 1.3);
    s.addText(b[0], { x: x + 0.15, y: 1.45, w: 1.35, h: 0.75, align: "center", fontFace: HF, fontSize: 30, bold: true, color: b[1], valign: "middle", isTextBox: true, margin: 0 });
    s.addText(b[2], { x: x + 1.6, y: 1.42, w: 2.7, h: 0.4, fontFace: BF, fontSize: 12.5, bold: true, color: C.ink, valign: "middle", isTextBox: true, margin: 0 });
    s.addText(b[3], { x: x + 1.6, y: 1.82, w: 2.7, h: 0.85, fontFace: BF, fontSize: 10.5, color: C.text, valign: "top", isTextBox: true, margin: 0 });
  });

  const hdr = (t) => ({ text: t, options: { bold: true, color: "FFFFFF", fill: { color: C.teal } } });
  const cut = (t, n) => (t.length > n ? t.slice(0, n - 1).trimEnd() + "…" : t);
  const rowsT = [[hdr("Đáp án gốc"), hdr("Hệ trả lời"), hdr("Vì sao nhóm thấy đáng ngờ")]];
  MR.cac_cau_dang_ngo.forEach((c) => rowsT.push([cut(c.dap_an_goc, 120), cut(c.he_tra_loi, 135), cut(c.vi_sao_dang_ngo, 165)]));
  s.addTable(rowsT, { x: 0.4, y: 2.75, w: 9.1, colW: [2.7, 3.0, 3.4], fontFace: BF, fontSize: 9,
    color: C.text, border: { type: "solid", color: C.line, pt: 0.75 }, valign: "middle", rowH: 0.72 });

  card(s, 0.4, 5.02, 9.1, 0.48, C.pale);
  s.addText([{ text: "Vì vậy: ", options: { bold: true, color: C.ink } },
    { text: "giữ nguyên kế hoạch chấm 3 lần lấy trung bình, và dùng đúng một model chấm cho cả LightMem lẫn APEX-MEM để sai lệch này triệt tiêu khi so sánh.", options: { color: C.text } }],
    { x: 0.6, y: 5.04, w: 8.7, h: 0.44, fontFace: BF, fontSize: 10.5, valign: "middle", isTextBox: true, margin: 0 });
}

// 10 ─ Chi phí so sánh
{
  const R = CP.apex_report, L = CP.lm_cost;
  const s = base("Cả hai hệ đều tốn nhất ở bước dựng bộ nhớ", "CHI PHÍ VÀ THỜI GIAN",
    "LightMem: thời gian dựng trung vị 33 phút, trả lời 3 giây. APEX-MEM: 88% token nằm ở bước dựng. Thời gian đo trong điều kiện chạy song song khác nhau nên không dùng để kết luận hệ nào nhanh hơn. Chưa có số token của LightMem.");
  const hdr = (t) => ({ text: t, options: { bold: true, color: "FFFFFF", fill: { color: C.teal }, align: "center" } });
  const c = (t, o = {}) => ({ text: t, options: { align: "center", ...o } });
  const rows = [[{ text: "Mỗi câu hỏi", options: { bold: true, color: "FFFFFF", fill: { color: C.teal } } }, hdr("LightMem"), hdr("APEX-MEM")],
    ["Dựng bộ nhớ, trung vị", c(`${L.build_min_median.toFixed(0)} phút`), c(`${num1(R.build_lat_p50_p95_s[0] / 60)} phút`)],
    ["Dựng bộ nhớ, p95", c(`${L.build_min_p95.toFixed(0)} phút`), c(`${num1(R.build_lat_p50_p95_s[1] / 60)} phút`)],
    ["Trả lời, trung vị", c(`${num1(L.answer_s_median)} giây`), c(`${num1(R.answer_lat_p50_p95_s[0])} giây`)],
    ["Lời gọi LLM khi dựng", c("chưa ghi", { color: C.mute }), c(num1(R.build_calls))],
    ["Token khi dựng", c("chưa ghi", { color: C.mute }), c(`${thou(R.build_tokens)} (${num1(R.build_share)}% tổng)`)],
    ["Token khi trả lời", c("chưa ghi", { color: C.mute }), c(thou(R.answer_tokens))]];
  s.addTable(rows, { x: 0.5, y: 1.3, w: 9, colW: [3.4, 2.6, 3.0], fontFace: BF, fontSize: 12, color: C.text,
    border: { type: "solid", color: C.line, pt: 0.75 }, valign: "middle", rowH: 0.42 });
  const pts = [
    "Thời gian đo khi chạy song song khác nhau (LightMem 5–9 luồng, APEX-MEM 2–8 luồng) và bị hạn mức tài khoản làm chậm: chỉ để tham khảo, không dùng để nói hệ nào nhanh hơn.",
    "LightMem chưa có số token: script không ghi lại, và 9router chèn thêm khoảng 2.500 token vào mỗi lời gọi nên số đếm qua router bị phình.",
    `APEX-MEM phục vụ đúng model: ${thou(R.served_models["gpt-5.6-luna"])} lời gọi luna và ${R.served_models["gpt-5.6-terra"]} lời gọi terra (chấm), không có model nào bị đổi lén.`];
  s.addText(pts.map((t, i) => ({ text: t, options: { bullet: true, breakLine: i < pts.length - 1, paraSpaceAfter: 5 } })),
    { x: 0.5, y: 4.35, w: 9, h: 1.1, fontFace: BF, fontSize: 10.5, color: C.text, valign: "top", isTextBox: true, margin: 0 });
}

// 8 ─ Sự cố
{
  const s = base("Sự cố gặp phải và cách xử lý", "SỰ CỐ KỸ THUẬT", "Các lỗi này đều nằm ở môi trường chạy, không phải ở thiết kế baseline.");
  const hdr = (t) => ({ text: t, options: { bold: true, color: "FFFFFF", fill: { color: C.teal } } });
  const rows = [[hdr("Sự cố"), hdr("Nguyên nhân"), hdr("Cách xử lý")],
    ["Script gốc không chạy", "Dùng f-string kiểu Python 3.12, môi trường là 3.11", "Viết script bọc ngoài, không sửa mã gốc"],
    ["Lỗi “meta tensor” khi chạy song song", "Nhiều luồng cùng nạp model, đụng nhau", "Khóa phần nạp model; mỗi luồng nạp một lần"],
    ["Cạn RAM (pagefile)", "Nạp lại model cho từng câu, không giải phóng kịp", "Cache model theo luồng, dọn bộ nhớ sau mỗi câu"],
    ["Windows chặn Python", "Smart App Control chặn file chưa ký", "Bật/tắt lại Smart App Control"],
    ["Hết hạn mức (429), rồi token bị thu hồi (401)", "Tài khoản gói free; chạy 8 luồng cạn nhanh, sau đó 2 token OAuth bị vô hiệu", "Giảm số luồng; đăng nhập lại từ đầu; chờ hạn mức mở lại"],
    ["9router tắt giữa chừng", "Chưa xác định chắc; nghi máy ngủ hoặc tiến trình bị đóng", "Chạy 9router trong terminal riêng; chạy lại lệnh cũ để tiếp tục"]];
  s.addTable(rows, { x: 0.5, y: 1.4, w: 9, colW: [2.5, 3.4, 3.1], fontFace: BF, fontSize: 11, color: C.text, border: { type: "solid", color: C.line, pt: 0.75 }, valign: "middle", rowH: 0.55 });
}

// 9 ─ Tổng kết
{
  const s = pres.addSlide();
  s.background = { color: C.ink };
  s.addText("Chưa có bằng chứng APEX-MEM hơn LightMem", { x: 0.7, y: 0.45, w: 8.6, h: 0.75, fontFace: HF, fontSize: 28, bold: true, color: "FFFFFF", isTextBox: true, margin: 0 });
  s.addText(partial ? `Số liệu trên ${done}/${total} câu dev` : `Đã chạy đủ ${total} câu dev`, { x: 0.7, y: 1.2, w: 8.6, h: 0.35, fontFace: BF, fontSize: 14, bold: true, color: C.amber, isTextBox: true, margin: 0 });
  const asst = S.types.find((t) => t.type === "single-session-assistant");
  const pv = CP.paired.mcnemar_p.toFixed(2).replace(".", ",");
  const left = [`Cả hai hệ chạy đủ ${total} câu dev, cùng model trả lời, cùng model chấm, cùng prompt chấm.`,
    `APEX-MEM ${pct(CP.apex.micro)}, LightMem ${pct(CP.lm.micro)}; McNemar p = ${pv}, chưa khác biệt.`,
    `Chênh lệch nằm ở loại lượt trợ lý (+${CP.by_type["single-session-assistant"].apex - CP.by_type["single-session-assistant"].lm}); năm loại còn lại LightMem hơn nhẹ.`,
    "Nguyên nhân nghi là cấu hình: LightMem chỉ lưu lượt người dùng, APEX-MEM lưu cả hai.",
    "Cả hai hệ truy xuất gần như không sai; lỗi nằm ở trích xuất và suy luận."];
  s.addText(left.map((t, i) => ({ text: t, options: { bullet: true, breakLine: i < left.length - 1, paraSpaceAfter: 8 } })),
    { x: 0.7, y: 1.72, w: 4.3, h: 2.45, fontFace: BF, fontSize: 12, color: "E6EEF7", valign: "top", isTextBox: true, margin: 0 });
  s.addText("Bước tiếp", { x: 5.3, y: 1.75, w: 4.0, h: 0.35, fontFace: HF, fontSize: 16, bold: true, color: C.amber, isTextBox: true, margin: 0 });
  const nxt = ["Chạy lại LightMem loại lượt trợ lý (17 câu) với messages_use = user_assistant để so công bằng.",
    "Chấm 3 lần lấy trung bình cho cả hai hệ, đúng kế hoạch đánh giá.",
    `Soi ${CP.paired.only_apex + CP.paired.only_lm} câu hai hệ trả lời khác nhau để biết mỗi hệ mạnh ở đâu.`,
    "Chốt với anh: chạy cả 350 câu test hay một mẫu con có phân tầng, vì hạn mức tài khoản."];
  s.addText(nxt.map((t, i) => ({ text: `${i + 1}.  ${t}`, options: { breakLine: i < nxt.length - 1, paraSpaceAfter: 8 } })),
    { x: 5.3, y: 2.12, w: 4.0, h: 2.05, fontFace: BF, fontSize: 11.5, color: "E6EEF7", valign: "top", isTextBox: true, margin: 0 });
  const tiles = [[`${pct(CP.apex.micro)} · ${pct(CP.lm.micro)}`, "APEX-MEM · LightMem, gộp chung"], [`p = ${pv}`, "McNemar, chưa khác biệt"]];
  tiles.forEach((t, i) => {
    const x = 0.7 + i * 4.6;
    s.addShape(pres.shapes.RECTANGLE, { x, y: 4.25, w: 4.0, h: 0.85, fill: { color: "1B3457" }, line: { color: "2C4A73", width: 0.75 } });
    s.addText(t[0], { x: x + 0.15, y: 4.35, w: 2.2, h: 0.65, fontFace: HF, fontSize: 21, bold: true, color: C.amber, valign: "middle", isTextBox: true, margin: 0 });
    s.addText(t[1], { x: x + 2.4, y: 4.35, w: 1.5, h: 0.65, fontFace: BF, fontSize: 11.5, color: "B9C9DD", valign: "middle", isTextBox: true, margin: 0 });
  });
  s.addNotes("Slide tổng kết tự cập nhật theo stats.json. Khi chạy xong 150 câu, chạy lại gen_stats.py và build_deck.js.");
}

pres.writeFile({ fileName: OUT }).then(() => console.log("OK", OUT));
