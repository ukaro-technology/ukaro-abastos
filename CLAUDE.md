# CLAUDE.md — Ukaro Abastos (Sistema de Bodega)

Instrucciones para Claude Code al trabajar en este proyecto.

## Cliente
**Leida** — Bodega/abasto en Guanare, Venezuela.
Sistema de gestión de inventario, ventas, proveedores, clientes y finanzas.

## Estado
**En producción** — IP: 161.35.142.183 (DigitalOcean)
42 tests pasando. 2 bugs resueltos 2026-04-16.
Deploy pendiente: no hay git en el working copy del servidor.

---

## Stack

| Capa | Tecnología | Notas |
|------|-----------|-------|
| Backend | Django 5.2.6 + Python 3.12+ | `DJANGO_SETTINGS_MODULE=bodega_system.settings` |
| Base de datos | PostgreSQL 16 (prod), SQLite (dev) | Switch automático por env var `DB_NAME` |
| CSS | Tailwind CDN + crispy-tailwind | `CRISPY_TEMPLATE_PACK = 'tailwind'` |
| JS | HTMX (django-htmx) | Middleware HtmxMiddleware activo |
| Archivos estáticos | WhiteNoise | CompressedManifestStaticFilesStorage |
| API | Django REST Framework | SessionAuthentication, solo autenticados |
| Historial | django-simple-history | HistoryRequestMiddleware activo |
| PDF | ReportLab | Para reportes y comprobantes |
| Deploy | Docker + Nginx + Gunicorn | 3 workers, timeout 120s |

---

## Estructura del proyecto

```
ukaro-abastos/
├── bodega_system/             # Django root (manage.py aquí)
│   ├── bodega_system/         # Config (settings.py, urls.py, wsgi.py, views.py)
│   ├── accounts/              # User (AbstractUser), login, roles
│   ├── inventory/             # Category, Product, InventoryAdjustment, ProductCombo, ComboItem
│   ├── sales/                 # Sale, SaleItem
│   ├── suppliers/             # Supplier, SupplierOrder, SupplierOrderItem, SupplierPayment
│   ├── customers/             # Customer, CustomerCredit, CreditPayment, CustomerGeneralPayment
│   ├── finances/              # Expense, ExpenseReceipt, DailyClose
│   ├── utils/                 # Middleware, context_processors, API consolidada
│   ├── performance/           # Métricas de rendimiento
│   ├── templates/             # Templates globales
│   ├── static/                # CSS, JS, imágenes
│   ├── tests/                 # Tests Playwright (frontend)
│   └── scripts/               # Scripts auxiliares
├── docker-compose.yml         # PostgreSQL 16 + Web + Nginx
├── Dockerfile
├── nginx/nginx.conf
├── .env.example
└── requirements.txt
```

---

## Modelos clave

### Auth
- `accounts.User` (AbstractUser) — `AUTH_USER_MODEL = 'accounts.User'`
- Roles via middleware `RoleBasedAccessMiddleware`

### Inventario
- `Category` → `Product` (con historial simple_history)
- `InventoryAdjustment` — ajustes manuales de stock
- `ProductCombo` → `ComboItem` — combos de productos

### Ventas
- `Sale` → `SaleItem` — ventas con ítems

### Proveedores
- `Supplier` → `SupplierOrder` → `SupplierOrderItem`
- `SupplierPayment` — pagos a proveedores

### Clientes
- `Customer` → `CustomerCredit` → `CreditPayment`
- `CustomerGeneralPayment` — pagos generales

### Finanzas
- `Expense` → `ExpenseReceipt` — gastos con comprobantes
- `DailyClose` — cierre diario de caja

---

## Multi-tenant

**NO tiene multi-tenant.** Este proyecto es single-tenant (una sola bodega).
No usa Organization/TenantMiddleware/for_tenant().

---

## PKs
`DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'` — AutoField, NO UUIDs.

---

## Localización
- `LANGUAGE_CODE = 'es-ve'`
- `TIME_ZONE = 'America/Caracas'`
- `USE_TZ = False` — fechas sin timezone

---

## URLs principales

```
/                    → Dashboard (login required)
/accounts/login/     → Login
/admin/              → Django admin
/sales/              → Ventas
/inventory/          → Inventario
/customers/          → Clientes
/suppliers/          → Proveedores
/finances/           → Finanzas
/performance/        → Métricas
/utils/              → Utilidades (tasa de cambio, etc.)
/api/                → APIs consolidadas (DRF)
/analytics/          → Dashboard analytics
/my-stats/           → Estadísticas del usuario
```

---

## Comandos de desarrollo

```bash
cd bodega_system
python3 -m venv env
source env/bin/activate
pip install -r ../requirements.txt
python manage.py migrate
python manage.py runserver
# http://localhost:8000
```

## Tests

```bash
cd bodega_system
python manage.py test
# Tests en: accounts, inventory, sales, suppliers, customers, finances
# Tests Playwright en: tests/test_frontend_playwright.py
```

---

## Deploy (Docker)

```bash
# En el servidor (161.35.142.183)
docker compose up -d --build
# Nginx en puerto 80, Gunicorn en 8000 (interno)
```

## Variables de entorno

```
SECRET_KEY=<clave segura>
DEBUG=False
ALLOWED_HOSTS=161.35.142.183,localhost
DB_NAME=abastos_db
DB_USER=abastos_user
DB_PASSWORD=<contraseña segura>
DB_HOST=db
DB_PORT=5432
```

---

## Contexto de negocio

- **Finanzas duales:** El sistema maneja USD y Bs (bolívares) con tasa de cambio configurable
- **Tasa de cambio** se inyecta globalmente via `utils.context_processors.exchange_rate`
- **Créditos de clientes:** Sistema de fiado con pagos parciales
- **Cierre diario:** Cuadre de caja al final del día
- **Combos:** Productos agrupados con precio especial

---

## Advertencias

1. **Deploy sin git:** El servidor de producción no tiene git configurado en el working copy. Deploy manual via Docker.
2. **Ramas huérfanas en GitHub:** Hay varias ramas `claude/*` que probablemente deben limpiarse.
3. **USE_TZ = False:** Cuidado al comparar timestamps si se integra con sistemas que usan UTC.

---

*Documento generado: 2026-04-25 por claude-code*
