# inventory/management/commands/ajuste_ventas_externas.py
# Aplica ajustes de inventario a partir de ventas registradas en un sistema externo.
# Úsalo cuando hubo ventas en PythonAnywhere que no se reflejaron en DigitalOcean.
#
# Flujo:
#   1. En PythonAnywhere: python manage.py exportar_ventas_dia 2026-04-06 --output ventas.json
#   2. Copiar ventas.json a este servidor
#   3. Aquí: python manage.py ajuste_ventas_externas ventas.json
#
# Opciones:
#   --dry-run     Solo muestra qué haría, sin modificar nada
#   --usuario ID  ID del usuario registrado como autor del ajuste (default: primer superuser)

import json
from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from inventory.models import InventoryAdjustment, Product

User = get_user_model()


class Command(BaseCommand):
    help = "Aplica ajustes de inventario desde un JSON de ventas externas (PythonAnywhere)"

    def add_arguments(self, parser):
        parser.add_argument(
            "archivo",
            type=str,
            help="Ruta al archivo JSON exportado con exportar_ventas_dia",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Simula el ajuste sin guardar nada en la base de datos",
        )
        parser.add_argument(
            "--usuario",
            type=int,
            default=None,
            help="ID del usuario que realiza el ajuste (default: primer superuser)",
        )

    def handle(self, *args, **options):
        # Cargar JSON
        try:
            with open(options["archivo"], encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            raise CommandError(f"Archivo no encontrado: {options['archivo']}")
        except json.JSONDecodeError as e:
            raise CommandError(f"JSON inválido: {e}")

        ventas = data.get("ventas", [])
        fecha = data.get("fecha", "desconocida")
        origen = data.get("exportado_desde", "sistema externo")

        if not ventas:
            self.stdout.write(self.style.WARNING("El archivo no contiene ventas."))
            return

        # Obtener usuario para el ajuste
        if options["usuario"]:
            try:
                usuario = User.objects.get(pk=options["usuario"])
            except User.DoesNotExist:
                raise CommandError(f"Usuario con ID {options['usuario']} no existe.")
        else:
            usuario = User.objects.filter(is_superuser=True).first()
            if not usuario:
                raise CommandError(
                    "No hay superusuarios. Usa --usuario ID para especificar uno."
                )

        dry_run = options["dry_run"]
        if dry_run:
            self.stdout.write(self.style.WARNING("--- MODO DRY-RUN: no se guardará nada ---\n"))

        self.stdout.write(
            f"Ajustando inventario — ventas del {fecha} ({origen})\n"
            f"Usuario: {usuario.username} | Productos en archivo: {len(ventas)}\n"
        )

        # Procesar ajustes
        aplicados = []
        errores = []

        with transaction.atomic():
            for item in ventas:
                barcode = item.get("barcode", "")
                nombre = item.get("nombre", barcode)
                try:
                    cantidad = Decimal(str(item.get("cantidad_vendida", 0)))
                except InvalidOperation:
                    errores.append(f"  ✗ {nombre}: cantidad inválida ({item.get('cantidad_vendida')})")
                    continue

                if cantidad <= 0:
                    errores.append(f"  ✗ {nombre}: cantidad debe ser > 0")
                    continue

                try:
                    producto = Product.objects.get(barcode=barcode)
                except Product.DoesNotExist:
                    errores.append(f"  ✗ {nombre} (código: {barcode}): producto no encontrado en DO")
                    continue

                stock_anterior = producto.stock
                nuevo_stock = max(stock_anterior - cantidad, Decimal("0"))

                if not dry_run:
                    InventoryAdjustment.objects.create(
                        product=producto,
                        adjustment_type="remove",
                        quantity=cantidad,
                        previous_stock=stock_anterior,
                        new_stock=nuevo_stock,
                        reason=f"Ajuste migración: ventas del {fecha} registradas en {origen}",
                        adjusted_by=usuario,
                    )
                    producto.stock = nuevo_stock
                    producto.save(update_fields=["stock"])

                estado = "(DRY-RUN)" if dry_run else "✓"
                aplicados.append(
                    f"  {estado} {nombre}: {stock_anterior} → {nuevo_stock} (-{cantidad})"
                )

            if dry_run:
                # Revertir todo si es dry-run
                transaction.set_rollback(True)

        # Resumen
        self.stdout.write("\n--- AJUSTES APLICADOS ---")
        for linea in aplicados:
            self.stdout.write(linea)

        if errores:
            self.stdout.write("\n--- ERRORES (no se aplicaron) ---")
            for linea in errores:
                self.stdout.write(self.style.ERROR(linea))

        self.stdout.write(
            self.style.SUCCESS(
                f"\nResumen: {len(aplicados)} ajustados, {len(errores)} errores"
            )
        )
        if dry_run:
            self.stdout.write(
                self.style.WARNING("Dry-run completado. Vuelve a correr sin --dry-run para aplicar.")
            )
