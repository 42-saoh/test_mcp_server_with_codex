FROM python:3.11-slim

# --- 기본 설정 ---
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_HOME=/app

WORKDIR ${APP_HOME}

# --- OS 패키지 ---
# - pyodbc + SQL Server 접속: unixODBC + msodbcsql18
# - faiss-cpu: libgomp1
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    gnupg \
    ca-certificates \
    unixodbc \
    unixodbc-dev \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Microsoft ODBC Driver 18 for SQL Server
# (Debian slim 기준)
RUN set -eux; \
    curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft.gpg; \
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/microsoft.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" > /etc/apt/sources.list.d/microsoft-prod.list; \
    apt-get update; \
    ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18; \
    rm -rf /var/lib/apt/lists/*

# --- Python 의존성 ---
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- 애플리케이션 소스 ---
COPY app ./app
COPY standards ./standards

# 런타임 디렉토리 (볼륨 마운트가 덮어쓸 수 있음)
RUN mkdir -p /data/faiss /app/logs

# MCP HTTP(=streamable-http) 기본 포트
EXPOSE 9700

# NOTE:
# - FastAPI entrypoint is app.main:app.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9700"]
