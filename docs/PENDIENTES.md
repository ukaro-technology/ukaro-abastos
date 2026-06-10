# Pendientes — Ukaro Abastos

## Decisiones activas
- Cliente activo: Leida. LIVE en https://abastos.ukarosoft.com (DigitalOcean 161.35.142.183)
- Deploy policy: DigitalOcean (cumplido)
- Deploy manual via Docker (SSH + docker compose). Sin GitHub Actions.
- SSL: Let's Encrypt (Certbot webroot), renovación por cron (host, 3am diario). Cert expira 2026-08-31.

## Próximos pasos
- [ ] **CI/CD pipeline** (GitHub Actions) — auto-deploy al push en main

## Completado
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
2026-06-10: [snapshot automático — 1 commit(s)]
- 09ed439 Fix: redondear valores numéricos en formset antes de enviar a Django
