FROM python:3.11-slim

WORKDIR /app

# ffmpeg: faster-whisper decodifica ogg/opus (WhatsApp/Telegram) con él.
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir fastapi uvicorn faster-whisper python-multipart

COPY . .

EXPOSE 8090

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8090"]
