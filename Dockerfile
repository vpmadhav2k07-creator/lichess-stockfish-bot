# Step 1: Build on top of standard Python lightweight image
FROM python:3.10-slim

# Step 2: Force system updates and explicitly install the Stockfish binary
RUN apt-get update && apt-get install -y \
    stockfish \
    && rm -rf /var/lib/apt/lists/*

# Step 3: Configure workspace environmental pathways
WORKDIR /app

# Step 4: Inject and execute python dependency caching 
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Step 5: Copy code script assets 
COPY . .

# Step 6: Launch application entrypoint
CMD ["python", "bot.py"]
