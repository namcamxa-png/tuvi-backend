# 🚀 Hướng dẫn Deploy Backend AI Đại sư Tử Vi

Backend gồm các file (để CHUNG một thư mục):
```
main.py
tu_vi_engine.py
system_prompt.py
database_phu.json
requirements.txt
Dockerfile
.dockerignore
```

> ⚠️ **API key:** KHÔNG bao giờ ghi key vào code. Luôn truyền qua biến môi trường `ANTHROPIC_API_KEY`.

---

## A. Chạy thử trên máy (không Docker)

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...        # Windows: set ANTHROPIC_API_KEY=sk-ant-...
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```
Mở http://localhost:8000/health để kiểm tra. Mở `frontend-luan-giai.html` (sửa `API_BASE="http://localhost:8000"`) để thử giao diện.

---

## B. Deploy bằng Docker (VPS / máy chủ riêng)

```bash
# 1. Build image
docker build -t tuvi-api .

# 2. Chạy container (thay key thật)
docker run -d --name tuvi-api -p 8000:8000 \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  --restart unless-stopped \
  tuvi-api

# 3. Kiểm tra
curl http://localhost:8000/health
```

### Gắn domain + HTTPS (khuyên dùng Nginx reverse proxy)
Trỏ `api.ungdungcamxa.com` về IP VPS, rồi tạo file Nginx:
```nginx
server {
    listen 80;
    server_name api.ungdungcamxa.com;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```
Bật SSL miễn phí:
```bash
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d api.ungdungcamxa.com
```

---

## C. Deploy lên Render.com (nhanh, không cần VPS)

1. Đẩy code lên một repo GitHub (gồm các file trên).
2. Vào **render.com** → **New → Web Service** → chọn repo.
3. Cấu hình:
   - **Environment:** Docker (Render tự nhận `Dockerfile`), hoặc Python với:
     - **Build Command:** `pip install -r requirements.txt`
     - **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Environment Variables:** thêm `ANTHROPIC_API_KEY = sk-ant-...`
4. Deploy → Render cấp URL dạng `https://tuvi-api.onrender.com`.
5. Trong `frontend-luan-giai.html`, đổi `API_BASE` thành URL đó.

> 💡 Railway.app, Fly.io cũng làm tương tự (đều nhận Dockerfile sẵn).

---

## D. Nối vào website ungdungcamxa.com

- Cách 1: Đưa trang `frontend-luan-giai.html` lên hosting (đổi `API_BASE` sang domain API thật).
- Cách 2: Trong web hiện tại, thay nút "Lập lá số" để **gọi API backend** (lấy bài luận của đại sư) thay vì chỉ luận tại chỗ. Logic fetch y như trong `frontend-luan-giai.html`.

### ⚠️ CORS
Trong `main.py`, production nên đổi:
```python
allow_origins=["https://ungdungcamxa.com"]
```
thay cho `["*"]` để chỉ cho web của mình gọi API.

---

## Chi phí vận hành (ước tính)
- **Claude API:** trả theo token mỗi lần luận giải (vài trăm → ~2000 token output/lượt). Nên đặt giới hạn số lượt/ngày hoặc yêu cầu khách để lại SĐT trước khi luận (vừa kiểm soát chi phí, vừa thu lead).
- **Hosting backend:** VPS rẻ (~2-5 USD/tháng) hoặc Render free tier (ngủ khi không dùng) / trả phí để luôn bật.
