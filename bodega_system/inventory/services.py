# inventory/services.py - Service Layer para Productos

import logging
from decimal import Decimal
from typing import Optional, Dict, Any
from django.db import transaction

logger = logging.getLogger(__name__)


class ProductService:
    """
    Service Layer para operaciones de productos

    Centraliza la lógica de negocio relacionada con productos para:
    - Crear productos con validaciones consistentes
    - Actualizar precios con tasas de cambio
    - Validar datos de productos
    - Reutilizar lógica en diferentes módulos
    """

    @staticmethod
    def validate_product_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Valida datos de producto antes de crear/actualizar

        Args:
            data: Diccionario con datos del producto

        Returns:
            Dict con datos validados

        Raises:
            ValueError: Si algún dato es inválido
        """
        from inventory.models import Product

        errors = []

        # Validar campos requeridos
        required_fields = ['name', 'barcode', 'category']
        for field in required_fields:
            if not data.get(field):
                errors.append(f"El campo '{field}' es requerido")

        # Validar barcode único
        barcode = data.get('barcode')
        if barcode:
            existing = Product.objects.filter(barcode=barcode)
            if data.get('product_id'):
                existing = existing.exclude(pk=data['product_id'])

            if existing.exists():
                errors.append(f"Ya existe un producto con el código de barras '{barcode}'")

        # Validar precios positivos
        price_fields = ['purchase_price_usd', 'selling_price_usd']
        for field in price_fields:
            if field in data and data[field] is not None:
                try:
                    price = Decimal(str(data[field]))
                    if price <= 0:
                        errors.append(f"El precio '{field}' debe ser mayor a cero")
                except (ValueError, TypeError):
                    errors.append(f"El precio '{field}' debe ser un número válido")

        # Validar que precio de venta > precio de compra (warning, no error)
        if ('purchase_price_usd' in data and 'selling_price_usd' in data and
            data['purchase_price_usd'] and data['selling_price_usd']):
            purchase = Decimal(str(data['purchase_price_usd']))
            selling = Decimal(str(data['selling_price_usd']))
            if selling < purchase:
                logger.warning("Selling price is less than purchase price", extra={
                    'name': data.get('name'),
                    'purchase_price': float(purchase),
                    'selling_price': float(selling),
                })

        # Validar stock y min_stock
        if 'stock' in data and data['stock'] is not None:
            try:
                stock = Decimal(str(data['stock']))
                if stock < 0:
                    errors.append("El stock no puede ser negativo")
            except (ValueError, TypeError):
                errors.append("El stock debe ser un número válido")

        if 'min_stock' in data and data['min_stock'] is not None:
            try:
                min_stock = Decimal(str(data['min_stock']))
                if min_stock < 0:
                    errors.append("El stock mínimo no puede ser negativo")
            except (ValueError, TypeError):
                errors.append("El stock mínimo debe ser un número válido")

        if errors:
            raise ValueError("; ".join(errors))

        return data

    @staticmethod
    def calculate_price_bs(price_usd: Decimal, exchange_rate=None) -> Decimal:
        """
        Calcula precio en Bs a partir de precio en USD

        Args:
            price_usd: Precio en USD
            exchange_rate: Objeto ExchangeRate o None para usar la tasa actual

        Returns:
            Precio en Bs

        Raises:
            ValueError: Si no hay tasa de cambio configurada
        """
        from utils.models import ExchangeRate

        if exchange_rate is None:
            exchange_rate = ExchangeRate.get_latest_rate()
            if not exchange_rate:
                raise ValueError(
                    "No hay tasa de cambio configurada. "
                    "Configure una tasa antes de crear productos."
                )

        return price_usd * exchange_rate.bs_to_usd

    @staticmethod
    @transaction.atomic
    def create_product(
        name: str,
        barcode: str,
        category,
        purchase_price_usd: Decimal,
        selling_price_usd: Decimal,
        unit_type: str = 'unit',
        description: str = '',
        stock: Decimal = Decimal('0'),
        min_stock: Decimal = Decimal('5'),
        is_active: bool = True,
        exchange_rate=None,
        created_by=None
    ):
        """
        Crea un nuevo producto con validaciones y cálculos automáticos

        Args:
            name: Nombre del producto
            barcode: Código de barras único
            category: Instancia de Category
            purchase_price_usd: Precio de compra en USD
            selling_price_usd: Precio de venta en USD
            unit_type: Tipo de unidad ('unit', 'kg', 'liter', 'box', 'pack')
            description: Descripción opcional
            stock: Stock inicial (default: 0)
            min_stock: Stock mínimo (default: 5)
            is_active: Si el producto está activo (default: True)
            exchange_rate: ExchangeRate a usar (default: tasa actual)
            created_by: Usuario que crea el producto (opcional)

        Returns:
            Product: Instancia del producto creado

        Raises:
            ValueError: Si los datos son inválidos o no hay tasa de cambio
        """
        from inventory.models import Product

        # Validar datos
        data = ProductService.validate_product_data({
            'name': name,
            'barcode': barcode,
            'category': category,
            'purchase_price_usd': purchase_price_usd,
            'selling_price_usd': selling_price_usd,
            'stock': stock,
            'min_stock': min_stock,
        })

        # Calcular precios en Bs
        purchase_price_bs = ProductService.calculate_price_bs(purchase_price_usd, exchange_rate)
        selling_price_bs = ProductService.calculate_price_bs(selling_price_usd, exchange_rate)

        # Crear producto
        product = Product.objects.create(
            name=name,
            barcode=barcode,
            category=category,
            unit_type=unit_type,
            description=description,
            purchase_price_usd=purchase_price_usd,
            purchase_price_bs=purchase_price_bs,
            selling_price_usd=selling_price_usd,
            selling_price_bs=selling_price_bs,
            stock=stock,
            min_stock=min_stock,
            is_active=is_active
        )

        logger.info("Product created via service layer", extra={
            'product_id': product.id,
            'product_name': product.name,
            'barcode': product.barcode,
            'category_id': category.id,
            'created_by': created_by.id if created_by else None,
        })

        return product

    @staticmethod
    @transaction.atomic
    def create_product_from_order_form(form, exchange_rate, created_by=None):
        """
        Crea un producto desde un formulario de orden de compra

        Esta es una función de conveniencia que extrae los datos del formulario
        y llama a create_product().

        Args:
            form: Formulario con cleaned_data que contiene campos new_product_*
            exchange_rate: ExchangeRate a usar para conversión
            created_by: Usuario que crea el producto

        Returns:
            Product: Instancia del producto creado

        Raises:
            ValueError: Si los datos son inválidos
        """
        from inventory.models import Product

        try:
            # Extraer datos del formulario
            name = form.cleaned_data['new_product_name']
            barcode = form.cleaned_data['new_product_barcode']
            category = form.cleaned_data['new_product_category']
            selling_price_usd = form.cleaned_data['new_product_selling_price_usd']
            purchase_price_usd = form.cleaned_data['price_usd']
            unit_type = form.cleaned_data.get('new_product_unit_type', 'unit')
            description = form.cleaned_data.get('new_product_description', '')
            min_stock = form.cleaned_data.get('new_product_min_stock', Decimal('5'))

            if not category:
                raise ValueError("Categoría es requerida")

            # Crear producto usando el método principal
            product = ProductService.create_product(
                name=name,
                barcode=barcode,
                category=category,
                purchase_price_usd=purchase_price_usd,
                selling_price_usd=selling_price_usd,
                unit_type=unit_type,
                description=description,
                stock=Decimal('0'),  # Stock inicial en 0, se actualiza al recibir orden
                min_stock=min_stock,
                is_active=True,
                exchange_rate=exchange_rate,
                created_by=created_by
            )

            logger.info("Product created from order form", extra={
                'product_id': product.id,
                'source': 'supplier_order',
            })

            return product

        except Exception as e:
            logger.error("Failed to create product from order form", exc_info=True, extra={
                'form_data': {k: str(v) for k, v in form.cleaned_data.items() if k.startswith('new_product')},
            })
            raise

    @staticmethod
    @transaction.atomic
    def update_product_prices(product, exchange_rate=None):
        """
        Actualiza los precios en Bs de un producto usando la tasa de cambio

        Args:
            product: Instancia de Product
            exchange_rate: ExchangeRate a usar (default: tasa actual)

        Returns:
            Product: Producto actualizado. Si está en modo 'bs_fixed', el precio de VENTA
                no se toca (es fijo por decisión del admin) — pero el de COMPRA sigue
                sincronizándose con la tasa como siempre, porque congelar solo aplica a
                venta (spec: docs/specs/precios-estables-bs.md, sección 7.2).

        Raises:
            ValueError: Si no hay tasa de cambio configurada
        """
        from inventory.models import Product

        if exchange_rate is None:
            from utils.models import ExchangeRate
            exchange_rate = ExchangeRate.get_latest_rate()
            if not exchange_rate:
                raise ValueError("No hay tasa de cambio configurada")

        old_purchase_bs = product.purchase_price_bs
        old_selling_bs = product.selling_price_bs

        product.purchase_price_bs = product.purchase_price_usd * exchange_rate.bs_to_usd
        if product.pricing_mode != Product.PRICING_MODE_BS_FIXED:
            product.selling_price_bs = product.selling_price_usd * exchange_rate.bs_to_usd
        product.save()

        logger.info("Product prices updated", extra={
            'product_id': product.id,
            'old_purchase_bs': float(old_purchase_bs),
            'new_purchase_bs': float(product.purchase_price_bs),
            'old_selling_bs': float(old_selling_bs),
            'new_selling_bs': float(product.selling_price_bs),
            'exchange_rate': float(exchange_rate.bs_to_usd),
        })

        return product

    @staticmethod
    def bulk_update_prices(queryset=None, exchange_rate=None):
        """
        Actualiza los precios en Bs de múltiples productos

        Args:
            queryset: QuerySet de productos (default: todos los productos activos)
            exchange_rate: ExchangeRate a usar (default: tasa actual)

        Returns:
            int: Cantidad de productos actualizados. El precio de VENTA de los productos en
                modo 'bs_fixed' nunca se toca aquí (es fijo por decisión del admin); el de
                COMPRA sí se sincroniza siempre, para todos los productos (spec: sección 7.2).

        Raises:
            ValueError: Si no hay tasa de cambio configurada
        """
        from inventory.models import Product
        from utils.models import ExchangeRate

        if exchange_rate is None:
            exchange_rate = ExchangeRate.get_latest_rate()
            if not exchange_rate:
                raise ValueError("No hay tasa de cambio configurada")

        if queryset is None:
            queryset = Product.objects.filter(is_active=True)

        count = 0
        with transaction.atomic():
            for product in queryset:
                product.purchase_price_bs = product.purchase_price_usd * exchange_rate.bs_to_usd
                if product.pricing_mode != Product.PRICING_MODE_BS_FIXED:
                    product.selling_price_bs = product.selling_price_usd * exchange_rate.bs_to_usd
                product.save()
                count += 1

        logger.info("Bulk product prices updated", extra={
            'count': count,
            'exchange_rate': float(exchange_rate.bs_to_usd),
        })

        return count


class TraceabilityService:
    """
    Service Layer para trazabilidad de stock de un producto.

    Ver docs/specs/auditoria-inventario.md. Combina las 3 fuentes que
    mueven Product.stock en este sistema (ventas, ajustes manuales,
    compras recibidas) en una sola línea de tiempo, con el stock
    reconstruido antes/después de cada evento.
    """

    @staticmethod
    def build_product_events(product, date_from=None, date_to=None):
        """
        Arma la línea de tiempo de eventos que movieron el stock de un producto.

        Reconstruye el stock antes/después de cada evento partiendo del
        stock ACTUAL (product.stock) y deshaciendo cada evento hacia atrás
        en el tiempo — por eso se traen TODOS los eventos históricos del
        producto (no solo los del rango pedido) y luego se filtra el rango
        solo para mostrar, pero el cálculo de stock usa el historial
        completo para ser exacto.

        Asume que ventas, ajustes de inventario y recepción de compras son
        las únicas formas en que el stock de un producto cambia en este
        sistema (no hay otro código que edite Product.stock directamente
        fuera de esos 3 flujos).

        Args:
            product: instancia de Product
            date_from: date o None — límite inferior para MOSTRAR (no para calcular)
            date_to: date o None — límite superior para MOSTRAR (no para calcular)

        Returns:
            list de dicts, ordenados del más reciente al más viejo, cada uno con:
            date, tipo ('venta'|'ajuste'|'compra'), delta, stock_before,
            stock_after, referencia, detalle
        """
        from sales.models import SaleItem
        from suppliers.models import SupplierOrderItem

        eventos = []

        for item in SaleItem.objects.filter(product=product).select_related('sale'):
            eventos.append({
                'date': item.sale.date,
                'tipo': 'venta',
                'delta': -item.quantity,
                'referencia': f'Venta #{item.sale.pk}',
                'detalle': f'Cliente: {item.sale.customer.name if item.sale.customer else "s/d"}',
            })

        for adj in product.adjustments.select_related('adjusted_by'):
            signo = 1 if adj.adjustment_type == 'add' else -1
            delta = adj.new_stock - adj.previous_stock  # exacto, cubre también 'set'
            eventos.append({
                'date': adj.adjusted_at,
                'tipo': 'ajuste',
                'delta': delta,
                'referencia': f'Ajuste #{adj.pk} ({adj.get_adjustment_type_display()})',
                'detalle': adj.reason,
            })

        for item in SupplierOrderItem.objects.filter(
            product=product, order__status='received'
        ).select_related('order', 'order__supplier'):
            eventos.append({
                'date': item.order.received_date or item.order.order_date,
                'tipo': 'compra',
                'delta': item.quantity,
                'referencia': f'Orden #{item.order.pk} ({item.order.supplier.name})',
                'detalle': f'{item.quantity} recibidas',
            })

        eventos.sort(key=lambda e: e['date'], reverse=True)

        stock_actual = product.stock
        for evento in eventos:
            evento['stock_after'] = stock_actual
            evento['stock_before'] = stock_actual - evento['delta']
            stock_actual = evento['stock_before']

        if date_from:
            eventos = [e for e in eventos if e['date'].date() >= date_from]
        if date_to:
            eventos = [e for e in eventos if e['date'].date() <= date_to]

        return eventos
