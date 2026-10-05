# -*- coding: utf-8 -*-
import json, io, time, sys
sys.stdout.reconfigure(encoding="utf-8")
import crawl_tuvi as c

PER = {"https://tuvi.khosachquy.com": 250, "https://khamthientuhoa.com": 150}
total = 0
with io.open("tuvi_kb.jsonl", "w", encoding="utf-8") as out:
    for src in c.SOURCES:
        base = src["base"].rstrip("/")
        cap = PER.get(base, 120)
        try:
            bai = sorted(c.thu_thap_url_bai(src))
        except Exception as e:
            print("gather err", base, e); continue
        print(base, "->", len(bai), "bai, cap", cap)
        n = 0
        for url in bai:
            if n >= cap:
                break
            try:
                h = c.fetch(url)
                title, content = c.lam_sach(h)
                if len(content) < 200:
                    continue
                rec = {"id": "KB-%d" % (abs(hash(url)) % 10**10), "url": url,
                       "source": base, "phai": src.get("phai", ""),
                       "title": title, "content": content[:12000]}
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                n += 1; total += 1
            except Exception:
                pass
            time.sleep(0.1)
        print(base, "saved", n)
print("DONE total", total)
