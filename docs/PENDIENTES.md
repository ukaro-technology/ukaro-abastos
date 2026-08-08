# Pendientes — Ukaro Abastos

## Decisiones activas
- Cliente activo: Leida. LIVE en https://abastos.ukarosoft.com (DigitalOcean 161.35.142.183)
- Deploy policy: DigitalOcean (cumplido)
- Deploy manual via Docker (SSH + docker compose). Sin GitHub Actions.
- SSL: Let's Encrypt (Certbot webroot), renovación por cron (host, 3am diario). Cert expira 2026-08-31.
- **Migración de droplet $12→$6/mes en curso (2026-08-08)** — el disco NUNCA fue el cuello de botella real
  (DB 86MB, uso real 8.1G/48G tras limpieza). El riesgo real es RAM: el plan de $6/mes trae 1GB (no 2GB), y el
  droplet actual estaba en 84% de uso con gunicorn sin `--max-requests` (workers creciendo sin techo en 27
  días de uptime, hasta 1.08GB solo el contenedor web). Aplicado ya: `--max-requests 500
  --max-requests-jitter 50` (commit `2903f4b`, desplegado en prod) + swap de 2GB en el droplet actual. Con
  esto el uso total bajó de 84% a 37% (706Mi/1.9Gi) tras el restart. **Monitoreo activo en el servidor**
  (`/root/ram_monitor/ram.log`, cron cada 15 min) para confirmar que se mantiene bajo con tráfico real
   24-48h antes de decidir migrar. Plan si se confirma: Camino B (droplet nuevo desde cero, NO snapshot — DO
  no permite reducir el disco asignado de un snapshot, así que Camino A está descartado de entrada).
  Pendiente doctl (Simón todavía no generó el token de API).
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
- [ ] **Migración droplet DO $12→$6/mes** — revisar `/root/ram_monitor/ram.log` en 24-48h (después de
      2026-08-08 ~05:00 UTC) y decidir si el uso estable entra cómodo en 1GB. Si sí: Camino B (droplet nuevo,
      Ubuntu limpio + git clone + docker compose + restaurar DB con pg_dump + swap+max-requests desde el
      arranque + cutover DNS del subdominio `abastos.ukarosoft.com` + cert Let's Encrypt nuevo). Backup de DB
      verificado y descargado localmente ANTES de cualquier paso irreversible.
- [ ] Configurar rotación de logs del daemon de Docker (ver hallazgo arriba) — horario de bajo tráfico.
- [ ] Rotación + copia externa de los backups JSON manuales (`/app/backups` en el contenedor web).
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
