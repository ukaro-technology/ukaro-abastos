# parts/tests.py
"""
Tests del perfil de negocio y de la adaptación a tienda de repuestos (perfil 'motoparts'):
- Perfil por defecto ('bodega') sin cambios de comportamiento
- Compatibilidad con motos (PartInfo) desde el formulario de producto
- Búsqueda palabra por palabra, sin tildes, por moto compatible
- Método 'Efectivo $' con descuento calculado en el servidor
- Comprobante por WhatsApp
- Gestión de marcas y modelos de moto
"""

import json
import os
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from bodega_system.business import feature, get_business
from inventory.models import Category, Product
from inventory.search import search_products
from parts.models import MotoBrand, MotoModel, PartInfo
from sales.models import Sale
from sales.whatsapp import normalize_phone, receipt_whatsapp_url
from utils.models import ExchangeRate, StoreSettings

User = get_user_model()

MOTOPARTS = mock.patch.dict(os.environ, {'BUSINESS_PROFILE': 'motoparts'})


def make_product(category, name, barcode, selling='10.00', stock=20):
    return Product.objects.create(
        name=name, barcode=barcode, category=category,
        purchase_price_usd=Decimal('5.00'), selling_price_usd=Decimal(selling),
        stock=Decimal(stock), min_stock=Decimal('2'),
    )


class BaseMotoTest(TestCase):

    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_user(username='moto_admin', password='pass123', is_admin=True)
        ExchangeRate.objects.create(date=timezone.now().date(), bs_to_usd=Decimal('200.00'), updated_by=self.admin)
        self.category = Category.objects.create(name='Frenos')
        bera = MotoBrand.objects.create(name='Bera')
        empire = MotoBrand.objects.create(name='Empire Keeway')
        self.sbr = MotoModel.objects.create(brand=bera, name='SBR 150', displacement_cc=150)
        self.horse = MotoModel.objects.create(brand=empire, name='Horse 150', displacement_cc=150)

        self.pads = make_product(self.category, 'Pastillas de freno delanteras', 'P001')
        PartInfo.objects.create(product=self.pads, part_brand='Genérica').compatible_models.set([self.sbr])
        self.spark = make_product(self.category, 'Bujía NGK C7HSA', 'P002', selling='3.50')
        PartInfo.objects.create(product=self.spark, part_number='C7HSA').compatible_models.set([self.sbr, self.horse])
        self.client.login(username='moto_admin', password='pass123')


class BusinessProfileTest(TestCase):

    def test_default_profile_is_bodega(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop('BUSINESS_PROFILE', None)
            self.assertEqual(get_business()['key'], 'bodega')
            self.assertFalse(feature('moto_parts'))
            self.assertFalse(feature('cash_usd'))

    def test_unknown_profile_falls_back_to_bodega(self):
        with mock.patch.dict(os.environ, {'BUSINESS_PROFILE': 'no-existe'}):
            self.assertEqual(get_business()['key'], 'bodega')

    @MOTOPARTS
    def test_motoparts_profile(self):
        business = get_business()
        self.assertEqual(business['name'], 'SuperMoto Speed')
        self.assertTrue(feature('moto_parts'))
        self.assertFalse(feature('schedules'))


class SearchTest(BaseMotoTest):

    @MOTOPARTS
    def test_tokens_match_name_and_compatible_moto(self):
        result = search_products(Product.objects.all(), 'pastilla sbr')
        self.assertEqual(list(result), [self.pads])

    @MOTOPARTS
    def test_accent_insensitive(self):
        result = search_products(Product.objects.all(), 'bujia')
        self.assertEqual(list(result), [self.spark])

    @MOTOPARTS
    def test_search_by_moto_brand_returns_distinct(self):
        result = search_products(Product.objects.all(), 'bera 150')
        self.assertEqual(sorted(p.pk for p in result), sorted([self.pads.pk, self.spark.pk]))

    @MOTOPARTS
    def test_search_by_part_number(self):
        self.assertEqual(list(search_products(Product.objects.all(), 'c7hsa')), [self.spark])

    def test_bodega_profile_ignores_moto_fields(self):
        os.environ.pop('BUSINESS_PROFILE', None)
        self.assertEqual(list(search_products(Product.objects.all(), 'sbr')), [])
        self.assertEqual(list(search_products(Product.objects.all(), 'pastilla delanteras')), [self.pads])

    @MOTOPARTS
    def test_pos_search_api_includes_part_info(self):
        response = self.client.get('/inventory/api/products/search/', {'q': 'horse'})
        products = response.json()['products']
        self.assertEqual(len(products), 1)
        self.assertIn('Empire Keeway Horse 150', products[0]['part']['compatibility'])

    @MOTOPARTS
    def test_barcode_api_accepts_part_number(self):
        response = self.client.get(reverse('product_by_barcode', args=['c7hsa']))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['id'], self.spark.pk)


class ProductFormPartInfoTest(BaseMotoTest):

    def _post_data(self, **extra):
        data = {
            'name': 'Disco de freno', 'barcode': 'D001', 'category': self.category.pk,
            'unit_type': 'unit', 'pricing_mode': 'usd', 'purchase_price_usd': '10',
            'selling_price_usd': '20', 'min_stock': '2', 'is_active': 'on',
            'part-part_brand': 'Genérica', 'part-quality': 'generic',
            'part-location': 'Estante 1', 'part-compatible_models': [self.sbr.pk, self.horse.pk],
        }
        data.update(extra)
        return data

    @MOTOPARTS
    def test_create_product_saves_compatibility(self):
        response = self.client.post(reverse('inventory:product_create'), self._post_data())
        self.assertEqual(response.status_code, 302)
        product = Product.objects.get(barcode='D001')
        self.assertEqual(product.part_info.location, 'Estante 1')
        self.assertEqual(set(product.part_info.compatible_models.all()), {self.sbr, self.horse})

    def test_bodega_profile_creates_no_part_info(self):
        os.environ.pop('BUSINESS_PROFILE', None)
        response = self.client.post(reverse('inventory:product_create'), self._post_data())
        self.assertEqual(response.status_code, 302)
        self.assertFalse(PartInfo.objects.filter(product__barcode='D001').exists())

    @MOTOPARTS
    def test_edit_form_shows_part_section(self):
        response = self.client.get(reverse('inventory:product_update', args=[self.pads.pk]))
        self.assertContains(response, 'Datos del Repuesto')
        self.assertContains(response, 'SBR 150')


class CashUsdDiscountTest(BaseMotoTest):

    def setUp(self):
        super().setUp()
        settings_obj = StoreSettings.get()
        settings_obj.cash_usd_discount_percent = Decimal('16.67')
        settings_obj.save()

    def _sell(self, method, **extra):
        data = {'items': [{'product_id': self.pads.pk, 'quantity': 3}], 'payment_method': method}
        data.update(extra)
        return self.client.post(reverse('sales:create_sale_api'), json.dumps(data), content_type='application/json')

    @MOTOPARTS
    def test_cash_usd_applies_discount_server_side(self):
        response = self._sell('cash_usd', total_bs=1)  # el total del navegador se ignora
        self.assertEqual(response.status_code, 200)
        sale = Sale.objects.get(pk=response.json()['id'])
        # 3 × $10 = $30 → 16.67% = $5.00 → $25.00
        self.assertEqual(sale.discount_usd, Decimal('5.00'))
        self.assertEqual(sale.total_usd, Decimal('25.00'))
        self.assertEqual(sale.total_bs, Decimal('5000.00'))
        self.assertTrue(response.json()['whatsapp_url'].startswith('https://wa.me/'))

    @MOTOPARTS
    def test_other_methods_have_no_discount(self):
        response = self._sell('mobile', mobile_reference='123')
        sale = Sale.objects.get(pk=response.json()['id'])
        self.assertEqual(sale.discount_usd, Decimal('0'))
        self.assertEqual(sale.total_usd, Decimal('30.00'))

    def test_cash_usd_rejected_when_module_off(self):
        os.environ.pop('BUSINESS_PROFILE', None)
        response = self._sell('cash_usd')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Sale.objects.exists())

    @MOTOPARTS
    def test_settings_page_updates_percent(self):
        response = self.client.post(reverse('utils:store_settings'), {'cash_usd_discount_percent': '10'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(StoreSettings.get().cash_usd_discount_percent, Decimal('10'))


class WhatsAppReceiptTest(BaseMotoTest):

    def test_normalize_venezuelan_phone(self):
        self.assertEqual(normalize_phone('0414-123.45.67'), '584141234567')
        self.assertEqual(normalize_phone('+58 414 1234567'), '584141234567')
        self.assertEqual(normalize_phone('123'), '')

    @MOTOPARTS
    def test_receipt_url_contains_total(self):
        response = self.client.post(
            reverse('sales:create_sale_api'),
            json.dumps({'items': [{'product_id': self.spark.pk, 'quantity': 2}], 'payment_method': 'card'}),
            content_type='application/json',
        )
        sale = Sale.objects.get(pk=response.json()['id'])
        url = receipt_whatsapp_url(sale)
        self.assertIn('SuperMoto%20Speed', url)
        self.assertIn('Total%3A%20%247.00', url)


class MotoListViewTest(BaseMotoTest):

    def test_add_brand_and_model(self):
        url = reverse('parts:moto_list')
        self.client.post(url, {'action': 'add_brand', 'brand-name': 'Yamaha'})
        yamaha = MotoBrand.objects.get(name='Yamaha')
        self.client.post(url, {'action': 'add_model', 'model-brand': yamaha.pk,
                               'model-name': 'YBR 125', 'model-displacement_cc': '125'})
        self.assertTrue(MotoModel.objects.filter(brand=yamaha, name='YBR 125').exists())

    def test_employee_cannot_access(self):
        User.objects.create_user(username='moto_emp', password='pass123', is_employee=True)
        self.client.login(username='moto_emp', password='pass123')
        self.assertEqual(self.client.get(reverse('parts:moto_list')).status_code, 403)


class SeedCommandTest(TestCase):

    @MOTOPARTS
    def test_seed_loads_demo(self):
        from django.core.management import call_command
        call_command('seed_motoparts_demo', stdout=open(os.devnull, 'w'))
        self.assertGreater(Product.objects.count(), 100)
        self.assertTrue(Sale.objects.filter(payment_method='cash_usd', discount_usd__gt=0).exists())
        self.assertTrue(User.objects.filter(username='dueno', is_admin=True).exists())
        # El guion del demo (docs/demo-supermoto-guion.md) usa este caucho de $30
        caucho = Product.objects.get(name='Caucho trasero 90/90-18')
        self.assertEqual(caucho.selling_price_usd, Decimal('30.00'))
        self.assertGreater(caucho.stock, 0)

    @MOTOPARTS
    def test_if_empty_skips_when_products_exist(self):
        from django.core.management import call_command
        category = Category.objects.create(name='Real')
        make_product(category, 'Producto real', 'REAL001')
        call_command('seed_motoparts_demo', '--if-empty', stdout=open(os.devnull, 'w'))
        self.assertEqual(Product.objects.count(), 1)

    @mock.patch.dict(os.environ, {'BUSINESS_PROFILE': 'motoparts', 'DEMO_PASSWORD': 'otra-clave'})
    def test_demo_password_from_env(self):
        from django.core.management import call_command
        call_command('seed_motoparts_demo', stdout=open(os.devnull, 'w'))
        self.assertTrue(User.objects.get(username='dueno').check_password('otra-clave'))
