#!/bin/bash
# Respaldo diario de la base de Ukaro Abastos durante la contingencia en PythonAnywhere.
#
# En PA, una tarea programada (23:05 Caracas) copia la base con la API backup de sqlite3 a
# ~/respaldo/abastos.sqlite3 (copia consistente aunque la web esté escribiendo). Este script, que corre en
# la laptop con un timer de systemd del usuario, la descarga, verifica su integridad y guarda las últimas 30.
# Ver docs/CONTINGENCIA-PYTHONANYWHERE.md.
set -euo pipefail

DESTINO="$HOME/respaldos/abastos/pa-diario"
TOKEN_FILE="$HOME/.config/pythonanywhere-token.txt"
URL="https://www.pythonanywhere.com/api/v0/user/Bodegaleida/files/path/home/Bodegaleida/respaldo/abastos.sqlite3"
CONSERVAR=30

mkdir -p "$DESTINO"
chmod 700 "$DESTINO"
TOKEN=$(tr -d '[:space:]' < "$TOKEN_FILE")
ARCHIVO="$DESTINO/abastos-pa-$(date +%Y%m%d-%H%M).sqlite3"
TMP="$ARCHIVO.part"

curl -sf --retry 3 -H "Authorization: Token $TOKEN" -o "$TMP" "$URL"

# Verificar antes de darlo por bueno: integridad SQLite + última venta registrada
RESUMEN=$(python3 - "$TMP" <<'PY'
import sqlite3, sys
c = sqlite3.connect(sys.argv[1])
ok = c.execute('pragma integrity_check').fetchone()[0]
if ok != 'ok':
    sys.exit(f'integridad: {ok}')
n, ultima = c.execute('select count(*), max(date) from sales_sale').fetchone()
print(f'{n} ventas, última {ultima}')
PY
)
mv "$TMP" "$ARCHIVO"
chmod 600 "$ARCHIVO"

# Rotación: conservar solo las últimas $CONSERVAR copias
ls -1t "$DESTINO"/abastos-pa-*.sqlite3 | tail -n +$((CONSERVAR + 1)) | xargs -r rm --

echo "$(date '+%F %T') OK $(basename "$ARCHIVO"): $RESUMEN"
