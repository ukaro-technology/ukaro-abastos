# inventory/tests_audit.py
"""
Tests para la auditoría de inventario (conteo físico vs sistema +
trazabilidad por producto). Ver docs/specs/auditoria-inventario.md.
"""

from decimal import Decimal

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from inventory.models import Category, Product, InventoryAdjustment, InventoryCount, InventoryCountItem
from inventory.services import TraceabilityService
from inventory.tests import make_admin, make_employee, make_exchange_rate, make_category, make_product
from customers.models import Customer
from sales.models import Sale, SaleItem
from suppliers.models import Supplier, SupplierOrder, SupplierOrderItem

User = get_user_model()


# ─────────────────────────────────────────────
# MODELOS: InventoryCount / InventoryCountItem
# ─────────────────────────────────────────────

class InventoryCountItemModelTest(TestCase):

    def setUp(self):
        self.admin = make_admin('audit_admin')
        make_exchange_rate(self.admin)
        self.cat = make_category('AuditCat')
        self.product = make_product(self.cat, barcode='AUD001', stock=10)
        self.count = InventoryCount.objects.create(category=self.cat, counted_by=self.admin)

    def test_difference_negative_when_physical_lower(self):
        """Físico menor que sistema -> diferencia negativa (falta stock)"""
        item = InventoryCountItem.objects.create(
            count=self.count, product=self.product,
            system_stock=Decimal('10'), physical_stock=Decimal('7'),
        )
        self.assertEqual(item.difference, Decimal('-3'))

    def test_difference_positive_when_physical_higher(self):
        """Físico mayor que sistema -> diferencia positiva (sobra stock)"""
        item = InventoryCountItem.objects.create(
            count=self.count, product=self.product,
            system_stock=Decimal('10'), physical_stock=Decimal('12'),
        )
        self.assertEqual(item.difference, Decimal('2'))

    def test_difference_zero_when_equal(self):
        item = InventoryCountItem.objects.create(
            count=self.count, product=self.product,
            system_stock=Decimal('10'), physical_stock=Decimal('10'),
        )
        self.assertEqual(item.difference, Decimal('0'))

    def test_difference_value_usd(self):
        """difference_value_usd = difference * purchase_price_usd del producto"""
        item = InventoryCountItem.objects.create(
            count=self.count, product=self.product,
            system_stock=Decimal('10'), physical_stock=Decimal('7'),
        )
        # make_product usa purchase_usd='5.00' por default
        self.assertEqual(item.difference_value_usd, Decimal('-3') * Decimal('5.00'))

    def test_items_with_difference_excludes_matching(self):
        p2 = make_product(self.cat, barcode='AUD002', stock=5)
        InventoryCountItem.objects.create(count=self.count, product=self.product,
            system_stock=Decimal('10'), physical_stock=Decimal('7'))  # con diferencia
        InventoryCountItem.objects.create(count=self.count, product=p2,
            system_stock=Decimal('5'), physical_stock=Decimal('5'))  # sin diferencia
        self.assertEqual(self.count.items_with_difference.count(), 1)

    def test_total_difference_value_usd_sums_only_differences(self):
        p2 = make_product(self.cat, barcode='AUD003', stock=5, purchase_usd='2.00')
        InventoryCountItem.objects.create(count=self.count, product=self.product,
            system_stock=Decimal('10'), physical_stock=Decimal('7'))  # -3 * 5.00 = -15
        InventoryCountItem.objects.create(count=self.count, product=p2,
            system_stock=Decimal('5'), physical_stock=Decimal('8'))  # +3 * 2.00 = +6
        self.assertEqual(self.count.total_difference_value_usd, Decimal('-15') + Decimal('6'))


# ─────────────────────────────────────────────
# TraceabilityService
# ─────────────────────────────────────────────

class TraceabilityServiceTest(TestCase):

    def setUp(self):
        self.admin = make_admin('trace_admin')
        make_exchange_rate(self.admin)
        self.cat = make_category('TraceCat')
        self.product = make_product(self.cat, barcode='TRC001', stock=Decimal('50'))
        self.customer = Customer.objects.create(name='Cliente Trace', phone='0000')
        self.supplier = Supplier.objects.create(name='Proveedor Trace')

    def _make_sale(self, quantity, days_ago=0):
        sale = Sale.objects.create(
            customer=self.customer, user=self.admin,
            total_bs=Decimal('100'), total_usd=Decimal('3'),
            exchange_rate_used=Decimal('40'), payment_method='cash', is_credit=False,
        )
        Sale.objects.filter(pk=sale.pk).update(date=timezone.now() - timedelta(days=days_ago))
        sale.refresh_from_db()
        SaleItem.objects.create(sale=sale, product=self.product, quantity=Decimal(quantity),
                                price_bs=Decimal('50'), price_usd=Decimal('1.5'))
        return sale

    def _make_adjustment(self, adj_type, quantity, previous, new, days_ago=0):
        adj = InventoryAdjustment.objects.create(
            product=self.product, adjustment_type=adj_type, quantity=Decimal(quantity),
            previous_stock=Decimal(previous), new_stock=Decimal(new),
            reason='test', adjusted_by=self.admin,
        )
        InventoryAdjustment.objects.filter(pk=adj.pk).update(
            adjusted_at=timezone.now() - timedelta(days=days_ago)
        )
        return adj

    def _make_received_order(self, quantity, days_ago=0):
        order = SupplierOrder.objects.create(
            supplier=self.supplier, created_by=self.admin, status='received',
            received_date=timezone.now() - timedelta(days=days_ago),
        )
        return SupplierOrderItem.objects.create(order=order, product=self.product,
                                                quantity=Decimal(quantity), price_usd=Decimal('2'))

    def test_empty_history_returns_empty_list(self):
        eventos = TraceabilityService.build_product_events(self.product)
        self.assertEqual(eventos, [])

    def test_sale_produces_negative_delta(self):
        self._make_sale(quantity='3')
        eventos = TraceabilityService.build_product_events(self.product)
        self.assertEqual(len(eventos), 1)
        self.assertEqual(eventos[0]['tipo'], 'venta')
        self.assertEqual(eventos[0]['delta'], Decimal('-3'))

    def test_received_purchase_produces_positive_delta(self):
        self._make_received_order(quantity='8')
        eventos = TraceabilityService.build_product_events(self.product)
        self.assertEqual(len(eventos), 1)
        self.assertEqual(eventos[0]['tipo'], 'compra')
        self.assertEqual(eventos[0]['delta'], Decimal('8'))

    def test_pending_purchase_order_is_excluded(self):
        """Una orden NO recibida no debe contar como movimiento de stock"""
        order = SupplierOrder.objects.create(
            supplier=self.supplier, created_by=self.admin, status='pending',
        )
        SupplierOrderItem.objects.create(order=order, product=self.product,
                                         quantity=Decimal('8'), price_usd=Decimal('2'))
        eventos = TraceabilityService.build_product_events(self.product)
        self.assertEqual(eventos, [])

    def test_adjustment_delta_uses_previous_and_new_stock(self):
        self._make_adjustment('add', '10', previous='40', new='50')
        eventos = TraceabilityService.build_product_events(self.product)
        self.assertEqual(eventos[0]['tipo'], 'ajuste')
        self.assertEqual(eventos[0]['delta'], Decimal('10'))

    def test_chronological_order_most_recent_first(self):
        self._make_adjustment('add', '10', previous='30', new='40', days_ago=3)
        self._make_sale(quantity='2', days_ago=2)
        self._make_received_order(quantity='12', days_ago=1)
        eventos = TraceabilityService.build_product_events(self.product)
        tipos = [e['tipo'] for e in eventos]
        self.assertEqual(tipos, ['compra', 'venta', 'ajuste'])

    def test_stock_reconstruction_matches_current_stock(self):
        """El stock_after del evento más reciente debe ser el stock actual real"""
        self.product.stock = Decimal('50')
        self.product.save()
        self._make_adjustment('add', '10', previous='40', new='50', days_ago=2)
        self._make_sale(quantity='3', days_ago=1)
        # stock actual queda en 50 aunque la venta de -3 "debería" haberlo bajado
        # (en este test no llamamos a la lógica de venta real que descuenta stock,
        # solo probamos que la reconstrucción es consistente con product.stock)
        eventos = TraceabilityService.build_product_events(self.product)
        self.assertEqual(eventos[0]['stock_after'], self.product.stock)
        # el evento más viejo (ajuste) debe resolver correctamente hacia atrás
        ajuste = [e for e in eventos if e['tipo'] == 'ajuste'][0]
        venta = [e for e in eventos if e['tipo'] == 'venta'][0]
        self.assertEqual(venta['stock_before'], venta['stock_after'] - venta['delta'])
        self.assertEqual(ajuste['stock_before'], ajuste['stock_after'] - ajuste['delta'])

    def test_date_range_filters_events(self):
        self._make_adjustment('add', '10', previous='40', new='50', days_ago=60)
        self._make_sale(quantity='2', days_ago=5)
        hoy = timezone.now().date()
        eventos = TraceabilityService.build_product_events(
            self.product, date_from=hoy - timedelta(days=10), date_to=hoy
        )
        self.assertEqual(len(eventos), 1)
        self.assertEqual(eventos[0]['tipo'], 'venta')


# ─────────────────────────────────────────────
# VISTAS: permisos
# ─────────────────────────────────────────────

class InventoryAuditViewsPermissionTest(TestCase):

    def setUp(self):
        self.admin = make_admin('perm_admin')
        self.employee = make_employee('perm_emp')
        make_exchange_rate(self.admin)
        self.cat = make_category('PermCat')
        self.product = make_product(self.cat, barcode='PERM001')
        self.count = InventoryCount.objects.create(category=self.cat, counted_by=self.admin)

    def test_employee_blocked_from_count_create(self):
        self.client.login(username='perm_emp', password='pass123')
        response = self.client.get(reverse('inventory:inventory_count_create'))
        self.assertEqual(response.status_code, 403)

    def test_employee_blocked_from_count_list(self):
        self.client.login(username='perm_emp', password='pass123')
        response = self.client.get(reverse('inventory:inventory_count_list'))
        self.assertEqual(response.status_code, 403)

    def test_employee_blocked_from_count_detail(self):
        self.client.login(username='perm_emp', password='pass123')
        response = self.client.get(reverse('inventory:inventory_count_detail', args=[self.count.pk]))
        self.assertEqual(response.status_code, 403)

    def test_employee_blocked_from_traceability(self):
        self.client.login(username='perm_emp', password='pass123')
        response = self.client.get(reverse('inventory:product_traceability', args=[self.product.pk]))
        self.assertEqual(response.status_code, 403)

    def test_admin_can_access_all(self):
        self.client.login(username='perm_admin', password='pass123')
        for url in [
            reverse('inventory:inventory_count_create'),
            reverse('inventory:inventory_count_list'),
            reverse('inventory:inventory_count_detail', args=[self.count.pk]),
            reverse('inventory:product_traceability', args=[self.product.pk]),
        ]:
            self.assertEqual(self.client.get(url).status_code, 200)


# ─────────────────────────────────────────────
# VISTAS: flujo de creación de conteo
# ─────────────────────────────────────────────

class InventoryCountCreateViewTest(TestCase):

    def setUp(self):
        self.admin = make_admin('create_admin')
        make_exchange_rate(self.admin)
        self.client.login(username='create_admin', password='pass123')
        self.cat = make_category('CreateCat')
        self.p1 = make_product(self.cat, barcode='CREATE001', stock=10)
        self.p2 = make_product(self.cat, barcode='CREATE002', stock=20)

    def test_category_picker_shown_without_category_param(self):
        response = self.client.get(reverse('inventory:inventory_count_create'))
        self.assertContains(response, self.cat.name)

    def test_count_form_shows_products_of_category(self):
        response = self.client.get(reverse('inventory:inventory_count_create'), {'category': self.cat.pk})
        self.assertContains(response, self.p1.name)
        self.assertContains(response, self.p2.name)

    def test_post_creates_count_and_items(self):
        response = self.client.post(reverse('inventory:inventory_count_create'), {
            'category': str(self.cat.pk),
            'notes': 'conteo de prueba',
            f'physical_stock_{self.p1.pk}': '8',
            f'physical_stock_{self.p2.pk}': '20',
        })
        self.assertEqual(response.status_code, 302)
        count = InventoryCount.objects.get()
        self.assertEqual(count.items.count(), 2)
        item1 = count.items.get(product=self.p1)
        self.assertEqual(item1.difference, Decimal('-2'))

    def test_blank_field_is_skipped_not_treated_as_zero(self):
        """Un producto sin contar no debe crear un item con physical_stock=0"""
        self.client.post(reverse('inventory:inventory_count_create'), {
            'category': str(self.cat.pk),
            f'physical_stock_{self.p1.pk}': '8',
            f'physical_stock_{self.p2.pk}': '',  # sin contar
        })
        count = InventoryCount.objects.get()
        self.assertEqual(count.items.count(), 1)
        self.assertFalse(count.items.filter(product=self.p2).exists())

    def test_post_with_no_products_counted_does_not_save(self):
        response = self.client.post(reverse('inventory:inventory_count_create'), {
            'category': str(self.cat.pk),
            f'physical_stock_{self.p1.pk}': '',
            f'physical_stock_{self.p2.pk}': '',
        })
        self.assertEqual(InventoryCount.objects.count(), 0)
        self.assertEqual(response.status_code, 302)  # redirige de vuelta, no 500

    def test_all_categories_option(self):
        other_cat = make_category('OtherCat')
        p3 = make_product(other_cat, barcode='CREATE003', stock=5)
        response = self.client.post(reverse('inventory:inventory_count_create'), {
            'category': 'all',
            f'physical_stock_{self.p1.pk}': '10',
            f'physical_stock_{p3.pk}': '5',
        })
        self.assertEqual(response.status_code, 302)
        count = InventoryCount.objects.get()
        self.assertIsNone(count.category)
        self.assertEqual(count.items.count(), 2)


# ─────────────────────────────────────────────
# VISTAS: reporte de discrepancias + PDF
# ─────────────────────────────────────────────

class InventoryCountDetailViewTest(TestCase):

    def setUp(self):
        self.admin = make_admin('detail_admin')
        make_exchange_rate(self.admin)
        self.client.login(username='detail_admin', password='pass123')
        self.cat = make_category('DetailCat')
        self.product = make_product(self.cat, barcode='DETAIL001', stock=10, purchase_usd='3.00')
        self.count = InventoryCount.objects.create(category=self.cat, counted_by=self.admin)
        InventoryCountItem.objects.create(count=self.count, product=self.product,
            system_stock=Decimal('10'), physical_stock=Decimal('6'))

    def test_detail_shows_totals(self):
        response = self.client.get(reverse('inventory:inventory_count_detail', args=[self.count.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['totals']['con_diferencia'], 1)
        self.assertEqual(response.context['totals']['valor_diferencia_usd'], Decimal('-4') * Decimal('3.00'))

    def test_pdf_export_returns_pdf(self):
        response = self.client.get(
            reverse('inventory:inventory_count_detail', args=[self.count.pk]), {'format': 'pdf'}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')


# ─────────────────────────────────────────────
# VISTAS: trazabilidad
# ─────────────────────────────────────────────

class ProductTraceabilityViewTest(TestCase):

    def setUp(self):
        self.admin = make_admin('trace_view_admin')
        make_exchange_rate(self.admin)
        self.client.login(username='trace_view_admin', password='pass123')
        self.cat = make_category('TraceViewCat')
        self.product = make_product(self.cat, barcode='TRACEV001', stock=10)

    def test_default_range_is_last_30_days(self):
        response = self.client.get(reverse('inventory:product_traceability', args=[self.product.pk]))
        self.assertEqual(response.status_code, 200)
        hoy = timezone.now().date()
        self.assertEqual(response.context['date_to'], hoy.isoformat())
        self.assertEqual(response.context['date_from'], (hoy - timedelta(days=30)).isoformat())

    def test_pdf_export_returns_pdf(self):
        response = self.client.get(
            reverse('inventory:product_traceability', args=[self.product.pk]), {'format': 'pdf'}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
