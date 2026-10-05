# -*- coding: utf-8 -*-
"""
ingest_pdf.py — Trích text từ các PDF sách Tử Vi -> NẠP (append) vào kho RAG tuvi_kb.jsonl.

Cài: pip install pypdf
Chạy:
    PDF_DIR="D:/BO NAO/.../📥 HỘP NẠP"  python ingest_pdf.py     # hoặc để trống -> tự dò
PDF scan ảnh (không trích được text) sẽ bị BỎ QUA kèm cảnh báo (cần OCR riêng).

⚠️ Bản quyền: chỉ dùng nội bộ làm căn cứ luận (RAG). Sách là tài sản của tác giả/NXB.
"""
import os, re, io, glob, json, sys
from pypdf import PdfReader
sys.stdout.reconfigure(encoding="utf-8")

OUT = os.getenv("TUVI_KB_PATH", "tuvi_kb.jsonl")
SECTION = int(os.getenv("PDF_SECTION", "3000"))   # mỗi record ~3000 ký tự
MIN_DOC = 500                                       # dưới mức này coi là scan/ảnh -> bỏ


def tim_thu_muc():
    env = os.getenv("PDF_DIR")
    if env and os.path.isdir(env):
        return env
    for base in ("D:/BO NAO", "D:/BO NAO/BO NAO NAM HITTECH", "."):
        if not os.path.isdir(base):
            continue
        for root, _dirs, files in os.walk(base):
            if "HỘP NẠP" in root and any(f.lower().endswith(".pdf") for f in files):
                return root
    return "."


def phai_of(name: str) -> str:
    n = name.lower()
    if "tv34" in n or ("nam" in n and ("phai" in n or "phái" in n)):
        return "nam-phai"
    if "trung chau" in n or "trung châu" in n:
        return "bac-phai-trung-chau"
    return "co-dien"


def sections(text: str):
    text = re.sub(r"\s+", " ", text).strip()
    step = max(500, SECTION - 200)
    return [text[i:i + SECTION] for i in range(0, len(text), step)]


def main():
    d = tim_thu_muc()
    print("Thư mục PDF:", d)
    added = 0
    with io.open(OUT, "a", encoding="utf-8") as out:
        for f in sorted(glob.glob(os.path.join(d, "*.pdf"))):
            name = os.path.basename(f)
            try:
                r = PdfReader(f)
                full = []
                for p in r.pages:
                    full.append(p.extract_text() or "")
                text = "\n".join(full)
            except Exception as e:
                print("  [LỖI]", name, e); continue
            if len(text) < MIN_DOC:
                print(f"  [BỎ QUA - scan/ảnh] {name} ({len(r.pages)} trang, {len(text)} ký tự) -> cần OCR")
                continue
            phai = phai_of(name)
            secs = sections(text)
            for k, sec in enumerate(secs, 1):
                rec = {"id": "PDF-%d" % (abs(hash(name + str(k))) % 10**11),
                       "url": "pdf://" + name, "source": "pdf", "phai": phai,
                       "title": f"{os.path.splitext(name)[0]} (phần {k}/{len(secs)})",
                       "content": sec}
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                added += 1
            print(f"  [OK] {name[:40]} -> phái={phai}, {len(secs)} record")
    print("XONG: đã thêm", added, "record vào", OUT)


if __name__ == "__main__":
    main()
