# Spec — Demo SuperMoto Speed (tienda de repuestos de moto)

**Fecha:** 2026-10-21 · **Pedido por:** Simón · **Estado:** implementado en la rama `ccr-2db2fa98-fx0vm7`

## Contexto
SuperMoto Speed es una tienda de repuestos de moto en Guanare que abre ~1 de noviembre de
2026. Antes de contratar, el dueño verá un demo con su marca. Simón aprobó adaptar este mismo
sistema (no copiar el proyecto): **mismo código, un perfil por negocio, una instalación por
cliente**. El demo se publica en Render (`render.yaml`, `docs/deploy/render-demo.md`) o en
PythonAnywhere (`docs/deploy/pythonanywhere-demo.md`).

Datos del cliente que definieron el alcance: solo usan teléfonos (sin PC ni impresora), los
clientes piden "pastillas para una SBR" (por pieza y moto, no por código), unas piezas traen
código de barras y otras no, trabajan como Leida (USD a tasa BCV) pero el pago en dólares en
efectivo tiene descuento (ej. caucho $30 BCV → $25 en efectivo), dos usuarios con el mismo
nivel, sin factura fiscal por ahora.

## Decisiones

1. **Perfil de negocio** (`bodega_system/business.py`), elegido con `BUSINESS_PROFILE`
   (`bodega` por defecto = Leida sin cambios, `motoparts` = SuperMoto). Define nombre, logo,
   tema y módulos activos (`features`). Llega a las plantillas como `business`.
2. **Tema por CDN de Tailwind**: el tema `supermoto` redefine la paleta `blue` (color principal
   de todo el sistema) como el rojo de la marca (#FA0411) y pinta barra y menú en negro
   (`templates/base/_theme.html`). Cero cambios de clases en las plantillas existentes.
3. **App `parts`** (siempre instalada, tablas vacías en la bodega): `MotoBrand`, `MotoModel`,
   `PartInfo` (1 a 1 con `Product`: número de parte, marca, calidad, ubicación, universal,
   motos compatibles). `Product` **no cambia**. Se edita dentro del formulario de producto.
4. **Código de barras sigue obligatorio y único**: las piezas sin código usan el botón de
   "generar código" que ya existía (código interno). El escáner también acepta el número de
   parte. Así no se toca el esquema de Leida.
5. **Búsqueda palabra por palabra sin tildes** (`inventory/search.py`, `iregex` con clases de
   vocales), en el POS y en la lista de inventario. Aplica también a la bodega (mejora, no
   rompe nada); los campos de motos solo con `moto_parts`.
6. **Efectivo $**: método `cash_usd`, solo con el módulo `cash_usd`. Porcentaje único
   configurable (`utils.StoreSettings`, pantalla Configuración → Descuento en Efectivo $).
   El descuento se calcula **en el servidor**; `Sale.total_usd/total_bs` quedan descontados
   y `discount_percent/discount_usd` guardan el detalle. No aplica a ventas a crédito.
   La bodega rechaza `cash_usd` (400).
7. **Escáner con cámara**: `html5-qrcode@2.3.8` (unpkg), solo con `camera_scan`. Requiere HTTPS.
8. **Comprobante por WhatsApp** (`sales/whatsapp.py`): enlace `wa.me` con el resumen, en el
   detalle de venta y en un modal al completar la venta (en el teléfono `window.open` tras un
   `fetch` lo bloquea el navegador). Con `whatsapp_receipt`; la bodega conserva su
   comportamiento (abre el PDF).
9. **Módulos ocultos en el perfil motoparts**: Horarios y Rendimiento (siguen existiendo).
10. **Datos de ejemplo**: `python manage.py seed_motoparts_demo [--barcodes-pdf RUTA]` — motos
    de Bera, Empire Keeway, Suzuki y Yamaha, ~114 repuestos, clientes, fiados, proveedores,
    órdenes, gastos y un mes de ventas. Precios de referencia, no reales. Se niega a correr si
    ya hay productos (salvo `--force`).

## Fuera de alcance (después del demo, según el formulario del cliente)
Importación desde Excel/Google Sheets, devoluciones y garantías, precio para mecánicos,
cotizaciones y encargos, pago mixto (dos métodos en una venta), taller, factura fiscal,
migración a PostgreSQL/DonWeb.

## Limitaciones conocidas
- Reportes de rentabilidad por producto suman `SaleItem` a precio de lista: en ventas con
  descuento en efectivo, el ingreso por producto queda algo por encima del real (el total de
  la venta sí es correcto).
- El precio USD mostrado en el POS antes de cobrar no aplica precio al mayor (el servidor sí).

## Verificación
22 tests nuevos en `parts/tests.py`. Suite completa: mismas 9 failures + 5 errors
preexistentes, 0 regresiones (los tests de Playwright requieren Firefox, no disponible en el
entorno de desarrollo). Verificado con Chromium en viewport de teléfono: login, dashboard,
menú, búsqueda "pastilla sbr", carrito con Efectivo $, venta completada, inventario,
marcas/modelos, formulario de producto, detalle de venta. Probado `DEBUG=False` + gunicorn +
WhiteNoise sirviendo logo y estáticos.
