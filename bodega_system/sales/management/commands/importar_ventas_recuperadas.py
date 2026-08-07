# sales/management/commands/importar_ventas_recuperadas.py
# Recrea en esta base de datos las ventas exportadas de un sistema externo
# (PythonAnywhere) que nunca se reflejaron aquí — caso: caída de DigitalOcean
# por falta de pago el 10-11 de julio de 2026, atendida temporalmente con la
# versión de abril en PythonAnywhere.
#
# A diferencia de ajuste_ventas_externas (que solo corrige stock), este comando
# recrea la venta real completa: Sale + SaleItem + CustomerCredit si aplica,
# con la fecha original, para que también cuadren los reportes y el cierre
# diario (que se calculan en vivo a partir de Sale.objects). El descuento de
# inventario queda incluido aquí — NO corras además ajuste_ventas_externas
# para las mismas ventas o el stock se descontaría doble.
#
# Flujo:
#   1. En PythonAnywhere: python manage.py shell < scripts/export_ventas_recuperacion_10_11_julio.py
#   2. Traer export_ventas_10_11_julio.json a este servidor
#   3. Aquí, SIEMPRE primero en dry-run:
#        python manage.py importar_ventas_recuperadas export_ventas_10_11_julio.json --dry-run
#      Revisar los avisos, y solo entonces aplicar:
#        python manage.py importar_ventas_recuperadas export_ventas_10_11_julio.json --apply
#
# Idempotente: si una venta ya fue importada (se detecta por el marcador
# "[Recuperado PA#<id>]" en las notas), se salta en vez de duplicarla.

import json
from datetime import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from customers.models import Customer, CustomerCredit
from inventory.models import InventoryAdjustment, Product
from sales.models import Sale, SaleItem

User = get_user_model()


class Command(BaseCommand):
    help = "Recrea ventas completas (con inventario y crédito) desde un JSON exportado de otro sistema"

    def add_arguments(self, parser):
        parser.add_argument("archivo", type=str, help="Ruta al JSON exportado")
        parser.add_argument(
            "--apply",
            action="store_true",
            default=False,
            help="Aplica los cambios. Sin esto, solo simula (dry-run).",
        )
        parser.add_argument(
            "--fallback-user",
            type=str,
            default=None,
            help="Username a usar cuando el vendedor original no existe aquí (default: primer superuser)",
        )

    def handle(self, *args, **options):
        try:
            with open(options["archivo"], encoding="utf-8") as f:
                ventas = json.load(f)
        except FileNotFoundError:
            raise CommandError(f"Archivo no encontrado: {options['archivo']}")
        except json.JSONDecodeError as e:
            raise CommandError(f"JSON inválido: {e}")

        if not ventas:
            self.stdout.write(self.style.WARNING("El archivo no contiene ventas."))
            return

        if options["fallback_user"]:
            fallback_user = User.objects.filter(username=options["fallback_user"]).first()
            if not fallback_user:
                raise CommandError(f"Usuario de respaldo '{options['fallback_user']}' no existe aquí.")
        else:
            fallback_user = User.objects.filter(is_superuser=True).first()
            if not fallback_user:
                raise CommandError("No hay superusuarios. Usa --fallback-user para especificar uno.")

        apply_changes = options["apply"]
        self.stdout.write(
            ("--- MODO DRY-RUN: no se guardará nada ---\n" if not apply_changes else "--- APLICANDO CAMBIOS ---\n")
            + f"Vendedor de respaldo: {fallback_user.username} | Ventas en archivo: {len(ventas)}\n"
        )

        creadas, saltadas_ya_importadas, saltadas_sin_items = 0, 0, 0

        with transaction.atomic():
            for v in ventas:
                marcador = f"[Recuperado PA#{v['pa_sale_id']}]"

                if Sale.objects.filter(notes__startswith=marcador).exists():
                    saltadas_ya_importadas += 1
                    self.stdout.write(f"  = PA#{v['pa_sale_id']} ({v['date']}) ya estaba importada — se saltó")
                    continue

                avisos = []

                # --- Cliente (match por cédula, es la única clave confiable) ---
                customer = None
                if v.get("customer_cedula"):
                    customer = Customer.objects.filter(cedula=v["customer_cedula"]).first()
                    if not customer:
                        avisos.append(
                            f"cliente cédula {v['customer_cedula']} ({v.get('customer_name')}) no existe aquí "
                            "-> venta se importa sin cliente asociado"
                        )
                elif v.get("customer_name"):
                    avisos.append(
                        f"venta original con cliente '{v['customer_name']}' (tel: {v.get('customer_phone') or 's/d'}) "
                        "sin cédula registrada -> no se puede emparejar con certeza, se importa sin cliente. "
                        "Si corresponde, asocia el cliente a mano después en Django admin."
                    )

                if v["is_credit"] and not customer:
                    avisos.append("ERA VENTA A CRÉDITO y no se pudo asociar cliente -> revisar a mano el cobro pendiente")

                # --- Vendedor ---
                cashier = None
                if v.get("cashier_username"):
                    cashier = User.objects.filter(username=v["cashier_username"]).first()
                if not cashier:
                    avisos.append(f"vendedor original '{v.get('cashier_username')}' no existe aquí -> se asigna a '{fallback_user.username}'")
                    cashier = fallback_user

                # --- Ítems: resolver producto por barcode ANTES de crear nada ---
                resolved_items = []
                for item in v["items"]:
                    if item.get("combo_name"):
                        avisos.append(f"ítem de combo '{item['combo_name']}' NO migrado -> agregar a mano si corresponde")
                        continue
                    product = (
                        Product.objects.filter(barcode=item["product_barcode"]).first()
                        if item.get("product_barcode")
                        else None
                    )
                    if not product:
                        avisos.append(
                            f"producto barcode={item.get('product_barcode')} ({item.get('product_name')}) "
                            "no existe aquí -> ítem NO migrado, revisar a mano"
                        )
                        continue
                    resolved_items.append((product, item))

                if not resolved_items:
                    saltadas_sin_items += 1
                    self.stdout.write(
                        self.style.ERROR(f"  x PA#{v['pa_sale_id']} ({v['date']}) SIN NINGÚN ÍTEM VÁLIDO — no se importó. " + "; ".join(avisos))
                    )
                    continue

                original_dt = datetime.fromisoformat(v["date"])
                nota = f"{marcador} Venta original del {original_dt.strftime('%d/%m/%Y %H:%M')}, registrada en PythonAnywhere durante la caída de DigitalOcean (10-11 jul 2026). Importada el {datetime.now().strftime('%d/%m/%Y')}."
                if v.get("notes"):
                    nota += f" Notas originales: {v['notes']}"

                if apply_changes:
                    sale = Sale.objects.create(
                        customer=customer,
                        user=cashier,
                        total_bs=Decimal(v["total_bs"]),
                        total_usd=Decimal(v["total_usd"]),
                        exchange_rate_used=Decimal(v["exchange_rate_used"]),
                        payment_method=v["payment_method"],
                        mobile_reference=v.get("mobile_reference"),
                        is_credit=v["is_credit"],
                        notes=nota,
                    )
                    # date es auto_now_add -> ignora el valor pasado en create(),
                    # hay que forzarlo después con un update().
                    Sale.objects.filter(pk=sale.pk).update(date=original_dt)

                    for product, item in resolved_items:
                        qty = Decimal(item["quantity"])
                        SaleItem.objects.create(
                            sale=sale,
                            product=product,
                            quantity=qty,
                            price_bs=Decimal(item["price_bs"]),
                            price_usd=Decimal(item["price_usd"]),
                        )
                        previous_stock = product.stock
                        product.stock -= qty
                        product.save(update_fields=["stock"])
                        InventoryAdjustment.objects.create(
                            product=product,
                            adjustment_type="remove",
                            quantity=qty,
                            previous_stock=previous_stock,
                            new_stock=product.stock,
                            reason=f"Venta recuperada PA#{v['pa_sale_id']} del {original_dt.strftime('%d/%m/%Y')} (caída DO)",
                            adjusted_by=cashier,
                        )

                    if v["is_credit"] and customer and v.get("credit"):
                        c = v["credit"]
                        CustomerCredit.objects.create(
                            customer=customer,
                            sale=sale,
                            amount_bs=Decimal(c["amount_bs"]),
                            amount_usd=Decimal(c["amount_usd"]),
                            exchange_rate_used=Decimal(c["exchange_rate_used"]),
                            date_due=datetime.fromisoformat(c["date_due"]).date() if c.get("date_due") else None,
                            notes=(c.get("notes") or "") + " [recuperado tras caída DO]",
                        )

                creadas += 1
                estado = "OK" if not avisos else "OK CON AVISOS"
                linea = f"  + PA#{v['pa_sale_id']} ({v['date']}) {estado}"
                if avisos:
                    linea += " — " + "; ".join(avisos)
                self.stdout.write(self.style.WARNING(linea) if avisos else linea)

            if not apply_changes:
                transaction.set_rollback(True)

        self.stdout.write(
            self.style.SUCCESS(
                f"\nResumen: {creadas} {'importadas' if apply_changes else 'se importarían'} | "
                f"{saltadas_ya_importadas} ya estaban | {saltadas_sin_items} sin ítems válidos (no importadas)"
            )
        )
        if not apply_changes:
            self.stdout.write(self.style.WARNING("Dry-run: nada fue escrito. Revisa los avisos y corre de nuevo con --apply."))
