# Spec: Auditoría de Inventario (conteo físico vs sistema + trazabilidad)

**Proyecto:** ukaro-abastos
**Fecha:** 2026-08-08
**Autor:** Claude Code (supervisado por Simón)
**Estado:** borrador

## 1. Outcome (Resultado esperado)

Leida (o quien haga la auditoría) puede registrar el conteo físico real de la bodega, ver
automáticamente en qué productos difiere del sistema y por cuánto (en unidades y en USD), guardar
ese conteo como registro histórico, e imprimir/guardar un PDF con el detalle — y para cualquier
producto puntual, puede ver una línea de tiempo con todo lo que movió su stock (ventas, ajustes,
compras recibidas) para poder explicar el número ante una auditoría.

## 2. Scope

### Incluido
- **Modelo `InventoryCount`** (cabecera de una auditoría física): fecha, usuario que la hizo, notas,
  estado (`in_progress`/`completed`). Queda como registro permanente — no es un formulario que se usa
  y se descarta.
- **Modelo `InventoryCountItem`**: producto, `system_stock` (snapshot del stock del sistema al momento
  del conteo — no se recalcula después, para que el reporte no cambie si el stock del sistema sigue
  moviéndose), `physical_stock` (lo que se contó a mano), `difference` (calculado), `difference_value_usd`
  (calculado con `purchase_price_usd`).
- **Flujo de conteo:** elegir categoría (o "todas") → tabla con todos los productos activos de esa
  categoría, un input numérico por producto para el conteo físico → guardar → se crea el
  `InventoryCount` + sus items, con `system_stock` tomado en ese momento.
- **Reporte de discrepancias** (HTML + botón PDF, mismo patrón que `inventory_report`): tabla de
  productos con diferencia ≠ 0, ordenada por `|difference_value_usd|` descendente (lo que más impacta
  primero), con totales (cuántos productos con diferencia, valor total de la diferencia).
- **Lista de auditorías pasadas** (`inventory_count_list`, patrón `Paginator` estándar del proyecto):
  fecha, quién la hizo, cuántos productos con diferencia, link al detalle/PDF de cada una.
- **Reporte de trazabilidad por producto** (`product_traceability`): dado un producto y un rango de
  fechas (default: últimos 30 días), tabla cronológica combinando:
  - Ventas (`SaleItem` vía `sale.date`, cantidad negativa, referencia a la venta)
  - Ajustes manuales (`InventoryAdjustment.adjusted_at`, ya trae `reason`)
  - Compras recibidas (`SupplierOrderItem` vía `order.received_date`, solo `order.status='received'`,
    cantidad positiva)
  Con stock previo/nuevo cuando el dato está disponible (lo trae `InventoryAdjustment`; para
  ventas/compras se puede reconstruir corriendo el delta hacia atrás desde `product.stock` actual).
  Exportable a PDF, mismo patrón que los demás reportes.
- Permisos: todo detrás de `admin_required` (es herramienta de auditoría, no de operación diaria).
- Reusar `generate_pdf_response` de `finances/pdf_generators.py` para los PDFs nuevos — mismo look
  and feel que el resto de reportes del sistema.

### Excluido (por ahora, explícitamente fuera de esta spec)
- **Auto-ajustar el stock del sistema al valor físico contado.** El reporte de discrepancias es solo
  informativo en esta primera versión — no crea `InventoryAdjustment` automáticamente. (Ver pregunta
  abierta #1 abajo — si Simón lo quiere, es un paso más, no gran esfuerzo, pero cambia el nivel de
  riesgo de la feature y prefiero que sea una decisión explícita, no un default.)
- Conteo físico de combos (`ProductCombo`) — el sistema no tiene combos cargados actualmente (0 en
  producción), no hay nada que auditar ahí todavía.
- Cualquier tipo de conteo cíclico automático/programado, notificaciones, o app móvil para contar con
  el celular en el pasillo — esto es un formulario web como el resto del sistema, se llena desde una
  compu/tablet en la bodega.
- Dashboard en tiempo real — el objetivo declarado es documentación imprimible/archivable, no un panel
  interactivo.

## 3. Constraints (Restricciones)

- Django 5.2.6, sin multi-tenant (single-tenant, NO usar `.for_tenant()` — no existe ese patrón en
  este proyecto, es de otros proyectos Ukarasoft).
- `USE_TZ = False`, `TIME_ZONE = America/Caracas` — igual que el resto del sistema, fechas naive.
- PKs `BigAutoField` (default del proyecto), no UUID.
- Seguir el patrón ya establecido en `finances/views.py` + `finances/pdf_generators.py`:
  `request.GET` para filtros, `Paginator` para listas, `generate_pdf_response()` para PDFs
  (headers/rows/summary/metadata, no reinventar generación de PDF a mano).
- `admin_required` para las vistas nuevas (mismo decorador que ya usa `adjustment_list`).
- Tests con pytest-django antes de mergear (regla no negociable del proyecto — ver
  `bodega_system/tests/` para el patrón existente, hay 121+ tests).
- Migraciones nuevas (`InventoryCount`, `InventoryCountItem`) — revisar
  `docs/PENDIENTES.md`/convención `db-migration-strategy` antes de aplicar en producción.

## 4. Decisions Already Made

- Persistir el conteo como modelo (no un formulario de un solo uso) — Simón dijo explícitamente que
  quiere "guardarlos para su posterior revisión".
- `admin_required`, no `sales_access_required` — es herramienta de auditoría interna, no de venta.
- Reusar `generate_pdf_response` en vez de un generador de PDF nuevo desde cero.
- Combos quedan fuera del alcance (no hay datos que auditar).
- `system_stock` se guarda como snapshot en `InventoryCountItem` al momento del conteo, no se
  recalcula después — así el PDF de una auditoría vieja no cambia si el stock del sistema se sigue
  moviendo.

## 5. Preguntas abiertas — necesito tu respuesta antes de implementar

1. **¿El reporte de discrepancias debe poder generar los `InventoryAdjustment` automáticamente** para
   dejar el stock del sistema igual al conteo físico (con un botón explícito tipo "aplicar
   correcciones", no automático al guardar), **o preferís que quede solo informativo** y que cualquier
   corrección la hagan a mano desde la pantalla de ajustes que ya existe?
2. **¿Quién puede iniciar/completar un conteo?** ¿Cualquier admin, o específicamente Leida? (Ahora
   mismo Dueño/Veterinario/Encargado no aplica a este proyecto — ukaro-abastos no tiene roles
   diferenciados más allá de `is_admin`, así que la pregunta real es: ¿algún empleado no-admin debería
   poder REGISTRAR un conteo físico aunque no pueda ver el reporte de discrepancias completo?)
3. **Trazabilidad: ¿30 días por default está bien,** o normalmente vas a querer rangos más largos
   (ej. "todo julio" para casos como el de la caída de DO)?

## 6. Tasks (Implementación) — pendiente de aprobación, no arrancar todavía

1. [ ] Modelos `InventoryCount` + `InventoryCountItem` (app `inventory`) + migración
2. [ ] Vista `inventory_count_create` (elegir categoría, tabla de conteo, guardar)
3. [ ] Vista `inventory_count_detail` (reporte de discrepancias de un conteo puntual + botón PDF)
4. [ ] Vista `inventory_count_list` (histórico, patrón `Paginator` estándar)
5. [ ] `pdf_inventory_count_report()` en `finances/pdf_generators.py` (o `inventory/pdf_generators.py`
   si se prefiere mantenerlo en la app de inventario — a decidir según dónde viven los otros PDFs de
   esa app, si los hay)
6. [ ] Vista `product_traceability` (selector de producto + rango de fechas, timeline combinada)
7. [ ] `pdf_product_traceability()` (mismo patrón)
8. [ ] Templates (siguiendo el sistema de diseño ya usado en `inventory_report.html`/`adjustment_list.html`)
9. [ ] URLs + entradas de menú/navegación donde corresponda
10. [ ] Tests: cálculo de discrepancias (casos con stock igual, mayor, menor, producto sin conteo),
    construcción de la línea de tiempo de trazabilidad (orden cronológico correcto, mezcla de las 3
    fuentes), permisos (`admin_required` bloquea no-admins)
11. [ ] Verificación manual con datos reales de producción (no solo sintéticos) antes de dar por
    terminado — capturar pantallas, mismo criterio que el resto del proyecto

## 7. Verification (Cómo verificar)

- [ ] `pytest` en verde, incluyendo los tests nuevos del punto 10
- [ ] Verificación manual: hacer un conteo real de una categoría chica en producción, confirmar que
  las discrepancias calculadas coinciden con una cuenta a mano
- [ ] Verificación manual: pedir la trazabilidad de un producto con historial mixto (venta + ajuste +
  compra) y confirmar que el orden y los deltas son correctos
- [ ] PDFs se generan sin error y con el mismo estilo visual que los reportes existentes
- [ ] Review de Simón antes de mergear
