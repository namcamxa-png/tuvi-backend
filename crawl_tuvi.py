# -*- coding: utf-8 -*-
"""
crawl_tuvi.py — Nạp TOÀN BỘ bài viết Tử Vi vào kho tri thức RAG (tuvi_kb.jsonl).

Chạy script này 1 lần (hoặc định kỳ) để "đại sư có đủ kiến thức".
Nó đọc sitemap của từng nguồn -> lấy mọi URL bài -> tải & làm sạch -> lưu 1 dòng JSON/bài.

Cài đặt:
    pip install requests trafilatura   (trafilatura để tách nội dung sạch; nếu thiếu sẽ dùng regex)

Chạy:
    python crawl_tuvi.py

⚠️ BẢN QUYỀN: nội dung thuộc về trang nguồn. Chỉ dùng kho này cho mục đích THAM KHẢO NỘI BỘ
   của hệ thống luận giải (RAG trích dẫn), nên ghi nguồn; nếu phát hành lại công khai cần xin phép.
"""

import os
import re
import json
import time
import html
import urllib.request
from urllib.parse import urlparse

# ----- Cấu hình nguồn -----
# Mỗi nguồn:
#   base            : tên miền
#   phai            : nhãn phân loại (tong-hop / nam-phai / bac-phai / tu-hoa...)
#   hint (tùy chọn) : URL bài phải CHỨA chuỗi này (vd "/bai/"). Để "" nếu bài là slug gốc.
#   sitemap_filter  : chỉ quét các sitemap con có tên chứa chuỗi này (vd "post" cho WordPress).
SOURCES = [
    {"base": "https://tuvi.khosachquy.com", "phai": "tong-hop", "hint": "/bai/"},
    {"base": "https://khamthientuhoa.com",  "phai": "khamthien-tuhoa", "hint": "", "sitemap_filter": "post"},
    # Thêm nguồn Nam/Bắc phái của Sếp tại đây, ví dụ:
    # {"base": "https://<nguon-nam-phai>", "phai": "nam-phai", "hint": ""},
    # {"base": "https://<nguon-bac-phai>", "phai": "bac-phai", "hint": ""},
]
OUT_PATH = os.getenv("KB_OUT", "tuvi_kb.jsonl")
DELAY = float(os.getenv("CRAWL_DELAY", "0.5"))   # giây nghỉ giữa request
MAX_ARTICLES = int(os.getenv("MAX_ARTICLES", "0"))  # 0 = tải hết; >0 = giới hạn số bài
TIMEOUT = 20
UA = "Mozilla/5.0 (compatible; UngDungCamXa-KB/1.0)"
EXCLUDE = ("/tag/", "/category/", "/hoi-dap", "/tim-kiem", "/gioi-thieu", "/ebook")

try:
    import trafilatura  # tách nội dung bài rất sạch
    HAS_TRAF = True
except Exception:
    HAS_TRAF = False


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        raw = r.read()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("utf-8", "ignore")


def locs(xml: str) -> list:
    return re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml)


def _la_bai(u: str, base: str, hint: str) -> bool:
    if u.endswith(".xml"):
        return False
    if any(x in u for x in EXCLUDE):
        return False
    if hint:
        return hint in u
    # không có hint: coi là bài nếu là URL con (có path) và không phải trang chủ
    path = u[len(base):].strip("/") if u.startswith(base) else u
    return len(path) > 0 and "/" not in path.rstrip("/")  # slug 1 cấp (kiểu WordPress)


def thu_thap_url_bai(src: dict) -> set:
    """Đọc sitemap index -> các sitemap con -> mọi URL bài (theo hint & sitemap_filter của nguồn)."""
    base = src["base"].rstrip("/")
    hint = src.get("hint", "")
    smf = src.get("sitemap_filter", "")
    urls = set()
    try:
        idx = fetch(base + "/sitemap.xml")
    except Exception as e:
        print("  [!] Không đọc được sitemap:", e)
        return urls
    subs = locs(idx)
    sitemaps = [u for u in subs if u.endswith(".xml")] or [base + "/sitemap.xml"]
    if smf:
        sitemaps = [s for s in sitemaps if smf in s]
    for sm in sitemaps:
        try:
            xml = fetch(sm)
        except Exception:
            continue
        for u in locs(xml):
            if u.endswith(".xml"):
                try:
                    for u2 in locs(fetch(u)):
                        if _la_bai(u2, base, hint):
                            urls.add(u2)
                except Exception:
                    pass
            elif _la_bai(u, base, hint):
                urls.add(u)
        time.sleep(DELAY)
    return urls


def lam_sach(htmltext: str) -> tuple:
    """Trả (title, content_text) — tách đúng ruột bài, bỏ menu/breadcrumb/player/footer."""
    m = re.search(r"<title[^>]*>(.*?)</title>", htmltext, re.S | re.I)
    title = html.unescape(re.sub(r"\s+", " ", m.group(1)).strip()) if m else ""
    title = re.split(r"\s[—|]\s", title)[0].strip()

    # Ưu tiên trafilatura (sạch nhất) nếu có cài
    if HAS_TRAF:
        t = trafilatura.extract(htmltext, include_comments=False, include_tables=False)
        if t and len(t) > 200:
            return title, t

    # Fallback: cắt theo container nội dung phổ biến + bỏ đuôi
    h = re.sub(r"(?is)<(script|style|head|nav|header|footer|aside).*?</\1>", " ", htmltext)
    m2 = re.search(r'<(?:div|article|section)[^>]*class="[^"]*(?:article-content|entry-content|post-content|td-post-content|article-body)[^"]*"[^>]*>', h, re.I)
    if m2:
        h = h[m2.end():]
    low = h.lower()
    for mk in ["bài viết liên quan", "bài viết mới", "related", "article-card",
               "entry-footer", "chia sẻ bài", "bình luận"]:
        j = low.find(mk)
        if j != -1:
            h = h[:j]; low = h.lower()
    h = re.sub(r"(?s)<[^>]+>", " ", h)
    txt = html.unescape(re.sub(r"\s+", " ", h)).strip()
    for bp in ["Trang chủ ›", "Nghe bài viết", "📋 Mục lục", "🔊", "▶ Nghe", "Copy link", "Facebook"]:
        txt = txt.replace(bp, " ")
    return title, re.sub(r"\s+", " ", txt).strip()


def main():
    seen = set()
    n = 0
    with open(OUT_PATH, "w", encoding="utf-8") as out:
        for src in SOURCES:
            base, phai = src["base"], src.get("phai", "")
            print(f"== Nguồn {base} ({phai}) ==")
            bai = thu_thap_url_bai(src)
            print(f"   Tìm thấy {len(bai)} bài")
            for i, url in enumerate(sorted(bai), 1):
                if MAX_ARTICLES and n >= MAX_ARTICLES:
                    print(f"   (đạt giới hạn MAX_ARTICLES={MAX_ARTICLES})")
                    break
                if url in seen:
                    continue
                seen.add(url)
                try:
                    htmltext = fetch(url)
                    title, content = lam_sach(htmltext)
                    if len(content) < 200:
                        continue
                    rec = {
                        "id": f"KB-{abs(hash(url)) % (10**10)}",
                        "url": url,
                        "source": urlparse(url).netloc,
                        "phai": phai,
                        "title": title,
                        "content": content[:12000],
                    }
                    out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    n += 1
                    if i % 20 == 0:
                        print(f"   ...đã lưu {i}")
                except Exception as e:
                    print("   [bỏ qua]", url, e)
                time.sleep(DELAY)
    print(f"XONG: đã lưu {n} bài vào {OUT_PATH}")


if __name__ == "__main__":
    main()
