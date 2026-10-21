# Publicar el demo de SuperMoto Speed en PythonAnywhere

Guía para montar el demo (perfil `motoparts`) en una cuenta de PythonAnywhere. Toma unos
20–30 minutos la primera vez. El demo usa SQLite; para producción real se migra a
PostgreSQL cuando se decida el hosting definitivo.

> Antes de empezar: el repositorio es privado. Para clonarlo desde PythonAnywhere hace falta
> un **token de GitHub de solo lectura** (GitHub → Settings → Developer settings →
> Personal access tokens → Fine-grained → acceso de lectura a `ukaro-technology/ukaro-abastos`
> → permiso "Contents: Read-only"). No lo guardes en ningún archivo del repositorio.

## 1. Cuenta y código

1. Crea la cuenta en pythonanywhere.com. El nombre de usuario será parte del enlace:
   `https://TU_USUARIO.pythonanywhere.com`. Para el demo, la cuenta gratuita alcanza.
2. Abre **Consoles → Bash** y clona el repositorio:

   ```bash
   git clone https://TU_TOKEN@github.com/ukaro-technology/ukaro-abastos.git
   cd ukaro-abastos
   git checkout ccr-2db2fa98-fx0vm7   # o main, cuando la rama ya esté integrada
   ```

3. Crea el entorno virtual e instala dependencias:

   ```bash
   mkvirtualenv --python=python3.12 supermoto   # si 3.12 no está, usa 3.11 o 3.13 (Django 5.2 pide 3.10+)
   pip install -r requirements.txt
   ```

## 2. Base de datos y datos de ejemplo

En la misma consola (con el entorno `supermoto` activo):

```bash
cd ~/ukaro-abastos/bodega_system
export BUSINESS_PROFILE=motoparts
python manage.py migrate
python manage.py seed_motoparts_demo --barcodes-pdf ~/etiquetas_demo.pdf
python manage.py collectstatic --noinput
```

El comando crea los usuarios `dueno`, `papa` (administradores) y `vendedor` (empleado), con
la contraseña `supermoto2026`. **Cámbiala antes de darle el enlace al cliente** (Usuarios →
editar, o `python manage.py changepassword dueno`).

`etiquetas_demo.pdf` (en la carpeta de inicio, pestaña **Files**) trae 12 códigos de
barras de productos del demo, para probar el escáner con la cámara (ver el guion del demo).

## 3. Aplicación web

1. Pestaña **Web → Add a new web app → Manual configuration → Python 3.12**.
2. **Virtualenv**: `/home/TU_USUARIO/.virtualenvs/supermoto`
3. **Source code**: `/home/TU_USUARIO/ukaro-abastos/bodega_system`
4. Abre el **WSGI configuration file** (enlace en la misma pestaña), borra todo y pega:

   ```python
   import os
   import sys

   path = '/home/TU_USUARIO/ukaro-abastos/bodega_system'
   if path not in sys.path:
       sys.path.insert(0, path)

   os.environ['DJANGO_SETTINGS_MODULE'] = 'bodega_system.settings'
   os.environ['BUSINESS_PROFILE'] = 'motoparts'
   os.environ['DEBUG'] = 'False'
   os.environ['SECRET_KEY'] = 'PEGA_AQUI_UNA_CLAVE_LARGA_Y_ALEATORIA'
   os.environ['ALLOWED_HOSTS'] = 'TU_USUARIO.pythonanywhere.com'
   os.environ['CSRF_TRUSTED_ORIGINS'] = 'https://TU_USUARIO.pythonanywhere.com'

   from django.core.wsgi import get_wsgi_application
   application = get_wsgi_application()
   ```

   Para generar la clave: `python -c "import secrets; print(secrets.token_urlsafe(50))"`.

5. **Static files** (en la pestaña Web): URL `/static/` → Directory
   `/home/TU_USUARIO/ukaro-abastos/bodega_system/staticfiles`
6. Activa **Force HTTPS**. Es obligatorio: sin HTTPS el navegador no deja usar la cámara
   para escanear códigos.
7. Presiona **Reload** y abre `https://TU_USUARIO.pythonanywhere.com`.

## 4. Actualizar el demo después de cambios

```bash
cd ~/ukaro-abastos && git pull
workon supermoto
cd bodega_system
export BUSINESS_PROFILE=motoparts
python manage.py migrate
python manage.py collectstatic --noinput
```

Y **Reload** en la pestaña Web.

## Cosas a tener en cuenta

- **Cuenta gratuita**: la aplicación se desactiva si no se renueva; en la pestaña Web hay un
  botón para extenderla. Antes de mostrarle el demo al cliente, revisa que esté activa.
- **Tasa BCV**: el demo trae una tasa de ejemplo (200 Bs/$). Ponle la tasa real del día en
  Configuración → Tasa de Cambio antes de la reunión, si no los precios en Bs se verán raros.
- **Datos de ejemplo**: precios, números de parte, clientes y proveedores son inventados. El
  comando se niega a correr si ya hay productos, para no mezclarse con datos reales.
- **Para empezar de cero**: borra `bodega_system/db.sqlite3` y repite el paso 2.
