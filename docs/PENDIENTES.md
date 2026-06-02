# Pendientes — Ukaro Abastos

## Decisiones activas
- Cliente activo: Leida. LIVE en https://abastos.ukarosoft.com (DigitalOcean 161.35.142.183)
- Deploy policy: DigitalOcean (cumplido)
- Deploy manual via Docker (SSH + docker compose). Sin GitHub Actions.
- SSL: Let's Encrypt (Certbot webroot), renovación por cron (host, 3am diario). Cert expira 2026-08-31.

## Próximos pasos
- [ ] **Server git divergente** — 6 archivos modificados sin commitear en /root/abastos
      (customers/views.py, api_views.py, 4 templates) + rama atrás de origin.
      Reconciliar sin perder hotfixes de producción.
- [ ] Health endpoint /health/ para monitoreo automático en Factory
- [ ] CI/CD pipeline (GitHub Actions)
- [ ] Limpiar ramas huérfanas `claude/*` en GitHub

## Completado
- [x] **Subdominio + HTTPS** ✅ (2026-06-02) — abastos.ukarosoft.com, cert Let's Encrypt,
      redirección 80→443, HSTS, cookies seguras, CSRF_TRUSTED_ORIGINS, cron de renovación.
- [x] Deploy inicial en DigitalOcean ✅ (2026-04-25)
- [x] 42+ tests pasando ✅
- [x] Finanzas duales USD/Bs con tasa de cambio ✅
- [x] 2 bugs resueltos ✅ (2026-04-16)

## Última sesión
2026-06-02: Subdominio abastos.ukarosoft.com con HTTPS completo. DNS (A record en
Squarespace/Google) → 161.35.142.183. nginx con bloque SSL 443 + redirección + HSTS,
docker-compose con servicio certbot + volúmenes, settings.py con SECURE_PROXY_SSL_HEADER
y cookies seguras. Cert emitido (exp 2026-08-31), renovación cron + dry-run OK.
Deploy quirúrgico vía scp de 3 archivos (NO git pull) para no tocar la divergencia del server.
