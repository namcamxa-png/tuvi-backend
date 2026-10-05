# -*- coding: utf-8 -*-
"""
rag_tuvi.py — Truy xuất kho tri thức Tử Vi cho RAG.

Ưu tiên VECTOR SEMANTIC SEARCH nếu có file vector (tuvi_vectors.npz) -> tìm theo NGỮ NGHĨA.
Nếu không có vector (hoặc thiếu numpy) -> tự động fallback TÌM THEO TỪ KHÓA trên tuvi_kb.jsonl.
"""

import os
import re
import json
import unicodedata

KB_PATH = os.getenv("TUVI_KB_PATH", "tuvi_kb.jsonl")
VEC_PATH = os.getenv("VEC_PATH", "tuvi_vectors.npz")

# ---------------- trạng thái nạp ----------------
_KB = []
_KB_LOADED = False
_VEC = None           # numpy array (N, D) đã chuẩn hóa
_VEC_META = None      # list[dict] song song với _VEC
_VEC_LOADED = False


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.lower()


# ---------------- VECTOR ----------------
def _load_vec():
    global _VEC, _VEC_META, _VEC_LOADED
    if _VEC_LOADED:
        return
    _VEC_LOADED = True
    meta_path = VEC_PATH + ".meta.jsonl"
    if not (os.path.exists(VEC_PATH) and os.path.exists(meta_path)):
        return
    try:
        import numpy as np
        data = np.load(VEC_PATH)
        _VEC = data["vecs"]
        _VEC_META = [json.loads(l) for l in open(meta_path, encoding="utf-8") if l.strip()]
        if len(_VEC_META) != _VEC.shape[0]:
            _VEC = None
            _VEC_META = None
    except Exception:
        _VEC = None
        _VEC_META = None


def _vec_search(query: str, k: int, max_chars: int):
    import numpy as np
    import embedder
    qv = embedder.embed([query], kind="query")[0]
    qv = np.asarray(qv, dtype="float32")
    n = np.linalg.norm(qv) or 1.0
    qv = qv / n
    if qv.shape[0] != _VEC.shape[1]:
        raise ValueError("Chiều vector query khác kho (đổi provider? cần build_embeddings lại).")
    sims = _VEC @ qv
    idx = sims.argsort()[::-1][:k]
    out = []
    for i in idx:
        m = _VEC_META[int(i)]
        out.append({"title": m.get("title", ""), "url": m.get("url", ""),
                    "phai": m.get("phai", ""), "trich": (m.get("text", "") or "")[:max_chars],
                    "score": float(sims[int(i)])})
    return out


# ---------------- KEYWORD (fallback) ----------------
def _load_kb():
    global _KB_LOADED
    if _KB_LOADED:
        return
    _KB_LOADED = True
    if not os.path.exists(KB_PATH):
        return
    try:
        for line in open(KB_PATH, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            r["_norm"] = _norm((r.get("title", "") + " ") * 3 + r.get("content", ""))
            _KB.append(r)
    except Exception:
        pass


def _kw_search(tu_khoa, k, max_chars):
    _load_kb()
    if not _KB:
        return []
    terms = list(dict.fromkeys(_norm(t) for t in tu_khoa if t and len(t) >= 2))
    if not terms:
        return []
    ghi = []
    for r in _KB:
        hay = r["_norm"]
        sc = 0
        for t in terms:
            c = hay.count(t)
            if c:
                sc += min(c, 5) + (3 if t in _norm(r.get("title", "")) else 0)
        if sc:
            ghi.append((sc, r))
    ghi.sort(key=lambda x: x[0], reverse=True)
    out = []
    for sc, r in ghi[:k]:
        content = r.get("content", "")
        low = _norm(content)
        pos = 0
        for t in terms:
            i = low.find(t)
            if i >= 0:
                pos = max(0, i - 120)
                break
        out.append({"title": r.get("title", ""), "url": r.get("url", ""),
                    "phai": r.get("phai", ""), "trich": content[pos:pos + max_chars].strip()})
    return out


# ---------------- API chung ----------------
def co_kho() -> dict:
    _load_vec(); _load_kb()
    return {"vector_chunks": (0 if _VEC is None else int(_VEC.shape[0])), "kb_bai": len(_KB)}


def dung_vector() -> bool:
    _load_vec()
    return _VEC is not None


def tim_tri_thuc(tu_khoa, k: int = 4, max_chars: int = 700):
    """tu_khoa: list[str]. Trả [{title,url,phai,trich}]. Ưu tiên vector, fallback keyword."""
    _load_vec()
    if _VEC is not None:
        try:
            return _vec_search(" ".join([t for t in tu_khoa if t]), k, max_chars)
        except Exception:
            pass  # lỗi provider/chiều -> rơi về keyword
    return _kw_search(tu_khoa, k, max_chars)
