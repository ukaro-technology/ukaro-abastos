# inventory/tests_service.py
"""
Tests para el Service Layer de productos (FASE 3.2)
"""

from decimal import Decimal
from datetime import timedelta
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import transaction

from inventory.models import Product, Category
from inventory.services import ProductService
from utils.models import ExchangeRate

User = get_user_model()


class ProductServiceValidationTest(TestCase):
    """Tests para validaciones del ProductService"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testadmin',
            email='admin@test.com',
            password='testpass123',
            is_admin=True
        )

        self.exchange_rate = ExchangeRate.objects.create(
            date=timezone.now().date(),
            bs_to_usd=Decimal('45.50'),
            updated_by=self.user
        )

        self.category = Category.objects.create(name='Test Category')

    def test_validate_product_data_success(self):
        """Datos válidos deben pasar la validación"""
        data = {
            'name': 'Producto Test',
            'barcode': '123456789',
            'category': self.category,
            'purchase_price_usd': Decimal('10.00'),
            'selling_price_usd': Decimal('15.00'),
            'stock': 10,
            'min_stock': 5
        }

        validated = ProductService.validate_product_data(data)
        self.assertEqual(validated, data)

    def test_validate_requires_name(self):
        """Debe requerir nombre del producto"""
        data = {
            'name': '',  # Vacío
            'barcode': '123456789',
            'category': self.category,
            'purchase_price_usd': Decimal('10.00'),
            'selling_price_usd': Decimal('15.00')
        }

        with self.assertRaises(ValueError) as context:
            ProductService.validate_product_data(data)

        self.assertIn('El nombre del producto es requerido', str(context.exception))

    def test_validate_requires_category(self):
        """Debe requerir categoría"""
        data = {
            'name': 'Producto Test',
            'barcode': '123456789',
            'category': None,
            'purchase_price_usd': Decimal('10.00'),
            'selling_price_usd': Decimal('15.00')
        }

        with self.assertRaises(ValueError) as context:
            ProductService.validate_product_data(data)

        self.assertIn('La categoría es requerida', str(context.exception))

    def test_validate_unique_barcode(self):
        """Código de barras debe ser único"""
        # Crear producto con barcode
        Product.objects.create(
            name='Producto Existente',
            barcode='123456789',
            category=self.category,
            purchase_price_usd=Decimal('10.00'),
            purchase_price_bs=Decimal('455.00'),
            selling_price_usd=Decimal('15.00'),
            selling_price_bs=Decimal('682.50')
        )

        # Intentar validar datos con mismo barcode
        data = {
            'name': 'Producto Nuevo',
            'barcode': '123456789',  # Duplicado
            'category': self.category,
            'purchase_price_usd': Decimal('10.00'),
            'selling_price_usd': Decimal('15.00')
        }

        with self.assertRaises(ValueError) as context:
            ProductService.validate_product_data(data)

        self.assertIn('Ya existe un producto con este código de barras', str(context.exception))

    def test_validate_positive_prices(self):
        """Precios deben ser mayores a cero"""
        data = {
            'name': 'Producto Test',
            'barcode': '123456789',
            'category': self.category,
            'purchase_price_usd': Decimal('-10.00'),  # Negativo
            'selling_price_usd': Decimal('15.00')
        }

        with self.assertRaises(ValueError) as context:
            ProductService.validate_product_data(data)

        self.assertIn('Los precios deben ser mayores a cero', str(context.exception))

    def test_validate_selling_price_greater_than_purchase(self):
        """Precio de venta debe ser mayor al de compra"""
        data = {
            'name': 'Producto Test',
            'barcode': '123456789',
            'category': self.category,
            'purchase_price_usd': Decimal('20.00'),
            'selling_price_usd': Decimal('15.00')  # Menor que compra
        }

        with self.assertRaises(ValueError) as context:
            ProductService.validate_product_data(data)

        self.assertIn('El precio de venta debe ser mayor al de compra', str(context.exception))

    def test_validate_non_negative_stock(self):
        """Stock no debe ser negativo"""
        data = {
            'name': 'Producto Test',
            'barcode': '123456789',
            'category': self.category,
            'purchase_price_usd': Decimal('10.00'),
            'selling_price_usd': Decimal('15.00'),
            'stock': -5  # Negativo
        }

        with self.assertRaises(ValueError) as context:
            ProductService.validate_product_data(data)

        self.assertIn('El stock no puede ser negativo', str(context.exception))


class ProductServicePriceCalculationTest(TestCase):
    """Tests para cálculos de precios"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testadmin',
            email='admin@test.com',
            password='testpass123',
            is_admin=True
        )

        self.exchange_rate = ExchangeRate.objects.create(
            date=timezone.now().date(),
            bs_to_usd=Decimal('45.50'),
            updated_by=self.user
        )

    def test_calculate_price_bs_with_exchange_rate(self):
        """Debe calcular precio en Bs correctamente"""
        price_usd = Decimal('10.00')
        price_bs = ProductService.calculate_price_bs(price_usd, self.exchange_rate)

        self.assertEqual(price_bs, Decimal('455.00'))  # 10 * 45.50

    def test_calculate_price_bs_without_exchange_rate_uses_latest(self):
        """Sin tasa explícita, debe usar la más reciente"""
        price_usd = Decimal('10.00')
        price_bs = ProductService.calculate_price_bs(price_usd)

        self.assertEqual(price_bs, Decimal('455.00'))

    def test_calculate_price_bs_without_any_exchange_rate_raises_error(self):
        """Debe fallar si no hay tasa de cambio"""
        ExchangeRate.objects.all().delete()

        price_usd = Decimal('10.00')

        with self.assertRaises(ValueError) as context:
            ProductService.calculate_price_bs(price_usd)

        self.assertIn('No hay tasa de cambio configurada', str(context.exception))


class ProductServiceCreateTest(TestCase):
    """Tests para creación de productos"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testadmin',
            email='admin@test.com',
            password='testpass123',
            is_admin=True
        )

        self.exchange_rate = ExchangeRate.objects.create(
            date=timezone.now().date(),
            bs_to_usd=Decimal('45.50'),
            updated_by=self.user
        )

        self.category = Category.objects.create(name='Test Category')

    def test_create_product_success(self):
        """Debe crear producto correctamente"""
        product = ProductService.create_product(
            name='Producto Test',
            barcode='123456789',
            category=self.category,
            purchase_price_usd=Decimal('10.00'),
            selling_price_usd=Decimal('15.00'),
            stock=10,
            min_stock=5
        )

        self.assertIsNotNone(product.pk)
        self.assertEqual(product.name, 'Producto Test')
        self.assertEqual(product.purchase_price_usd, Decimal('10.00'))
        self.assertEqual(product.purchase_price_bs, Decimal('455.00'))  # 10 * 45.50
        self.assertEqual(product.selling_price_usd, Decimal('15.00'))
        self.assertEqual(product.selling_price_bs, Decimal('682.50'))  # 15 * 45.50
        self.assertEqual(product.stock, 10)

    def test_create_product_with_invalid_data_raises_error(self):
        """Datos inválidos deben fallar"""
        with self.assertRaises(ValueError):
            ProductService.create_product(
                name='',  # Nombre vacío
                barcode='123456789',
                category=self.category,
                purchase_price_usd=Decimal('10.00'),
                selling_price_usd=Decimal('15.00')
            )

    def test_create_product_without_exchange_rate_raises_error(self):
        """Debe fallar si no hay tasa de cambio"""
        ExchangeRate.objects.all().delete()

        with self.assertRaises(ValueError) as context:
            ProductService.create_product(
                name='Producto Test',
                barcode='123456789',
                category=self.category,
                purchase_price_usd=Decimal('10.00'),
                selling_price_usd=Decimal('15.00')
            )

        self.assertIn('No hay tasa de cambio', str(context.exception))

    def test_create_product_with_optional_fields(self):
        """Debe crear producto con campos opcionales"""
        product = ProductService.create_product(
            name='Producto Test',
            barcode='123456789',
            category=self.category,
            purchase_price_usd=Decimal('10.00'),
            selling_price_usd=Decimal('15.00'),
            description='Descripción de prueba',
            bulk_price_usd=Decimal('12.00'),
            bulk_min_quantity=10
        )

        self.assertEqual(product.description, 'Descripción de prueba')
        self.assertEqual(product.bulk_price_usd, Decimal('12.00'))
        self.assertEqual(product.bulk_price_bs, Decimal('546.00'))  # 12 * 45.50
        self.assertEqual(product.bulk_min_quantity, 10)


class ProductServiceUpdatePricesTest(TestCase):
    """Tests para actualización de precios"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testadmin',
            email='admin@test.com',
            password='testpass123',
            is_admin=True
        )

        self.exchange_rate = ExchangeRate.objects.create(
            date=timezone.now().date(),
            bs_to_usd=Decimal('45.50'),
            updated_by=self.user
        )

        self.category = Category.objects.create(name='Test Category')

        self.product = Product.objects.create(
            name='Producto Test',
            barcode='123456789',
            category=self.category,
            purchase_price_usd=Decimal('10.00'),
            purchase_price_bs=Decimal('455.00'),
            selling_price_usd=Decimal('15.00'),
            selling_price_bs=Decimal('682.50')
        )

    def test_update_product_prices_with_new_exchange_rate(self):
        """Debe actualizar precios en Bs con nueva tasa"""
        # Crear nueva tasa de cambio
        new_rate = ExchangeRate.objects.create(
            date=timezone.now().date(),
            bs_to_usd=Decimal('50.00'),
            updated_by=self.user
        )

        ProductService.update_product_prices(self.product, new_rate)

        self.product.refresh_from_db()
        self.assertEqual(self.product.purchase_price_bs, Decimal('500.00'))  # 10 * 50
        self.assertEqual(self.product.selling_price_bs, Decimal('750.00'))  # 15 * 50

    def test_update_product_prices_uses_latest_rate_if_none_provided(self):
        """Sin tasa explícita, debe usar la más reciente"""
        # Crear nueva tasa de cambio
        ExchangeRate.objects.create(
            date=timezone.now().date(),
            bs_to_usd=Decimal('50.00'),
            updated_by=self.user
        )

        ProductService.update_product_prices(self.product)

        self.product.refresh_from_db()
        self.assertEqual(self.product.purchase_price_bs, Decimal('500.00'))
        self.assertEqual(self.product.selling_price_bs, Decimal('750.00'))

    def test_bulk_update_prices(self):
        """Debe actualizar precios de múltiples productos"""
        # Crear más productos
        product2 = Product.objects.create(
            name='Producto 2',
            barcode='987654321',
            category=self.category,
            purchase_price_usd=Decimal('20.00'),
            purchase_price_bs=Decimal('910.00'),
            selling_price_usd=Decimal('30.00'),
            selling_price_bs=Decimal('1365.00')
        )

        product3 = Product.objects.create(
            name='Producto 3',
            barcode='555555555',
            category=self.category,
            purchase_price_usd=Decimal('5.00'),
            purchase_price_bs=Decimal('227.50'),
            selling_price_usd=Decimal('8.00'),
            selling_price_bs=Decimal('364.00')
        )

        # Crear nueva tasa
        new_rate = ExchangeRate.objects.create(
            date=timezone.now().date(),
            bs_to_usd=Decimal('50.00'),
            updated_by=self.user
        )

        # Actualizar todos los productos
        queryset = Product.objects.all()
        count = ProductService.bulk_update_prices(queryset, new_rate)

        self.assertEqual(count, 3)

        # Verificar actualizaciones
        self.product.refresh_from_db()
        self.assertEqual(self.product.purchase_price_bs, Decimal('500.00'))

        product2.refresh_from_db()
        self.assertEqual(product2.purchase_price_bs, Decimal('1000.00'))

        product3.refresh_from_db()
        self.assertEqual(product3.purchase_price_bs, Decimal('250.00'))

    def test_bulk_update_prices_with_no_products(self):
        """Bulk update sin productos debe retornar 0"""
        queryset = Product.objects.none()
        count = ProductService.bulk_update_prices(queryset)

        self.assertEqual(count, 0)

    def test_bulk_update_prices_uses_latest_rate_if_none_provided(self):
        """Bulk update sin tasa debe usar la más reciente"""
        # Crear nueva tasa
        ExchangeRate.objects.create(
            date=timezone.now().date(),
            bs_to_usd=Decimal('50.00'),
            updated_by=self.user
        )

        queryset = Product.objects.all()
        count = ProductService.bulk_update_prices(queryset)

        self.assertEqual(count, 1)

        self.product.refresh_from_db()
        self.assertEqual(self.product.purchase_price_bs, Decimal('500.00'))

    def test_update_product_prices_does_not_touch_selling_price_bs_when_fixed(self):
        """update_product_prices no debe tocar selling_price_bs de un producto bs_fixed —
        pero SÍ debe seguir sincronizando purchase_price_bs (compra nunca se congela)"""
        self.product.pricing_mode = Product.PRICING_MODE_BS_FIXED
        self.product.selling_price_bs = Decimal('999.00')
        self.product.save()

        new_rate = ExchangeRate.objects.create(
            date=timezone.now().date() + timedelta(days=1),
            bs_to_usd=Decimal('50.00'),
            updated_by=self.user
        )
        ProductService.update_product_prices(self.product, new_rate)

        self.product.refresh_from_db()
        self.assertEqual(self.product.selling_price_bs, Decimal('999.00'))  # sin tocar
        self.assertEqual(self.product.purchase_price_bs, Decimal('500.00'))  # 10 * 50, sí se actualiza

    def test_bulk_update_prices_excludes_selling_price_of_bs_fixed_products(self):
        """bulk_update_prices no debe tocar el precio de VENTA de productos bs_fixed, pero sí
        el de compra de todos"""
        self.product.pricing_mode = Product.PRICING_MODE_BS_FIXED
        self.product.selling_price_bs = Decimal('999.00')
        self.product.save()

        usd_product = Product.objects.create(
            name='Producto USD normal',
            barcode='USDNORMAL999',
            category=self.category,
            purchase_price_usd=Decimal('20.00'),
            purchase_price_bs=Decimal('910.00'),
            selling_price_usd=Decimal('30.00'),
            selling_price_bs=Decimal('1365.00')
        )

        new_rate = ExchangeRate.objects.create(
            date=timezone.now().date() + timedelta(days=1),
            bs_to_usd=Decimal('50.00'),
            updated_by=self.user
        )
        count = ProductService.bulk_update_prices(Product.objects.all(), new_rate)

        self.assertEqual(count, 2)

        self.product.refresh_from_db()
        self.assertEqual(self.product.selling_price_bs, Decimal('999.00'))  # bs_fixed intacto
        self.assertEqual(self.product.purchase_price_bs, Decimal('500.00'))  # compra sí actualiza

        usd_product.refresh_from_db()
        self.assertEqual(usd_product.selling_price_bs, Decimal('1500.00'))  # 30 * 50, normal


class ProductServiceIntegrationTest(TestCase):
    """Tests de integración completos"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testadmin',
            email='admin@test.com',
            password='testpass123',
            is_admin=True
        )

        self.exchange_rate = ExchangeRate.objects.create(
            date=timezone.now().date(),
            bs_to_usd=Decimal('45.50'),
            updated_by=self.user
        )

        self.category = Category.objects.create(name='Test Category')

    def test_complete_product_lifecycle(self):
        """Test de ciclo completo: crear → actualizar precios"""
        # 1. Crear producto
        product = ProductService.create_product(
            name='Producto Test',
            barcode='123456789',
            category=self.category,
            purchase_price_usd=Decimal('10.00'),
            selling_price_usd=Decimal('15.00'),
            stock=10
        )

        self.assertEqual(product.purchase_price_bs, Decimal('455.00'))

        # 2. Cambiar tasa de cambio
        new_rate = ExchangeRate.objects.create(
            date=timezone.now().date(),
            bs_to_usd=Decimal('50.00'),
            updated_by=self.user
        )

        # 3. Actualizar precios
        ProductService.update_product_prices(product, new_rate)

        product.refresh_from_db()
        self.assertEqual(product.purchase_price_bs, Decimal('500.00'))
        self.assertEqual(product.selling_price_bs, Decimal('750.00'))

        # 4. Verificar que USD no cambió
        self.assertEqual(product.purchase_price_usd, Decimal('10.00'))
        self.assertEqual(product.selling_price_usd, Decimal('15.00'))
