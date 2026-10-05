# Dockerfile — AI Đại sư Tử Vi (FastAPI backend)
FROM python:3.12-slim

# Thư mục làm việc trong container
WORKDIR /app

# Cài bộ công cụ biên dịch (gcc + Rust) để build các thư viện con
# như pminit (py-iztro cần) vốn phải biên dịch từ mã nguồn.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential gcc curl ca-certificates \
    && curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
        | sh -s -- -y --default-toolchain stable --profile minimal \
    && rm -rf /var/lib/apt/lists/*
ENV PATH="/root/.cargo/bin:${PATH}"

# Cài thư viện trước (tận dụng cache layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Chép toàn bộ source (main.py, tu_vi_engine.py, system_prompt.py, database_phu.json)
COPY . .

# Cổng chạy
EXPOSE 8000

# Biến môi trường (truyền khi chạy: -e ANTHROPIC_API_KEY=...)
ENV CLAUDE_MODEL=claude-3-5-sonnet-latest \
    PHU_DB_PATH=database_phu.json \
    MAX_PHU=8

# Khởi chạy. Render/Railway truyền $PORT -> dùng shell form để đọc được biến.
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
