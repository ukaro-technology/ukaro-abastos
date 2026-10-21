#!/bin/sh
# Arranque del contenedor cuando corre solo (Render con Docker, demos).
# En el servidor de Leida NO se usa: docker-compose.yml define su propio `command`.
set -e
python manage.py migrate --noinput
python manage.py collectstatic --noinput
if [ "$BUSINESS_PROFILE" = "motoparts" ]; then
    # Datos de ejemplo del demo SuperMoto Speed, solo si la base está vacía
    python manage.py seed_motoparts_demo --if-empty
fi
exec gunicorn bodega_system.wsgi:application \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers "${WEB_CONCURRENCY:-3}" \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -
