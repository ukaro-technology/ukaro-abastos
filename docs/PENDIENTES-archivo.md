# Archivo histórico — ukaro-abastos

> Secciones de bitácora movidas desde `PENDIENTES.md` el 2026-09-10.
> Nada se perdió: esto es el registro completo de lo ya terminado.
> `PENDIENTES.md` queda solo con lo vivo.

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
