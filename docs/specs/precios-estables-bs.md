# Spec: Precios Estables en Bs

**Proyecto:** ukaro-abastos
**Fecha:** 2026-08-17 (decisiones cerradas, aprobada e implementada: 2026-09-04)
**Autor:** Claude Code (supervisado por Simón)
**Estado:** implementada — ver sección 7 (decisiones cerradas) y sección 9 (notas de implementación)

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

## 6. Tasks (implementación)

1. [x] Migración: agregar `Product.pricing_mode` (`CharField`, choices `usd`/`bs_fixed`, default `usd`).
2. [x] `Product.get_current_price_bs()`: branch por `pricing_mode`. De paso se agregó
   `Product.get_current_price_usd()` (equivalente informativo en modo `bs_fixed`) y ambos métodos
   ganaron parámetros `quantity` y `exchange_rate` opcionales — necesarios para no romper precio al
   mayor (no contemplado en el diseño original, ver sección 9.1) y para no repetir la consulta de
   tasa ítem por ítem en una venta.
3. [x] `Product.get_current_purchase_price_bs()`: sin cambios — siempre modo `usd` (decisión 7.2).
4. [x] `ProductService.bulk_update_prices` / `update_product_prices`: excluyen el precio de VENTA de
   productos `bs_fixed`; el de COMPRA se sigue sincronizando siempre, para todos los productos.
5. [x] `sales/api_views.py`: reemplazado el cálculo manual duplicado tanto en `process_regular_sale`
   como en el loop de pre-cálculo de totales de `create_sale_api` (esta segunda duplicación no estaba
   listada explícitamente en esta spec, pero es el mismo patrón — ver sección 9.2).
6. [x] `inventory/api_views.py`: `profit_margin`/`profit_percentage` en `product_detail_api` ahora usan
   `get_current_price_bs()`/`get_current_purchase_price_bs()`.
7. [x] `ProductForm`: `pricing_mode` (select) + `selling_price_bs` condicional, con Alpine.js
   (`x-show`, sin JS inline) en `product_form.html`.
8. [x] Templates: `product_form.html` (toggle + campo Bs + equivalente informativo + margen
   recalculado), `product_list.html` y `product_detail.html` (badge "Bs fijo").
9. [x] Bug preexistente de `inventory/api_views.py:310` corregido (decisión 7.3) — el reporte de
   valorización (`product_stock_summary_api`) ahora calcula en vivo con la tasa actual vía
   `Case`/`When` sobre `pricing_mode`, en vez de leer las columnas vestigiales.
10. [x] Tests nuevos: modelo (`ProductPricingModeTest`), formulario (`ProductFormPricingModeTest`),
    API de venta (`SaleCreateAPIBsFixedTest`), servicio (exclusión bs_fixed en
    `ProductServiceUpdatePricesTest`), reporte de valorización (`ProductStockSummaryValorizationTest`).
11. [ ] Actualizar `docs/PENDIENTES.md` al cerrar.

## 7. Decisiones (cerradas por Simón el 2026-09-04)

1. **Nivel del toggle: solo por producto individual.** Sin acción masiva por ahora — se puede agregar
   después sobre el mismo campo si Leida lo necesita.
2. **Alcance de "congelar": confirmado — solo el precio de VENTA se congela.** El precio de compra a
   proveedores siempre sigue en USD × tasa actual, sin importar el modo del producto. Verificado en
   `ProductService.update_product_prices`/`bulk_update_prices` y en `ProductForm.clean()`.
3. **Bug de valorización de inventario: corregido en el mismo trabajo.** `product_stock_summary_api`
   ya no lee `purchase_price_bs`/`selling_price_bs` (vestigiales) — calcula en vivo con la tasa actual
   y respeta el precio fijo de los productos `bs_fixed`.
4. **Aviso de precio desactualizado: no implementado — se empezó simple.** Puede agregarse después
   sin romper nada si Leida lo pide tras usar la feature.

## 8. Verification

- [x] Tests pasan (`python manage.py test inventory sales`) — las únicas fallas del suite son 6
  preexistentes, no relacionadas (verificado corriendo el mismo test contra el commit previo a esta
  sesión, `git worktree` en `f0f909a`: fallan exactamente igual sin ninguno de estos cambios).
- [ ] Prueba manual pendiente: crear un producto en modo `bs_fixed` desde la UI real, vender una
  unidad, confirmar que `SaleItem.price_bs` coincide exactamente con el precio fijado.
- [ ] Prueba manual pendiente: cambiar la tasa BCV y confirmar visualmente que el precio del producto
  `bs_fixed` no se mueve, mientras que uno en modo `usd` sí refleja la tasa nueva.
- [ ] Review de Simón (y de Leida, si hace falta validar el flujo desde el punto de vista de uso
  diario en caja).

## 9. Notas de implementación (hallazgos durante el desarrollo, no cambian el diseño aprobado)

1. **Precio al mayor (`is_bulk_pricing`) no estaba contemplado en el diseño original** (secciones 1-7
   no lo mencionan) y resultó ser una feature real y activa en `sales/api_views.py` y
   `product_form.html` — no un campo vestigial. Reemplazar ingenuamente el cálculo por
   `product.get_current_price_bs()` sin parámetros habría roto el precio al mayor para TODO producto
   en modo `usd` (regresión real, no cosmética). Se resolvió dándole a `get_current_price_bs()`/
   `get_current_price_usd()` un parámetro `quantity` opcional que preserva el comportamiento actual en
   modo `usd`, y se decidió (no estaba en la spec original) que el modo `bs_fixed` **no tiene
   equivalente de precio al mayor** — `ProductForm.clean()` rechaza activar ambos a la vez, y la UI
   deshabilita el checkbox de precio al mayor cuando el modo es Bs fijo.
2. **Segunda duplicación del cálculo de precio, no listada en la spec original:** además de
   `process_regular_sale` (sí mencionado en la tarea 5 original), `create_sale_api` tiene un loop de
   pre-cálculo de totales (`total_usd`/`total_bs` de la venta) que repetía la misma fórmula manual por
   separado. Si solo se corregía `process_regular_sale`, el total de la venta y el precio real de cada
   ítem habrían quedado inconsistentes para productos `bs_fixed`. Se corrigieron ambos con la misma
   fuente de verdad.
3. **`utils/api_views.py:product_by_barcode`** (el endpoint real que usa el punto de venta al escanear
   un código de barras, `templates/sales/sale_form.html`) tenía la misma fórmula duplicada — no
   mencionado en la spec original porque no se había rastreado hasta ahí. Corregido para no mostrarle
   al cajero un precio incorrecto de un producto `bs_fixed` al escanearlo.
4. **Bug real preexistente, no relacionado, corregido de paso** (autorizado explícitamente por Simón
   antes de tocarlo): el conversor USD→Bs de `product_form.html` (el mismo bloque editado para el
   toggle) inyectaba `{{ latest_exchange_rate.bs_to_usd }}` sin `|unlocalize` dentro de una expresión
   JS — con `LANGUAGE_CODE=es-ve` esto renderiza con coma decimal (`40,00`), y `purchasePrice * 40,00`
   en JS es el operador coma (evalúa `purchasePrice * 40`, lo descarta, y el resultado real es `40.00`
   fijo vía `.toFixed(2)` sobre `50`... en la práctica: el preview de conversión siempre mostraba
   "Bs 0.00"). Mismo patrón de bug ya documentado en el histórico de la calculadora del navbar
   (ver `docs/PENDIENTES.md`, punto de la calculadora, 2026-08-17).
5. **Hallazgo sin corregir, anotado en `docs/PENDIENTES.md` como deuda aparte:** en
   `inventory/api_views.py:product_by_barcode_api`, el bloque `bulk_pricing` lee
   `product.bulk_price_bs`, un atributo que **no existe** en el modelo `Product` (solo existe
   `bulk_price_usd`) — cualquier producto con `is_bulk_pricing=True` que se escanee por esta ruta
   específica (`inventory:product_by_barcode_api`, distinta de la que usa el punto de venta) dispara
   un `AttributeError` no controlado. No se tocó por estar fuera del alcance de esta spec (estructura
   de datos de precio al mayor, no de precios en Bs), pero queda documentado para no perderlo.
