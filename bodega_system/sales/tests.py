# sales/tests.py
"""
Tests exhaustivos para el módulo sales:
- Sale model (propiedades, métodos)
- SaleItem model (subtotales)
- Vista sale_list (filtros por rol, búsqueda)
- API create_sale (creación JSON, crédito, stock)
- Vista sale_detail (acceso por rol)
"""

import json
from decimal import Decimal
from datetime import date, timedelta

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone

from sales.models import Sale, SaleItem
from inventory.models import Category, Product
from customers.models import Customer, CustomerCredit
from utils.models import ExchangeRate

User = get_user_model()


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def make_admin(username='sale_admin'):
    return User.objects.create_user(username=username, password='pass123', is_admin=True)

def make_employee(username='sale_emp'):
    return User.objects.create_user(username=username, password='pass123', is_employee=True)

def make_exchange_rate(user, rate='45.50'):
    cache.clear()
    return ExchangeRate.objects.create(
        date=timezone.now().date(),
        bs_to_usd=Decimal(rate),
        updated_by=user
    )

def make_category(name='Sale Cat'):
    return Category.objects.create(name=name)

def make_product(cat, barcode='SAL001', name='Producto Venta',
                 purchase_usd='5.00', selling_usd='8.00', stock=100):
    return Product.objects.create(
        name=name,
        barcode=barcode,
        category=cat,
        purchase_price_usd=Decimal(purchase_usd),
        purchase_price_bs=Decimal('0'),
        selling_price_usd=Decimal(selling_usd),
        selling_price_bs=Decimal('0'),
        stock=Decimal(str(stock)),
        min_stock=Decimal('5')
    )

def make_customer(name='Cliente Venta'):
    return Customer.objects.create(
        name=name,
        credit_limit_usd=Decimal('500.00'),
        is_active=True
    )

def make_sale(user, customer=None, total_bs='455.00', total_usd='10.00',
              payment_method='cash', is_credit=False, notes=''):
    return Sale.objects.create(
        customer=customer,
        user=user,
        total_bs=Decimal(total_bs),
        total_usd=Decimal(total_usd),
        exchange_rate_used=Decimal('45.50'),
        payment_method=payment_method,
        is_credit=is_credit,
        notes=notes
    )


# ─────────────────────────────────────────────
# SALE MODEL TESTS
# ─────────────────────────────────────────────

class SaleModelTest(TestCase):

    def setUp(self):
        cache.clear()
        self.admin = make_admin()
        make_exchange_rate(self.admin)
        self.cat = make_category()
        self.product = make_product(self.cat)

    def test_create_sale_cash(self):
        """Debe crear venta de contado"""
        sale = make_sale(self.admin, payment_method='cash')
        self.assertEqual(sale.payment_method, 'cash')
        self.assertFalse(sale.is_credit)
        self.assertEqual(sale.user, self.admin)

    def test_create_sale_card(self):
        """Debe crear venta con punto de venta"""
        sale = make_sale(self.admin, payment_method='card')
        self.assertEqual(sale.payment_method, 'card')

    def test_create_sale_mobile_with_reference(self):
        """Debe crear venta con pago móvil y referencia"""
        sale = Sale.objects.create(
            user=self.admin,
            total_bs=Decimal('455.00'),
            total_usd=Decimal('10.00'),
            exchange_rate_used=Decimal('45.50'),
            payment_method='mobile',
            mobile_reference='REF123456',
            is_credit=False
        )
        self.assertEqual(sale.payment_method, 'mobile')
        self.assertEqual(sale.mobile_reference, 'REF123456')

    def test_create_sale_credit(self):
        """Debe crear venta a crédito"""
        customer = make_customer()
        sale = make_sale(self.admin, customer=customer, is_credit=True)
        self.assertTrue(sale.is_credit)
        self.assertEqual(sale.customer, customer)

    def test_item_count_no_items(self):
        """Venta sin ítems debe tener item_count = 0"""
        sale = make_sale(self.admin)
        self.assertEqual(sale.item_count, 0)

    def test_item_count_with_items(self):
        """item_count debe sumar la cantidad de todos los ítems"""
        sale = make_sale(self.admin)
        SaleItem.objects.create(
            sale=sale,
            product=self.product,
            quantity=Decimal('3'),
            price_bs=Decimal('364.00'),
            price_usd=Decimal('8.00')
        )
        SaleItem.objects.create(
            sale=sale,
            product=self.product,
            quantity=Decimal('2'),
            price_bs=Decimal('364.00'),
            price_usd=Decimal('8.00')
        )
        self.assertEqual(sale.item_count, 5)

    def test_get_payment_method_icon_cash(self):
        """Efectivo debe tener icono de billete"""
        sale = Sale(payment_method='cash')
        self.assertEqual(sale.get_payment_method_icon(), '💵')

    def test_get_payment_method_icon_card(self):
        """Punto de venta debe tener icono de tarjeta"""
        sale = Sale(payment_method='card')
        self.assertEqual(sale.get_payment_method_icon(), '💳')

    def test_get_payment_method_icon_mobile(self):
        """Pago móvil debe tener icono de teléfono"""
        sale = Sale(payment_method='mobile')
        self.assertEqual(sale.get_payment_method_icon(), '📱')

    def test_get_payment_method_display_with_icon_mobile_ref(self):
        """Pago móvil con referencia incluye la referencia"""
        sale = Sale(payment_method='mobile', mobile_reference='REF999')
        display = sale.get_payment_method_display_with_icon()
        self.assertIn('REF999', display)

    def test_str_representation(self):
        """__str__ debe incluir el ID de la venta"""
        sale = make_sale(self.admin)
        result = str(sale)
        self.assertIn(str(sale.id), result)

    def test_ordering_most_recent_first(self):
        """Las ventas deben ordenarse por fecha descendente"""
        s1 = make_sale(self.admin)
        s2 = make_sale(self.admin)
        sales = list(Sale.objects.all())
        self.assertGreaterEqual(sales[0].pk, sales[1].pk)


# ─────────────────────────────────────────────
# SALE ITEM MODEL TESTS
# ─────────────────────────────────────────────

class SaleItemModelTest(TestCase):

    def setUp(self):
        cache.clear()
        self.admin = make_admin('item_admin')
        make_exchange_rate(self.admin)
        self.cat = make_category('Item Cat')
        self.product = make_product(self.cat, barcode='ITEM001')
        self.sale = make_sale(self.admin)

    def make_item(self, qty='2', price_bs='364.00', price_usd='8.00'):
        return SaleItem.objects.create(
            sale=self.sale,
            product=self.product,
            quantity=Decimal(qty),
            price_bs=Decimal(price_bs),
            price_usd=Decimal(price_usd)
        )

    def test_subtotal_bs(self):
        """subtotal_bs = quantity * price_bs"""
        item = self.make_item(qty='3', price_bs='364.00')
        self.assertEqual(item.subtotal_bs, Decimal('1092.00'))

    def test_subtotal_usd(self):
        """subtotal_usd = quantity * price_usd"""
        item = self.make_item(qty='3', price_usd='8.00')
        self.assertEqual(item.subtotal_usd, Decimal('24.00'))

    def test_subtotal_alias(self):
        """subtotal debe ser alias de subtotal_bs"""
        item = self.make_item(qty='2', price_bs='364.00')
        self.assertEqual(item.subtotal, item.subtotal_bs)

    def test_str_representation(self):
        """__str__ debe incluir nombre del producto y cantidad"""
        item = self.make_item()
        result = str(item)
        self.assertIn(self.product.name, result)


# ─────────────────────────────────────────────
# SALE LIST VIEW TESTS
# ─────────────────────────────────────────────

class SaleListViewTest(TestCase):

    def setUp(self):
        cache.clear()
        self.client = Client()
        self.admin = make_admin('slist_admin')
        self.employee = make_employee('slist_emp')
        self.other_emp = make_employee('slist_other')
        make_exchange_rate(self.admin)
        # Admin sale
        self.sale_admin = make_sale(self.admin, notes='venta admin')
        # Employee sale
        self.sale_emp = make_sale(self.employee, notes='venta empleado')
        self.url = reverse('sales:sale_list')

    def test_anonymous_redirects(self):
        """Sin autenticación debe redirigir"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_admin_sees_all_sales(self):
        """Admin ve todas las ventas"""
        self.client.login(username='slist_admin', password='pass123')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        # La vista usa paginación: las ventas están en page_obj
        context_sales = list(response.context['page_obj'])
        pks = [s.pk for s in context_sales]
        self.assertIn(self.sale_admin.pk, pks)
        self.assertIn(self.sale_emp.pk, pks)

    def test_employee_sees_only_own_sales(self):
        """Empleado solo ve sus propias ventas"""
        self.client.login(username='slist_emp', password='pass123')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        context_sales = list(response.context['page_obj'])
        pks = [s.pk for s in context_sales]
        self.assertIn(self.sale_emp.pk, pks)
        self.assertNotIn(self.sale_admin.pk, pks)

    def test_search_filter_by_notes(self):
        """Búsqueda por notas debe filtrar ventas"""
        self.client.login(username='slist_admin', password='pass123')
        response = self.client.get(self.url, {'q': 'venta admin'})
        self.assertEqual(response.status_code, 200)
        pks = [s.pk for s in response.context['page_obj']]
        self.assertIn(self.sale_admin.pk, pks)

    def test_credit_filter_shows_credits_only(self):
        """Filtro de crédito muestra solo ventas a crédito"""
        customer = make_customer()
        credit_sale = make_sale(self.admin, customer=customer, is_credit=True)
        self.client.login(username='slist_admin', password='pass123')
        response = self.client.get(self.url, {'credit_filter': 'credit'})
        self.assertEqual(response.status_code, 200)
        pks = [s.pk for s in response.context['page_obj']]
        self.assertIn(credit_sale.pk, pks)
        self.assertNotIn(self.sale_admin.pk, pks)


# ─────────────────────────────────────────────
# SALE CREATE API TESTS
# ─────────────────────────────────────────────

class SaleCreateAPITest(TestCase):

    def setUp(self):
        cache.clear()
        self.client = Client()
        self.admin = make_admin('api_sale_admin')
        self.employee = make_employee('api_sale_emp')
        make_exchange_rate(self.admin)
        self.cat = make_category('API Sale Cat')
        self.product = make_product(self.cat, barcode='APISALE001', stock=50)
        self.url = reverse('sales:create_sale_api')

    def _post_sale(self, data, user='api_sale_admin'):
        self.client.login(username=user, password='pass123')
        return self.client.post(
            self.url,
            json.dumps(data),
            content_type='application/json'
        )

    def test_create_cash_sale_success(self):
        """Crear venta de contado debe retornar éxito"""
        data = {
            'items': [{'product_id': self.product.pk, 'quantity': 2}],
            'payment_method': 'cash',
            'is_credit': False
        }
        response = self._post_sale(data)
        self.assertIn(response.status_code, [200, 201])
        response_data = json.loads(response.content)
        # API retorna {'id': ..., 'message': ..., 'total_usd': ...}
        self.assertIn('id', response_data)

    def test_create_sale_employee(self):
        """Empleado también puede crear ventas"""
        data = {
            'items': [{'product_id': self.product.pk, 'quantity': 1}],
            'payment_method': 'cash',
            'is_credit': False
        }
        response = self._post_sale(data, user='api_sale_emp')
        self.assertIn(response.status_code, [200, 201])

    def test_create_sale_decrements_stock(self):
        """Crear venta debe decrementar el stock del producto"""
        initial_stock = self.product.stock
        data = {
            'items': [{'product_id': self.product.pk, 'quantity': 5}],
            'payment_method': 'cash',
            'is_credit': False
        }
        response = self._post_sale(data)
        self.assertIn(response.status_code, [200, 201])
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, initial_stock - 5)

    def test_create_sale_empty_items_fails(self):
        """Venta sin ítems debe fallar con 400"""
        data = {
            'items': [],
            'payment_method': 'cash',
            'is_credit': False
        }
        response = self._post_sale(data)
        self.assertEqual(response.status_code, 400)
        response_data = json.loads(response.content)
        self.assertIn('error', response_data)

    def test_create_sale_without_exchange_rate_fails(self):
        """Venta sin tasa de cambio configurada debe fallar"""
        ExchangeRate.objects.all().delete()
        cache.clear()
        data = {
            'items': [{'product_id': self.product.pk, 'quantity': 1}],
            'payment_method': 'cash',
            'is_credit': False
        }
        response = self._post_sale(data)
        self.assertEqual(response.status_code, 400)
        response_data = json.loads(response.content)
        self.assertIn('error', response_data)

    def test_anonymous_cannot_create_sale(self):
        """Usuario anónimo no puede crear ventas"""
        data = {
            'items': [{'product_id': self.product.pk, 'quantity': 1}],
            'payment_method': 'cash'
        }
        response = self.client.post(
            self.url,
            json.dumps(data),
            content_type='application/json'
        )
        self.assertIn(response.status_code, [302, 403])

    def test_create_credit_sale_success(self):
        """Crear venta a crédito con cliente"""
        customer = make_customer('Credit API Customer')
        data = {
            'items': [{'product_id': self.product.pk, 'quantity': 2}],
            'payment_method': 'cash',
            'is_credit': True,
            'customer_id': customer.pk
        }
        response = self._post_sale(data)
        self.assertIn(response.status_code, [200, 201])
        response_data = json.loads(response.content)
        # API retorna {'id': ..., 'message': ..., 'total_usd': ...}
        self.assertIn('id', response_data)
        # Verificar que se creó la venta a crédito
        sale = Sale.objects.get(pk=response_data['id'])
        self.assertTrue(sale.is_credit)


# ─────────────────────────────────────────────
# SALE CREATE API — PRECIO ESTABLE EN BS (spec: precios-estables-bs)
# ─────────────────────────────────────────────

class SaleCreateAPIBsFixedTest(TestCase):
    """Verifica que vender un producto en modo 'bs_fixed' respeta el precio fijo — y que el
    total de la venta (calculado antes de crear los ítems) coincide exactamente con el precio
    de cada SaleItem (ambos deben usar la misma fuente: Product.get_current_price_bs)."""

    def setUp(self):
        cache.clear()
        self.client = Client()
        self.admin = make_admin('bsfixed_sale_admin')
        make_exchange_rate(self.admin, rate='40.00')
        self.cat = make_category('BsFixed Sale Cat')
        self.product = make_product(self.cat, barcode='BSFIXED001', stock=50, selling_usd='8.00')
        self.product.pricing_mode = Product.PRICING_MODE_BS_FIXED
        self.product.selling_price_bs = Decimal('500.00')
        self.product.save()
        self.url = reverse('sales:create_sale_api')

    def _post_sale(self, data, user='bsfixed_sale_admin'):
        self.client.login(username=user, password='pass123')
        return self.client.post(
            self.url,
            json.dumps(data),
            content_type='application/json'
        )

    def test_sale_uses_fixed_bs_price_not_usd_times_rate(self):
        """El precio Bs del ítem debe ser el fijo (500.00 × 2), no USD × tasa"""
        data = {
            'items': [{'product_id': self.product.pk, 'quantity': 2}],
            'payment_method': 'cash',
            'is_credit': False
        }
        response = self._post_sale(data)
        self.assertIn(response.status_code, [200, 201])
        response_data = json.loads(response.content)

        sale = Sale.objects.get(pk=response_data['id'])
        item = sale.items.first()
        self.assertEqual(item.price_bs, Decimal('500.00'))
        # Total de la venta (calculado en el loop de pre-cálculo) debe coincidir con el total
        # real de los ítems (calculado en process_regular_sale) — misma fuente de verdad.
        self.assertEqual(sale.total_bs, item.price_bs * 2)

    def test_sale_price_survives_rate_change(self):
        """Cambiar la tasa BCV no debe afectar el precio de venta del producto bs_fixed"""
        make_exchange_rate(self.admin, rate='999.00', days_offset=1)
        data = {
            'items': [{'product_id': self.product.pk, 'quantity': 1}],
            'payment_method': 'cash',
            'is_credit': False
        }
        response = self._post_sale(data)
        response_data = json.loads(response.content)
        sale = Sale.objects.get(pk=response_data['id'])
        self.assertEqual(sale.items.first().price_bs, Decimal('500.00'))

    def test_usd_mode_product_unaffected_in_same_sale(self):
        """Un producto en modo usd, vendido junto a uno bs_fixed, sigue calculando con la tasa"""
        usd_product = make_product(
            self.cat, barcode='USDNORMAL001', stock=50, selling_usd='8.00'
        )
        data = {
            'items': [
                {'product_id': self.product.pk, 'quantity': 1},
                {'product_id': usd_product.pk, 'quantity': 1},
            ],
            'payment_method': 'cash',
            'is_credit': False
        }
        response = self._post_sale(data)
        response_data = json.loads(response.content)
        sale = Sale.objects.get(pk=response_data['id'])
        prices_bs = sorted(item.price_bs for item in sale.items.all())
        self.assertEqual(prices_bs, sorted([Decimal('500.00'), Decimal('8.00') * Decimal('40.00')]))


# ─────────────────────────────────────────────
# SALE DETAIL VIEW TESTS
# ─────────────────────────────────────────────

class SaleDetailViewTest(TestCase):

    def setUp(self):
        cache.clear()
        self.client = Client()
        self.admin = make_admin('detail_admin')
        self.employee = make_employee('detail_emp')
        self.other_emp = make_employee('detail_other')
        make_exchange_rate(self.admin)
        self.admin_sale = make_sale(self.admin)
        self.emp_sale = make_sale(self.employee)

    def test_detail_accessible_admin(self):
        """Admin puede ver cualquier venta"""
        self.client.login(username='detail_admin', password='pass123')
        url = reverse('sales:sale_detail', args=[self.emp_sale.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_detail_employee_own_sale(self):
        """Empleado puede ver su propia venta"""
        self.client.login(username='detail_emp', password='pass123')
        url = reverse('sales:sale_detail', args=[self.emp_sale.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_detail_employee_other_sale_forbidden(self):
        """Empleado no puede ver la venta de otro empleado"""
        self.client.login(username='detail_other', password='pass123')
        url = reverse('sales:sale_detail', args=[self.emp_sale.pk])
        response = self.client.get(url)
        # Debe ser 403 o redirigir
        self.assertIn(response.status_code, [403, 302, 404])

    def test_detail_anonymous_redirects(self):
        """Sin autenticación debe redirigir"""
        url = reverse('sales:sale_detail', args=[self.admin_sale.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
