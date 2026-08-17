# Spec: Precios Estables en Bs

**Proyecto:** ukaro-abastos
**Fecha:** 2026-08-17
**Autor:** Claude Code (supervisado por Simón)
**Estado:** borrador — pendiente de decisiones abiertas (sección 7) y aprobación de Simón

## 1. Outcome (Resultado esperado)

Leida puede marcar productos puntuales como **"precio estable en Bs"** y fijarles un precio de venta
en bolívares que el sistema usa tal cual (en el punto de venta, en el detalle del producto y en los
reportes) hasta que ella misma lo cambie a mano — sin que suba o baje solo cuando alguien actualice la
tasa BCV. El resto de los productos (modo por defecto) sigue funcionando exactamente igual que hoy:
precio en Bs = precio en USD × tasa BCV del momento.

## 2. Cómo funciona el sistema HOY (hallazgo, no es una decisión — es el punto de partida real)

Investigado el código antes de diseñar, porque el comportamiento actual no es "Bs se recalcula al
guardar la tasa": **es más simple y más volátil que eso.**

- El sistema es 100% USD-céntrico: `Product.selling_price_usd` es el único precio que un admin edita
  (`ProductForm` en `inventory/forms.py` ni siquiera expone `selling_price_bs`/`purchase_price_bs`
  como campos del formulario).
- El "precio actual en Bs" que ve el cajero **no sale de una columna de la base de datos** — se calcula
  al vuelo, en cada request, como `selling_price_usd × ExchangeRate.get_latest_rate().bs_to_usd`
  (`Product.get_current_price_bs()` en `inventory/models.py:189`). Esto es lo que sirve
  `inventory/api_views.py` al carrito del punto de venta (`sale_form.html`), y es lo que
  `sales/api_views.py:process_regular_sale` recalcula (con su propia multiplicación, duplicada) al
  momento de guardar la venta.
- Las columnas `Product.selling_price_bs` / `purchase_price_bs` en la base de datos **sí existen pero
  hoy son prácticamente vestigiales**: solo se escriben una vez, al crear el producto
  (`ProductService.create_product`). Las funciones pensadas para mantenerlas sincronizadas
  (`ProductService.update_product_prices` y `bulk_update_prices`, en `inventory/services.py`) **no las
  llama nadie en el código de producción** — ni un signal al guardar `ExchangeRate`, ni ninguna vista.
  Con el tiempo quedan desactualizadas.
- **Bug preexistente encontrado de paso** (no lo introduce esta spec, ya existe): el reporte de
  valorización de inventario (`inventory/api_views.py:310`,
  `Sum(F('stock') * F('selling_price_bs'))`) sí lee esa columna vestigial directamente por SQL, así
  que el valor total de inventario en Bs que muestra ese reporte puede estar desactualizado respecto a
  la tasa actual. Ver sección 7 para decidir si se corrige junto con esta feature.
- Combos (`ProductCombo.combo_price_bs`) ya son "Bs fijo, no derivado de USD" — pero el módulo de
  combos está deshabilitado en el menú (`<!-- TEMPORALMENTE DESHABILITADO -->` en `base.html`) y su
  flujo de venta tiene un `TODO` pendiente en `sales/api_views.py`. Fuera de alcance de esta spec.

**Consecuencia para el diseño:** no hay que "romper" un mecanismo de recálculo automático — hay que
introducir el concepto de que un producto puede tener un precio Bs que es la fuente de verdad, en vez
de un precio USD que siempre lo es. El punto correcto para centralizar esa decisión es
`Product.get_current_price_bs()`, porque casi todos los caminos de lectura ya pasan por ahí (excepto
`sales/api_views.py`, que duplica la fórmula en vez de llamarlo — se corrige como parte de esta spec).

## 3. Scope

### Incluido
- Campo nuevo `Product.pricing_mode` (`'usd'` por defecto | `'bs_fixed'`), por producto — no hay modo
  global ni por categoría (ver decisión abierta 7.1).
- Cuando `pricing_mode='bs_fixed'`:
  - `selling_price_bs` pasa a ser un campo **editable directamente** en `ProductForm` (hoy no lo es).
  - `Product.get_current_price_bs()` devuelve `self.selling_price_bs` tal cual, sin tocar la tasa.
  - `selling_price_usd` se seguía mostrando (de solo lectura, calculado al vuelo como
    `selling_price_bs / tasa_actual`) únicamente como referencia informativa de margen — no dirige el
    precio de venta. `purchase_price_usd` no cambia de comportamiento (ver 7.2: la compra a
    proveedores se sigue manejando en USD siempre, congelar solo aplica a precio de venta).
  - `ProductService.bulk_update_prices` / `update_product_prices` **excluyen** productos en
    `bs_fixed` (`.exclude(pricing_mode='bs_fixed')`).
- `sales/api_views.py:process_regular_sale` deja de recalcular `price_usd * exchange_rate.bs_to_usd`
  a mano y pasa a llamar `product.get_current_price_bs()` — mismo resultado para productos en modo
  `usd` (comportamiento actual, sin cambios), y respeta el precio fijo para productos en `bs_fixed`.
  De paso elimina una duplicación de lógica de precios que hoy vive en dos lugares.
- `inventory/api_views.py:55-57` (cálculo de `profit_margin` con el campo crudo `selling_price_bs`)
  pasa a usar `get_current_price_bs()` también, para que el margen mostrado sea consistente con el
  precio real de venta en ambos modos.
- UI: en `product_form.html`, un toggle "Precio estable en Bs" que al activarse:
  - Muestra un campo numérico para el precio en Bs (en vez del campo USD como precio "mandante").
  - Muestra un texto de ayuda con el equivalente USD actual, sin permitir editarlo.
- UI: en `product_list.html` / `product_detail.html`, una etiqueta visible ("Bs fijo") en los
  productos que estén en ese modo, para que no se confunda con el resto.
- Historial de cambios de precio ya viene gratis: `Product` ya tiene `HistoricalRecords()`
  (`django-simple-history`), así que cada cambio manual del precio Bs queda auditado sin trabajo
  adicional.
- Migración de datos: productos existentes quedan todos en `pricing_mode='usd'` (comportamiento
  actual, sin cambios para nadie que no active el toggle).
- Tests: cobertura para ambos modos en `Product.get_current_price_bs()`, en la API de creación de
  venta (`create_sale_api`), y en `bulk_update_prices` (confirma que NO toca productos `bs_fixed`).

### Excluido (explícitamente, no es "para después" silencioso)
- Combos (`ProductCombo`) — ya están en Bs fijo por diseño previo, pero el módulo está deshabilitado;
  no se toca en esta spec.
- Congelar el precio de **compra** (`purchase_price_usd`/`_bs`) — la compra a proveedores sigue
  siempre en USD × tasa actual, sin importar el modo del producto.
- Cualquier automatismo de "sugerir" cuándo actualizar el precio Bs fijo (por ejemplo, alertar si la
  tasa se movió mucho desde la última vez que se fijó el precio). Podría ser una spec futura si Leida
  lo pide después de usar la feature.
- Tocar el flujo de créditos de clientes (`customers` app) — ya guarda `amount_bs`/`amount_usd`/
  `exchange_rate_used` como snapshot congelado al momento de la venta (`CustomerCredit`,
  `sales/api_views.py:102-110`), así que un producto en `bs_fixed` no le agrega ningún problema nuevo:
  el crédito ya no se recalcula con la tasa del día, se calculó una sola vez al vender.

## 4. Constraints

- Stack: Django + HTMX + Alpine.js + Tailwind (según `CLAUDE.md` del proyecto).
- Single-tenant (este proyecto no tiene multi-tenant, no aplica `.for_tenant()`).
- `USE_TZ = False` — sin implicaciones aquí, no se tocan fechas/horas.
- Tests obligatorios antes de cualquier merge (42+ tests actuales deben seguir pasando, más los
  nuevos de esta feature).
- Solo administradores pueden crear/editar productos (`admin_required` ya presente en
  `product_create`/`product_update`) — el toggle de precio estable hereda ese mismo permiso, no se
  agrega un permiso nuevo.

## 5. Decisions Already Made

- El modo es **por producto**, no global ni por categoría (más simple de implementar y de razonar; un
  toggle por categoría se puede agregar después como acción masiva sobre el mismo campo si hace
  falta).
- Se centraliza toda la lectura de "precio de venta actual en Bs" en
  `Product.get_current_price_bs()` — ningún otro lugar del código vuelve a multiplicar
  `selling_price_usd * tasa` a mano.
- El precio de compra a proveedores NO se congela nunca — solo el precio de venta al público.
- No se toca el flujo de créditos de clientes: ya está desacoplado de la tasa del día por diseño
  previo (snapshot al momento de la venta).

## 6. Tasks (implementación — a ejecutar solo después de aprobación)

1. [ ] Migración: agregar `Product.pricing_mode` (`CharField`, choices `usd`/`bs_fixed`, default `usd`).
2. [ ] `Product.get_current_price_bs()`: branch por `pricing_mode`.
3. [ ] `Product.get_current_purchase_price_bs()`: revisar si necesita el mismo tratamiento o se deja
   siempre en modo `usd` (según decisión 7.2).
4. [ ] `ProductService.bulk_update_prices` / `update_product_prices`: excluir `bs_fixed`.
5. [ ] `sales/api_views.py:process_regular_sale`: reemplazar cálculo manual por
   `product.get_current_price_bs()`.
6. [ ] `inventory/api_views.py`: usar `get_current_price_bs()` en el cálculo de `profit_margin`.
7. [ ] `ProductForm`: campo condicional de precio Bs + toggle de modo (probablemente con Alpine.js
   para mostrar/ocultar en el mismo form, sin JS inline — ver skill `form-design`/`alpine-components`).
8. [ ] Templates: `product_form.html`, `product_list.html`, `product_detail.html` — toggle y badge
   visual.
9. [ ] Decidir y, si aplica, corregir el bug preexistente de `inventory/api_views.py:310` (sección 7.3).
10. [ ] Tests nuevos (modelo, servicio, API de venta, formulario).
11. [ ] Actualizar `docs/PENDIENTES.md` al cerrar.

## 7. Preguntas abiertas (decidir antes de implementar)

1. **Nivel del toggle:** ¿por producto individual (recomendado, ya asumido en la sección 5) o también
   se necesita una acción masiva ("aplicar Bs fijo a toda una categoría de un tirón")? Si Leida
   piensa fijar precios de decenas de productos a la vez, vale la pena una acción bulk desde
   `product_list.html` en vez de entrar producto por producto.
2. **Alcance de "congelar":** ¿confirmar que solo el precio de **venta** se congela y el de **compra**
   siempre sigue en USD/tasa? Así lo asume la sección 5, pero es la decisión de negocio más importante
   de esta spec — vale confirmarla explícitamente.
3. **Bug preexistente de valorización de inventario** (sección 2): ¿se corrige en el mismo trabajo
   (sincronizar `selling_price_bs` también para productos en modo `usd`, para que el reporte de
   valorización sea preciso en ambos modos) o se deja anotado en `docs/PENDIENTES.md` como deuda
   aparte, para no mezclar un fix de un bug viejo con una feature nueva?
4. **Aviso de precio desactualizado:** cuando la tasa BCV suba/baje mucho desde la última vez que se
   fijó un precio Bs estable, ¿el sistema debe mostrar algún aviso visual ("este precio no se toca
   hace X días / la tasa se movió Y%") para que Leida no se le olvide revisarlo? Se puede agregar
   después sin romper nada si se prefiere empezar simple.

## 8. Verification (cómo verificar antes de dar por cerrada la spec)

- [ ] Tests pasan (`python manage.py test`).
- [ ] Prueba manual: crear un producto en modo `bs_fixed`, vender una unidad, confirmar que
  `SaleItem.price_bs` coincide exactamente con el precio fijado (no con USD × tasa del día).
- [ ] Prueba manual: cambiar la tasa BCV y confirmar que el precio del producto `bs_fixed` no se
  mueve, mientras que un producto en modo `usd` sí refleja la tasa nueva.
- [ ] Review de Simón (y de Leida, si hace falta validar el flujo desde el punto de vista de uso
  diario en caja).
