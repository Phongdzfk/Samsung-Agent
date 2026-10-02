"""Ghép "phần LightMem" (part-lightmem-wide.pptx) vào SAU deck tuần 4 của nhóm -> một file .pptx.

Không sửa file gốc của ai: đọc hai file, ghi ra file thứ ba.

Cách làm (mức gói OOXML, vì hai deck cùng do pptxgenjs dựng nên cùng bộ khung: 1 layout, 1 master,
1 notesMaster, khổ 13,33x7,5 inch):
  - chép slide / notesSlide / chart / embedding của phần LightMem sang, đổi số thứ tự cho không trùng;
  - cập nhật [Content_Types].xml, presentation.xml (danh sách slide), presentation.xml.rels, app.xml.

Chạy:  PART=1 node build_deck.js && python merge_decks.py
"""
import re
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent.parent / "Tuan 4" / "bao-cao-tuan4-apexmem.pptx"
PART = HERE / "part-lightmem-wide.pptx"
OUT = HERE.parent.parent / "Tuan 4" / "bao-cao-tuan4-tong-hop-apexmem-lightmem.pptx"

REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def count(names, pat):
    return len([n for n in names if re.fullmatch(pat, n)])


def main():
    zb, zp = zipfile.ZipFile(BASE), zipfile.ZipFile(PART)
    parts = {n: zb.read(n) for n in zb.namelist()}
    nb, npart = zb.namelist(), zp.namelist()

    n_slides_b = count(nb, r"ppt/slides/slide\d+\.xml")
    n_slides_p = count(npart, r"ppt/slides/slide\d+\.xml")
    n_charts_b = count(nb, r"ppt/charts/chart\d+\.xml")
    n_emb_b = len([n for n in nb if n.startswith("ppt/embeddings/") and not n.endswith("/")])
    print(f"gốc: {n_slides_b} slide, {n_charts_b} chart | phần LightMem: {n_slides_p} slide")

    # bảng đổi tên
    slide_map = {i: n_slides_b + i for i in range(1, n_slides_p + 1)}
    chart_map = {j: n_charts_b + j for j in range(1, count(npart, r"ppt/charts/chart\d+\.xml") + 1)}
    emb_old = sorted(n for n in npart if n.startswith("ppt/embeddings/") and not n.endswith("/"))
    emb_map = {}
    for k, name in enumerate(emb_old, start=1):
        ext = name.rsplit(".", 1)[1]
        emb_map[name] = f"ppt/embeddings/Microsoft_Excel_Worksheet{n_emb_b + k}.{ext}"

    # Target có thể là "../charts/chart1.xml" (tương đối) hoặc "/ppt/charts/chart1.xml" (tuyệt đối): giữ nguyên tiền tố
    PFX = r'Target="((?:\.\./)|(?:/ppt/))'

    def remap_rel_targets(text, slide_ctx=None):
        text = re.sub(PFX + r'slides/slide(\d+)\.xml"', lambda m: f'Target="{m.group(1)}slides/slide{slide_map[int(m.group(2))]}.xml"', text)
        text = re.sub(PFX + r'notesSlides/notesSlide(\d+)\.xml"', lambda m: f'Target="{m.group(1)}notesSlides/notesSlide{slide_map[int(m.group(2))]}.xml"', text)
        text = re.sub(PFX + r'charts/chart(\d+)\.xml"', lambda m: f'Target="{m.group(1)}charts/chart{chart_map[int(m.group(2))]}.xml"', text)
        text = re.sub(PFX + r'embeddings/([^"]+)"',
                      lambda m: f'Target="{m.group(1)}embeddings/' + emb_map["ppt/embeddings/" + m.group(2)].split("/")[-1] + '"', text)
        return text

    for i, ni in slide_map.items():
        parts[f"ppt/slides/slide{ni}.xml"] = zp.read(f"ppt/slides/slide{i}.xml")
        parts[f"ppt/slides/_rels/slide{ni}.xml.rels"] = remap_rel_targets(
            zp.read(f"ppt/slides/_rels/slide{i}.xml.rels").decode("utf-8")).encode("utf-8")
        nn = f"ppt/notesSlides/notesSlide{i}.xml"
        if nn in npart:
            parts[f"ppt/notesSlides/notesSlide{ni}.xml"] = zp.read(nn)
            parts[f"ppt/notesSlides/_rels/notesSlide{ni}.xml.rels"] = remap_rel_targets(
                zp.read(f"ppt/notesSlides/_rels/notesSlide{i}.xml.rels").decode("utf-8")).encode("utf-8")
    for j, nj in chart_map.items():
        parts[f"ppt/charts/chart{nj}.xml"] = zp.read(f"ppt/charts/chart{j}.xml")
        parts[f"ppt/charts/_rels/chart{nj}.xml.rels"] = remap_rel_targets(
            zp.read(f"ppt/charts/_rels/chart{j}.xml.rels").decode("utf-8")).encode("utf-8")
    for old, new in emb_map.items():
        parts[new] = zp.read(old)

    # [Content_Types].xml
    ct = parts["[Content_Types].xml"].decode("utf-8")
    add = []
    for ni in slide_map.values():
        add.append(f'<Override PartName="/ppt/slides/slide{ni}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>')
        add.append(f'<Override PartName="/ppt/notesSlides/notesSlide{ni}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.notesSlide+xml"/>')
    for nj in chart_map.values():
        add.append(f'<Override PartName="/ppt/charts/chart{nj}.xml" ContentType="application/vnd.openxmlformats-officedocument.drawingml.chart+xml"/>')
    ct = ct.replace("</Types>", "".join(add) + "</Types>")
    parts["[Content_Types].xml"] = ct.encode("utf-8")

    # presentation.xml.rels + presentation.xml
    prel = parts["ppt/_rels/presentation.xml.rels"].decode("utf-8")
    max_rid = max(int(x) for x in re.findall(r'Id="rId(\d+)"', prel))
    pres = parts["ppt/presentation.xml"].decode("utf-8")
    max_sid = max(int(x) for x in re.findall(r'<p:sldId id="(\d+)"', pres))
    rel_add, sld_add = [], []
    for k, ni in enumerate(slide_map.values(), start=1):
        rid = f"rId{max_rid + k}"
        rel_add.append(f'<Relationship Id="{rid}" Type="{REL_NS}/slide" Target="slides/slide{ni}.xml"/>')
        sld_add.append(f'<p:sldId id="{max_sid + k}" r:id="{rid}"/>')
    prel = prel.replace("</Relationships>", "".join(rel_add) + "</Relationships>")
    pres = pres.replace("</p:sldIdLst>", "".join(sld_add) + "</p:sldIdLst>", 1)
    parts["ppt/_rels/presentation.xml.rels"] = prel.encode("utf-8")
    parts["ppt/presentation.xml"] = pres.encode("utf-8")

    # docProps/app.xml: số slide
    if "docProps/app.xml" in parts:
        app = parts["docProps/app.xml"].decode("utf-8")
        app = re.sub(r"<Slides>\d+</Slides>", f"<Slides>{n_slides_b + n_slides_p}</Slides>", app)
        parts["docProps/app.xml"] = app.encode("utf-8")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    order = ["[Content_Types].xml"] + [n for n in parts if n != "[Content_Types].xml"]
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as zo:
        for n in order:
            zo.writestr(n, parts[n])
    print(f"đã ghi {OUT.name}: {n_slides_b + n_slides_p} slide")


if __name__ == "__main__":
    sys.exit(main())
