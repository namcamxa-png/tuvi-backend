# -*- coding: utf-8 -*-
"""
build_embeddings.py — Chia nhỏ (chunk) kho tri thức + sinh vector embedding -> lưu để RAG dùng.

Chạy SAU khi đã có tuvi_kb.jsonl:
    # chọn nhà cung cấp:
    export EMBED_PROVIDER=voyage   &&  export VOYAGE_API_KEY=...     # khuyên dùng
    # hoặc: export EMBED_PROVIDER=local   (pip install sentence-transformers)
    # hoặc: để trống -> auto -> hash (offline, chạy tạm)
    python build_embeddings.py

Tạo ra:
    tuvi_vectors.npz           (ma trận vector float32, nén)
    tuvi_vectors.npz.meta.jsonl(metadata từng chunk: title/url/phai/text)
"""

import os
import io
import json
import sys
import numpy as np

import embedder

sys.stdout.reconfigure(encoding="utf-8")

KB_PATH = os.getenv("TUVI_KB_PATH", "tuvi_kb.jsonl")
VEC_PATH = os.getenv("VEC_PATH", "tuvi_vectors.npz")
CHUNK = int(os.getenv("CHUNK_CHARS", "900"))
OVERLAP = int(os.getenv("CHUNK_OVERLAP", "150"))
BATCH = int(os.getenv("EMBED_BATCH", "64"))


def chunk_text(text):
    text = (text or "").strip()
    if len(text) <= CHUNK:
        return [text] if text else []
    out, i = [], 0
    step = max(100, CHUNK - OVERLAP)
    while i < len(text):
        out.append(text[i:i + CHUNK])
        i += step
    return out


def main():
    recs = [json.loads(l) for l in io.open(KB_PATH, encoding="utf-8") if l.strip()]
    meta, texts = [], []
    for r in recs:
        for ch in chunk_text(r.get("content", "")):
            meta.append({"title": r.get("title", ""), "url": r.get("url", ""),
                         "phai": r.get("phai", ""), "text": ch})
            texts.append((r.get("title", "") + ". " + ch)[:2000])
    print(f"Nguồn {len(recs)} bài -> {len(texts)} chunk. Provider: {embedder.chon_provider()}")

    vecs = []
    for i in range(0, len(texts), BATCH):
        vecs.extend(embedder.embed(texts[i:i + BATCH], kind="document"))
        print(f"  embedded {min(i + BATCH, len(texts))}/{len(texts)}")

    arr = np.asarray(vecs, dtype="float32")
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    arr = arr / norms
    np.savez_compressed(VEC_PATH, vecs=arr)
    with io.open(VEC_PATH + ".meta.jsonl", "w", encoding="utf-8") as f:
        for m in meta:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")
    print(f"XONG: {arr.shape} -> {VEC_PATH} (+ .meta.jsonl)")


if __name__ == "__main__":
    main()
