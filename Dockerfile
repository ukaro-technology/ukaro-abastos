FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Dependencias del sistema para psycopg2 y Pillow
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    libjpeg-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el proyecto Django
COPY bodega_system/ .

EXPOSE 8000

# Migra, junta los estáticos y arranca gunicorn (ver el script). docker-compose.yml
# (servidor de Leida) reemplaza este comando con el suyo.
CMD ["sh", "scripts/start_web.sh"]
