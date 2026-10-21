# parts/management/commands/seed_motoparts_demo.py
"""
Carga los DATOS DE EJEMPLO del demo de SuperMoto Speed (perfil 'motoparts').

Crea usuarios, tasa BCV, marcas y modelos de moto comunes en Guanare/Portuguesa, ~120
repuestos con compatibilidad, clientes, fiados, proveedores, órdenes de compra, gastos y un
mes de ventas. Todos los precios y números de parte son de referencia: sirven para mostrar
el sistema, no son una lista de precios real.

Uso:
    BUSINESS_PROFILE=motoparts python manage.py seed_motoparts_demo
    python manage.py seed_motoparts_demo --barcodes-pdf etiquetas_demo.pdf

Se niega a correr si ya hay productos en la base de datos (para no mezclar el demo con
datos reales), salvo que se pase --force. Con --if-empty no hace nada si ya hay productos
(así se puede correr en cada arranque del servidor, como en render.yaml). La contraseña de
los usuarios del demo sale de la variable DEMO_PASSWORD, si existe.
"""

import os
import random
from datetime import datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import User
from customers.models import CreditPayment, Customer, CustomerCredit
from finances.models import Expense
from inventory.models import Category, InventoryAdjustment, Product
from parts.models import MotoBrand, MotoModel, PartInfo
from sales.models import Sale, SaleItem
from suppliers.models import Supplier, SupplierOrder, SupplierOrderItem
from utils.models import ExchangeRate, StoreSettings

# En un demo publicado en internet, DEMO_PASSWORD (variable de entorno) reemplaza esta clave.
DEFAULT_DEMO_PASSWORD = 'supermoto2026'
BCV_RATE = Decimal('200.00')
CASH_USD_DISCOUNT = Decimal('16.67')
CENT = Decimal('0.01')

MOTOS = {
    'Bera': [('SBR 150', 150), ('Socialista 150', 150), ('Cobra 200', 200)],
    'Empire Keeway': [('Horse 150', 150), ('Owen 150', 150), ('Arsen II 150', 150), ('TX 200', 200)],
    'Suzuki': [('GN 125', 125), ('EN 125', 125)],
    'Yamaha': [('YBR 125', 125), ('DT 175', 175), ('BWS 125', 125)],
}

# Grupos de motos que comparten la misma pieza (datos de ejemplo)
G = {
    'bera150': ['Bera SBR 150', 'Bera Socialista 150'],
    'cobra': ['Bera Cobra 200'],
    'horse': ['Empire Keeway Horse 150'],
    'owen': ['Empire Keeway Owen 150', 'Empire Keeway Arsen II 150'],
    'tx': ['Empire Keeway TX 200'],
    'gn': ['Suzuki GN 125', 'Suzuki EN 125'],
    'ybr': ['Yamaha YBR 125'],
    'dt': ['Yamaha DT 175'],
    'bws': ['Yamaha BWS 125'],
}
GROUP_LABEL = {
    'bera150': 'Bera SBR/Socialista', 'cobra': 'Bera Cobra 200', 'horse': 'Empire Horse',
    'owen': 'Empire Owen/Arsen', 'tx': 'Empire TX 200', 'gn': 'Suzuki GN/EN 125',
    'ybr': 'Yamaha YBR 125', 'dt': 'Yamaha DT 175', 'bws': 'Yamaha BWS 125',
}

# (categoría, nombre, grupos o None si es universal, precio venta USD, calidades)
# calidades: lista de (calidad, marca, factor de precio)
# La etiqueta va en el nombre cuando hay varias calidades; la marca solo si es una marca real.
GEN = [('generic', '', Decimal('1'))]
GEN_ORI = [('generic', 'Genérica', Decimal('1')), ('original', 'Original', Decimal('1.9'))]
CATALOG = [
    ('Frenos', 'Pastillas de freno delanteras', ['bera150', 'horse', 'owen', 'gn', 'ybr', 'cobra', 'bws'], '4.50', GEN_ORI),
    ('Frenos', 'Bandas de freno traseras', ['bera150', 'horse', 'owen', 'gn', 'ybr', 'dt'], '5.00', GEN),
    ('Frenos', 'Disco de freno delantero', ['bera150', 'horse', 'cobra'], '22.00', GEN),
    ('Frenos', 'Bomba de freno delantera', ['bera150', 'horse'], '18.00', GEN),
    ('Frenos', 'Guaya de freno trasero', ['gn', 'ybr', 'dt'], '3.50', GEN),
    ('Motor', 'Kit de cilindro 150cc (pistón y anillos)', [['bera150', 'horse', 'owen']], '38.00', GEN),
    ('Motor', 'Kit de cilindro 125cc (pistón y anillos)', [['gn', 'ybr']], '32.00', GEN),
    ('Motor', 'Kit de cilindro 200cc (pistón y anillos)', [['cobra', 'tx']], '45.00', GEN),
    ('Motor', 'Cadena de tiempo', ['bera150', 'horse', 'gn', 'ybr'], '7.00', GEN),
    ('Motor', 'Juego de empacaduras de motor', ['bera150', 'horse', 'gn', 'ybr', 'cobra'], '9.00', GEN),
    ('Motor', 'Válvulas de admisión y escape 150cc', [['bera150', 'horse', 'owen']], '8.50', GEN),
    ('Motor', 'Válvulas de admisión y escape 125cc', [['gn', 'ybr']], '8.00', GEN),
    ('Motor', 'Carburador completo', ['bera150', 'horse', 'gn', 'ybr'], '24.00', GEN),
    ('Eléctrico', 'CDI', ['bera150', 'horse', 'owen', 'gn', 'ybr', 'cobra'], '12.00', GEN),
    ('Eléctrico', 'Regulador de voltaje', ['bera150', 'horse', 'gn', 'ybr'], '10.00', GEN),
    ('Eléctrico', 'Bobina de encendido', [['bera150', 'horse', 'owen', 'gn', 'ybr']], '8.00', GEN),
    ('Eléctrico', 'Suiche de encendido', ['bera150', 'horse', 'gn'], '9.50', GEN),
    ('Eléctrico', 'Batería 12N7-3B', [['bera150', 'horse', 'owen', 'gn']], '32.00', GEN),
    ('Eléctrico', 'Batería YTX7A-BS', [['bws', 'cobra', 'tx']], '38.00', GEN),
    ('Eléctrico', 'Bombillo halógeno 12V 35/35W', None, '2.00', GEN),
    ('Eléctrico', 'Corneta 12V', None, '4.00', GEN),
    ('Transmisión', 'Kit de arrastre 428 (cadena, piñón y corona)', [['bera150', 'horse', 'owen', 'gn', 'ybr']], '22.00',
     [('generic', 'Estándar', Decimal('1')), ('alternative', 'Reforzado', Decimal('1.45'))]),
    ('Transmisión', 'Kit de arrastre 520 (cadena, piñón y corona)', [['cobra', 'tx']], '35.00', GEN),
    ('Transmisión', 'Discos de clutch (juego)', ['bera150', 'horse', 'gn', 'ybr'], '12.00', GEN),
    ('Transmisión', 'Guaya de clutch', ['bera150', 'horse', 'gn', 'ybr'], '3.50', GEN),
    ('Suspensión y dirección', 'Amortiguadores traseros (par)', ['bera150', 'horse', 'gn', 'ybr'], '28.00', GEN),
    ('Suspensión y dirección', 'Rodamientos de dirección (juego)', [['bera150', 'horse', 'owen', 'gn', 'ybr']], '8.00', GEN),
    ('Suspensión y dirección', 'Rodamiento de rueda 6301-2RS', None, '2.50', GEN),
    ('Suspensión y dirección', 'Barras de horquilla (par)', ['bera150', 'horse'], '30.00', GEN),
    ('Cauchos y tripas', 'Caucho trasero 90/90-18', [['bera150', 'horse', 'owen', 'ybr']], '30.00', GEN),
    ('Cauchos y tripas', 'Caucho delantero 2.75-18', [['bera150', 'gn', 'ybr', 'horse']], '26.00', GEN),
    ('Cauchos y tripas', 'Caucho trasero 100/80-17', [['cobra', 'tx']], '36.00', GEN),
    ('Cauchos y tripas', 'Caucho 130/70-12 (scooter)', [['bws']], '29.00', GEN),
    ('Cauchos y tripas', 'Tripa rin 18', None, '5.00', GEN),
    ('Lubricantes', 'Aceite Motul 3000 20W-50 4T 1L', None, '8.00', [('original', 'Motul', Decimal('1'))]),
    ('Lubricantes', 'Aceite Castrol Actevo 20W-50 4T 1L', None, '8.50', [('original', 'Castrol', Decimal('1'))]),
    ('Lubricantes', 'Aceite 20W-50 4T 1L', None, '5.00', GEN),
    ('Lubricantes', 'Aceite 2T Motul 1L', [['dt']], '9.00', [('original', 'Motul', Decimal('1'))]),
    ('Lubricantes', 'Líquido de frenos DOT 4', None, '4.00', GEN),
    ('Lubricantes', 'Grasa en spray para cadena', None, '6.00', GEN),
    ('Filtros', 'Filtro de aire', ['bera150', 'horse', 'gn', 'ybr', 'cobra'], '5.00', GEN),
    ('Filtros', 'Filtro de gasolina', None, '1.50', GEN),
    ('Bujías', 'Bujía NGK C7HSA', [['bera150', 'horse', 'owen', 'ybr', 'bws']], '3.50', [('original', 'NGK', Decimal('1'))]),
    ('Bujías', 'Bujía NGK D8EA', [['gn', 'cobra', 'tx']], '4.00', [('original', 'NGK', Decimal('1'))]),
    ('Bujías', 'Bujía NGK B8ES', [['dt']], '4.00', [('original', 'NGK', Decimal('1'))]),
    ('Accesorios', 'Espejos retrovisores (par)', None, '7.00', GEN),
    ('Accesorios', 'Manillas de freno y clutch (par)', None, '6.00', GEN),
    ('Accesorios', 'Puños de manubrio (par)', None, '4.00', GEN),
    ('Accesorios', 'Forro de asiento', None, '8.00', GEN),
    ('Accesorios', 'Stop trasero LED', None, '6.00', GEN),
    ('Cascos y protección', 'Casco integral certificado', None, '45.00', GEN),
    ('Cascos y protección', 'Casco abierto', None, '22.00', GEN),
    ('Cascos y protección', 'Guantes para motorizado (par)', None, '8.00', GEN),
    ('Cascos y protección', 'Impermeable de dos piezas', None, '12.00', GEN),
    ('Herramientas', 'Juego de llaves combinadas', None, '15.00', GEN),
    ('Herramientas', 'Extractor de volante', None, '9.00', GEN),
]

REAL_BRANDS = {'NGK', 'Motul', 'Castrol'}

CUSTOMERS = [
    ('Taller El Pana (José Rodríguez)', 'mecánico'),
    ('Mecánica Hermanos Pérez', 'mecánico'),
    ('Luis Mendoza', 'mototaxista'),
    ('Carlos Gutiérrez', 'delivery'),
    ('Andrea Torres', ''),
    ('Pedro Castillo', ''),
    ('Yorman Silva', 'mototaxista'),
    ('María Escalona', ''),
]

SUPPLIERS = [
    ('Distribuidora de Repuestos Los Llanos (ejemplo)', 'Acarigua'),
    ('Importadora Moto Centro (ejemplo)', 'Barquisimeto'),
    ('Lubricantes y Cauchos Portuguesa (ejemplo)', 'Guanare'),
]


def money(value):
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def ean13(rng):
    digits = [7, 5, 9] + [rng.randint(0, 9) for _ in range(9)]
    total = sum(d * (3 if i % 2 else 1) for i, d in enumerate(digits))
    return ''.join(map(str, digits)) + str((10 - total % 10) % 10)


class Command(BaseCommand):
    help = 'Carga los datos de ejemplo del demo de SuperMoto Speed (repuestos de moto)'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true',
                            help='Cargar aunque ya existan productos')
        parser.add_argument('--if-empty', action='store_true',
                            help='No hacer nada (y salir sin error) si ya hay productos. Para '
                                 'correrlo en cada arranque del servidor, como en Render')
        parser.add_argument('--barcodes-pdf', metavar='RUTA',
                            help='Además, generar un PDF con códigos de barras de prueba para el escáner')

    def handle(self, *args, **options):
        if Product.objects.exists() and options['if_empty']:
            self.stdout.write('Ya hay productos: no se cargan datos de ejemplo.')
            if options['barcodes_pdf']:
                self.write_barcodes_pdf(options['barcodes_pdf'])
            return
        if Product.objects.exists() and not options['force']:
            raise CommandError('Ya hay productos en la base de datos. Usa --force si de verdad '
                               'quieres agregar los datos de ejemplo.')

        self.rng = random.Random(2026)
        with transaction.atomic():
            owner = self.create_users()
            self.create_rate_and_settings(owner)
            models = self.create_motos()
            products = self.create_products(models)
            customers = self.create_customers()
            self.create_suppliers(owner, products)
            self.create_sales(owner, products, customers)
            self.create_expenses(owner)

        if options['barcodes_pdf']:
            self.write_barcodes_pdf(options['barcodes_pdf'])

        self.stdout.write(self.style.SUCCESS(
            f'Demo cargado: {Product.objects.count()} productos, {Sale.objects.count()} ventas.\n'
            f'Usuarios: dueno / papa (administradores), vendedor (empleado). '
            f'Contraseña de todos: {"(la de DEMO_PASSWORD)" if os.environ.get("DEMO_PASSWORD") else DEFAULT_DEMO_PASSWORD}\n'
            f'Tasa BCV de ejemplo: {BCV_RATE} Bs/$ — actualízala en Configuración → Tasa de Cambio.'
        ))

    # ------------------------------------------------------------------ usuarios y ajustes
    def create_users(self):
        users = {}
        for username, first, last, is_admin in [
            ('dueno', 'Dueño', 'SuperMoto', True),
            ('papa', 'Papá', 'SuperMoto', True),
            ('vendedor', 'Vendedor', 'Demo', False),
        ]:
            user, _ = User.objects.get_or_create(username=username, defaults={
                'first_name': first, 'last_name': last,
                'is_admin': is_admin, 'is_employee': not is_admin,
            })
            user.set_password(os.environ.get('DEMO_PASSWORD') or DEFAULT_DEMO_PASSWORD)
            user.save()
            users[username] = user
        return users['dueno']

    def create_rate_and_settings(self, owner):
        today = datetime.now().date()
        for days_ago in range(30, -1, -1):
            rate = BCV_RATE - Decimal(days_ago) * Decimal('0.35')
            ExchangeRate.objects.update_or_create(
                date=today - timedelta(days=days_ago),
                defaults={'bs_to_usd': money(rate), 'updated_by': owner},
            )
        settings_obj = StoreSettings.get()
        settings_obj.cash_usd_discount_percent = CASH_USD_DISCOUNT
        settings_obj.save()

    # ------------------------------------------------------------------ motos y catálogo
    def create_motos(self):
        models = {}
        for brand_name, items in MOTOS.items():
            brand, _ = MotoBrand.objects.get_or_create(name=brand_name)
            for name, cc in items:
                moto, _ = MotoModel.objects.get_or_create(brand=brand, name=name,
                                                          defaults={'displacement_cc': cc})
                models[str(moto)] = moto
        return models

    def create_products(self, models):
        rng = self.rng
        products = []
        internal = 0
        for category_name, base_name, groups, price, qualities in CATALOG:
            category, _ = Category.objects.get_or_create(name=category_name)
            # Cada entrada de `groups` es una pieza: un grupo suelto ('bera150') o una lista de
            # grupos que comparten la misma pieza. None = pieza universal.
            pieces = [None] if groups is None else groups
            for piece in pieces:
                keys = [] if piece is None else ([piece] if isinstance(piece, str) else piece)
                for quality, label, factor in qualities:
                    sell = money(Decimal(price) * factor * Decimal(rng.choice(['1', '1', '1.1', '0.9'])))
                    cost = money(sell / Decimal(rng.choice(['1.35', '1.4', '1.5', '1.6'])))
                    name = base_name
                    if len(keys) == 1 and isinstance(piece, str):
                        name = f'{base_name} {GROUP_LABEL[piece]}'
                    if len(qualities) > 1:
                        name = f'{name} ({label})'

                    if rng.random() < 0.6:
                        barcode = ean13(rng)
                    else:
                        internal += 1
                        barcode = f'SM-{internal:04d}'

                    min_stock = Decimal(rng.choice([2, 3, 4, 5]))
                    stock = Decimal(rng.choice([0, 1, 2]) if rng.random() < 0.12 else rng.randint(4, 25))
                    product = Product.objects.create(
                        name=name, barcode=barcode, category=category,
                        purchase_price_usd=cost, purchase_price_bs=cost * BCV_RATE,
                        selling_price_usd=sell, selling_price_bs=sell * BCV_RATE,
                        stock=stock + 10, min_stock=min_stock,
                    )
                    part = PartInfo.objects.create(
                        product=product,
                        part_brand=label if label in REAL_BRANDS else '',
                        quality=quality,
                        part_number=(f'{rng.randint(10000, 99999)}-{rng.choice(["KWB", "KVS", "GN5", "BR1", "HS0"])}-'
                                     f'{rng.randint(100, 999)}') if quality == 'original' or rng.random() < 0.4 else '',
                        location=f'Estante {rng.randint(1, 6)}, gaveta {rng.choice("ABCD")}',
                        is_universal=piece is None,
                    )
                    names = [m for key in keys for m in G[key]]
                    part.compatible_models.set([models[n] for n in names])
                    InventoryAdjustment.objects.create(
                        product=product, adjustment_type='set', quantity=product.stock,
                        previous_stock=Decimal('0'), new_stock=product.stock,
                        reason='Stock inicial (datos de ejemplo)', adjusted_by=User.objects.get(username='dueno'),
                    )
                    # `stock + 10`: margen para las ventas del historial; al final queda `stock`
                    product._target_stock = stock
                    products.append(product)
        return products

    def create_customers(self):
        customers = []
        for name, kind in CUSTOMERS:
            customer, _ = Customer.objects.get_or_create(name=name, defaults={
                'notes': f'Cliente de ejemplo ({kind})' if kind else 'Cliente de ejemplo',
                'credit_limit_usd': Decimal('150') if kind == 'mecánico' else Decimal('40'),
            })
            customers.append(customer)
        return customers

    # ------------------------------------------------------------------ proveedores
    def create_suppliers(self, owner, products):
        rng = self.rng
        now = datetime.now()
        for index, (name, city) in enumerate(SUPPLIERS):
            supplier, _ = Supplier.objects.get_or_create(name=name, defaults={
                'contact_person': 'Vendedor de ejemplo', 'address': city,
                'notes': 'Proveedor de ejemplo para el demo',
            })
            for order_index in range(2):
                status = 'received' if order_index == 0 or index == 2 else 'pending'
                order = SupplierOrder.objects.create(
                    supplier=supplier, status=status, created_by=owner,
                    exchange_rate_used=BCV_RATE, notes='Orden de ejemplo',
                )
                total = Decimal('0')
                for product in rng.sample(products, 5):
                    quantity = Decimal(rng.randint(4, 12))
                    SupplierOrderItem.objects.create(
                        order=order, product=product, quantity=quantity,
                        price_usd=product.purchase_price_usd,
                        selling_price_usd=product.selling_price_usd,
                    )
                    total += quantity * product.purchase_price_usd
                order_date = now - timedelta(days=rng.randint(3, 25))
                SupplierOrder.objects.filter(pk=order.pk).update(
                    order_date=order_date,
                    received_date=order_date + timedelta(days=2) if status == 'received' else None,
                    total_usd=money(total), total_bs=money(total * BCV_RATE),
                    paid=status == 'received' and index != 1,
                    paid_amount_usd=money(total) if status == 'received' and index != 1 else Decimal('0'),
                    paid_amount_bs=money(total * BCV_RATE) if status == 'received' and index != 1 else Decimal('0'),
                )

    # ------------------------------------------------------------------ ventas
    def create_sales(self, owner, products, customers):
        rng = self.rng
        sellers = list(User.objects.filter(username__in=['dueno', 'papa', 'vendedor']))
        today = datetime.now().date()
        rates = {r.date: r.bs_to_usd for r in ExchangeRate.objects.all()}
        popular = [p for p in products if p.category.name in ('Frenos', 'Lubricantes', 'Bujías', 'Eléctrico', 'Filtros')]

        for days_ago in range(29, -1, -1):
            day = today - timedelta(days=days_ago)
            rate = rates.get(day, BCV_RATE)
            for _ in range(rng.randint(3, 8) if day.weekday() != 6 else rng.randint(0, 2)):
                when = datetime.combine(day, time(rng.randint(8, 17), rng.randint(0, 59)))
                lines = []
                for product in rng.sample(popular if rng.random() < 0.7 else products, rng.choice([1, 1, 1, 2, 2, 3])):
                    if product.stock > product._target_stock:
                        lines.append((product, Decimal(rng.choice([1, 1, 1, 2]))))
                if not lines:
                    continue

                customer = rng.choice(customers) if rng.random() < 0.35 else None
                is_credit = bool(customer) and rng.random() < 0.3
                method = rng.choice(['cash_usd', 'cash_usd', 'mobile', 'mobile', 'card', 'cash'])
                total_usd = sum((p.selling_price_usd * q for p, q in lines), Decimal('0'))
                discount_percent = discount_usd = Decimal('0')
                if method == 'cash_usd' and not is_credit:
                    discount_percent = CASH_USD_DISCOUNT
                    discount_usd = money(total_usd * discount_percent / 100)
                total_usd = money(total_usd - discount_usd)

                sale = Sale.objects.create(
                    customer=customer, user=rng.choice(sellers),
                    total_usd=total_usd, total_bs=money(total_usd * rate), exchange_rate_used=rate,
                    payment_method=method, is_credit=is_credit,
                    mobile_reference=str(rng.randint(100000, 999999)) if method == 'mobile' else None,
                    discount_percent=discount_percent, discount_usd=discount_usd,
                )
                Sale.objects.filter(pk=sale.pk).update(date=when)
                for product, quantity in lines:
                    SaleItem.objects.create(sale=sale, product=product, quantity=quantity,
                                            price_usd=product.selling_price_usd,
                                            price_bs=money(product.selling_price_usd * rate))
                    previous = product.stock
                    product.stock -= quantity
                    product.save(update_fields=['stock'])
                    InventoryAdjustment.objects.create(
                        product=product, adjustment_type='remove', quantity=quantity,
                        previous_stock=previous, new_stock=product.stock,
                        reason=f'Venta #{sale.id} (datos de ejemplo)', adjusted_by=sale.user,
                    )

                if is_credit:
                    credit = CustomerCredit.objects.create(
                        customer=customer, sale=sale, amount_bs=sale.total_bs, amount_usd=sale.total_usd,
                        exchange_rate_used=rate, date_due=day + timedelta(days=15),
                        notes=f'Crédito por venta #{sale.id}',
                    )
                    CustomerCredit.objects.filter(pk=credit.pk).update(date_created=when)
                    if days_ago > 10 and rng.random() < 0.6:
                        paid = money(sale.total_usd / 2)
                        CreditPayment.objects.create(
                            credit=credit, amount_usd=paid, amount_bs=money(paid * rate),
                            exchange_rate_used=rate, payment_method='cash', received_by=owner,
                            notes='Abono (datos de ejemplo)',
                        )

        # Ajustar al stock objetivo (algunos productos quedan en stock bajo o agotados)
        for product in products:
            if product.stock != product._target_stock:
                previous = product.stock
                product.stock = product._target_stock
                product.save(update_fields=['stock'])
                InventoryAdjustment.objects.create(
                    product=product, adjustment_type='set', quantity=product.stock,
                    previous_stock=previous, new_stock=product.stock,
                    reason='Conteo inicial (datos de ejemplo)', adjusted_by=owner,
                )

    def create_expenses(self, owner):
        today = datetime.now().date()
        for category, description, amount, days_ago in [
            ('rent', 'Alquiler del local', '150.00', 20),
            ('utilities', 'Internet del local', '25.00', 15),
            ('utilities', 'Electricidad', '12.00', 10),
            ('supplies', 'Bolsas y material de empaque', '8.00', 5),
        ]:
            Expense.objects.create(
                category=category, description=f'{description} (ejemplo)',
                amount_usd=Decimal(amount), amount_bs=money(Decimal(amount) * BCV_RATE),
                exchange_rate_used=BCV_RATE, date=today - timedelta(days=days_ago), created_by=owner,
            )

    # ------------------------------------------------------------------ PDF de códigos
    def write_barcodes_pdf(self, path):
        """Hoja con códigos de barras de productos del demo, para probar el escáner con la
        cámara del teléfono apuntando a la pantalla o a la hoja impresa."""
        from reportlab.graphics.barcode import eanbc
        from reportlab.graphics.shapes import Drawing
        from reportlab.graphics import renderPDF
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.units import inch
        from reportlab.pdfgen import canvas

        products = [p for p in Product.objects.filter(stock__gt=0).order_by('name')
                    if p.barcode.isdigit() and len(p.barcode) == 13][:12]
        pdf = canvas.Canvas(path, pagesize=letter)
        width, height = letter
        pdf.setFont('Helvetica-Bold', 14)
        pdf.drawString(0.75 * inch, height - 0.75 * inch, 'SuperMoto Speed — códigos de prueba del demo')
        for index, product in enumerate(products):
            col, row = index % 2, index // 2
            x = 0.75 * inch + col * 3.75 * inch
            y = height - 1.9 * inch - row * 1.5 * inch
            widget = eanbc.Ean13BarcodeWidget(product.barcode)
            x0, y0, x1, y1 = widget.getBounds()
            drawing = Drawing(x1 - x0, y1 - y0, transform=[1.6, 0, 0, 1.6, 0, 0])
            drawing.add(widget)
            renderPDF.draw(drawing, pdf, x, y)
            pdf.setFont('Helvetica', 8)
            pdf.drawString(x, y - 12, product.name[:60])
        pdf.save()
        self.stdout.write(f'PDF de códigos de barras: {path}')
