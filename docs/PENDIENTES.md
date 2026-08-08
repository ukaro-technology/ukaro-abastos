# Pendientes — Ukaro Abastos

## Decisiones activas
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
- **Migración de droplet $12→$6/mes COMPLETADA (2026-08-08).** Droplet nuevo:
  `ubuntu-s-1vcpu-1gb-nyc3-01` (ID `590854857`, IP `157.245.211.83`, nyc3, 1GB/25GB, mismo VPC). Droplet viejo
  `ubuntu-s-1vcpu-2gb-nyc3-01` (ID `562942552`, IP `161.35.142.183`) **sigue corriendo como rollback** — `db` y
  `nginx` arriba, `web` detenido a propósito (evita escrituras divergentes; nginx ahí devuelve 502 a quien
  todavía le resuelva la IP vieja). **No destruir hasta confirmar unos días de estabilidad real en el nuevo.**
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
- [ ] **Recuperación de ventas 10-11 jul (ver decisión activa arriba)** — backup de la BD del droplet nuevo
      → copiar JSON ya exportado → `importar_ventas_recuperadas ... --dry-run` → revisar avisos (14 créditos)
      con Simón → `--apply` solo con su confirmación → verificar reportes/inventario/créditos después.
- [ ] **Revisar `/root/ram_monitor/ram.log` del droplet NUEVO (157.245.211.83) en 24-48h** con tráfico real
      de un día completo de ventas — confirmar que 1GB aguanta cómodo antes de destruir el droplet viejo.
- [ ] **Destruir droplet viejo (`562942552`, 161.35.142.183) una vez confirmada la estabilidad** — decisión
      2026-08-08: esperar 1 día completo de ventas reales, no más. **Importante:** un droplet *apagado* en DO
      sigue facturando el 100% del precio (el disco/IP siguen reservados) — apagarlo NO ahorra nada, solo
      destruirlo lo hace. Factura de DO baja a ~$6/mes recién después de destruir droplet viejo + ambos
      snapshots (ver próximo punto).
- [ ] Destruir snapshot huérfano `smartsolutions-1779244513767` (6.36GB, ~$0.40/mes) — confirmar con Simón si
      el snapshot manual `bodega-backup` (2026-08-08) también se puede borrar una vez el droplet nuevo esté
      confirmado, o si se quiere conservar como resguardo aparte.
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
2026-08-08: [snapshot automático — 1 commit(s)]
- 2903f4b fix: reciclar workers de gunicorn con --max-requests para evitar crecimiento de RAM sin techo
