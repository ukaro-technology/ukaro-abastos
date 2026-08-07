# scripts/export_ventas_recuperacion_10_11_julio.py
#
# Exporta el detalle COMPLETO de las ventas del 10 y 11 de julio de 2026
# (días de caída de DigitalOcean por falta de pago, atendidos con la versión
# de abril reactivada en PythonAnywhere) para poder recrearlas en producción.
#
# A diferencia de exportar_ventas_dia (que solo exporta cantidades agregadas
# para ajustar inventario), este script exporta cada venta individual completa
# — cliente, método de pago, precios, crédito — porque el objetivo es recrear
# las ventas reales, no solo corregir stock.
#
# Uso (en la consola Bash de PythonAnywhere, dentro del directorio del proyecto):
#   python manage.py shell < scripts/export_ventas_recuperacion_10_11_julio.py
#
# Genera export_ventas_10_11_julio.json en el directorio actual.
# Es de SOLO LECTURA — no modifica nada en PythonAnywhere.
#
# NOTA: esta instancia es anterior a la migración del 5-abr-2026 que agregó
# el campo `cedula` a Customer, así que no existe aquí. Se usa getattr() por
# si acaso, y se exporta teléfono como identificador secundario.

import json
from datetime import date

from sales.models import Sale

FECHA_DESDE = date(2026, 7, 10)
FECHA_HASTA = date(2026, 7, 11)


def dec(valor):
    """Decimal -> str para no perder precisión al pasar por JSON."""
    return str(valor) if valor is not None else None


ventas = (
    Sale.objects.filter(date__date__gte=FECHA_DESDE, date__date__lte=FECHA_HASTA)
    .select_related("customer", "user")
    .prefetch_related("items", "items__product", "items__combo")
    .order_by("date")
)

data = []
for sale in ventas:
    items = []
    for item in sale.items.all():
        items.append(
            {
                "product_barcode": item.product.barcode if item.product else None,
                "product_name": item.product.name if item.product else None,
                "combo_name": item.combo.name if item.combo else None,
                "quantity": dec(item.quantity),
                "price_bs": dec(item.price_bs),
                "price_usd": dec(item.price_usd),
            }
        )

    credito = None
    if sale.is_credit and hasattr(sale, "credit"):
        c = sale.credit
        credito = {
            "amount_bs": dec(c.amount_bs),
            "amount_usd": dec(c.amount_usd),
            "exchange_rate_used": dec(c.exchange_rate_used),
            "date_due": c.date_due.isoformat() if c.date_due else None,
            "notes": c.notes,
        }

    data.append(
        {
            "pa_sale_id": sale.id,
            "date": sale.date.isoformat(),
            "customer_cedula": getattr(sale.customer, "cedula", None) if sale.customer else None,
            "customer_name": sale.customer.name if sale.customer else None,
            "customer_phone": sale.customer.phone if sale.customer else None,
            "cashier_username": sale.user.username if sale.user else None,
            "total_bs": dec(sale.total_bs),
            "total_usd": dec(sale.total_usd),
            "exchange_rate_used": dec(sale.exchange_rate_used),
            "payment_method": sale.payment_method,
            "mobile_reference": sale.mobile_reference,
            "is_credit": sale.is_credit,
            "notes": sale.notes,
            "items": items,
            "credit": credito,
        }
    )

with open("export_ventas_10_11_julio.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"\nExportadas {len(data)} ventas -> export_ventas_10_11_julio.json")
if data:
    print(f"Rango real encontrado: {data[0]['date']} -> {data[-1]['date']}")
    con_combo = sum(1 for v in data for it in v["items"] if it["combo_name"])
    con_credito = sum(1 for v in data if v["is_credit"])
    print(f"Ventas con crédito: {con_credito} | ítems de combo (revisión manual): {con_combo}")
else:
    print("¡Atención! No se encontró ninguna venta en ese rango — revisa las fechas.")
