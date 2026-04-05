# customers/management/commands/clean_customers.py
# Comando para limpiar todos los clientes y sus datos relacionados.
# Las ventas existentes quedan intactas con customer=NULL.
# Usar SOLO cuando se desea reiniciar el registro de clientes desde cero.

from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = 'Elimina todos los clientes y sus créditos/pagos. Las ventas quedan intactas.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirmar',
            action='store_true',
            help='Confirmar que deseas eliminar TODOS los clientes y sus datos relacionados.',
        )

    def handle(self, *args, **options):
        if not options['confirmar']:
            self.stdout.write(self.style.WARNING(
                '\n⚠️  ADVERTENCIA: Este comando eliminará TODOS los clientes, créditos y pagos.\n'
                '   Las ventas existentes quedarán con customer=NULL (historial intacto).\n\n'
                '   Para confirmar, ejecuta:\n'
                '   python manage.py clean_customers --confirmar\n'
            ))
            return

        # Importar modelos aquí para evitar problemas de importación circular
        from customers.models import CreditPayment, CustomerCredit, CustomerGeneralPayment, Customer

        self.stdout.write('Iniciando limpieza de clientes...')

        with transaction.atomic():
            # Paso 1: pagos de créditos (dependen de CustomerCredit)
            count = CreditPayment.objects.count()
            CreditPayment.objects.all().delete()
            self.stdout.write(f'  ✓ Pagos de crédito eliminados: {count}')

            # Paso 2: créditos de clientes (dependen de Sale y Customer)
            count = CustomerCredit.objects.count()
            CustomerCredit.objects.all().delete()
            self.stdout.write(f'  ✓ Créditos eliminados: {count}')

            # Paso 3: pagos generales (dependen de Customer)
            count = CustomerGeneralPayment.objects.count()
            CustomerGeneralPayment.objects.all().delete()
            self.stdout.write(f'  ✓ Pagos generales eliminados: {count}')

            # Paso 4: clientes
            count = Customer.objects.count()
            Customer.objects.all().delete()
            self.stdout.write(f'  ✓ Clientes eliminados: {count}')

        self.stdout.write(self.style.SUCCESS(
            '\n✅ Limpieza completada. Puedes registrar los clientes desde cero.\n'
            '   Las ventas históricas quedaron intactas (customer=NULL).\n'
        ))
