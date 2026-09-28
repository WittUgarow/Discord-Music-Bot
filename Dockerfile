FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y curl unzip ffmpeg \
    && curl -fsSL https://deno.land/install.sh | sh \
    && ln -s /root/.deno/bin/deno /usr/local/bin/deno \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p downloads

CMD ["python", "music-bot.py"]
