# Pendientes — Ukaro Abastos

## Decisiones activas
- **COMPLETADO (2026-08-17) — Calculadora integrada en el navbar + spec de "Precios Estables en Bs".**
  - **Calculadora:** botón en el header (visible para todo usuario autenticado, todas las vistas),
    panel con dos pestañas — calculadora básica de 4 operaciones, y conversor "USD físico → BCV"
    (monto en efectivo × factor de prima calle editable, ej. 10$ físico ≈ 11.20$ BCV → factor 1.12,
    más tasa BCV precargada desde `ExchangeRate`). El factor de prima **no se guarda en el servidor**
    — vive en `localStorage` del navegador, decisión explícita de Simón de empezar simple sin tocar
    backend. Archivos: `templates/base/_calculator.html`, `static/js/calculator.js` (Alpine.data
    component), `templates/base/base.html`.
  - **Bug encontrado y corregido en el camino:** usar `{% static %}` en `base.html` rompió ~168 tests
    (`ValueError: Missing staticfiles manifest entry`) — es el **primer uso de `{% static %}` en todo
    el proyecto**, y este entorno nunca corrió `collectstatic` (no existe `bodega_system/staticfiles/`),
    así que `CompressedManifestStaticFilesStorage` (WhiteNoise) revienta con manifest vacío en modo
    estricto. Confirmado corriendo el suite completo con y sin el cambio (`git stash`) antes y después
    del fix — no era flakiness. Solución: ruta literal `/static/js/calculator.js` en vez de
    `{% static %}`, consistente con que ningún otro template del proyecto usa ese tag. **435 tests,
    mismas 9 failures + 6 errors preexistentes (no relacionadas), 0 regresiones.**
  - **Bug real en producción tras el primer deploy (Simón lo reportó con captura — panel abierto
    solo, clics sin efecto):** el primer deploy pasó los 435 tests de Django pero **nunca se probó con
    un navegador real** — los tests de Django no ejecutan Alpine.js. Diagnosticado con la extensión de
    Chrome contra el sitio en vivo (consola: `Alpine Expression Error: ukaroCalculator is not
    defined`), reproducido también con Node+jsdom para descartar teorías antes de tocar código.
    **Causa raíz real:** `calculator.js` se cargaba DESPUÉS del script de Alpine en `base.html` — con
    `defer`, Alpine llama `Alpine.start()` (que dispara `alpine:init`) en cuanto termina de cargar,
    así que el `addEventListener('alpine:init', ...)` de `calculator.js` se registraba demasiado
    tarde y nunca se enteraba. Fix: invertir el orden de los `<script defer>` (el que registra
    `Alpine.data()` siempre va ANTES que el script de Alpine). **De paso, dos bugs más encontrados
    arreglando esto:** (1) `LANGUAGE_CODE=es-ve` renderiza decimales con coma (`777,50`), rompiendo
    la llamada JS `ukaroCalculator(777,50)` que Alpine interpreta como dos argumentos — resuelto con
    `{% load l10n %}` + `{% localize off %}`; (2) mientras documentaba el fix anterior, un comentario
    Django `{# ... #}` de varias líneas se filtró como texto plano en la página — **`{# #}` no
    soporta multilínea en Django** (limitación real del motor, no un typo), hay que usar
    `{% comment %}...{% endcomment %}` para comentarios largos. Los 3 fixes verificados con clics
    reales en el navegador (Chrome, extensión conectada) contra el server local antes de re-desplegar
    — no solo contra tests de servidor. **Lección para la próxima vez con features de JS/Alpine:
    probar con navegador real ANTES de dar por buena una feature, los tests de Django no alcanzan.**
  - **Incidente en producción mientras el fix de arriba corría en background (Simón no podía
    registrar ventas):** un cliente tenía la página abierta con el bug viejo (el de `ukaroCalculator
    is not defined`) todavía cargado, y el fallo en cadena de Alpine terminó ejecutando
    `open = false` en el scope global del navegador en vez del scope del componente — en JS eso crea
    automáticamente `window.open = false`, **pisando la función nativa `window.open()`** que el flujo
    de ventas usa (para abrir el comprobante). Mitigación inmediata: recargar la página (el problema
    es solo de memoria del navegador, no toca backend/BD). Solución de fondo: el mismo fix del orden
    de scripts de arriba. Simón corrió el redeploy manualmente esta vez porque el clasificador de
    permisos bloqueó mis comandos SSH en ese momento puntual.
  - **Segunda vuelta de la calculadora, pedida por Simón tras probarla:** (1) **soporte de teclado**
    en la pestaña Calculadora — números, `+ - × / .` `Enter` `⌫`, vía un único listener
    `window.addEventListener('keydown', ...)` registrado en `init()` (no gatilla si el panel está
    cerrado, si la pestaña activa no es "calc", o si el foco está en un input/textarea/select de
    OTRA parte de la página, para no robarle las teclas a un formulario abierto detrás); `Escape`
    sigue cerrando el panel entero (ya existía) y no se duplicó esa tecla para evitar pisarlo.
    (2) **Conversor USD → Bs rediseñado:** se eliminó el campo "factor / prima calle" (1.12) —
    ahora el usuario ingresa directamente la **tasa calle en Bs por USD físico** (ej. 46.00), y
    `Total en Bs = monto × tasaCalle`; el "Equivalente USD BCV" pasó a ser un dato secundario/de
    referencia (`Total en Bs / tasaBcv`), ya no el insumo del cálculo. La tasa calle se sigue
    recordando en `localStorage` (mismo criterio que antes con el factor). Verificado con clics y
    tecleo reales en Chrome antes de pedir el redeploy.
  - **Tercer bug de la misma tanda (Simón: "sigo sin poder usar el teclado" después del redeploy de
    arriba):** no era el código — el `nginx` de producción sirve `/static/` con
    `Cache-Control: public, immutable, max-age=2592000` (30 días, confirmado con `curl -I`). Como
    `calculator.js` se referencia con una ruta literal fija (ver el bug de `{% static %}`/manifest más
    arriba en este mismo punto), el navegador de Simón lo había cacheado en su primera visita y con
    `immutable` **nunca vuelve a pedirlo al servidor**, sin importar cuántas veces se redeploye. Fix:
    cache-buster manual en la URL (`calculator.js?v=2` en `base.html`, con un comentario bien visible
    de "subir este número al editar el archivo o el cambio no le llega a nadie que ya lo haya
    cargado"). **De paso, tercera vez en el día que reincido en el mismo error:** escribí
    `{% static %}` como texto dentro de un comentario **HTML** (`<!-- ... {% static %} ... -->`)
    pensando que HTML comment protegía el texto — Django tokeniza `{% %}` en TODO el archivo, HTML
    comments no lo blindan (solo `{# #}` o `{% comment %}` lo hacen). Verificado esta vez con
    `Alpine.$data()` real contra la página en vivo en producción (no un screenshot — la herramienta de
    captura de la extensión de Chrome se colgó ese día — sino leyendo el estado reactivo real del
    componente tras simular el tecleo `1,2,+,8,Enter` con `KeyboardEvent` de verdad: `display` pasó de
    `"0"` a `"20"`).
- **COMPLETADO (2026-09-04) — Precios Estables en Bs, implementado.** Spec en
  `docs/specs/precios-estables-bs.md` (4 decisiones cerradas por Simón, implementada, 26 tests
  nuevos en verde, 0 regresiones — suite completa comparada test por test contra el commit previo a
  la sesión vía `git worktree`, mismas 9 failures + 6 errors preexistentes en ambos lados, ninguno
  nuevo).
  - `Product.pricing_mode` (`usd` default | `bs_fixed`), por producto (no hay acción masiva ni modo
    global — decisión explícita de Simón, se puede agregar después). Toggle en
    `product_form.html`; en modo `bs_fixed` el campo mandante pasa a ser `selling_price_bs` (editable)
    y `selling_price_usd` queda como referencia informativa de solo lectura (Bs fijo / tasa actual).
  - Precio de compra a proveedores **nunca se congela**, sin importar el modo (decisión explícita de
    Simón) — `ProductService.update_product_prices`/`bulk_update_prices` siguen sincronizando
    `purchase_price_bs` siempre, solo excluyen `selling_price_bs` de productos `bs_fixed`.
  - `Product.get_current_price_bs()`/`get_current_price_usd()` centralizan toda la lógica de precio
    de venta (punto de venta, reportes, detalle) — ganaron parámetros `quantity` y `exchange_rate`
    opcionales, necesarios para no romper **precio al mayor** (`is_bulk_pricing`), una feature real y
    activa que el diseño original de la spec no había contemplado. Se decidió (no estaba en la spec
    original) que precio al mayor y Bs fijo son mutuamente excluyentes — activar ambos a la vez da
    error de validación.
  - Bug preexistente del reporte de valorización de inventario (`inventory/api_views.py`,
    `product_stock_summary_api`) corregido en el mismo trabajo, a pedido explícito de Simón: ya no lee
    las columnas `purchase_price_bs`/`selling_price_bs` (vestigiales), calcula en vivo con la tasa
    actual respetando el modo de cada producto.
  - **De rebote, corregidos 2 bugs reales más** (mismo patrón ya documentado arriba con la
    calculadora): (1) `sales/api_views.py` y `utils/api_views.py:product_by_barcode` (el endpoint
    real que usa el punto de venta al escanear) tenían la misma fórmula de precio duplicada — de no
    corregirse, un producto `bs_fixed` habría mostrado precio incorrecto al cajero o un total de venta
    inconsistente con el precio real del ítem. (2) el conversor USD→Bs de `product_form.html`
    inyectaba la tasa sin `|unlocalize` en una expresión JS — con `LANGUAGE_CODE=es-ve` (coma decimal)
    el operador coma de JS hacía que el preview de conversión SIEMPRE mostrara "Bs 0.00" — autorizado
    por Simón antes de tocarlo, corregido en las 3 líneas afectadas del mismo bloque.
  - **Hallazgo sin corregir, anotado como deuda aparte** (fuera de alcance de esta spec):
    `inventory/api_views.py:product_by_barcode_api` lee `product.bulk_price_bs`, un atributo que no
    existe en el modelo (`Product` solo tiene `bulk_price_usd`) — cualquier producto con precio al
    mayor activo que se escanee por esa ruta específica (`inventory:product_by_barcode_api`, distinta
    de la que usa el punto de venta real) dispara un `AttributeError` 500 no controlado.
  - **Pendiente, no bloqueante:** prueba manual en navegador real (crear producto `bs_fixed`, vender,
    cambiar tasa BCV, confirmar visualmente) — todavía no hecha, solo verificado con tests de Django.
    Deploy a producción pendiente de que Simón revise el resultado.
- **COMPLETADO (2026-08-08) — Auditoría de inventario (conteo físico vs sistema + trazabilidad por
  producto).** Spec en `docs/specs/auditoria-inventario.md` (aprobada por Simón, implementada, 29 tests
  nuevos en verde, verificado con datos reales de producción). Motivado por la necesidad de cuadrar los
  27 productos que no matchearon en la recuperación de ventas de julio (ver punto siguiente) y por
  pedido explícito de Simón de tener el sistema "lo más robusto posible para auditorías".
  - Modelos `InventoryCount`/`InventoryCountItem` (snapshot de stock del sistema al momento del conteo,
    no se recalcula después).
  - `/inventory/counts/` (histórico), `/inventory/counts/new/` (registrar conteo por categoría o
    todas), reporte de discrepancias con PDF — **solo informativo, no auto-ajusta stock** (decisión
    explícita de Simón).
  - `/inventory/products/<id>/traceability/` — línea de tiempo combinada de ventas + ajustes + compras
    recibidas que afectaron el stock de un producto, con reconstrucción exacta del stock antes/después
    de cada evento, exportable a PDF, default 30 días.
  - Todo detrás de `admin_required`.
  - **Pendiente, no bloqueante:** agregar botón/entrada de menú visible (funciona por URL directa);
    hacer el primer conteo físico REAL con Leida contando en la bodega (no lo puede simular Claude Code).
- **De paso, verificado (no fue necesario arreglar nada):** Simón reportó que el filtro de fechas de
  Ventas no funcionaba — se probó a fondo (ORM + HTTP completo) y **sí funciona correctamente**. La
  sospecha real: lo probó antes de la recuperación de ventas de julio, cuando no había datos en ese
  rango. De paso se hizo un barrido de QA de las otras 10 listas con filtros del sistema
  (`product_list`, `adjustment_list`, `combo_list`, `customer_list`, `credit_list`, `supplier_list`,
  `order_list`, `expense_list`) — **todos funcionan correctamente**, ningún bug real encontrado.
- **COMPLETADO (2026-08-08) — Recuperación de ventas del 10-11 jul 2026 (caída de DO por falta de pago).**
  DO estuvo caído esos 2 días; Leida usó temporalmente una copia de abril del sistema en PythonAnywhere
  (`bodegaleida.pythonanywhere.com`) y esas ventas nunca se pasaron a DO, descuadrando inventario/reportes.
  - Backup fresco (`pg_dump`, verificado con `pg_restore --list`) del droplet nuevo (`157.245.211.83`) ANTES
    de tocar nada.
  - Export real de PythonAnywhere (234 ventas, 10/07 08:41 → 11/07 15:28, 14 a crédito, 0 combos, ≈$448.03)
    ya traído a `/home/sabh/Escritorio/export_ventas_10_11_julio.json` (local, NO en git — datos reales de
    clientes).
  - `--dry-run` revisado antes de aplicar: **207 ventas válidas, 27 sin ítems** (producto no existe en DO
    por barcode — típicamente productos con barcode "manual"/de texto tipo `huevo`, `SUN2`, `bolsap`, etc.
    que no coinciden con el catálogo actual; **quedaron sin importar, pendiente revisión manual** si Leida
    quiere agregarlas a mano).
  - `--apply` corrido: **207 ventas recreadas** con inventario descontado (`InventoryAdjustment` trazable),
    fecha original preservada, marcador `[Recuperado PA#<id>]` en `notes` (idempotente).
  - **Créditos — decisión explícita de Simón:** de las 14 ventas a crédito del lote, **solo se dejó como
    deuda real rastreada la de Anita** (cliente ya existente, id 120, cédula 26636968, tel 04160584897,
    venta PA#26100, $1.05, vence 2026-08-09) — enlazada a mano vía ORM (`Sale.customer` + `CustomerCredit`
    creado manualmente, porque el matching automático por cédula no aplica: el sistema origen es anterior a
    que `Customer` tuviera ese campo). **Los otros 13 créditos (~$64.22 total: Pacheco andres hijo x2, la
    negra miguelito x3, evelin negro bello, La nena, tio ami, Andrea vecina, Isbelia, Dra Ortega los caneyes
    x2, Simon) se importaron como venta normal (`is_credit=True` preservado, inventario/ingreso correctos)
    pero SIN `CustomerCredit`** — no quedan como deuda por cobrar en el sistema, a pedido explícito del
    cliente. Si en el futuro se necesita revertir esto para alguno, están identificables por el marcador
    `[Recuperado PA#<id>]` en `Sale.notes` (ids PA#26054, 26067, 26070, 26073, 26074, 26083, 26145, 26154,
    26167, 26198, 26241, 26242, 26258).
  - Verificado post-import: 207 recuperadas, 14 con `is_credit=True`, 1 con cliente asociado, 1
    `CustomerCredit` creado (Anita, id 1861).
  - **Pendiente, no bloqueante:** las 27 ventas sin ítems válidos (producto no matcheado por barcode) — si
    Leida quiere esos datos también, hay que mapear esos barcodes/nombres a mano contra el catálogo actual.
  - Nota de proceso: el comando `importar_ventas_recuperadas` solo tiene `--apply` (default = dry-run); su
    propio comentario interno menciona un `--dry-run` que no existe como flag — corregir el comentario en
    algún momento para no confundir a la próxima persona.
- Cliente activo: Leida. LIVE en https://abastos.ukarosoft.com
- Deploy policy: DigitalOcean (cumplido)
- Deploy manual via Docker (SSH + docker compose). Sin GitHub Actions.
- SSL: Let's Encrypt (Certbot webroot), renovación por cron (host, 3am diario). Cert nuevo expira 2026-11-06.
- **Migración de droplet $12→$6/mes COMPLETADA y CERRADA (2026-08-08, cierre 2026-08-11).** Droplet
  activo: `ubuntu-s-1vcpu-1gb-nyc3-01` (ID `590854857`, IP `157.245.211.83`, nyc3, 1GB/25GB). Droplet
  viejo (`562942552`) + snapshot huérfano + `bodega-backup` **destruidos el 2026-08-11**, tras 3 días de
  monitoreo real sin un solo evento de OOM-killer (pico de RAM: 632MB/961MB = 66%, `abastos_web` estable
  en ~206MB gracias al fix de `--max-requests`). Backup fresco (`pg_dump`) tomado y guardado localmente
  justo antes de destruir, por las dudas. Factura de DO debería reflejar ~$6/mes desde ahora.
  - Causa raíz real (no la sospechada originalmente): el disco NUNCA fue el cuello de botella (DB 86MB, uso
    real 8.1G/48G tras limpieza en el viejo). El riesgo real era RAM: gunicorn sin `--max-requests` dejaba
    crecer los workers sin techo (27 días de uptime → 1.08GB solo el contenedor web, 84% de RAM total). Fix:
    `--max-requests 500 --max-requests-jitter 50` (commit `2903f4b`) + swap 2GB — bajó a 37% en el viejo.
    Camino A (snapshot+resize) descartado de entrada: DO no permite reducir el disco asignado de un snapshot.
  - Migración real: Camino B (droplet nuevo desde cero) — Docker + git clone (`origin/main` commit `d8228db`)
    + `.env` copiado + swap 2GB + `--max-requests` desde el arranque + `pg_dump`/`pg_restore` (conteos
    verificados idénticos: 51044 ventas, 982 productos, 66 clientes, 7 usuarios).
  - **DNS de `ukarosoft.com` vive en Google Domains/Cloud DNS, no en DigitalOcean** — no hay DNS-01
    automatizable con el token de DO. Cert emitido post-cutover vía HTTP-01 (webroot) contra un
    `nginx.conf` "bootstrap" temporal (solo HTTP, sin bloque 443) para evitar el problema de huevo-y-gallina
    de nginx no arrancando sin un cert que todavía no existía. Cutover: Simón cambió el A record → se detuvo
    `web` en el viejo → propagación ya confirmada en Google/Cloudflare/Quad9/OpenDNS → cert emitido → swap al
    `nginx.conf` real. **Nota para la próxima vez:** un `docker compose restart` de nginx no siempre
    recarga de verdad (visto en esta sesión, causó ~10 min de diagnóstico de un 502 fantasma que en
    realidad era DNS cacheado en la propia máquina de trabajo, no un problema del servidor) — usar
    `up -d --force-recreate --no-deps` para garantizar un reload real.
  - Cron de renovación de cert + monitoreo de RAM (`/root/ram_monitor/ram.log`, cada 15 min) replicados en
    el droplet nuevo, mismo criterio que el viejo.
  - Token de API de DigitalOcean generado por Simón y usado vía `doctl` (instalado en
    `~/.local/bin/doctl` en la máquina de trabajo) — no hay backups automáticos de DO activados (verificado,
    `backup_ids: None`). Snapshot huérfano `smartsolutions-1779244513767` (6.36GB, ~$0.40/mes) sigue sin
    limpiar — pendiente. Hay además un snapshot manual reciente `bodega-backup` (2026-08-08, 7.86GB) que
    Simón generó por su cuenta como resguardo extra antes de esta sesión.
- **Hallazgo aparte, no bloqueante:** servidor tenía el puntero de git 6 commits atrás de `origin/main`
  (reconciliado en esta sesión con `git stash && git pull --ff-only && git stash pop`, sin pérdida — el
  contenido ya coincidía con origin/main, solo faltaba el pull). Volver a verificar antes de cualquier deploy
  futuro que no se haya vuelto a desincronizar.
- **Hallazgo aparte, no bloqueante:** backup interno vía vista Django (`/backups`, manual, sin cron) dumpea
  la DB completa a JSON en un volumen Docker (`abastos_backup_volume`) — 4 backups de ~110MB solo en la
  semana del 5-8 ago, sin rotación ni copia fuera del servidor. Útil pero no reemplaza un `pg_dump` externo
  real. Falta: rotación automática + copia a almacenamiento externo.
- **Hallazgo aparte, no bloqueante:** logs de contenedores Docker sin rotación configurada en el daemon
  (`json.log` ya en 114-124MB cada uno al momento del diagnóstico). Falta: `/etc/docker/daemon.json` con
  `log-opts` (`max-size`/`max-file`) — requiere reiniciar el daemon de Docker, lo que reinicia TODOS los
  contenedores a la vez (web+nginx+db simultáneo, más disruptivo que el restart aislado de `web` que ya se
  hizo). Programar para un horario de bajo tráfico.

## Próximos pasos
- [ ] Configurar rotación de logs del daemon de Docker en el droplet NUEVO (ver hallazgo arriba) — horario de
      bajo tráfico, reinicia los 3 contenedores a la vez.
- [ ] Rotación + copia externa de los backups JSON manuales (`/app/backups` en el contenedor web).
- [ ] Arreglar el servicio `certbot` en `docker-compose.yml` — no tiene `networks:` explícito, así que cae en
      la red default de Compose en vez de `abastos_network` (funciona igual porque solo necesita los
      volúmenes compartidos, pero es inconsistente con el resto de los servicios).
- [ ] **CI/CD pipeline** (GitHub Actions) — auto-deploy al push en main

## Completado
- [x] **Validaciones robustas órdenes de compra** ✅ (2026-06-10) — Endpoint JSON + localStorage. Commit 088b87f. 56 tests.
  - Endpoint `/suppliers/orders/api/create/` reemplaza Django formsets — valida con Decimal, transacción atómica
  - localStorage guarda borrador automáticamente; restaura si hay recarga o error de red
  - Errores específicos por producto (qué campo falló y en qué producto)
  - Spinner + botón deshabilitado durante envío — sin doble submit
  - Sin recarga de página en caso de error — trabajo del usuario nunca se pierde
- [x] **Bug órdenes de compra vacías** ✅ (2026-06-05) — Fix Alpine.effect + guard servidor. Commits 12ad878, 2c05057.
- [x] **Reconciliación git servidor** ✅ (2026-06-05) — 7 archivos del servidor sincronizados a local (cédula, anti-doble-submit, health). Commit 113eb0c.
- [x] **Ramas huérfanas eliminadas** ✅ (2026-06-05) — 5 ramas claude/* + fixed-sales-selector.
- [x] **Health endpoint /health/** ✅ (2026-06-05) — https://abastos.ukarosoft.com/health/ {"status":"ok","db":true}
- [x] **Subdominio + HTTPS** ✅ (2026-06-02) — abastos.ukarosoft.com, cert Let's Encrypt,
      redirección 80→443, HSTS, cookies seguras, CSRF_TRUSTED_ORIGINS, cron de renovación.
- [x] Deploy inicial en DigitalOcean ✅ (2026-04-25)
- [x] 121+ tests pasando ✅
- [x] Finanzas duales USD/Bs con tasa de cambio ✅
- [x] 2 bugs resueltos ✅ (2026-04-16)

## Última sesión
2026-09-06: [snapshot automático — 0
0 commit(s)]
