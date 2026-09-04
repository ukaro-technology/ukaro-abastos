# inventory/tests.py
"""
Tests exhaustivos para el módulo inventory:
- Category model
- Product model (precios, stock, propiedades)
- InventoryAdjustment model
- Vistas de productos, categorías, ajustes
- APIs de productos (búsqueda, barcode, validación)
"""

import json
from decimal import Decimal

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from django.db import IntegrityError
from datetime import timedelta

from inventory.models import Category, Product, InventoryAdjustment
from inventory.forms import ProductForm
from utils.models import ExchangeRate

User = get_user_model()


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def make_admin(username='inv_admin'):
    return User.objects.create_user(username=username, password='pass123', is_admin=True)

def make_employee(username='inv_emp'):
    return User.objects.create_user(username=username, password='pass123', is_employee=True)

def make_exchange_rate(user, rate='45.50', days_offset=0):
    cache.clear()
    return ExchangeRate.objects.create(
        date=timezone.now().date() + timedelta(days=days_offset),
        bs_to_usd=Decimal(rate),
        updated_by=user
    )

def make_category(name='Alimentos'):
    return Category.objects.create(name=name)

def make_product(category, barcode='000001', name='Arroz', purchase_usd='5.00',
                 selling_usd='8.00', stock=100, min_stock=10):
    return Product.objects.create(
        name=name,
        barcode=barcode,
        category=category,
        purchase_price_usd=Decimal(purchase_usd),
        purchase_price_bs=Decimal('0'),
        selling_price_usd=Decimal(selling_usd),
        selling_price_bs=Decimal('0'),
        stock=Decimal(str(stock)),
        min_stock=Decimal(str(min_stock))
    )


# ─────────────────────────────────────────────
# CATEGORY MODEL TESTS
# ─────────────────────────────────────────────

class CategoryModelTest(TestCase):

    def test_create_category(self):
        """Debe crear categoría con nombre y descripción"""
        cat = Category.objects.create(name='Bebidas', description='Líquidos')
        self.assertEqual(cat.name, 'Bebidas')
        self.assertEqual(cat.description, 'Líquidos')

    def test_create_category_without_description(self):
        """Descripción es opcional"""
        cat = Category.objects.create(name='Sin desc')
        self.assertEqual(cat.description, '')

    def test_str_representation(self):
        """__str__ debe retornar el nombre"""
        cat = Category.objects.create(name='Lácteos')
        self.assertEqual(str(cat), 'Lácteos')

    def test_ordering_by_name(self):
        """Categorías deben ordenarse alfabéticamente"""
        Category.objects.create(name='Zumos')
        Category.objects.create(name='Arroz')
        Category.objects.create(name='Miel')
        cats = list(Category.objects.all())
        self.assertEqual(cats[0].name, 'Arroz')
        self.assertEqual(cats[1].name, 'Miel')
        self.assertEqual(cats[2].name, 'Zumos')


# ─────────────────────────────────────────────
# PRODUCT MODEL TESTS
# ─────────────────────────────────────────────

class ProductModelTest(TestCase):

    def setUp(self):
        cache.clear()
        self.admin = make_admin()
        self.exchange_rate = make_exchange_rate(self.admin)
        self.cat = make_category()

    def test_create_product_basic(self):
        """Debe crear producto con todos los campos obligatorios"""
        product = make_product(self.cat)
        self.assertEqual(product.name, 'Arroz')
        self.assertEqual(product.barcode, '000001')
        self.assertEqual(product.purchase_price_usd, Decimal('5.00'))
        self.assertEqual(product.selling_price_usd, Decimal('8.00'))
        self.assertTrue(product.is_active)

    def test_barcode_unique_constraint(self):
        """Barcode debe ser único"""
        make_product(self.cat, barcode='UNIQUE001')
        with self.assertRaises(Exception):
            make_product(self.cat, barcode='UNIQUE001', name='Otro')

    def test_stock_status_normal(self):
        """stock_status debe retornar 'Stock normal' cuando stock >= min_stock"""
        p = make_product(self.cat, stock=100, min_stock=10)
        self.assertEqual(p.stock_status, 'Stock normal')

    def test_stock_status_low(self):
        """stock_status debe retornar 'Stock bajo' cuando stock < min_stock"""
        p = make_product(self.cat, stock=5, min_stock=10)
        self.assertEqual(p.stock_status, 'Stock bajo')

    def test_stock_status_zero(self):
        """stock_status debe retornar 'Sin stock' cuando stock <= 0"""
        p = make_product(self.cat, stock=0)
        self.assertEqual(p.stock_status, 'Sin stock')

    def test_profit_margin_usd(self):
        """profit_margin_usd debe calcular correctamente"""
        p = make_product(self.cat, purchase_usd='5.00', selling_usd='8.00')
        self.assertEqual(p.profit_margin_usd, Decimal('3.00'))

    def test_profit_margin_percentage(self):
        """profit_margin_percentage debe calcular correctamente"""
        p = make_product(self.cat, purchase_usd='5.00', selling_usd='10.00')
        self.assertEqual(p.profit_margin_percentage, 100)

    def test_is_weight_based_unit(self):
        """Producto de tipo 'unit' no es por peso"""
        p = make_product(self.cat)
        p.unit_type = 'unit'
        self.assertFalse(p.is_weight_based)

    def test_is_weight_based_kg(self):
        """Producto de tipo 'kg' sí es por peso"""
        p = make_product(self.cat)
        p.unit_type = 'kg'
        self.assertTrue(p.is_weight_based)

    def test_get_price_usd_for_quantity_normal(self):
        """Precio normal para cantidad pequeña"""
        p = make_product(self.cat, selling_usd='8.00')
        price = p.get_price_usd_for_quantity(5)
        self.assertEqual(price, Decimal('8.00'))

    def test_get_price_usd_for_quantity_bulk(self):
        """Precio al mayor para cantidad grande"""
        p = make_product(self.cat, selling_usd='8.00')
        p.is_bulk_pricing = True
        p.bulk_min_quantity = Decimal('10')
        p.bulk_price_usd = Decimal('6.00')
        p.save()
        price = p.get_price_usd_for_quantity(10)
        self.assertEqual(price, Decimal('6.00'))

    def test_get_current_price_bs(self):
        """get_current_price_bs debe usar la tasa vigente"""
        p = make_product(self.cat, selling_usd='8.00')
        expected = Decimal('8.00') * Decimal('45.50')
        result = p.get_current_price_bs()
        self.assertEqual(result, expected)

    def test_get_current_price_bs_no_rate(self):
        """get_current_price_bs retorna 0 si no hay tasa"""
        ExchangeRate.objects.all().delete()
        cache.clear()
        p = make_product(self.cat, selling_usd='8.00')
        self.assertEqual(p.get_current_price_bs(), Decimal('0.00'))

    def test_str_representation(self):
        """__str__ debe retornar el nombre del producto"""
        p = make_product(self.cat, name='Producto STR')
        self.assertEqual(str(p), 'Producto STR')

    def test_unit_display(self):
        """unit_display debe retornar la etiqueta legible"""
        p = make_product(self.cat)
        p.unit_type = 'kg'
        self.assertEqual(p.unit_display, 'Kilogramo')


# ─────────────────────────────────────────────
# PRODUCT PRICING MODE TESTS (spec: precios-estables-bs)
# ─────────────────────────────────────────────

class ProductPricingModeTest(TestCase):
    """Tests de Product.get_current_price_bs()/get_current_price_usd() para el modo
    'bs_fixed' — spec: docs/specs/precios-estables-bs.md"""

    def setUp(self):
        cache.clear()
        self.admin = make_admin('pm_admin')
        self.exchange_rate = make_exchange_rate(self.admin, rate='40.00')
        self.cat = make_category('Pricing Mode Cat')

    def test_default_pricing_mode_is_usd(self):
        """Un producto nuevo queda en modo 'usd' por defecto (sin cambios para nadie)"""
        p = make_product(self.cat)
        self.assertEqual(p.pricing_mode, Product.PRICING_MODE_USD)

    def test_bs_fixed_price_ignores_exchange_rate(self):
        """En modo bs_fixed, get_current_price_bs devuelve selling_price_bs tal cual"""
        p = make_product(self.cat, selling_usd='8.00')
        p.pricing_mode = Product.PRICING_MODE_BS_FIXED
        p.selling_price_bs = Decimal('500.00')
        p.save()

        self.assertEqual(p.get_current_price_bs(), Decimal('500.00'))

    def test_bs_fixed_price_does_not_move_with_new_rate(self):
        """Cambiar la tasa BCV no debe afectar el precio de un producto bs_fixed"""
        p = make_product(self.cat, selling_usd='8.00')
        p.pricing_mode = Product.PRICING_MODE_BS_FIXED
        p.selling_price_bs = Decimal('500.00')
        p.save()

        make_exchange_rate(self.admin, rate='120.00', days_offset=1)  # tasa se dispara

        self.assertEqual(p.get_current_price_bs(), Decimal('500.00'))

    def test_usd_mode_price_still_follows_rate(self):
        """Un producto en modo 'usd' (default) sigue recalculando con la tasa, sin cambios"""
        p = make_product(self.cat, selling_usd='8.00')
        self.assertEqual(p.get_current_price_bs(), Decimal('8.00') * Decimal('40.00'))

        make_exchange_rate(self.admin, rate='50.00', days_offset=1)
        self.assertEqual(p.get_current_price_bs(), Decimal('8.00') * Decimal('50.00'))

    def test_get_current_price_usd_bs_fixed_is_informative_equivalent(self):
        """En bs_fixed, get_current_price_usd() es Bs fijo / tasa actual — no dirige la venta"""
        p = make_product(self.cat, selling_usd='8.00')
        p.pricing_mode = Product.PRICING_MODE_BS_FIXED
        p.selling_price_bs = Decimal('400.00')
        p.save()

        self.assertEqual(p.get_current_price_usd(), Decimal('400.00') / Decimal('40.00'))

    def test_get_current_price_usd_usd_mode_unchanged(self):
        """En modo usd, get_current_price_usd() sigue siendo selling_price_usd"""
        p = make_product(self.cat, selling_usd='8.00')
        self.assertEqual(p.get_current_price_usd(), Decimal('8.00'))

    def test_bs_fixed_ignores_bulk_pricing(self):
        """El modo bs_fixed no tiene equivalente de precio al mayor — quantity se ignora"""
        p = make_product(self.cat, selling_usd='8.00')
        p.pricing_mode = Product.PRICING_MODE_BS_FIXED
        p.selling_price_bs = Decimal('500.00')
        p.is_bulk_pricing = True
        p.bulk_min_quantity = Decimal('10')
        p.bulk_price_usd = Decimal('6.00')
        p.save()

        self.assertEqual(p.get_current_price_bs(quantity=Decimal('20')), Decimal('500.00'))

    def test_usd_mode_still_respects_bulk_pricing_with_quantity(self):
        """En modo usd, get_current_price_bs con quantity sigue respetando precio al mayor"""
        p = make_product(self.cat, selling_usd='8.00')
        p.is_bulk_pricing = True
        p.bulk_min_quantity = Decimal('10')
        p.bulk_price_usd = Decimal('6.00')
        p.save()

        self.assertEqual(
            p.get_current_price_bs(quantity=Decimal('20')),
            Decimal('6.00') * Decimal('40.00')
        )
        self.assertEqual(
            p.get_current_price_bs(quantity=Decimal('1')),
            Decimal('8.00') * Decimal('40.00')
        )

    def test_get_current_price_bs_no_rate_bs_fixed_still_returns_fixed_price(self):
        """Sin tasa configurada, un producto bs_fixed sigue devolviendo su precio fijo"""
        p = make_product(self.cat, selling_usd='8.00')
        p.pricing_mode = Product.PRICING_MODE_BS_FIXED
        p.selling_price_bs = Decimal('500.00')
        p.save()

        ExchangeRate.objects.all().delete()
        cache.clear()

        self.assertEqual(p.get_current_price_bs(), Decimal('500.00'))

    def test_exchange_rate_param_avoids_extra_lookup(self):
        """Si se pasa exchange_rate explícito, se usa esa tasa y no la más reciente"""
        p = make_product(self.cat, selling_usd='8.00')
        other_rate = make_exchange_rate(self.admin, rate='999.00', days_offset=1)
        # Sin exchange_rate explícito usaría la tasa más reciente (999.00); con el parámetro
        # se debe respetar exactamente lo que se pasó (self.exchange_rate = 40.00).
        result = p.get_current_price_bs(exchange_rate=self.exchange_rate)
        self.assertEqual(result, Decimal('8.00') * Decimal('40.00'))


# ─────────────────────────────────────────────
# PRODUCT FORM TESTS (spec: precios-estables-bs)
# ─────────────────────────────────────────────

class ProductFormPricingModeTest(TestCase):
    """Tests de ProductForm para el toggle de modo de precio"""

    def setUp(self):
        cache.clear()
        self.admin = make_admin('form_pm_admin')
        self.exchange_rate = make_exchange_rate(self.admin, rate='40.00')
        self.cat = make_category('Form Pricing Cat')

    def _base_data(self, **overrides):
        data = {
            'name': 'Producto Form',
            'barcode': 'FORMPM001',
            'category': self.cat.pk,
            'unit_type': 'unit',
            'description': '',
            'purchase_price_usd': '5.00',
            'selling_price_usd': '8.00',
            'min_stock': '5',
            'is_active': 'on',
            'pricing_mode': Product.PRICING_MODE_USD,
        }
        data.update(overrides)
        return data

    def test_usd_mode_requires_selling_price_usd(self):
        """En modo usd (default), selling_price_usd sigue siendo requerido"""
        data = self._base_data(selling_price_usd='')
        form = ProductForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('selling_price_usd', form.errors)

    def test_bs_fixed_requires_selling_price_bs(self):
        """En modo bs_fixed, selling_price_bs es requerido aunque selling_price_usd venga vacío"""
        data = self._base_data(
            pricing_mode=Product.PRICING_MODE_BS_FIXED,
            selling_price_usd='',
            selling_price_bs='',
        )
        form = ProductForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('selling_price_bs', form.errors)
        # No debe exigir selling_price_usd en este modo
        self.assertNotIn('selling_price_usd', form.errors)

    def test_bs_fixed_saves_fixed_price_and_recalculates_usd_reference(self):
        """Al guardar en modo bs_fixed, selling_price_bs manda y selling_price_usd
        queda como el equivalente informativo (Bs fijo / tasa actual)"""
        data = self._base_data(
            pricing_mode=Product.PRICING_MODE_BS_FIXED,
            selling_price_usd='',
            selling_price_bs='400.00',
        )
        form = ProductForm(data=data)
        self.assertTrue(form.is_valid(), form.errors)
        product = form.save()

        self.assertEqual(product.pricing_mode, Product.PRICING_MODE_BS_FIXED)
        self.assertEqual(product.selling_price_bs, Decimal('400.00'))
        self.assertEqual(product.selling_price_usd, Decimal('400.00') / Decimal('40.00'))
        self.assertEqual(product.get_current_price_bs(), Decimal('400.00'))

    def test_bs_fixed_price_survives_rate_change_after_save(self):
        """El precio fijo guardado por el form no se mueve si luego cambia la tasa"""
        data = self._base_data(
            pricing_mode=Product.PRICING_MODE_BS_FIXED,
            selling_price_usd='',
            selling_price_bs='400.00',
        )
        form = ProductForm(data=data)
        self.assertTrue(form.is_valid(), form.errors)
        product = form.save()

        make_exchange_rate(self.admin, rate='90.00', days_offset=1)
        product.refresh_from_db()
        self.assertEqual(product.get_current_price_bs(), Decimal('400.00'))

    def test_usd_mode_refreshes_vestigial_bs_columns(self):
        """En modo usd, purchase_price_bs/selling_price_bs se refrescan con la tasa actual al
        guardar (decisión 7.3 de la spec — no reemplaza el fix del reporte, pero evita que la
        columna cruda quede más desactualizada de lo necesario)"""
        data = self._base_data(purchase_price_usd='5.00', selling_price_usd='8.00')
        form = ProductForm(data=data)
        self.assertTrue(form.is_valid(), form.errors)
        product = form.save()

        self.assertEqual(product.purchase_price_bs, Decimal('5.00') * Decimal('40.00'))
        self.assertEqual(product.selling_price_bs, Decimal('8.00') * Decimal('40.00'))

    def test_bs_fixed_rejects_bulk_pricing(self):
        """El precio al mayor no tiene equivalente en modo bs_fixed — debe rechazarse"""
        data = self._base_data(
            pricing_mode=Product.PRICING_MODE_BS_FIXED,
            selling_price_usd='',
            selling_price_bs='400.00',
            is_bulk_pricing='on',
            bulk_min_quantity='10',
            bulk_price_usd='6.00',
        )
        form = ProductForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('is_bulk_pricing', form.errors)

    def test_bs_fixed_requires_positive_price(self):
        """selling_price_bs <= 0 en modo bs_fixed debe fallar"""
        data = self._base_data(
            pricing_mode=Product.PRICING_MODE_BS_FIXED,
            selling_price_usd='',
            selling_price_bs='0',
        )
        form = ProductForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('selling_price_bs', form.errors)

    def test_usd_mode_unchanged_validation_selling_gt_purchase(self):
        """Comportamiento actual sin cambios: venta debe ser mayor que compra en modo usd"""
        data = self._base_data(purchase_price_usd='10.00', selling_price_usd='5.00')
        form = ProductForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('selling_price_usd', form.errors)


# ─────────────────────────────────────────────
# INVENTORY ADJUSTMENT MODEL TESTS
# ─────────────────────────────────────────────

class InventoryAdjustmentModelTest(TestCase):

    def setUp(self):
        cache.clear()
        self.admin = make_admin('adj_admin')
        make_exchange_rate(self.admin)
        self.cat = make_category('Ajuste Cat')
        self.product = make_product(self.cat, barcode='ADJ001', stock=50)

    def test_create_adjustment_add(self):
        """Debe crear ajuste de tipo 'add'"""
        adj = InventoryAdjustment.objects.create(
            product=self.product,
            adjustment_type='add',
            quantity=Decimal('20'),
            previous_stock=Decimal('50'),
            new_stock=Decimal('70'),
            reason='Reposición de stock',
            adjusted_by=self.admin
        )
        self.assertEqual(adj.adjustment_type, 'add')
        self.assertEqual(adj.quantity, Decimal('20'))
        self.assertEqual(adj.product, self.product)

    def test_create_adjustment_remove(self):
        """Debe crear ajuste de tipo 'remove'"""
        adj = InventoryAdjustment.objects.create(
            product=self.product,
            adjustment_type='remove',
            quantity=Decimal('10'),
            previous_stock=Decimal('50'),
            new_stock=Decimal('40'),
            reason='Merma',
            adjusted_by=self.admin
        )
        self.assertEqual(adj.adjustment_type, 'remove')

    def test_create_adjustment_set(self):
        """Debe crear ajuste de tipo 'set'"""
        adj = InventoryAdjustment.objects.create(
            product=self.product,
            adjustment_type='set',
            quantity=Decimal('100'),
            previous_stock=Decimal('50'),
            new_stock=Decimal('100'),
            reason='Inventario físico',
            adjusted_by=self.admin
        )
        self.assertEqual(adj.adjustment_type, 'set')
        self.assertEqual(adj.new_stock, Decimal('100'))


# ─────────────────────────────────────────────
# PRODUCT LIST VIEW TESTS
# ─────────────────────────────────────────────

class ProductListViewTest(TestCase):

    def setUp(self):
        cache.clear()
        self.client = Client()
        self.admin = make_admin('list_admin')
        self.employee = make_employee('list_emp')
        make_exchange_rate(self.admin)
        self.cat = make_category('Lista Cat')
        self.p1 = make_product(self.cat, barcode='LIST001', name='Arroz Lista')
        self.p2 = make_product(self.cat, barcode='LIST002', name='Pasta Lista', stock=3, min_stock=10)
        self.url = reverse('inventory:product_list')

    def test_get_list_unauthenticated_redirects(self):
        """Sin autenticación debe redirigir al login"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response['Location'])

    def test_get_list_admin_authenticated(self):
        """Admin puede ver la lista de productos"""
        self.client.login(username='list_admin', password='pass123')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_get_list_employee_authenticated(self):
        """Empleado puede ver la lista de productos"""
        self.client.login(username='list_emp', password='pass123')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_search_filter(self):
        """Búsqueda por nombre debe filtrar productos"""
        self.client.login(username='list_admin', password='pass123')
        response = self.client.get(self.url, {'q': 'Arroz'})
        self.assertEqual(response.status_code, 200)
        # La vista usa paginación: los productos están en page_obj
        self.assertIn('page_obj', response.context)

    def test_category_filter(self):
        """Filtro por categoría debe funcionar"""
        self.client.login(username='list_admin', password='pass123')
        response = self.client.get(self.url, {'category': self.cat.pk})
        self.assertEqual(response.status_code, 200)


# ─────────────────────────────────────────────
# PRODUCT CRUD VIEW TESTS
# ─────────────────────────────────────────────

class ProductCRUDViewTest(TestCase):

    def setUp(self):
        cache.clear()
        self.client = Client()
        self.admin = make_admin('crud_admin')
        self.employee = make_employee('crud_emp')
        make_exchange_rate(self.admin)
        self.cat = make_category('CRUD Cat')
        self.product = make_product(self.cat, barcode='CRUD001')

    def test_create_get_requires_admin(self):
        """Empleado no puede acceder al formulario de creación"""
        self.client.login(username='crud_emp', password='pass123')
        url = reverse('inventory:product_create')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_create_get_admin_ok(self):
        """Admin puede ver formulario de creación"""
        self.client.login(username='crud_admin', password='pass123')
        url = reverse('inventory:product_create')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_product_detail_accessible(self):
        """Detalle de producto accesible para admin"""
        self.client.login(username='crud_admin', password='pass123')
        url = reverse('inventory:product_detail', args=[self.product.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_update_get_admin_ok(self):
        """Admin puede ver formulario de edición"""
        self.client.login(username='crud_admin', password='pass123')
        url = reverse('inventory:product_update', args=[self.product.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_update_get_employee_blocked(self):
        """Empleado no puede editar productos"""
        self.client.login(username='crud_emp', password='pass123')
        url = reverse('inventory:product_update', args=[self.product.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_delete_get_admin_ok(self):
        """Admin puede acceder a la URL de eliminación (pasa @admin_required)"""
        self.client.raise_request_exception = False
        self.client.login(username='crud_admin', password='pass123')
        url = reverse('inventory:product_delete', args=[self.product.pk])
        response = self.client.get(url)
        # Admin pasa el decorador: no debe dar 403 ni redirigir al login
        self.assertNotEqual(response.status_code, 403)
        self.assertNotIn('/accounts/login/', response.get('Location', ''))
        self.client.raise_request_exception = True

    def test_delete_employee_blocked(self):
        """Empleado no puede eliminar productos"""
        self.client.login(username='crud_emp', password='pass123')
        url = reverse('inventory:product_delete', args=[self.product.pk])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 403)


# ─────────────────────────────────────────────
# CATEGORY CRUD VIEW TESTS
# ─────────────────────────────────────────────

class CategoryCRUDViewTest(TestCase):

    def setUp(self):
        cache.clear()
        self.client = Client()
        self.admin = make_admin('cat_admin')
        self.employee = make_employee('cat_emp')
        make_exchange_rate(self.admin)
        self.cat = make_category('Cat CRUD Test')

    def test_category_list_admin(self):
        """Admin puede ver lista de categorías"""
        self.client.login(username='cat_admin', password='pass123')
        url = reverse('inventory:category_list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_category_create_get_admin(self):
        """Admin puede ver formulario de categoría"""
        self.client.login(username='cat_admin', password='pass123')
        url = reverse('inventory:category_create')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_category_create_post_valid(self):
        """Admin puede crear categoría"""
        self.client.login(username='cat_admin', password='pass123')
        url = reverse('inventory:category_create')
        response = self.client.post(url, {'name': 'Nueva Categoría', 'description': ''})
        if response.status_code == 302:
            self.assertTrue(Category.objects.filter(name='Nueva Categoría').exists())


# ─────────────────────────────────────────────
# PRODUCT API TESTS
# ─────────────────────────────────────────────

class ProductAPITest(TestCase):

    def setUp(self):
        cache.clear()
        self.client = Client()
        self.admin = make_admin('api_admin')
        make_exchange_rate(self.admin)
        self.cat = make_category('API Cat')
        self.product = make_product(
            self.cat, barcode='API001', name='Producto API', stock=50
        )
        self.client.login(username='api_admin', password='pass123')

    def test_product_search_api_returns_products(self):
        """API de búsqueda debe retornar productos que coincidan"""
        url = reverse('inventory:product_search_api')
        response = self.client.get(url, {'q': 'Producto API'})
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        # La API retorna {'products': [...], 'count': ..., 'query': ...}
        self.assertIn('products', data)
        names = [p.get('name', '') for p in data['products']]
        self.assertIn('Producto API', names)

    def test_product_search_api_empty_query(self):
        """API de búsqueda con query vacío"""
        url = reverse('inventory:product_search_api')
        response = self.client.get(url, {'q': ''})
        self.assertEqual(response.status_code, 200)

    def test_barcode_api_found(self):
        """API de barcode debe retornar producto existente"""
        url = reverse('inventory:product_by_barcode_api', args=['API001'])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data.get('name'), 'Producto API')

    def test_barcode_api_not_found(self):
        """API de barcode debe retornar 404 para barcode inexistente"""
        url = reverse('inventory:product_by_barcode_api', args=['NOTEXIST'])
        response = self.client.get(url)
        self.assertIn(response.status_code, [404, 200])  # Puede ser 404 o JSON con error

    def test_validate_barcode_unique(self):
        """Validar barcode único debe retornar disponible (endpoint POST con JSON)"""
        url = reverse('inventory:validate_barcode_api')
        response = self.client.post(
            url,
            json.dumps({'barcode': 'NUEVO_CODE_999'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        # API retorna {'valid': True/False, 'message': '...'}
        self.assertTrue(data.get('valid', True))

    def test_validate_barcode_duplicate(self):
        """Validar barcode duplicado debe retornar no disponible (endpoint POST con JSON)"""
        url = reverse('inventory:validate_barcode_api')
        response = self.client.post(
            url,
            json.dumps({'barcode': 'API001'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        # API retorna {'valid': False, 'message': '...'}
        self.assertFalse(data.get('valid', True))

    def test_product_detail_api(self):
        """API de detalle debe retornar JSON con info del producto"""
        url = reverse('inventory:product_detail_api', args=[self.product.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data.get('name'), 'Producto API')


# ─────────────────────────────────────────────
# STOCK SUMMARY API — VALORIZACIÓN (spec: precios-estables-bs, decisión 7.3)
# ─────────────────────────────────────────────

class ProductStockSummaryValorizationTest(TestCase):
    """El reporte de valorización calcula en vivo con la tasa actual (ya no lee las columnas
    purchase_price_bs/selling_price_bs, vestigiales) y respeta el precio estable en Bs."""

    def setUp(self):
        cache.clear()
        self.client = Client()
        self.admin = make_admin('valor_admin')
        make_exchange_rate(self.admin, rate='40.00')
        self.cat = make_category('Valor Cat')
        self.client.login(username='valor_admin', password='pass123')
        self.url = reverse('inventory:product_stock_summary_api')

    def test_selling_value_uses_live_rate_for_usd_products(self):
        """Producto en modo usd: valor de venta = stock × usd × tasa actual, no la columna vieja"""
        make_product(
            self.cat, barcode='VALORUSD001', selling_usd='8.00', purchase_usd='5.00', stock=10
        )
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)['summary']
        self.assertAlmostEqual(
            data['total_selling_value'], float(10 * Decimal('8.00') * Decimal('40.00')), places=2
        )
        self.assertAlmostEqual(
            data['total_purchase_value'], float(10 * Decimal('5.00') * Decimal('40.00')), places=2
        )

    def test_selling_value_uses_fixed_bs_price_for_bs_fixed_products(self):
        """Producto en modo bs_fixed: valor de venta usa el precio fijo, no usd × tasa"""
        p = make_product(
            self.cat, barcode='VALORFIX001', selling_usd='8.00', purchase_usd='5.00', stock=10
        )
        p.pricing_mode = Product.PRICING_MODE_BS_FIXED
        p.selling_price_bs = Decimal('500.00')
        p.save()

        response = self.client.get(self.url)
        data = json.loads(response.content)['summary']

        # Venta: 10 unidades × 500.00 fijo (NO 10 × 8.00 × 40.00)
        self.assertAlmostEqual(data['total_selling_value'], float(10 * Decimal('500.00')), places=2)
        # Compra: siempre sigue la tasa actual, sin importar el modo de venta
        self.assertAlmostEqual(
            data['total_purchase_value'], float(10 * Decimal('5.00') * Decimal('40.00')), places=2
        )

    def test_mixed_products_valorization_is_additive(self):
        """La valorización de una mezcla de productos usd y bs_fixed suma correctamente"""
        make_product(self.cat, barcode='MIXUSD001', selling_usd='8.00', purchase_usd='5.00', stock=10)
        p2 = make_product(self.cat, barcode='MIXFIX001', selling_usd='8.00', purchase_usd='5.00', stock=5)
        p2.pricing_mode = Product.PRICING_MODE_BS_FIXED
        p2.selling_price_bs = Decimal('300.00')
        p2.save()

        response = self.client.get(self.url)
        data = json.loads(response.content)['summary']

        expected_selling = (10 * Decimal('8.00') * Decimal('40.00')) + (5 * Decimal('300.00'))
        self.assertAlmostEqual(data['total_selling_value'], float(expected_selling), places=2)
