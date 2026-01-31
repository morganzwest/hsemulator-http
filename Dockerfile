# ================================
# Base image: Python + Debian
# ================================
# NOTE: Python 3.14 image does not exist yet.
# Use 3.13 (stable). Change to python:3.14-slim when available.
FROM python:3.13-slim

# Prevent Python from buffering stdout/stderr
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# ================================
# System dependencies
# ================================
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    gnupg \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# ================================
# Install Node.js (LTS)
# ================================
# Use NodeSource (required for stable crypto on Debian)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && node --version \
    && npm --version

# ================================
# Python dependencies
# ================================
WORKDIR /app

# Copy only requirements first for layer caching
COPY requirements.txt .

RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ================================
# Application code
# ================================
COPY . .

# ================================
# Runtime configuration
# ================================
EXPOSE 8000

# IMPORTANT:
# - Use python -m to ensure correct interpreter
# - run.py already handles Windows vs non-Windows logic
CMD ["python", "run.py"]
