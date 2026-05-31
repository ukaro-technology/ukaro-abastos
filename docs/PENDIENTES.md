# Pendientes — Ukaro Abastos

## Decisiones activas
- Cliente activo: Leida. LIVE en DigitalOcean 161.35.142.183
- Deploy policy: DigitalOcean (cumplido)
- Deploy manual via Docker (sin git en el working copy del servidor)
- Sin GitHub Actions — deploy se hace con SSH + docker compose

## Próximos pasos
- [ ] **SSL con Certbot — CRÍTICO** (cliente activo sin HTTPS desde producción)
- [ ] Git en working copy del servidor (actualmente deploy manual via Docker)
- [ ] Dominio propio (actualmente solo IP)
- [ ] Health endpoint /health/ para monitoreo automático en Factory
- [ ] CI/CD pipeline (GitHub Actions)
- [ ] Limpiar ramas huérfanas `claude/*` en GitHub

## Completado
- [x] Deploy inicial en DigitalOcean ✅ (2026-04-25)
- [x] 42+ tests pasando ✅
- [x] Finanzas duales USD/Bs con tasa de cambio ✅
- [x] 2 bugs resueltos ✅ (2026-04-16)

## Última sesión
2026-05-31: Revisión de estado. Sin sesión de desarrollo activa desde 2026-05-01.
SSL crítico sigue pendiente — cliente vivo sin HTTPS. Próxima acción debe ser resolver esto.
