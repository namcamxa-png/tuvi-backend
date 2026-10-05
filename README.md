# 🔮 AI Đại Sư Tử Vi — Backend (Ứng Dụng Cảm Xạ)

Backend FastAPI luận giải lá số Tử Vi Đẩu Số bằng Claude API, nhập vai đại sư **Thái Bình Sơn Nhân**.
Lập lá số bằng `py-iztro`, lọc Phú cổ (RAG) từ `database_phu.json`, rồi gọi Claude sinh bài luận.

## 📂 Cấu trúc thư mục
```
tuvi-backend/
├── main.py              # FastAPI app + endpoint /luan-giai
├── tu_vi_engine.py      # Lập lá số (py-iztro)
├── system_prompt.py     # SYSTEM_PROMPT đại sư Thái Bình Sơn Nhân
├── database_phu.json    # Kho Phú cổ (RAG) — 40 câu, có keywords/tags/sao_chinh
├── requirements.txt     # Thư viện
├── Dockerfile           # Đóng gói container
├── .dockerignore
├── .gitignore
└── README.md
```

## ⚙️ Cài đặt & chạy local
```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...      # Windows: set ANTHROPIC_API_KEY=...
uvicorn main:app --reload --port 8000
```
- Kiểm tra: `GET http://localhost:8000/health`
- Tài liệu API tự sinh (Swagger): `http://localhost:8000/docs`

## 🔌 API
### `POST /luan-giai` — luận giải (THU PHÍ)
```json
{ "nam":1990, "thang":8, "ngay":16, "gio":14, "gioi_tinh":"nam", "ma_kich_hoat":"TV-ABCD1234" }
```
→ `{ "luan_giai":"<Markdown>", "phu_trich":[...], "la_so":{...} }`

### `POST /hoi-dai-su` — khách hỏi, Đại sư trả lời (THU PHÍ)
```json
{ "nam":1990,"thang":8,"ngay":16,"gio":14,"gioi_tinh":"nam","ma_kich_hoat":"TV-ABCD1234","cau_hoi":"Năm nay sự nghiệp con thế nào?" }
```
→ `{ "tra_loi":"<Markdown>", "cau_hoi":"..." }`

### `POST /admin/tao-ma` — tạo mã kích hoạt (cần header `X-Admin-Token`)
```json
{ "so_luot":5, "so_ma":1, "ghi_chu":"KH Nguyễn Văn A - CK 99k" }
```
→ `{ "da_tao":[ {"ma":"TV-XXXXXXXX","luot_con":5,...} ] }`

## 💰 Cơ chế thu phí (không cần cổng thanh toán)
1. Khách chuyển khoản (QR VietQR / Zalo / MoMo) cho Sếp.
2. Sếp gọi `/admin/tao-ma` (hoặc sửa tay `access_codes.json`) để tạo **mã kích hoạt** (mỗi mã N lượt), gửi mã cho khách.
3. Khách nhập mã trên web → mỗi lần luận/hỏi trừ 1 lượt; hết lượt thì mua gói mới.
> Nâng cấp sau: nối **PayOS/VNPay/MoMo** để tự tạo mã ngay sau khi thanh toán (cần tài khoản merchant).

Tạo nhanh 1 mã 5 lượt:
```bash
curl -X POST http://localhost:8000/admin/tao-ma -H "X-Admin-Token: $ADMIN_TOKEN" \
  -H "Content-Type: application/json" -d "{\"so_luot\":5,\"so_ma\":1}"
```

## 🔐 Biến môi trường
| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `ANTHROPIC_API_KEY` | (bắt buộc) | Khóa Claude API |
| `ADMIN_TOKEN` | (nên đặt) | Mật khẩu để gọi `/admin/tao-ma` |
| `REQUIRE_CODE` | `true` | Bật thu phí (bắt buộc mã). Đặt `false` để chạy miễn phí lúc test |
| `CODES_PATH` | `access_codes.json` | File lưu mã kích hoạt |
| `CLAUDE_MODEL` | `claude-3-5-sonnet-latest` | Model dùng để luận |
| `PHU_DB_PATH` | `database_phu.json` | Đường dẫn kho Phú |
| `MAX_PHU` | `8` | Số câu phú tối đa đưa vào ngữ cảnh |

> ⚠️ `access_codes.json` là dữ liệu chạy thật — khi deploy Docker nên **mount volume** để không mất mã khi restart (vd `-v /data/tuvi:/app`).

## 🚀 Deploy
Xem **DEPLOY.md** (Docker/VPS + Nginx SSL, hoặc Render.com). Tóm tắt Docker:
```bash
docker build -t tuvi-api .
docker run -d -p 8000:8000 -e ANTHROPIC_API_KEY=sk-ant-... --restart unless-stopped tuvi-api
```

## 🖥️ Frontend
- `frontend-luan-giai.html` — trang demo gọi API (đổi `API_BASE`).
- Hoặc dùng web chính `ungdungcamxa` — đặt `window.UCX_API_BASE = "https://api.ungdungcamxa.com"` để bật nút “Thỉnh Đại sư luận giải (AI)” trong tab Tử Vi.

## ⚠️ Ghi chú
- Nội dung luận mang tính **tham khảo**, không thay thế tư vấn y tế/pháp lý/tài chính.
- Production: đổi CORS `allow_origins` về đúng domain; cân nhắc yêu cầu SĐT trước khi luận để kiểm soát chi phí API & thu lead.

## 💳 Thanh toán TỰ ĐỘNG qua MBBank (VietQR + SePay webhook)
Khách quét QR chuyển khoản → hệ thống tự nhận tiền → tự sinh mã → web tự mở khóa (Sếp không cần gửi mã tay).

**Luồng:** `/tao-don` tạo QR VietQR (nội dung CK = mã đơn `UCXxxxxxx`) → khách CK → **SePay** (liên kết MBBank) bắn `POST /webhook/thanh-toan` → backend khớp nội dung + số tiền → tạo mã kích hoạt, đánh dấu đơn `paid` → web đang `poll /trang-thai-don/{ma_don}` nhận mã → tự điền.

**Thiết lập 1 lần:**
1. Đăng ký **sepay.vn** (hoặc casso.vn) → liên kết **tài khoản MBBank** của Sếp (đọc biến động số dư).
2. Trong SePay, tạo **Webhook** trỏ tới `https://api.ungdungcamxa.com/webhook/thanh-toan`, đặt **API Key**.
3. Đặt các biến môi trường backend:

| Biến | Ví dụ | Ý nghĩa |
|---|---|---|
| `MB_SO_TK` | `0001234567` | Số TK MBBank nhận tiền |
| `MB_TEN_TK` | `DINH CONG NAM` | Tên chủ TK (IN HOA, không dấu) |
| `MB_BANK_CODE` | `MB` | Mã ngân hàng (MBBank: MB / 970422) |
| `GIA_SO_TIEN` | `99000` | Số tiền mỗi gói (VND) |
| `GIA_SO_LUOT` | `5` | Số lượt mỗi gói |
| `SEPAY_API_KEY` | `xxxxx` | Khớp API Key webhook trong SePay |
| `ORDERS_PATH` | `orders.json` | File lưu đơn hàng |

> `orders.json` & `access_codes.json` là dữ liệu chạy thật → Docker nên mount volume để không mất khi restart.
> Nâng cấp khác: Casso (đổi mapping field webhook), hoặc PayOS (VietQR có cổng chính thức).

## 📚 Nạp TOÀN BỘ kiến thức cho Đại sư (RAG)
Để đại sư "biết nhiều → luận hay", ta **không nhồi hết vào prompt** (tốn & quá ngữ cảnh) mà dùng **RAG**: crawl toàn bộ bài viết vào kho, lúc luận chỉ rút phần liên quan.

**Bước 1 — Crawl (chạy 1 lần hoặc định kỳ):**
```bash
pip install requests trafilatura
python crawl_tuvi.py        # đọc sitemap các nguồn -> tải mọi bài -> lưu tuvi_kb.jsonl
```
Sửa danh sách `SOURCES` trong `crawl_tuvi.py` để thêm nguồn **Nam phái / Bắc phái / Tứ Hóa** (mỗi nguồn gắn nhãn `phai`).

**Bước 2 — Backend tự dùng:** khi có `tuvi_kb.jsonl`, `/luan-giai` và `/hoi-dai-su` **tự truy xuất** (module `rag_tuvi.py`) các đoạn tri thức khớp với sao/cách cục/câu hỏi rồi đưa cho đại sư làm căn cứ. Không cần cấu hình gì thêm.

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `TUVI_KB_PATH` | `tuvi_kb.jsonl` | File kho tri thức RAG |

> ⚖️ **Bản quyền (đọc kỹ):** nội dung crawl thuộc về trang nguồn. Chỉ nên dùng **nội bộ** làm căn cứ luận (RAG trích dẫn ngắn, ghi nguồn). Phát hành lại công khai nguyên văn là rủi ro pháp lý — nên xin phép tác giả/trang nguồn. `tuvi_kb.jsonl` đã được đưa vào `.gitignore` (không commit) → sinh trực tiếp trên server hoặc mount volume.
### 🚀 Nâng cấp RAG lên VECTOR (semantic search)
Tìm theo **ngữ nghĩa** thay vì trùng từ — chính xác hơn nhiều khi kho tới hàng nghìn bài.

**Bước 1 — chọn nhà cung cấp embedding + dựng vector:**
```bash
pip install numpy
# Khuyên dùng Voyage (hệ Anthropic):
export EMBED_PROVIDER=voyage && export VOYAGE_API_KEY=...   && pip install voyageai
# hoặc local (không tốn API):  export EMBED_PROVIDER=local && pip install sentence-transformers
# hoặc để trống -> auto -> "hash" (offline, chạy tạm, chất lượng ~ keyword)
python build_embeddings.py        # tạo tuvi_vectors.npz (+ .meta.jsonl)
```
**Bước 2 — backend tự dùng:** nếu có `tuvi_vectors.npz`, `rag_tuvi.py` **tự chuyển sang vector search**; nếu không có (hoặc lỗi provider) **tự fallback về tìm từ khóa**. Không cần sửa code.

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `EMBED_PROVIDER` | `auto` | voyage / openai / local / hash / auto |
| `VOYAGE_API_KEY` / `OPENAI_API_KEY` | — | Khóa nhà cung cấp tương ứng |
| `EMBED_MODEL` | (mặc định theo provider) | Ghi đè tên model embedding |
| `VEC_PATH` | `tuvi_vectors.npz` | File vector |
| `CHUNK_CHARS` | `900` | Độ dài mỗi đoạn chunk |

> ⚠️ Đổi nhà cung cấp/model embedding thì **phải chạy lại `build_embeddings.py`** (chiều vector khác nhau). File vector đã đưa vào `.gitignore`.

## 💸 Tối ưu chi phí Token (đã áp dụng)
Để mỗi lần luận/hỏi rẻ nhất mà vẫn chất lượng:
1. **Gửi TÓM TẮT lá số, không gửi JSON thô.** `tu_vi_engine.tom_tat_la_so()` nén lá số thành text gọn (chỉ chính tinh + độ sáng + tứ hóa + phụ tinh quan trọng + đại hạn/lưu niên) → **cắt ~80–85% token input** so với dump JSON đầy đủ.
2. **Prompt caching.** `system` (bộ prompt đại sư — phần tĩnh, dài) được gắn `cache_control` → các lần gọi trong ~5 phút **giảm tới ~90%** chi phí token của phần system.
3. **Model rẻ cho Hỏi-Đáp.** `/hoi-dai-su` dùng `QA_MODEL` (mặc định **Haiku** — rẻ & nhanh); `/luan-giai` mới dùng Sonnet. Đổi qua `CLAUDE_MODEL` / `QA_MODEL`.
4. **Siết đầu ra & RAG.** `max_tokens` giảm (luận 1500, hỏi 700); RAG chỉ lấy 2–3 đoạn, mỗi đoạn ~550 ký tự.

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `CLAUDE_MODEL` | `claude-3-5-sonnet-latest` | Model luận giải đầy đủ |
| `QA_MODEL` | `claude-3-5-haiku-latest` | Model cho Hỏi-Đáp (rẻ hơn) |

5. **Cache kết quả luận (đã có).** `/luan-giai` lưu bài đã luận theo khóa `(ngày+giờ+giới tính+năm)`. Khách **xem lại** → trả bài từ cache: **0 token, không trừ lượt** (vẫn cần mã hợp lệ). Response có cờ `tu_cache: true/false`. Cache tự làm mới khi sang năm mới (vì có lưu niên).

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `CACHE_ENABLE` | `true` | Bật cache kết quả luận |
| `LUAN_CACHE_PATH` | `luan_cache.json` | File cache (nên mount volume như access_codes.json) |

---
© Ứng Dụng Cảm Xạ · Chuyên gia Đinh Công Nam · Hotline 0985 907 286
