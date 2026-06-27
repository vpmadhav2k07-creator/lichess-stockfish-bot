# Step 1: Base footprint (Never changes - Cached)
FROM python:3.10-slim

# FIX: Force Python to unbuffer stdout/stderr and flush logs instantly
ENV PYTHONUNBUFFERED=1

# Step 2: System dependencies (Rarely changes - Heavily Cached)
RUN apt-get update && apt-get install -y \
    stockfish \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Step 3: Python library cache layer (Only runs if requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Step 4: App code (Changes often - Only builds the diff, instantly)
COPY bot.py .

CMD ["python", "bot.py"]
