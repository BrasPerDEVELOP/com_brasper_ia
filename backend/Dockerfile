# LangChain 0.2.x resolves NumPy 1.26, which does not provide Python 3.13
# wheels. Keep the runtime on Python 3.11 until those dependencies are upgraded.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
WORKDIR /app/backend

EXPOSE 8002
CMD ["sh", "-c", "python manage.py migrate && uvicorn main:app --host 0.0.0.0 --port 8002"]
