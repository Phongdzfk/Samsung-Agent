// Dựng slide baseline LightMem từ stats.json.  Chạy:  python gen_stats.py && node build_deck.js
const pptxgen = require("pptxgenjs");
const fs = require("fs");
const path = require("path");

const S = JSON.parse(fs.readFileSync(path.join(__dirname, "stats.json"), "utf-8"));
// ket qua soi tay (khong sinh tu dong) — xem ghi chu trong chinh file do
const MR = JSON.parse(fs.readFileSync(path.join(__dirname, "manual_review.json"), "utf-8"));
const OUT = path.join(__dirname, "..", "bao-cao-lightmem-baseline.pptx");

const C = { ink: "10243E", teal: "1F6F8B", mint: "5FB49C", amber: "F2A541", red: "C8553D",
  bg: "F7F9FB", card: "FFFFFF", text: "1B2B3A", mute: "5B6B7A", line: "DCE3EA", pale: "E7F0F4" };
const HF = "Cambria", BF = "Calibri";
const VI = { "single-session-user": "Đơn phiên · người dùng", "single-session-assistant": "Đơn phiên · trợ lý",
  "single-session-preference": "Đơn phiên · sở thích", "multi-session": "Đa phiên",
  "temporal-reasoning": "Suy luận thời gian", "knowledge-update": "Cập nhật kiến thức" };
const pct = (x) => (x == null ? "—" : (x * 100).toFixed(1).replace(".", ",") + "%");
const done = S.n_done, total = S.n_dev;
const partial = done < total;

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9";
pres.title = "Baseline LightMem trên LongMemEval-S";

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
  s.addText("BASELINE LIGHTMEM", { x: 0.7, y: 1.2, w: 8.6, h: 0.4, fontFace: BF, fontSize: 14, bold: true, color: C.amber, isTextBox: true, margin: 0 });
  s.addText("LightMem trên LongMemEval-S", { x: 0.7, y: 1.65, w: 8.6, h: 1.1, fontFace: HF, fontSize: 40, bold: true, color: "FFFFFF", isTextBox: true, margin: 0 });
  s.addText("Đường cơ sở để so sánh với hệ thống của nhóm (APEX-MEM tái hiện)", { x: 0.7, y: 2.85, w: 8.6, h: 0.5, fontFace: BF, fontSize: 18, color: "CADCFC", isTextBox: true, margin: 0 });
  s.addText(`Tuần 3 · ${partial ? `số liệu sơ bộ ${done}/${total} câu dev` : `đủ ${total} câu dev`} · nhóm 2 thành viên · 09/2026`,
    { x: 0.7, y: 4.6, w: 8.6, h: 0.35, fontFace: BF, fontSize: 13, color: "8FA7C4", isTextBox: true, margin: 0 });
  s.addNotes("Deck tổng hợp phần cài đặt và chạy baseline LightMem. Số liệu sinh tự động từ thư mục kết quả; chạy lại gen_stats.py và build_deck.js khi có thêm câu.");
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
    ["LLM trích xuất + trả lời", S.llm || "cx/gpt-5.6-luna"], ["Model chấm", (S.judge || "cx/gpt-5.6-terra") + " — khác model trả lời"],
    ["Prompt chấm", "Prompt chính thức của LongMemEval, theo từng loại câu hỏi"], ["Truy xuất", "Top-20 ký ức, embedding all-MiniLM-L6-v2"]];
  rows.forEach((r, i) => {
    const y = 1.4 + i * 0.6;
    s.addText(r[0], { x: 0.5, y, w: 2.2, h: 0.5, fontFace: BF, fontSize: 12.5, bold: true, color: C.teal, valign: "middle", isTextBox: true, margin: 0 });
    s.addText(r[1], { x: 2.7, y, w: 4.1, h: 0.5, fontFace: BF, fontSize: 12.5, color: C.text, valign: "middle", isTextBox: true, margin: 0 });
  });
  card(s, 7.1, 1.4, 2.4, 3.5);
  s.addText(String(S.n_dev), { x: 7.1, y: 1.6, w: 2.4, h: 0.9, align: "center", fontFace: HF, fontSize: 54, bold: true, color: C.teal, isTextBox: true, margin: 0 });
  s.addText("câu dev để chạy và chỉnh", { x: 7.1, y: 2.5, w: 2.4, h: 0.4, align: "center", fontFace: BF, fontSize: 12, color: C.mute, isTextBox: true, margin: 0 });
  s.addText(String(S.n_test), { x: 7.1, y: 3.2, w: 2.4, h: 0.9, align: "center", fontFace: HF, fontSize: 54, bold: true, color: C.mute, isTextBox: true, margin: 0 });
  s.addText("câu test, khóa đến tuần 7", { x: 7.1, y: 4.1, w: 2.4, h: 0.4, align: "center", fontFace: BF, fontSize: 12, color: C.mute, isTextBox: true, margin: 0 });
}

// 4 ─ Tiến độ theo loại
{
  const s = base("Tiến độ chạy tập dev theo loại câu hỏi", "TIẾN ĐỘ", "Các câu chạy theo thứ tự trong tập dev nên chưa phủ đều 6 loại; loại chưa chạy sẽ chạy ở lượt sau.");
  const labels = S.types.map((t) => VI[t.type]);
  s.addChart(pres.charts.BAR, [
    { name: "Đã chạy", labels, values: S.types.map((t) => t.done) },
    { name: "Còn lại", labels, values: S.types.map((t) => t.dev - t.done) }],
    { x: 0.5, y: 1.3, w: 9, h: 3.7, barDir: "bar", barGrouping: "stacked", chartColors: [C.teal, "C9D5DF"],
      showLegend: true, legendPos: "b", legendFontSize: 11, legendColor: C.mute,
      showValue: true, dataLabelPosition: "ctr", dataLabelColor: "FFFFFF", dataLabelFontSize: 11,
      dataLabelFormatCode: "0;;;",
      catAxisLabelColor: C.text, catAxisLabelFontSize: 11, catAxisOrientation: "maxMin",
      valAxisLabelColor: C.mute, valAxisLabelFontSize: 10, valGridLine: { color: C.line, size: 0.5 }, catGridLine: { style: "none" } });
}

// 5 ─ Kết quả
{
  const asstT = S.types.find((t) => t.type === "single-session-assistant");
  const others = S.types.filter((t) => t.done && t !== asstT).map((t) => t.acc * 100);
  const s = base(`Năm loại đạt ${Math.round(Math.min(...others))}–${Math.round(Math.max(...others))}%, riêng lượt trợ lý ${Math.round(asstT.acc * 100)}%`, "KẾT QUẢ",
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
  s.addText([{ text: "Số liệu sơ bộ. ", options: { bold: true, color: C.red } },
    { text: `${inc.length ? "Chưa chạy đủ: " + inc.map((t) => `${VI[t.type]} ${t.done}/${t.dev}`).join(" · ") + ". " : ""}Nhóm câu từ chối (_abs) mới có ${S.abs.n} câu.`, options: { color: C.text } }],
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
    { text: `${nAsstNoData}/6 câu sai loại lượt trợ lý, hệ trả lời thẳng là không tìm thấy thông tin trong bộ nhớ, khớp với cấu hình user_only.`, options: { color: C.text } }],
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
    { text: "Mỗi ký ức LightMem trả về đều mở đầu bằng mốc thời gian của phiên. Khớp mốc đó với haystack_dates để biết ký ức đến từ phiên nào, rồi so với answer_session_ids của bộ dữ liệu.", options: { color: C.text } }],
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
    `Soi tay ${A.n} câu được chấm đúng và toàn bộ ${W.n} câu bị chấm sai. Không có câu nào được chấm đúng oan; có ${W.so_dang_ngo} câu nhóm cho rằng đáng lẽ nên tính đúng, nên accuracy thật có thể cao hơn khoảng 1,6 điểm.`);

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

// 7 ─ Chi phí
{
  const b = S.build_min;
  const s = base("Dựng bộ nhớ chiếm gần như toàn bộ thời gian", "VẬN HÀNH",
    "Thời gian dựng bộ nhớ chiếm gần như toàn bộ; truy xuất và trả lời rất nhanh. 9router chèn thêm khoảng 2.500 token system prompt vào mỗi lời gọi, nên số token đo qua router bị phình.");
  const stats = [[b ? b.median.toFixed(0) + " phút" : "—", "dựng bộ nhớ mỗi câu (trung vị)"], [S.retrieve_s ? S.retrieve_s.toFixed(2).replace(".", ",") + " s" : "—", "truy xuất"], [S.answer_s ? S.answer_s.toFixed(1).replace(".", ",") + " s" : "—", "sinh câu trả lời"]];
  stats.forEach((st, i) => {
    const x = 0.5 + i * 3.05;
    card(s, x, 1.4, 2.9, 1.5);
    s.addText(st[0], { x, y: 1.5, w: 2.9, h: 0.8, align: "center", fontFace: HF, fontSize: 34, bold: true, color: i === 0 ? C.red : C.teal, isTextBox: true, margin: 0 });
    s.addText(st[1], { x, y: 2.3, w: 2.9, h: 0.4, align: "center", fontFace: BF, fontSize: 12, color: C.mute, isTextBox: true, margin: 0 });
  });
  const pts = [
    "Mỗi câu gọi LLM hàng trăm lần: hội thoại dài chia thành hàng trăm topic, mỗi topic trích fact và xử lý riêng.",
    `Chạy 5–9 luồng song song, mỗi câu ${S.build_min.median.toFixed(0)} phút (chậm nhất ${S.build_min.max.toFixed(0)} phút); cả tập dev cần vài chục giờ.`,
    "9router chèn ~2,5 nghìn token system prompt mỗi lời gọi: khi báo cáo token phải tách phần này ra.",
    "Tài khoản ChatGPT có trần sử dụng: đã chạm giới hạn (429), phải chờ hoặc thêm tài khoản."];
  s.addText(pts.map((t, i) => ({ text: t, options: { bullet: true, breakLine: i < pts.length - 1, paraSpaceAfter: 6 } })),
    { x: 0.5, y: 3.15, w: 9, h: 1.9, fontFace: BF, fontSize: 13, color: C.text, valign: "top", isTextBox: true, margin: 0 });
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
    ["Lỗi 429 usage limit", "Hết hạn mức tài khoản ChatGPT", "Chờ mở lại hoặc thêm tài khoản"]];
  s.addTable(rows, { x: 0.5, y: 1.4, w: 9, colW: [2.5, 3.4, 3.1], fontFace: BF, fontSize: 11, color: C.text, border: { type: "solid", color: C.line, pt: 0.75 }, valign: "middle", rowH: 0.55 });
}

// 9 ─ Tổng kết
{
  const s = pres.addSlide();
  s.background = { color: C.ink };
  s.addText("Baseline chạy được, chưa đủ kết luận", { x: 0.7, y: 0.45, w: 8.6, h: 0.75, fontFace: HF, fontSize: 30, bold: true, color: "FFFFFF", isTextBox: true, margin: 0 });
  s.addText(partial ? `Số liệu trên ${done}/${total} câu dev` : `Đã chạy đủ ${total} câu dev`, { x: 0.7, y: 1.2, w: 8.6, h: 0.35, fontFace: BF, fontSize: 14, bold: true, color: C.amber, isTextBox: true, margin: 0 });
  const asst = S.types.find((t) => t.type === "single-session-assistant");
  const left = [`Cài đặt xong LightMem, chạy đầu-cuối được trên LongMemEval-S với ${S.llm}.`,
    `Chia dev/test khớp bản gốc của nhóm (150/350).`,
    `Sơ bộ: ${pct(S.macro)} macro trên 6/6 loại, ${done}/${total} câu dev.`,
    `Điểm yếu rõ nhất: loại lượt trợ lý chỉ ${pct(asst.acc)}, do cấu hình user_only không lưu lời trợ lý.`,
    `Truy xuất trúng bằng chứng ${S.retrieval.hit}/${S.retrieval.n} câu, nên lỗi nằm ở trích xuất và suy luận.`,
    `Thời gian là nút thắt: ~${S.build_min ? S.build_min.median.toFixed(0) : "?"} phút mỗi câu.`];
  s.addText(left.map((t, i) => ({ text: t, options: { bullet: true, breakLine: i < left.length - 1, paraSpaceAfter: 8 } })),
    { x: 0.7, y: 1.72, w: 4.3, h: 2.45, fontFace: BF, fontSize: 12, color: "E6EEF7", valign: "top", isTextBox: true, margin: 0 });
  s.addText("Bước tiếp", { x: 5.3, y: 1.75, w: 4.0, h: 0.35, fontFace: HF, fontSize: 16, bold: true, color: C.amber, isTextBox: true, margin: 0 });
  const nxt = [`Chạy nốt ${total - done} câu dev còn lại, nhất là nhóm _abs.`,
    "Chạy hệ APEX-MEM cùng model và cùng chấm để so công bằng.",
    "Thử lại LightMem với messages_use = user_assistant, xem loại lượt trợ lý cải thiện bao nhiêu.",
    "Chốt với anh: có chạy cả 350 câu test cho baseline không, vì hạn mức tài khoản.",
    "Chấm 3 lần lấy trung bình, đúng kế hoạch đánh giá."];
  s.addText(nxt.map((t, i) => ({ text: `${i + 1}.  ${t}`, options: { breakLine: i < nxt.length - 1, paraSpaceAfter: 8 } })),
    { x: 5.3, y: 2.12, w: 4.0, h: 2.05, fontFace: BF, fontSize: 11.5, color: "E6EEF7", valign: "top", isTextBox: true, margin: 0 });
  const tiles = [[pct(S.macro), `macro-average, ${S.n_types_run}/6 loại đã chạy`], [`${S.build_min ? S.build_min.median.toFixed(0) : "?"} phút`, "dựng bộ nhớ mỗi câu (trung vị)"]];
  tiles.forEach((t, i) => {
    const x = 0.7 + i * 4.6;
    s.addShape(pres.shapes.RECTANGLE, { x, y: 4.25, w: 4.0, h: 0.85, fill: { color: "1B3457" }, line: { color: "2C4A73", width: 0.75 } });
    s.addText(t[0], { x: x + 0.2, y: 4.35, w: 1.5, h: 0.65, fontFace: HF, fontSize: 26, bold: true, color: C.amber, valign: "middle", isTextBox: true, margin: 0 });
    s.addText(t[1], { x: x + 1.7, y: 4.35, w: 2.1, h: 0.65, fontFace: BF, fontSize: 11.5, color: "B9C9DD", valign: "middle", isTextBox: true, margin: 0 });
  });
  s.addNotes("Slide tổng kết tự cập nhật theo stats.json. Khi chạy xong 150 câu, chạy lại gen_stats.py và build_deck.js.");
}

pres.writeFile({ fileName: OUT }).then(() => console.log("OK", OUT));
