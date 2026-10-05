# -*- coding: utf-8 -*-
"""
main.py — Server backend FastAPI cho "AI Đại sư Tử Vi" (Ứng Dụng Cảm Xạ).

Tính năng:
  - POST /luan-giai      : lập lá số + lọc Phú (RAG) + Claude luận giải  (CÓ THU PHÍ: cần mã kích hoạt)
  - POST /hoi-dai-su     : khách hỏi — Đại sư trả lời theo lá số          (CÓ THU PHÍ: cần mã kích hoạt)
  - POST /admin/tao-ma   : tạo mã kích hoạt sau khi khách thanh toán      (cần X-Admin-Token)
  - GET  /health

Cơ chế thu phí (không cần cổng thanh toán):
  Khách chuyển khoản (QR/Zalo) -> Sếp tạo "mã kích hoạt" (mỗi mã có N lượt) -> khách nhập mã để dùng.
  Mỗi lần luận/hỏi trừ 1 lượt. Hết lượt -> mã vô hiệu.
  (Nâng cấp sau: nối cổng tự động PayOS/VNPay/MoMo để tạo mã tự động sau khi thanh toán thành công.)

Cài đặt:
  pip install fastapi "uvicorn[standard]" anthropic py-iztro
Chạy:
  export ANTHROPIC_API_KEY=sk-ant-...     (Windows: set ANTHROPIC_API_KEY=...)
  export ADMIN_TOKEN=matkhau-admin-cua-sep
  uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

import os
import re
import json
import time
import secrets
import logging
import threading
from urllib.parse import quote

import rag_tuvi   # kho tri thức RAG (tuvi_kb.jsonl)
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import anthropic

# Lá số thường do WEB (iztro JS) tính sẵn và gửi lên -> backend KHÔNG cần py-iztro.
# Vẫn thử nạp engine py-iztro để tương thích ngược; không có cũng chạy bình thường.
try:
    from tu_vi_engine import lap_la_so
except Exception as _e:  # py-iztro/PythonMonkey không cài được trên server -> bỏ qua
    lap_la_so = None

from system_prompt import SYSTEM_PROMPT, PROMPT_HOIDAP

# ------------------------------------------------------------------ cấu hình
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tuvi-api")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-latest")   # luận giải đầy đủ
QA_MODEL = os.getenv("QA_MODEL", "claude-3-5-haiku-latest")           # Hỏi-Đáp (rẻ hơn)
PHU_DB_PATH = os.getenv("PHU_DB_PATH", "database_phu.json")
MAX_PHU = int(os.getenv("MAX_PHU", "8"))

# Thu phí
REQUIRE_CODE = os.getenv("REQUIRE_CODE", "true").lower() in ("1", "true", "yes")
CODES_PATH = os.getenv("CODES_PATH", "access_codes.json")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "").strip()
GIA_MOI_GOI = os.getenv("GIA_MOI_GOI", "99.000đ / gói 5 lượt")  # chỉ để hiển thị /health

_lock = threading.Lock()

# ------------------------------------------------------------------ kho mã kích hoạt
def _load_codes() -> dict:
    try:
        with open(CODES_PATH, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        logger.error("Lỗi đọc %s: %s", CODES_PATH, e)
        return {}

def _save_codes(data: dict):
    tmp = CODES_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CODES_PATH)

def verify_code(ma, consume: bool = True) -> None:
    """Kiểm tra mã kích hoạt; consume=True thì trừ 1 lượt. Lỗi 402 nếu không hợp lệ.
    consume=False dùng khi khách XEM LẠI bài đã cache (không trừ lượt, chỉ cần mã từng hợp lệ)."""
    if not REQUIRE_CODE:
        return
    if not ma:
        raise HTTPException(status_code=402, detail="Cần mã kích hoạt. Vui lòng thanh toán để nhận mã.")
    ma = ma.strip().upper()
    with _lock:
        codes = _load_codes()
        info = codes.get(ma)
        if not info:
            raise HTTPException(status_code=402, detail="Mã kích hoạt không đúng.")
        if consume:
            if int(info.get("luot_con", 0)) <= 0:
                raise HTTPException(status_code=402, detail="Mã đã hết lượt. Vui lòng mua gói mới.")
            info["luot_con"] = int(info["luot_con"]) - 1
            codes[ma] = info
            _save_codes(codes)

# ------------------------------------------------------------------ cache kết quả luận
LUAN_CACHE_PATH = os.getenv("LUAN_CACHE_PATH", "luan_cache.json")
CACHE_ENABLE = os.getenv("CACHE_ENABLE", "true").lower() in ("1", "true", "yes")

def _cache_key(req) -> str:
    # gắn năm hiện tại để tự làm mới khi sang năm mới (vì luận có lưu niên)
    nam_now = time.localtime().tm_year
    return f"{req.nam}-{req.thang}-{req.ngay}-{req.gio}-{str(req.gioi_tinh).lower()}-{nam_now}"

def _cache_get(key):
    if not CACHE_ENABLE:
        return None
    try:
        with open(LUAN_CACHE_PATH, encoding="utf-8") as f:
            return json.load(f).get(key)
    except Exception:
        return None

def _cache_set(key, value):
    if not CACHE_ENABLE:
        return
    with _lock:
        try:
            with open(LUAN_CACHE_PATH, encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            d = {}
        d[key] = value
        tmp = LUAN_CACHE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
        os.replace(tmp, LUAN_CACHE_PATH)

def tao_ma(so_luot: int = 5, so_ma: int = 1, ghi_chu: str = "") -> List[dict]:
    out = []
    with _lock:
        codes = _load_codes()
        for _ in range(max(1, so_ma)):
            ma = "TV-" + secrets.token_hex(4).upper()
            codes[ma] = {"luot_con": int(so_luot), "ghi_chu": ghi_chu}
            out.append({"ma": ma, "luot_con": int(so_luot), "ghi_chu": ghi_chu})
        _save_codes(codes)
    return out

# ------------------------------------------------------------------ thanh toán tự động (VietQR + webhook MBBank)
MB_SO_TK = os.getenv("MB_SO_TK", "").strip()          # số tài khoản MBBank của Sếp
MB_TEN_TK = os.getenv("MB_TEN_TK", "").strip()        # tên chủ TK (IN HOA, không dấu)
MB_BANK_CODE = os.getenv("MB_BANK_CODE", "MB").strip()# MBBank: "MB" hoặc "970422"
GIA_SO_TIEN = int(os.getenv("GIA_SO_TIEN", "99000"))  # số tiền mỗi gói (VND)
GIA_SO_LUOT = int(os.getenv("GIA_SO_LUOT", "5"))      # số lượt mỗi gói
QR_TEMPLATE = os.getenv("QR_TEMPLATE", "compact2")    # kiểu ảnh VietQR
ORDERS_PATH = os.getenv("ORDERS_PATH", "orders.json")
SEPAY_API_KEY = os.getenv("SEPAY_API_KEY", "").strip()# token xác thực webhook (SePay/Casso)

def _load_orders() -> dict:
    try:
        with open(ORDERS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        logger.error("Lỗi đọc %s: %s", ORDERS_PATH, e)
        return {}

def _save_orders(data: dict):
    tmp = ORDERS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, ORDERS_PATH)

def vietqr_url(noi_dung: str, so_tien: int) -> str:
    return (f"https://img.vietqr.io/image/{MB_BANK_CODE}-{MB_SO_TK}-{QR_TEMPLATE}.png"
            f"?amount={so_tien}&addInfo={quote(noi_dung)}&accountName={quote(MB_TEN_TK)}")

def tao_don(so_luot: int, so_tien: int) -> str:
    ma_don = "UCX" + secrets.token_hex(3).upper()      # alphanumeric, an toàn qua nội dung CK
    with _lock:
        orders = _load_orders()
        orders[ma_don] = {"so_tien": int(so_tien), "so_luot": int(so_luot),
                          "trang_thai": "pending", "ma_kich_hoat": None, "tao_luc": time.time()}
        _save_orders(orders)
    return ma_don

# ------------------------------------------------------------------ nạp kho Phú
def _load_phu_db(path: str) -> list:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        logger.info("Đã nạp %d câu phú từ %s", len(data), path)
        return data
    except FileNotFoundError:
        logger.warning("Không tìm thấy %s — chạy không có RAG phú.", path)
        return []
    except Exception as e:
        logger.error("Lỗi đọc %s: %s", path, e)
        return []

PHU_DB = _load_phu_db(PHU_DB_PATH)

# ------------------------------------------------------------------ Claude client
def _get_client() -> anthropic.Anthropic:
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=500, detail="Chưa cấu hình ANTHROPIC_API_KEY trên server.")
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

def goi_claude(system_prompt: str, user_content: str, max_tokens: int = 1500,
               temperature: float = 0.8, model: str = None) -> str:
    client = _get_client()
    # Gọi có khả năng tự thích ứng với nhiều phiên bản SDK anthropic:
    # nếu SDK không nhận 'temperature' -> bỏ; nếu không nhận system dạng list
    # (prompt caching) -> hạ về system dạng chuỗi.
    base_params = dict(
        model=model or CLAUDE_MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": user_content}],
    )
    sys_cache = [{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}]

    def _try(params):
        return client.messages.create(**params)

    # Model đời mới (Claude 5) mặc định BẬT "thinking" -> ăn hết token, không còn chỗ
    # viết bài. Tắt thinking để model viết thẳng bài luận. Giữ cache_control để rẻ.
    no_think = {"type": "disabled"}
    try:
        attempts = [
            dict(base_params, system=sys_cache, thinking=no_think),           # tắt thinking + cache (ưu tiên)
            dict(base_params, system=system_prompt, thinking=no_think),       # tắt thinking, system chuỗi
            dict(base_params, system=sys_cache, temperature=temperature),     # (SDK không nhận thinking) cache + temp
            dict(base_params, system=sys_cache),                              # cache
            dict(base_params, system=system_prompt),                          # tối giản
        ]
        resp = None
        last_err = None
        for p in attempts:
            try:
                resp = _try(p)
                break
            except (TypeError, anthropic.APIStatusError, anthropic.APIConnectionError) as e:
                last_err = e
                continue
        if resp is None:
            raise last_err or RuntimeError("Không gọi được Claude")
    except anthropic.APIStatusError as e:
        logger.error("Claude API lỗi: %s", e)
        raise HTTPException(status_code=502, detail=f"Claude API lỗi: {getattr(e,'status_code','?')}")
    except anthropic.APIConnectionError:
        raise HTTPException(status_code=503, detail="Không kết nối được tới Claude API.")
    except Exception as e:
        logger.exception("Lỗi gọi Claude")
        raise HTTPException(status_code=500, detail=f"Lỗi khi gọi Claude: {e}")
    # Trích text từ mọi khối content (bỏ qua khối thinking/khác)
    parts = []
    for b in (resp.content or []):
        t = getattr(b, "text", None)
        if t:
            parts.append(t)
    ket_qua = "\n".join(parts).strip()
    if not ket_qua:
        types = [getattr(b, "type", "?") for b in (resp.content or [])]
        sr = getattr(resp, "stop_reason", "?")
        logger.error("Claude rỗng: stop_reason=%s block_types=%s", sr, types)
        raise HTTPException(status_code=502,
            detail=f"Claude không trả về nội dung (stop_reason={sr}, blocks={types}).")
    return ket_qua

# ------------------------------------------------------------------ FastAPI app
app = FastAPI(title="AI Đại sư Tử Vi — Ứng Dụng Cảm Xạ", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # production: ["https://ungdungcamxa.com"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------------ schema
class LaSoRequest(BaseModel):
    nam: int = Field(..., ge=1920, le=2030)
    thang: int = Field(..., ge=1, le=12)
    ngay: int = Field(..., ge=1, le=31)
    gio: int = Field(..., ge=0, le=23)
    gioi_tinh: str
    ma_kich_hoat: Optional[str] = None
    # Lá số do WEB (iztro) lập sẵn gửi lên (ưu tiên dùng, backend khỏi cần py-iztro)
    tom_tat: Optional[str] = None
    tat_ca_sao: Optional[List[str]] = None
    menh_vo_chinh_dieu: Optional[bool] = False


def _lay_la_so(req: "LaSoRequest"):
    """Trả về (tom_tat, tat_ca_sao:set, menh_vo_chinh_dieu).
    Ưu tiên lá số web (iztro) gửi lên; nếu không có thì thử py-iztro (nếu cài được)."""
    if req.tom_tat:
        return req.tom_tat, set(req.tat_ca_sao or []), bool(req.menh_vo_chinh_dieu)
    if lap_la_so is None:
        raise HTTPException(status_code=400,
            detail="Thiếu dữ liệu lá số. Vui lòng bấm 'Tra cứu / lập lá số' trên web trước khi thỉnh Đại sư.")
    kq = lap_la_so(req.nam, req.thang, req.ngay, req.gio, req.gioi_tinh)
    return kq.get("tom_tat", ""), set(kq.get("tat_ca_sao", set())), bool(kq.get("menh_vo_chinh_dieu", False))

class HoiDapRequest(LaSoRequest):
    cau_hoi: str = Field(..., min_length=3, max_length=500)

class TaoMaRequest(BaseModel):
    so_luot: int = Field(5, ge=1, le=100)
    so_ma: int = Field(1, ge=1, le=50)
    ghi_chu: str = ""

# ------------------------------------------------------------------ RAG lọc Phú
def loc_phu(tat_ca_sao: set, menh_vo_chinh_dieu: bool, phu_db: list) -> list:
    matched = []
    for p in phu_db:
        sc = p.get("sao_chinh") or []
        if sc:
            if all(s in tat_ca_sao for s in sc):
                matched.append(p)
        elif menh_vo_chinh_dieu and "vô chính diệu" in p.get("cach_cuc", "").lower():
            matched.append(p)
    matched.sort(key=lambda x: len(x.get("sao_chinh") or []), reverse=True)
    return matched[:MAX_PHU]

def _phu_text(phu: list) -> str:
    return "\n\n".join(
        f"- Cách cục: {p.get('cach_cuc','')}\n  Câu phú: {p.get('cau_phu_han','')}\n"
        f"  Nghĩa: {p.get('nghia_han_viet','')}\n  Ứng dụng: {p.get('luan_giai_hien_dai','')}"
        for p in phu
    ) or "(Không có câu phú đặc biệt.)"

def _kb_text(snips: list) -> str:
    if not snips:
        return ""
    return "\n\n".join(
        f"- [{s.get('phai','')}] {s.get('title','')}\n  {s.get('trich','')}" for s in snips
    )

def _terms_tu_phu(phu: list) -> list:
    terms = [p.get("cach_cuc", "") for p in phu]
    for p in phu:
        terms += (p.get("sao_chinh") or [])
    return terms

# ------------------------------------------------------------------ endpoints
@app.get("/health")
def health():
    return {"status": "ok", "model": CLAUDE_MODEL, "so_cau_phu": len(PHU_DB),
            "thu_phi": REQUIRE_CODE, "gia": GIA_MOI_GOI}

@app.post("/luan-giai")
def luan_giai(req: LaSoRequest):
    key = _cache_key(req)
    cached = _cache_get(key)
    if cached:
        # Xem lại bài đã luận: cần mã hợp lệ nhưng KHÔNG trừ lượt, KHÔNG gọi API (0 token)
        verify_code(req.ma_kich_hoat, consume=False)
        return {"luan_giai": cached.get("luan_giai", ""), "phu_trich": cached.get("phu_trich", []),
                "la_so": None, "tu_cache": True}
    verify_code(req.ma_kich_hoat, consume=True)   # tạo mới -> trừ 1 lượt (THU PHÍ)
    try:
        tom_tat, tat_ca_sao, menh_vcd = _lay_la_so(req)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Lỗi lập lá số")
        raise HTTPException(status_code=400, detail=f"Không lập được lá số: {e}")
    try:
        phu = loc_phu(tat_ca_sao, menh_vcd, PHU_DB)
    except Exception:
        phu = []
    try:
        kb = rag_tuvi.tim_tri_thuc(_terms_tu_phu(phu), k=3, max_chars=550)
    except Exception:
        kb = []
    kb_block = (f"Tri thức tham khảo (RAG, làm căn cứ, không chép nguyên văn):\n{_kb_text(kb)}\n\n" if kb else "")
    user_content = (
        "Lá số của Mệnh chủ (bản tóm tắt):\n"
        f"{tom_tat}\n\n"
        f"Câu phú cổ ứng với lá số:\n{_phu_text(phu)}\n\n"
        f"{kb_block}"
        "Xin đại sư luận giải đầy đủ theo quy trình 4 bước."
    )
    luan = goi_claude(SYSTEM_PROMPT, user_content, max_tokens=4000, temperature=0.8)
    _cache_set(key, {"luan_giai": luan, "phu_trich": phu})
    return {"luan_giai": luan, "phu_trich": phu, "la_so": None, "tu_cache": False}

@app.post("/hoi-dai-su")
def hoi_dai_su(req: HoiDapRequest):
    verify_code(req.ma_kich_hoat, consume=True)   # THU PHÍ
    try:
        tom_tat, tat_ca_sao, menh_vcd = _lay_la_so(req)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Không lập được lá số: {e}")
    try:
        phu = loc_phu(tat_ca_sao, menh_vcd, PHU_DB)
    except Exception:
        phu = []
    try:
        terms = [t for t in re.findall(r"\w+", req.cau_hoi, flags=re.UNICODE) if len(t) >= 2]
        terms += _terms_tu_phu(phu)
        kb = rag_tuvi.tim_tri_thuc(terms, k=2, max_chars=550)
    except Exception:
        kb = []
    kb_block = (f"Tri thức tham khảo:\n{_kb_text(kb)}\n\n" if kb else "")
    user_content = (
        "Tóm tắt lá số của Mệnh chủ:\n"
        f"{tom_tat}\n\n"
        f"{kb_block}"
        f"Câu hỏi của Mệnh chủ: {req.cau_hoi.strip()}\n\n"
        "Xin đại sư trả lời đúng trọng tâm, dựa trên lá số."
    )
    tra_loi = goi_claude(PROMPT_HOIDAP, user_content, max_tokens=1500, temperature=0.85, model=QA_MODEL)
    return {"tra_loi": tra_loi, "cau_hoi": req.cau_hoi}

@app.post("/admin/tao-ma")
def admin_tao_ma(req: TaoMaRequest, x_admin_token: Optional[str] = Header(default=None)):
    if not ADMIN_TOKEN or x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Sai hoặc thiếu X-Admin-Token.")
    ma_moi = tao_ma(req.so_luot, req.so_ma, req.ghi_chu)
    return {"da_tao": ma_moi}

# ------------------------------------------------------------------ thanh toán tự động
class TaoDonRequest(BaseModel):
    so_luot: Optional[int] = None

@app.post("/tao-don")
def tao_don_endpoint(req: TaoDonRequest):
    """Tạo đơn thanh toán: trả về QR VietQR (MBBank) + nội dung CK để khách quét."""
    if not MB_SO_TK:
        raise HTTPException(status_code=500, detail="Server chưa cấu hình tài khoản MBBank (MB_SO_TK, MB_TEN_TK).")
    so_luot = int(req.so_luot or GIA_SO_LUOT)
    ma_don = tao_don(so_luot, GIA_SO_TIEN)
    return {
        "ma_don": ma_don,
        "so_tien": GIA_SO_TIEN,
        "so_luot": so_luot,
        "ngan_hang": "MBBank",
        "so_tai_khoan": MB_SO_TK,
        "ten_tai_khoan": MB_TEN_TK,
        "noi_dung_ck": ma_don,
        "qr_url": vietqr_url(ma_don, GIA_SO_TIEN),
        "huong_dan": f"Chuyển {GIA_SO_TIEN:,}đ tới MBBank {MB_SO_TK} ({MB_TEN_TK}) — nội dung: {ma_don}",
    }

@app.get("/trang-thai-don/{ma_don}")
def trang_thai_don(ma_don: str):
    """Frontend gọi định kỳ để biết đã thanh toán chưa; trả mã kích hoạt khi xong."""
    o = _load_orders().get(ma_don.strip().upper())
    if not o:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn.")
    return {"trang_thai": o["trang_thai"], "ma_kich_hoat": o.get("ma_kich_hoat")}

@app.post("/webhook/thanh-toan")
def webhook_thanh_toan(payload: dict, authorization: Optional[str] = Header(default=None)):
    """
    Nhận biến động số dư từ SePay/Casso (đã liên kết MBBank).
    SePay gửi header: Authorization: Apikey <SEPAY_API_KEY>
    Payload (SePay) gồm: transferType ('in'), transferAmount, content, ...
    """
    if SEPAY_API_KEY:
        if not authorization or SEPAY_API_KEY not in authorization:
            raise HTTPException(status_code=401, detail="Sai API key webhook.")

    noi_dung = str(payload.get("content") or payload.get("description") or payload.get("addInfo") or "")
    loai = str(payload.get("transferType") or payload.get("type") or "in").lower()
    so_tien_raw = payload.get("transferAmount") or payload.get("amount") or payload.get("creditAmount") or 0
    try:
        so_tien = int(float(so_tien_raw))
    except (TypeError, ValueError):
        so_tien = 0

    if loai not in ("in", "money_in", "credit", "cong", ""):
        return {"success": True, "ignored": "không phải tiền vào"}

    key = noi_dung.replace(" ", "").upper()
    with _lock:
        orders = _load_orders()
        matched = None
        for ma_don, o in orders.items():
            if o["trang_thai"] == "pending" and ma_don in key and so_tien >= int(o["so_tien"]):
                matched = (ma_don, o)
                break
        if not matched:
            return {"success": True, "note": "không khớp đơn pending nào"}
        ma_don, o = matched
        ma_kich_hoat = "TV-" + secrets.token_hex(4).upper()
        codes = _load_codes()
        codes[ma_kich_hoat] = {"luot_con": int(o["so_luot"]), "ghi_chu": "Auto " + ma_don}
        _save_codes(codes)
        o["trang_thai"] = "paid"
        o["ma_kich_hoat"] = ma_kich_hoat
        orders[ma_don] = o
        _save_orders(orders)
    logger.info("Đã thanh toán đơn %s -> mã %s", ma_don, ma_kich_hoat)
    return {"success": True, "ma_don": ma_don, "ma_kich_hoat": ma_kich_hoat}

# ------------------------------------------------------------------ chạy trực tiếp
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
