# ===========================
# HuggingFace Spaces Dockerfile
# Port: 7860 (majburiy!)
# ===========================

FROM python:3.10-slim

# System paketlar
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    wget \
    curl \
    libsndfile1 \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Ish papkasi
WORKDIR /app

# Requirements avval (cache uchun)
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Barcha fayllarni ko'chirish
COPY backend/ ./backend/
COPY frontend/ ./frontend/

# Kerakli papkalar
RUN mkdir -p uploads outputs voices

# HuggingFace port 7860 majburiy!
EXPOSE 7860

# Serverni ishga tushirish
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "7860"]
