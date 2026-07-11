FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# system deps สำหรับ psycopg2 + Pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev libjpeg-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# รวม static ตอน build
RUN SECRET_KEY=build DEBUG=False python manage.py collectstatic --noinput

EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60"]
