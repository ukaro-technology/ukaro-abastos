# inventory/admin.py - ADMIN ACTUALIZADO PARA USD

from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin
from .models import Category, Product, InventoryAdjustment, ProductCombo, ComboItem

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
    search_fields = ('name',)


@admin.register(Product)
class ProductAdmin(SimpleHistoryAdmin):
    """Admin para productos con precios en USD"""
    list_display = (
        'name', 'barcode', 'category', 'unit_type',
        'pricing_mode',  # Precio estable en Bs (spec: docs/specs/precios-estables-bs.md)
        # ⭐ CAMBIO: Mostrar precios USD
        'purchase_price_usd', 'selling_price_usd',
        'get_current_price_bs',  # Mostrar equivalente en Bs
        'stock', 'stock_status', 'is_active'
    )
    list_filter = ('category', 'unit_type', 'is_active', 'is_bulk_pricing', 'pricing_mode')
    search_fields = ('name', 'barcode', 'description')
    readonly_fields = ('created_at', 'updated_at', 'get_current_price_bs', 'get_current_purchase_price_bs')

    fieldsets = (
        ('Información Básica', {
            'fields': ('name', 'barcode', 'category', 'description', 'image', 'unit_type')
        }),
        ('Precios (USD)', {
            'fields': (
                'purchase_price_usd', 'selling_price_usd',
                'get_current_purchase_price_bs', 'get_current_price_bs'
            )
        }),
        ('Precio estable en Bs', {
            'fields': ('pricing_mode', 'selling_price_bs'),
            'description': (
                'Modo "bs_fixed": selling_price_bs manda tal cual, no se recalcula con la '
                'tasa BCV. La validación completa (equivalente USD informativo, exclusión de '
                'precio al mayor) vive en ProductForm — usada por las vistas de la app, no '
                'por este panel de admin.'
            ),
        }),
        ('Inventario', {
            'fields': ('stock', 'min_stock', 'is_active')
        }),
        ('Precios al Mayor (USD)', {
            'fields': ('is_bulk_pricing', 'bulk_min_quantity', 'bulk_price_usd'),
            'classes': ('collapse',)
        }),
        ('Metadatos', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_current_price_bs(self, obj):
        """Mostrar precio actual en Bs"""
        price_bs = obj.get_current_price_bs()
        if price_bs > 0:
            return f"Bs {price_bs:,.2f}"
        return "No disponible"
    get_current_price_bs.short_description = "Precio Venta (Bs)"
    
    def get_current_purchase_price_bs(self, obj):
        """Mostrar precio de compra actual en Bs"""
        price_bs = obj.get_current_purchase_price_bs()
        if price_bs > 0:
            return f"Bs {price_bs:,.2f}"
        return "No disponible"
    get_current_purchase_price_bs.short_description = "Precio Compra (Bs)"


@admin.register(InventoryAdjustment)
class InventoryAdjustmentAdmin(admin.ModelAdmin):
    list_display = ('product', 'adjustment_type', 'quantity', 
                    'previous_stock', 'new_stock', 'adjusted_by', 'adjusted_at')
    list_filter = ('adjustment_type', 'adjusted_by', 'adjusted_at')
    search_fields = ('product__name', 'reason')
    readonly_fields = ('adjusted_at',)


# ADMIN PARA COMBOS (Pendiente de actualizar a USD)

class ComboItemInline(admin.TabularInline):
    model = ComboItem
    extra = 1
    autocomplete_fields = ['product']


@admin.register(ProductCombo)
class ProductComboAdmin(admin.ModelAdmin):
    """Admin para combos - PENDIENTE actualizar a USD"""
    list_display = (
        'name', 'combo_price_bs', 'is_active', 'created_at'
    )
    list_filter = ('is_active', 'created_at')
    search_fields = ('name', 'description')
    inlines = [ComboItemInline]
    readonly_fields = ('created_at',)
    
    fieldsets = (
        ('Información Básica', {
            'fields': ('name', 'description')
        }),
        ('Precios', {
            'fields': ('combo_price_bs',),
            'description': 'PENDIENTE: Actualizar a USD'
        }),
        ('Estado', {
            'fields': ('is_active', 'created_at')
        }),
    )


@admin.register(ComboItem)
class ComboItemAdmin(admin.ModelAdmin):
    list_display = ('combo', 'product', 'quantity')
    list_filter = ('combo',)
    search_fields = ('combo__name', 'product__name')
    autocomplete_fields = ['combo', 'product']