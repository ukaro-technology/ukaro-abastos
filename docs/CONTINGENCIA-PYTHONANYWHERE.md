# Contingencia: Ukaro Abastos en PythonAnywhere

Desde el **2026-10-09 23:31** (hora de Caracas) Leida trabaja en **https://bodegaleida.pythonanywhere.com**,
porque un problema de pago con DigitalOcean puede dejar sin acceso el droplet `157.245.211.83`.
Se espera volver a DigitalOcean en unos 15 días.

**Regla de oro:** mientras dure la contingencia, la ÚNICA base viva es la de PythonAnywhere. Antes de
reactivar `abastos_web` en cualquier droplet hay que traer esa base de vuelta (abajo). En julio de 2026
no se hizo y las ventas de 2 días se perdieron para el inventario hasta recuperarlas a mano en agosto.

## Cómo quedó montado

| Cosa | Dónde |
|---|---|
| Cuenta | `Bodegaleida` (plan gratis), API token en `~/.config/pythonanywhere-token.txt` de la laptop |
| Código | `/home/Bodegaleida/abastos` — clon de `main` (`8476508`) |
| Virtualenv | `/home/Bodegaleida/.virtualenvs/abastos` (Python 3.12) |
| Base | SQLite en `/home/Bodegaleida/abastos/bodega_system/db.sqlite3` |
| Variables de entorno | `/home/Bodegaleida/.abastos.env` (chmod 600; las lee el WSGI) |
| WSGI | `/var/www/bodegaleida_pythonanywhere_com_wsgi.py` |
| Estáticos | `/static/` → `bodega_system/staticfiles`, `/media/` → `bodega_system/media` |

En el droplet: `abastos_web` está **detenido** (`docker compose stop web`); `abastos_db` y Platform siguen arriba.

Respaldos en la laptop (`~/respaldos/abastos/`, fuera de git porque son datos reales):
- `abastos-FINAL-20261009-2331.dump` — pg_dump de producción en el momento del corte.
- `pa-inicial-20261009-2331.sqlite3` — la base con la que arrancó PythonAnywhere.
- `pythonanywhere-viejo/` — la copia de abril/julio que había antes en la cuenta (borrada de PA).

## Límites del plan gratis

- La web app **vence el 2026-10-25**: si la contingencia sigue, antes de esa fecha entrar a la pestaña
  *Web* y pulsar "Run until 3 months from today".
- 512 MB de disco (usado ~213 MB) y 100 s/día de CPU en consolas: no correr tareas pesadas allá.
- Más lento que el droplet (`/finances/` ~11 s). Solo `bodegaleida.pythonanywhere.com`, sin dominio propio.

## Vuelta a DigitalOcean

Script: `bodega_system/scripts/copiar_base.py` (ensayado ida y vuelta con datos reales el 2026-10-09).

1. Avisar a Leida y elegir un momento con la bodega cerrada.
2. En PythonAnywhere: deshabilitar la web app (pestaña *Web* o
   `POST /api/v0/user/Bodegaleida/webapps/bodegaleida.pythonanywhere.com/disable/`) para congelar la base.
3. Descargar la base:
   `curl -H "Authorization: Token $T" -o pa-final.sqlite3 https://www.pythonanywhere.com/api/v0/user/Bodegaleida/files/path/home/Bodegaleida/abastos/bodega_system/db.sqlite3`
   y guardarla en `~/respaldos/abastos/`.
4. Respaldar la base del droplet (`pg_dump`) aunque esté desactualizada.
5. Crear una base Postgres **vacía**, correr `manage.py migrate` contra ella y cargar:
   `python scripts/copiar_base.py a-postgres --pg "<dsn>" --sqlite pa-final.sqlite3`.
   El script aborta si alguna tabla no cuadra en filas o en las sumas de ventas, stock y créditos.
   Ensayarlo primero contra un Postgres local en Docker (`postgres:16-alpine`).
6. Apuntar `abastos_web` a esa base, `docker compose start web`, iniciar sesión y verificar que la
   última venta de PythonAnywhere aparece en `/sales/`.
7. Avisar a Leida que vuelve a `https://abastos.ukarosoft.com`, y dejar la web app de PA deshabilitada.

## Si hay que desplegar código durante la contingencia

En la consola de PA: `cd ~/abastos && git pull --ff-only`, luego `collectstatic` (cargando
`~/.abastos.env`) y recargar la web app. Respaldar antes `db.sqlite3` (descargarlo por la API).
