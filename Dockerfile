# Dockerfile — AI Đại sư Tử Vi (FastAPI backend)
FROM python:3.12-slim

WORKDIR /app

# Cài thư viện (đều có wheel sẵn -> build nhanh, không cần gcc/Rust)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Chép toàn bộ source
COPY . .

EXPOSE 8000

ENV CLAUDE_MODEL=claude-3-5-sonnet-latest \
    PHU_DB_PATH=database_phu.json \
    MAX_PHU=8

# Render/Railway truyền $PORT -> shell form để đọc được biến
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
