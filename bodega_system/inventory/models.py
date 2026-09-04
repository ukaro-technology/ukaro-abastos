# inventory/models.py - PRODUCTOS CON PRECIOS EN USD

from django.db import models
from django.urls import reverse
from simple_history.models import HistoricalRecords
from decimal import Decimal


class Category(models.Model):
    """Modelo para categorías de productos"""
    name = models.CharField(max_length=100, verbose_name="Nombre")
    description = models.TextField(blank=True, verbose_name="Descripción")

    class Meta:
        verbose_name = "Categoría"
        verbose_name_plural = "Categorías"
        ordering = ['name']

    def __str__(self):
        return self.name


class Product(models.Model):
    """Modelo para productos con precios en USD"""

    UNIT_TYPES = (
        ('unit', 'Unidad'),
        ('kg', 'Kilogramo'),
        ('gram', 'Gramo'),
        ('liter', 'Litro'),
        ('ml', 'Mililitro'),
    )

    # Modo de precio de venta (spec: docs/specs/precios-estables-bs.md)
    PRICING_MODE_USD = 'usd'
    PRICING_MODE_BS_FIXED = 'bs_fixed'
    PRICING_MODE_CHOICES = (
        (PRICING_MODE_USD, 'USD (precio en Bs se calcula con la tasa BCV)'),
        (PRICING_MODE_BS_FIXED, 'Precio estable en Bs (no se recalcula con la tasa)'),
    )

    name = models.CharField(max_length=200, verbose_name="Nombre")
    barcode = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="Código de Barras"
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name='products',
        verbose_name="Categoría"
    )
    description = models.TextField(blank=True, verbose_name="Descripción")
    image = models.ImageField(
        upload_to='products/',
        blank=True,
        null=True,
        verbose_name="Imagen"
    )
    unit_type = models.CharField(
        max_length=10,
        choices=UNIT_TYPES,
        default='unit',
        verbose_name="Tipo de Unidad"
    )

    # ⭐ CAMBIO PRINCIPAL: Precios en USD
    purchase_price_usd = models.DecimalField(
        max_digits=10,
        decimal_places=5,
        verbose_name="Precio de Compra (USD)"
    )
    purchase_price_bs = models.DecimalField(
        max_digits=12,
        decimal_places=5,
        default=0,
        verbose_name="Precio de Compra (Bs)",
        help_text="Se actualiza automáticamente con la tasa de cambio"
    )
    selling_price_usd = models.DecimalField(
        max_digits=10,
        decimal_places=5,
        verbose_name="Precio de Venta (USD)"
    )
    selling_price_bs = models.DecimalField(
        max_digits=12,
        decimal_places=5,
        default=0,
        verbose_name="Precio de Venta (Bs)",
        help_text="Se actualiza automáticamente con la tasa de cambio"
    )

    # Precio estable en Bs (spec: docs/specs/precios-estables-bs.md)
    pricing_mode = models.CharField(
        max_length=10,
        choices=PRICING_MODE_CHOICES,
        default=PRICING_MODE_USD,
        verbose_name="Modo de precio",
        help_text="'usd': el precio en Bs se recalcula con la tasa BCV en cada venta (comportamiento "
                   "por defecto). 'bs_fixed': selling_price_bs es la fuente de verdad, no se toca al "
                   "cambiar la tasa. Solo aplica al precio de VENTA — el de compra siempre sigue en USD."
    )

    # Inventario
    stock = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        default=0,
        verbose_name="Stock"
    )
    min_stock = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        default=5,
        verbose_name="Stock Mínimo"
    )

    # Metadatos
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Creado el")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Actualizado el")
    is_active = models.BooleanField(default=True, verbose_name="Activo")

    # Precios al mayor (en USD también)
    is_bulk_pricing = models.BooleanField(
        default=False,
        verbose_name="Precio al Mayor"
    )
    bulk_min_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Cantidad Mínima al Mayor"
    )
    bulk_price_usd = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Precio al Mayor (USD)"
    )

    # Historial para auditoría
    history = HistoricalRecords()

    class Meta:
        verbose_name = "Producto"
        verbose_name_plural = "Productos"
        ordering = ['name']
        indexes = [
            models.Index(fields=['category', 'is_active'], name='product_cat_active_idx'),
            models.Index(fields=['is_active', '-created_at'], name='product_active_recent_idx'),
            models.Index(fields=['barcode'], name='product_barcode_idx'),  # Ya hay unique=True pero index mejora búsquedas
        ]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('inventory:product_detail', args=[str(self.id)])

    @property
    def stock_status(self):
        """Devuelve el estado del stock"""
        if self.stock <= 0:
            return "Sin stock"
        elif self.stock < self.min_stock:
            return "Stock bajo"
        else:
            return "Stock normal"

    @property
    def profit_margin_usd(self):
        """Calcular margen de ganancia en USD"""
        if self.purchase_price_usd > 0:
            return self.selling_price_usd - self.purchase_price_usd
        return 0

    @property
    def profit_margin_percentage(self):
        """Calcular porcentaje de margen de ganancia"""
        if self.purchase_price_usd > 0:
            return (self.profit_margin_usd / self.purchase_price_usd) * 100
        return 0

    @property
    def unit_display(self):
        """Retorna la unidad para mostrar"""
        return dict(self.UNIT_TYPES)[self.unit_type]

    @property
    def is_weight_based(self):
        """Verifica si el producto se vende por peso o volumen variable"""
        return self.unit_type in ['kg', 'gram', 'liter', 'ml']

    def get_price_usd_for_quantity(self, quantity):
        """Calcula precio USD según cantidad (considera precios al mayor)"""
        if self.is_bulk_pricing and self.bulk_min_quantity and quantity >= self.bulk_min_quantity:
            return self.bulk_price_usd
        return self.selling_price_usd

    def get_price_bs_for_quantity(self, quantity, exchange_rate):
        """Calcula precio en Bs basado en USD y tasa de cambio"""
        price_usd = self.get_price_usd_for_quantity(quantity)
        return price_usd * exchange_rate

    def get_current_price_usd(self, quantity=None, exchange_rate=None):
        """
        Obtiene el precio de venta actual en USD.

        - Modo 'usd' (default): el precio en USD manda — considera precio al mayor si se
          pasa `quantity` (ver `get_price_usd_for_quantity`).
        - Modo 'bs_fixed': el precio en USD es solo informativo (no dirige la venta), se
          calcula al vuelo dividiendo el precio fijo en Bs entre la tasa BCV actual. No
          considera precio al mayor — el modo Bs fijo no tiene un equivalente de precio al
          mayor propio.

        `exchange_rate` (instancia de `ExchangeRate` o None): si se pasa, se usa esa tasa en
        vez de consultar `ExchangeRate.get_latest_rate()` — para no repetir la consulta ítem
        por ítem cuando quien llama (ej. `create_sale_api`) ya la trae de una transacción.
        """
        if self.pricing_mode == self.PRICING_MODE_BS_FIXED:
            if exchange_rate is None:
                from utils.models import ExchangeRate

                exchange_rate = ExchangeRate.get_latest_rate()
            if exchange_rate and exchange_rate.bs_to_usd:
                return self.selling_price_bs / exchange_rate.bs_to_usd
            return Decimal('0.00')

        if quantity is not None:
            return self.get_price_usd_for_quantity(quantity)
        return self.selling_price_usd

    def get_current_price_bs(self, quantity=None, exchange_rate=None):
        """
        Obtiene el precio de venta actual en Bs — fuente única de verdad para todo el
        sistema (punto de venta, reportes, detalle de producto).

        - Modo 'usd' (default): `selling_price_usd` (o el precio al mayor, si `quantity`
          alcanza `bulk_min_quantity`) × tasa BCV actual. Comportamiento sin cambios.
        - Modo 'bs_fixed': devuelve `selling_price_bs` tal cual, sin tocar la tasa ni la
          cantidad — es un precio fijo por decisión explícita del administrador.

        `exchange_rate`: ver `get_current_price_usd` — misma idea, evita re-consultar la
        tasa más reciente si quien llama ya la tiene.
        """
        if self.pricing_mode == self.PRICING_MODE_BS_FIXED:
            return self.selling_price_bs

        if exchange_rate is None:
            from utils.models import ExchangeRate

            exchange_rate = ExchangeRate.get_latest_rate()
        if not exchange_rate:
            return Decimal('0.00')

        price_usd = self.get_price_usd_for_quantity(quantity) if quantity is not None else self.selling_price_usd
        return price_usd * exchange_rate.bs_to_usd

    def get_current_purchase_price_bs(self):
        """Obtiene precio de compra actual en Bs"""
        from utils.models import ExchangeRate

        latest_rate = ExchangeRate.get_latest_rate()
        if latest_rate:
            return self.purchase_price_usd * latest_rate.bs_to_usd
        return Decimal('0.00')


class InventoryAdjustment(models.Model):
    """Ajuste de inventario"""
    ADJUSTMENT_TYPES = (
        ('add', 'Agregar'),
        ('remove', 'Eliminar'),
        ('set', 'Establecer')
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='adjustments',
        verbose_name="Producto"
    )
    adjustment_type = models.CharField(
        max_length=10,
        choices=ADJUSTMENT_TYPES,
        verbose_name="Tipo de Ajuste"
    )
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Cantidad"
    )
    previous_stock = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Stock Previo"
    )
    new_stock = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        verbose_name="Nuevo Stock"
    )
    reason = models.TextField(verbose_name="Razón")
    adjusted_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        related_name='inventory_adjustments',
        verbose_name="Ajustado por"
    )
    adjusted_at = models.DateTimeField(auto_now_add=True, verbose_name="Ajustado el")

    class Meta:
        verbose_name = "Ajuste de Inventario"
        verbose_name_plural = "Ajustes de Inventario"
        ordering = ['-adjusted_at']

    def __str__(self):
        return f"{self.get_adjustment_type_display()} - {self.product.name} - {self.quantity}"


class ProductCombo(models.Model):
    """Modelo para combos de productos - PENDIENTE PARA DESPUÉS"""
    name = models.CharField(
        max_length=200,
        verbose_name="Nombre del Combo"
    )
    description = models.TextField(
        blank=True,
        verbose_name="Descripción"
    )
    # TODO: Cambiar a USD después
    combo_price_bs = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Precio del Combo (Bs)"
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Activo"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Creado el")

    class Meta:
        verbose_name = "Combo de Productos"
        verbose_name_plural = "Combos de Productos"
        ordering = ['name']

    def __str__(self):
        return self.name


class ComboItem(models.Model):
    """Ítems que componen un combo - PENDIENTE PARA DESPUÉS"""
    combo = models.ForeignKey(
        ProductCombo,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name="Combo"
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        verbose_name="Producto"
    )
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        verbose_name="Cantidad"
    )

    class Meta:
        verbose_name = "Ítem de Combo"
        verbose_name_plural = "Ítems de Combo"
        unique_together = ['combo', 'product']

    def __str__(self):
        return f"{self.combo.name} - {self.product.name} ({self.quantity})"


class InventoryCount(models.Model):
    """Cabecera de una auditoría de conteo físico de la bodega.

    Queda como registro permanente (no es un formulario de un solo uso) para
    poder revisar auditorías pasadas. Ver docs/specs/auditoria-inventario.md.
    """
    STATUS_CHOICES = (
        ('in_progress', 'En Progreso'),
        ('completed', 'Completado'),
    )

    date = models.DateTimeField(auto_now_add=True, verbose_name="Fecha")
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='inventory_counts',
        verbose_name="Categoría",
        help_text="Vacío si el conteo fue de todas las categorías"
    )
    counted_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        related_name='inventory_counts',
        verbose_name="Realizado por"
    )
    status = models.CharField(
        max_length=15,
        choices=STATUS_CHOICES,
        default='completed',
        verbose_name="Estado"
    )
    notes = models.TextField(blank=True, verbose_name="Notas")
    corrections_applied_at = models.DateTimeField(
        null=True, blank=True, verbose_name="Correcciones Aplicadas El",
        help_text="Si tiene valor, ya se generaron los InventoryAdjustment de este conteo — no volver a aplicar"
    )
    corrections_applied_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='inventory_count_corrections',
        verbose_name="Correcciones Aplicadas Por"
    )

    class Meta:
        verbose_name = "Conteo de Inventario"
        verbose_name_plural = "Conteos de Inventario"
        ordering = ['-date']

    def __str__(self):
        categoria = self.category.name if self.category else "Todas las categorías"
        return f"Conteo del {self.date.strftime('%d/%m/%Y')} - {categoria}"

    @property
    def items_with_difference(self):
        return self.items.exclude(difference=0)

    @property
    def total_difference_value_usd(self):
        return sum(
            (item.difference_value_usd for item in self.items_with_difference),
            Decimal('0.00')
        )

    @property
    def is_corrected(self):
        return self.corrections_applied_at is not None


class InventoryCountItem(models.Model):
    """Línea de un InventoryCount: stock del sistema (snapshot) vs físico contado.

    system_stock se guarda al momento del conteo y NO se recalcula después,
    para que el reporte de una auditoría vieja no cambie si el stock del
    sistema se sigue moviendo (ver spec, Decisions Already Made).
    """
    count = models.ForeignKey(
        InventoryCount,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name="Conteo"
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name='count_items',
        verbose_name="Producto"
    )
    system_stock = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        verbose_name="Stock del Sistema",
        help_text="Snapshot de Product.stock al momento del conteo"
    )
    physical_stock = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        verbose_name="Stock Físico Contado"
    )
    difference = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        verbose_name="Diferencia",
        help_text="physical_stock - system_stock; negativo = falta stock"
    )

    class Meta:
        verbose_name = "Ítem de Conteo"
        verbose_name_plural = "Ítems de Conteo"
        unique_together = ['count', 'product']
        ordering = ['product__name']

    def save(self, *args, **kwargs):
        self.difference = self.physical_stock - self.system_stock
        super().save(*args, **kwargs)

    @property
    def difference_value_usd(self):
        return self.difference * self.product.purchase_price_usd

    def __str__(self):
        return f"{self.product.name} - sistema: {self.system_stock} / físico: {self.physical_stock}"