# Publicar el demo de SuperMoto Speed en Render

El archivo `render.yaml` (raíz del repositorio) es un *Blueprint*: Render lee ese archivo y
crea solo el servidor web y la base de datos PostgreSQL, con todas las variables de entorno.
No hay que configurar nada a mano. Toma unos 10 minutos, casi todo esperando el primer build.

## Pasos

1. Crea la cuenta en render.com (con la cuenta de GitHub es lo más rápido).
2. Dale acceso a Render al repositorio privado `ukaro-technology/ukaro-abastos` cuando lo
   pida (GitHub muestra la pantalla de permisos de la app de Render).
3. En el panel: **New → Blueprint** → elige el repositorio `ukaro-abastos`.
4. Render muestra lo que va a crear: `supermoto-demo` (web) y `supermoto-db` (PostgreSQL),
   ambos en plan gratuito. Te pide un valor para **DEMO_PASSWORD**: es la contraseña de los
   usuarios del demo (`admin`, `papa`, `vendedor`). Pon una que no sea fácil de adivinar,
   porque el enlace queda público en internet.
5. **Apply**. El primer build tarda unos minutos. Al arrancar, el servidor aplica las
   migraciones y carga los datos de ejemplo (solo la primera vez, cuando la base está vacía).
6. Abre el enlace del servicio (`https://supermoto-demo.onrender.com` o el que asigne Render
   si ese nombre está tomado) e inicia sesión con `admin` y tu DEMO_PASSWORD.
7. Pon la tasa BCV real del día en Configuración → Tasa de Cambio (el demo trae 200 Bs/$).

El dominio de Render se agrega solo a `ALLOWED_HOSTS` y `CSRF_TRUSTED_ORIGINS` (variable
`RENDER_EXTERNAL_HOSTNAME`, ver `settings.py`), y Render ya da HTTPS, que la cámara necesita.

## Si el servicio se creó como "Web Service" (Docker) en vez de Blueprint

Render detecta el `Dockerfile` y crea un servicio Docker **sin** las variables del Blueprint
(por eso no pide la contraseña). Para que funcione, en ese servicio:

1. **Settings → Branch**: `ccr-2db2fa98-fx0vm7` (en `main` todavía no está SuperMoto).
2. **Environment → Add Environment Variable**:
   - `BUSINESS_PROFILE` = `motoparts`
   - `DEBUG` = `False`  ← importante: sin esto se ven errores con datos internos
   - `SECRET_KEY` = (botón *Generate*)
   - `DEMO_PASSWORD` = la contraseña que quieras para `admin`, `papa` y `vendedor`
3. **Manual Deploy → Deploy latest commit**.

El contenedor migra, junta los estáticos y carga el demo al arrancar
(`bodega_system/scripts/start_web.sh`). Sin base PostgreSQL usa SQLite dentro del contenedor:
**cada vez que el servicio se duerme o se redespliega, el demo vuelve a quedar como nuevo**
(se pierde lo que se haya probado). Para que los datos duren, usa el Blueprint.


Cada `git push` a la rama `ccr-2db2fa98-fx0vm7` redespliega solo. Si la rama cambia (por
ejemplo, al integrarla a `main`), cambia `branch:` en `render.yaml` o en la configuración del
servicio.

## Limitaciones del plan gratuito (revisarlas en el panel de Render; cambian con el tiempo)

- **El servidor se duerme** tras un rato sin visitas y la primera carga después tarda cerca
  de un minuto. **Ábrelo uno o dos minutos antes del demo.**
- **La base de datos gratuita vence** al cabo de un tiempo (a la fecha de este documento,
  alrededor de 30 días). Sirve para el demo; para producción hay que pasar a un plan pago o
  al hosting definitivo.
- Los datos se guardan en PostgreSQL, así que lo que el cliente pruebe (ventas, productos) no
  se pierde cuando el servidor se duerme.

## Códigos de barras de prueba

Los datos de ejemplo usan una semilla fija, así que los códigos de barras salen **iguales en
cualquier instalación nueva del demo**. El PDF para probar el escáner se puede generar en
local y sirve para Render:

```bash
cd bodega_system
BUSINESS_PROFILE=motoparts python manage.py migrate
BUSINESS_PROFILE=motoparts python manage.py seed_motoparts_demo --if-empty --barcodes-pdf etiquetas_demo.pdf
```

## Empezar de cero

Borra la base `supermoto-db` desde el panel y vuelve a sincronizar el Blueprint: se crea
vacía y el servidor vuelve a cargar el demo al arrancar.
