# -*- coding: utf-8 -*-
"""
embedder.py — Sinh vector embedding cho văn bản (phục vụ RAG semantic search).

Tự chọn nhà cung cấp theo biến môi trường EMBED_PROVIDER:
  - "voyage" : Voyage AI (khuyên dùng với hệ Anthropic). Cần VOYAGE_API_KEY. pip install voyageai
  - "openai" : OpenAI embeddings. Cần OPENAI_API_KEY. pip install openai
  - "local"  : sentence-transformers (chạy máy, không tốn phí API). pip install sentence-transformers
  - "hash"   : fallback OFFLINE không cần cài gì (chất lượng thấp, chỉ để test/chạy tạm)
  - "auto"   : (mặc định) voyage nếu có key -> openai nếu có key -> local nếu cài -> hash
"""

import os
import re
import math
import hashlib
import unicodedata

PROVIDER = os.getenv("EMBED_PROVIDER", "auto").lower()
VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
EMBED_MODEL = os.getenv("EMBED_MODEL", "").strip()
HASH_DIM = int(os.getenv("HASH_DIM", "512"))

_local_model = None


def chon_provider() -> str:
    if PROVIDER != "auto":
        return PROVIDER
    if VOYAGE_API_KEY:
        return "voyage"
    if OPENAI_API_KEY:
        return "openai"
    try:
        import sentence_transformers  # noqa
        return "local"
    except Exception:
        return "hash"


# ---------- các nhà cung cấp ----------
def _voyage(texts, kind):
    import voyageai
    cli = voyageai.Client(api_key=VOYAGE_API_KEY)
    model = EMBED_MODEL or "voyage-3-lite"
    itype = "query" if kind == "query" else "document"
    return cli.embed(texts, model=model, input_type=itype).embeddings


def _openai(texts, kind):
    from openai import OpenAI
    cli = OpenAI(api_key=OPENAI_API_KEY)
    model = EMBED_MODEL or "text-embedding-3-small"
    r = cli.embeddings.create(model=model, input=texts)
    return [d.embedding for d in r.data]


def _local(texts, kind):
    global _local_model
    from sentence_transformers import SentenceTransformer
    if _local_model is None:
        _local_model = SentenceTransformer(EMBED_MODEL or "intfloat/multilingual-e5-small")
    prefix = "query: " if kind == "query" else "passage: "
    v = _local_model.encode([prefix + t for t in texts], normalize_embeddings=True)
    return [list(map(float, row)) for row in v]


def _norm_txt(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.findall(r"[a-z0-9]+", s.lower())


def _hash(texts, kind):
    """Bag-of-words hashing -> vector (offline, không phụ thuộc). Chất lượng ~ keyword."""
    out = []
    for t in texts:
        v = [0.0] * HASH_DIM
        for w in _norm_txt(t):
            h = int(hashlib.md5(w.encode()).hexdigest(), 16)
            v[h % HASH_DIM] += 1.0
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        out.append([x / n for x in v])
    return out


def embed(texts, kind="document"):
    """texts: list[str] -> list[list[float]]. kind: 'document' khi nạp, 'query' khi tìm."""
    if not texts:
        return []
    p = chon_provider()
    fn = {"voyage": _voyage, "openai": _openai, "local": _local, "hash": _hash}.get(p, _hash)
    return fn(texts, kind)
