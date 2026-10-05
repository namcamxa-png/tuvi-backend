# -*- coding: utf-8 -*-
"""
tu_vi_engine.py — Module lập lá số Tử Vi Đẩu Số (Bước 1).
Dùng thư viện py-iztro (bản Python của iztro) để an sao tự động.

Cài đặt:  pip install py-iztro
"""

from datetime import date
from py_iztro import Astro

# Khởi tạo 1 lần, tái sử dụng
_astro = Astro()


def gio_sang_timeindex(gio: int) -> int:
    """
    Chuyển giờ sinh (0-23 giờ dương lịch) sang chỉ số canh giờ 0-12 của iztro.
    0: 23h-1h (Tý sớm) ... 12: 23h-23h59 (Tý muộn).
    """
    try:
        gio = int(gio) % 24
    except (TypeError, ValueError):
        gio = 12  # mặc định giờ Ngọ nếu không rõ
    return (gio + 1) // 2  # 0..12 (23h -> 12)


def chuan_hoa_gioi_tinh(gioi_tinh) -> str:
    """Trả về '男' (nam) hoặc '女' (nữ) theo đúng đầu vào thư viện."""
    g = str(gioi_tinh).strip().lower()
    if g in ("nu", "nữ", "female", "f", "woman", "0"):
        return "女"
    return "男"


def _ten_sao(sao) -> str:
    """Lấy tên sao dù dữ liệu là object hay dict."""
    if sao is None:
        return ""
    if isinstance(sao, dict):
        return sao.get("name", "") or ""
    return getattr(sao, "name", "") or ""


def _sao_cua_cung(cung) -> list:
    """Gom tên mọi sao (chính + phụ + lẻ) của một cung."""
    ten = []
    for key in ("major_stars", "minor_stars", "adjective_stars",
                "majorStars", "minorStars", "adjectiveStars"):
        arr = cung.get(key) if isinstance(cung, dict) else getattr(cung, key, None)
        if arr:
            for s in arr:
                nm = _ten_sao(s)
                if nm:
                    ten.append(nm)
    return ten


def _to_dict(obj):
    """Chuyển pydantic object của py-iztro sang dict JSON-serializable."""
    for method in ("model_dump", "dict"):
        fn = getattr(obj, method, None)
        if callable(fn):
            try:
                return fn()
            except Exception:
                continue
    return obj


# ---------- Tóm tắt lá số GỌN để tiết kiệm token (thay cho JSON thô) ----------
def _attr(o, *keys):
    for k in keys:
        v = o.get(k) if isinstance(o, dict) else getattr(o, k, None)
        if v not in (None, ""):
            return v
    return ""

_KEEP_MINOR = {"Tả Phù", "Tả Phụ", "Hữu Bật", "Văn Xương", "Văn Khúc", "Thiên Khôi",
               "Thiên Việt", "Lộc Tồn", "Thiên Mã", "Kình Dương", "Đà La",
               "Hỏa Tinh", "Linh Tinh", "Địa Không", "Địa Kiếp"}

def _cung_tom_tat(cung) -> str:
    ten = _attr(cung, "name")
    br = _attr(cung, "earthly_branch", "earthlyBranch")
    majors = []
    for s in (_attr(cung, "major_stars", "majorStars") or []):
        nm = _ten_sao(s); b = _attr(s, "brightness"); mu = _attr(s, "mutagen")
        majors.append(nm + (f"[{b}]" if b else "") + (f"({mu})" if mu else ""))
    minors = []
    for s in (_attr(cung, "minor_stars", "minorStars") or []):
        nm = _ten_sao(s)
        if nm in _KEEP_MINOR:
            mu = _attr(s, "mutagen")
            minors.append(nm + (f"({mu})" if mu else ""))
    line = f"- {ten} ({br}): " + (", ".join(majors) if majors else "Vô chính diệu")
    if minors:
        line += " | phụ: " + ", ".join(minors)
    return line

def _van_tom_tat(horo) -> str:
    if not horo:
        return ""
    out = []
    for key, label in (("decadal", "Đại hạn"), ("yearly", "Lưu niên")):
        h = _attr(horo, key)
        if not h:
            continue
        stem = _attr(h, "heavenlyStem", "heavenly_stem")
        br = _attr(h, "earthlyBranch", "earthly_branch")
        mut = _attr(h, "mutagen")
        muts = ", ".join(mut) if isinstance(mut, (list, tuple)) else (str(mut) if mut else "")
        out.append(f"{label}: {stem} {br}" + (f"; tứ hóa: {muts}" if muts else ""))
    return "; ".join(out)

def tom_tat_la_so(astrolabe, horo=None) -> str:
    """Tạo bản tóm tắt lá số dạng text ngắn gọn (tiết kiệm token so với JSON thô)."""
    head = (f"Tứ trụ: {_attr(astrolabe,'chinese_date','chineseDate')}. "
            f"Con giáp: {_attr(astrolabe,'zodiac')}. Cung hoàng đạo: {_attr(astrolabe,'sign')}. "
            f"Ngũ hành cục: {_attr(astrolabe,'five_elements_class','fiveElementsClass')}. "
            f"Mệnh chủ: {_attr(astrolabe,'soul')}, Thân chủ: {_attr(astrolabe,'body')}.")
    palaces = _attr(astrolabe, "palaces") or []
    lines = [_cung_tom_tat(c) for c in palaces]
    van = _van_tom_tat(horo)
    return head + "\n12 cung:\n" + "\n".join(lines) + (("\n" + van) if van else "")


def lap_la_so(nam: int, thang: int, ngay: int, gio: int, gioi_tinh) -> dict:
    """
    Lập lá số Tử Vi.
    Trả về dict gồm:
      - la_so: toàn bộ dữ liệu lá số (dict)
      - van_trinh: dữ liệu đại hạn/lưu niên năm hiện tại (dict) nếu lấy được
      - tat_ca_sao: set tên tất cả sao xuất hiện trên lá số
      - menh_vo_chinh_dieu: bool (cung Mệnh không có chính tinh)
    """
    date_str = f"{int(nam)}-{int(thang)}-{int(ngay)}"
    time_index = gio_sang_timeindex(gio)
    gender = chuan_hoa_gioi_tinh(gioi_tinh)

    astrolabe = _astro.by_solar(date_str, time_index, gender, True, "vi-VN")

    # Gom sao & xác định Mệnh vô chính diệu
    tat_ca_sao = set()
    menh_vo_chinh_dieu = False
    palaces = getattr(astrolabe, "palaces", None) or []
    for cung in palaces:
        tat_ca_sao.update(_sao_cua_cung(cung))
        ten_cung = (cung.get("name") if isinstance(cung, dict)
                    else getattr(cung, "name", "")) or ""
        if "mệnh" in ten_cung.lower():
            major = (cung.get("major_stars") if isinstance(cung, dict)
                     else getattr(cung, "major_stars", None)) or \
                    (cung.get("majorStars") if isinstance(cung, dict)
                     else getattr(cung, "majorStars", None)) or []
            menh_vo_chinh_dieu = len(major) == 0

    # Vận trình năm hiện tại (đại hạn + lưu niên)
    van_trinh = None
    horo = None
    try:
        today = date.today().strftime("%Y-%m-%d")
        horo = astrolabe.horoscope(today)
        van_trinh = _to_dict(horo)
    except Exception:
        van_trinh = None

    # Bản tóm tắt gọn (tiết kiệm token khi gửi cho Claude)
    try:
        tom_tat = tom_tat_la_so(astrolabe, horo)
    except Exception:
        tom_tat = ""

    return {
        "la_so": _to_dict(astrolabe),
        "van_trinh": van_trinh,
        "tom_tat": tom_tat,
        "tat_ca_sao": tat_ca_sao,
        "menh_vo_chinh_dieu": menh_vo_chinh_dieu,
    }
