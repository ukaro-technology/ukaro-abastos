# inventory/management/commands/exportar_ventas_dia.py
# Exporta las ventas de un día como JSON para ajuste manual de inventario.
# Útil cuando el sistema externo (PythonAnywhere) tuvo ventas que no se reflejan aquí.
#
# Uso:
#   python manage.py exportar_ventas_dia 2026-04-06
#   python manage.py exportar_ventas_dia 2026-04-06 --output ventas_6abr.json

import json
from decimal import Decimal
from datetime import date, datetime

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Sum

from sales.models import SaleItem


class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)


class Command(BaseCommand):
    help = "Exporta las ventas de un día como JSON (para ajuste de inventario en otro sistema)"

    def add_arguments(self, parser):
        parser.add_argument(
            "fecha",
            type=str,
            help="Fecha en formato YYYY-MM-DD",
        )
        parser.add_argument(
            "--output",
            type=str,
            default=None,
            help="Archivo de salida (opcional). Si no se indica, imprime en consola.",
        )

    def handle(self, *args, **options):
        fecha_str = options["fecha"]
        try:
            fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        except ValueError:
            raise CommandError(f"Fecha inválida: '{fecha_str}'. Usa formato YYYY-MM-DD.")

        # Agrupa por código de barras para obtener total vendido por producto
        items = (
            SaleItem.objects.filter(
                sale__date__date=fecha,
                product__isnull=False,
            )
            .values("product__barcode", "product__name")
            .annotate(total_qty=Sum("quantity"))
            .order_by("product__name")
        )

        if not items:
            self.stdout.write(
                self.style.WARNING(f"No se encontraron ventas para el {fecha_str}.")
            )
            return

        data = {
            "fecha": fecha_str,
            "exportado_desde": "PythonAnywhere",
            "total_productos": len(items),
            "ventas": [
                {
                    "barcode": item["product__barcode"],
                    "nombre": item["product__name"],
                    "cantidad_vendida": str(item["total_qty"]),
                }
                for item in items
            ],
        }

        output = json.dumps(data, cls=DecimalEncoder, ensure_ascii=False, indent=2)

        if options["output"]:
            with open(options["output"], "w", encoding="utf-8") as f:
                f.write(output)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Exportados {len(items)} productos → {options['output']}"
                )
            )
        else:
            self.stdout.write(output)
            self.stdout.write(
                self.style.SUCCESS(f"\nTotal: {len(items)} productos con ventas el {fecha_str}")
            )
