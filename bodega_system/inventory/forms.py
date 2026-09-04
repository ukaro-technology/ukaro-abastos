# inventory/forms.py - FORMULARIO DE PRODUCTOS EN USD

from django import forms
from django.forms import inlineformset_factory
from django.db import transaction
from decimal import Decimal, InvalidOperation

from .models import Category, Product, InventoryAdjustment, ProductCombo, ComboItem


class ProductForm(forms.ModelForm):
    """Formulario para productos con precios en USD"""

    class Meta:
        model = Product
        fields = [
            'name', 'barcode', 'category', 'unit_type', 'description', 'image',
            # Modo de precio primero: los clean_* de los campos de precio lo leen desde
            # self.data (no dependen del orden), pero mantenerlo primero ayuda a leer el form.
            'pricing_mode',
            # ⭐ CAMBIO: Solo campos USD
            'purchase_price_usd', 'selling_price_usd',
            # Precio estable en Bs (spec: docs/specs/precios-estables-bs.md) — solo editable
            # cuando pricing_mode='bs_fixed', validado en clean(). purchase_price_bs no tiene
            # widget propio (nunca se edita a mano) pero se incluye para que clean() pueda
            # refrescarlo con la tasa actual — sin esto, Django ignora la asignación.
            'selling_price_bs', 'purchase_price_bs',
            'min_stock', 'is_active',
            # Precios al mayor en USD (pendiente de implementar)
            'is_bulk_pricing', 'bulk_min_quantity', 'bulk_price_usd'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'shadow-sm focus:ring-blue-500 focus:border-blue-500 block w-full sm:text-sm border-gray-300 rounded-md',
                'placeholder': 'Nombre del producto'
            }),
            'barcode': forms.TextInput(attrs={
                'class': 'shadow-sm focus:ring-blue-500 focus:border-blue-500 block w-full sm:text-sm border-gray-300 rounded-md',
                'placeholder': 'Código de barras'
            }),
            'category': forms.Select(attrs={
                'class': 'shadow-sm focus:ring-blue-500 focus:border-blue-500 block w-full sm:text-sm border-gray-300 rounded-md'
            }),
            'unit_type': forms.Select(attrs={
                'class': 'shadow-sm focus:ring-blue-500 focus:border-blue-500 block w-full sm:text-sm border-gray-300 rounded-md'
            }),
            'description': forms.Textarea(attrs={
                'class': 'shadow-sm focus:ring-blue-500 focus:border-blue-500 block w-full sm:text-sm border-gray-300 rounded-md',
                'rows': 3,
                'placeholder': 'Descripción del producto...'
            }),
            'image': forms.ClearableFileInput(attrs={
                'class': 'shadow-sm focus:ring-blue-500 focus:border-blue-500 block w-full sm:text-sm border-gray-300 rounded-md'
            }),
            # ⭐ PRECIOS EN USD
            'purchase_price_usd': forms.NumberInput(attrs={
                'class': 'shadow-sm focus:ring-blue-500 focus:border-blue-500 block w-full sm:text-sm border-gray-300 rounded-md',
                'step': '0.001',
                'min': '0',
                'placeholder': '0.00'
            }),
            'selling_price_usd': forms.NumberInput(attrs={
                'class': 'shadow-sm focus:ring-blue-500 focus:border-blue-500 block w-full sm:text-sm border-gray-300 rounded-md',
                'step': '0.001',
                'min': '0',
                'placeholder': '0.00'
            }),
            'pricing_mode': forms.Select(attrs={
                'class': 'shadow-sm focus:ring-blue-500 focus:border-blue-500 block w-full sm:text-sm border-gray-300 rounded-md'
            }),
            # purchase_price_bs no se edita a mano — se recalcula siempre en clean(), no
            # aparece en el template.
            'purchase_price_bs': forms.HiddenInput(),
            'selling_price_bs': forms.NumberInput(attrs={
                'class': 'shadow-sm focus:ring-blue-500 focus:border-blue-500 block w-full sm:text-sm border-gray-300 rounded-md',
                'step': '0.01',
                'min': '0',
                'placeholder': '0.00'
            }),
            'min_stock': forms.NumberInput(attrs={
                'class': 'shadow-sm focus:ring-blue-500 focus:border-blue-500 block w-full sm:text-sm border-gray-300 rounded-md',
                'step': '0.001',
                'min': '0',
                'placeholder': '5.000'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded'
            }),
            'is_bulk_pricing': forms.CheckboxInput(attrs={
                'class': 'h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded'
            }),
            'bulk_min_quantity': forms.NumberInput(attrs={
                'class': 'shadow-sm focus:ring-blue-500 focus:border-blue-500 block w-full sm:text-sm border-gray-300 rounded-md',
                'step': '0.001',
                'min': '0',
                'placeholder': '0.000'
            }),
            'bulk_price_usd': forms.NumberInput(attrs={
                'class': 'shadow-sm focus:ring-blue-500 focus:border-blue-500 block w-full sm:text-sm border-gray-300 rounded-md',
                'step': '0.01',
                'min': '0',
                'placeholder': '0.00'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Personalizar labels
        self.fields['purchase_price_usd'].label = 'Precio de Compra (USD)'
        self.fields['selling_price_usd'].label = 'Precio de Venta (USD)'
        self.fields['bulk_price_usd'].label = 'Precio al Mayor (USD)'
        self.fields['pricing_mode'].label = 'Modo de precio de venta'
        self.fields['selling_price_bs'].label = 'Precio de Venta Fijo (Bs)'

        # Help text
        self.fields['purchase_price_usd'].help_text = 'Precio de compra en dólares estadounidenses'
        self.fields['selling_price_usd'].help_text = 'Precio de venta en dólares estadounidenses'
        self.fields['selling_price_bs'].help_text = (
            'Precio de venta en bolívares que el sistema usa tal cual, sin recalcular con la '
            'tasa BCV, hasta que lo cambies a mano.'
        )

        # Hacer algunos campos requeridos
        self.fields['category'].required = True
        self.fields['purchase_price_usd'].required = True
        # ⭐ Precio estable en Bs: selling_price_usd pasa a ser de solo referencia (se
        # recalcula en clean()) y selling_price_bs pasa a ser el campo mandante — ninguno de
        # los dos es "siempre requerido" a nivel de campo, la exigencia real depende del modo
        # y se valida en clean().
        self.fields['selling_price_usd'].required = False
        self.fields['selling_price_bs'].required = False
        # purchase_price_bs: nunca se edita a mano (HiddenInput sin render en el template),
        # siempre se recalcula en clean() a partir de purchase_price_usd × tasa actual.
        self.fields['purchase_price_bs'].required = False

    def clean_purchase_price_usd(self):
        """Validar precio de compra"""
        price = self.cleaned_data.get('purchase_price_usd')

        if price is None:
            raise forms.ValidationError("El precio de compra es requerido.")

        if price <= 0:
            raise forms.ValidationError("El precio de compra debe ser mayor que cero.")

        return price

    def clean_selling_price_usd(self):
        """
        Validar precio de venta en USD.

        En modo 'bs_fixed' este campo deja de ser la fuente de verdad (se recalcula en
        clean() como referencia informativa a partir del precio Bs fijo), así que acá no se
        exige — se usa `self.data` en vez de `cleaned_data` porque el orden de limpieza de
        campos no está garantizado.
        """
        price = self.cleaned_data.get('selling_price_usd')
        pricing_mode = self.data.get('pricing_mode', Product.PRICING_MODE_USD)

        if pricing_mode == Product.PRICING_MODE_BS_FIXED:
            return price

        if price is None:
            raise forms.ValidationError("El precio de venta es requerido.")

        if price <= 0:
            raise forms.ValidationError("El precio de venta debe ser mayor que cero.")

        return price

    def clean(self):
        """Validaciones adicionales"""
        cleaned_data = super().clean()
        purchase_price = cleaned_data.get('purchase_price_usd')
        selling_price = cleaned_data.get('selling_price_usd')
        bulk_price = cleaned_data.get('bulk_price_usd')
        is_bulk_pricing = cleaned_data.get('is_bulk_pricing')
        bulk_min_quantity = cleaned_data.get('bulk_min_quantity')
        pricing_mode = cleaned_data.get('pricing_mode') or Product.PRICING_MODE_USD
        selling_price_bs = cleaned_data.get('selling_price_bs')

        from utils.models import ExchangeRate
        latest_rate = ExchangeRate.get_latest_rate()

        # El precio de COMPRA nunca se congela, sin importar el modo (decisión 7.2 de la
        # spec) — se refresca con la tasa actual en cada guardado, igual que siempre.
        if latest_rate and purchase_price:
            cleaned_data['purchase_price_bs'] = purchase_price * latest_rate.bs_to_usd

        if pricing_mode == Product.PRICING_MODE_BS_FIXED:
            # Precio estable en Bs: selling_price_bs manda, selling_price_usd se recalcula
            # como referencia informativa (spec: docs/specs/precios-estables-bs.md sección 3).
            if not selling_price_bs or selling_price_bs <= 0:
                self.add_error('selling_price_bs',
                    'El precio fijo en Bs es requerido y debe ser mayor que cero cuando el '
                    'modo de precio es "Precio estable en Bs".')
            else:
                if latest_rate and latest_rate.bs_to_usd:
                    selling_price = (selling_price_bs / latest_rate.bs_to_usd).quantize(Decimal('0.00001'))
                else:
                    # No hay tasa configurada: no se puede calcular el equivalente informativo.
                    # Se conserva el USD que ya tuviera el producto (o un mínimo simbólico para
                    # productos nuevos) — el campo no dirige la venta en este modo de todas formas.
                    selling_price = self.instance.selling_price_usd or Decimal('0.00001')
                cleaned_data['selling_price_usd'] = selling_price

            # El precio al mayor no tiene equivalente en modo Bs fijo — evita que quede
            # activado sin efecto real y confunda a quien lo revise después.
            if is_bulk_pricing:
                self.add_error('is_bulk_pricing',
                    'El precio al mayor no está disponible para productos con precio estable '
                    'en Bs (no tiene un precio al mayor fijo equivalente).')
        else:
            # Validar que precio de venta sea mayor que precio de compra (comportamiento actual)
            if purchase_price and selling_price:
                if selling_price <= purchase_price:
                    self.add_error('selling_price_usd',
                        'El precio de venta debe ser mayor que el precio de compra.')

            # Modo 'usd': selling_price_bs no se edita a mano (no está en la UI), pero se
            # refresca con la tasa actual en cada guardado para que la columna vestigial no
            # quede más desactualizada de lo necesario (el reporte de valorización ya no
            # depende de esto — calcula en vivo — pero otros lectores del campo crudo, como
            # el admin de Django, sí). Ver docs/specs/precios-estables-bs.md sección 7.3.
            if latest_rate and selling_price:
                cleaned_data['selling_price_bs'] = selling_price * latest_rate.bs_to_usd

            # Validar precios al mayor (no aplica en modo Bs fijo — ya se marcó como error
            # arriba si is_bulk_pricing estaba activo, no hace falta validar sus sub-campos).
            if is_bulk_pricing:
                if not bulk_min_quantity or bulk_min_quantity <= 0:
                    self.add_error('bulk_min_quantity',
                        'La cantidad mínima es requerida para precios al mayor.')

                if not bulk_price or bulk_price <= 0:
                    self.add_error('bulk_price_usd',
                        'El precio al mayor es requerido.')

                if selling_price and bulk_price and bulk_price >= selling_price:
                    self.add_error('bulk_price_usd',
                        'El precio al mayor debe ser menor que el precio regular.')

        return cleaned_data


class CategoryForm(forms.ModelForm):
    """Formulario para categorías"""

    class Meta:
        model = Category
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'shadow-sm focus:ring-blue-500 focus:border-blue-500 block w-full sm:text-sm border-gray-300 rounded-md'
            }),
            'description': forms.Textarea(attrs={
                'class': 'shadow-sm focus:ring-blue-500 focus:border-blue-500 block w-full sm:text-sm border-gray-300 rounded-md',
                'rows': 3
            }),
        }


class InventoryAdjustmentForm(forms.ModelForm):
    """Formulario para ajustes de inventario"""

    class Meta:
        model = InventoryAdjustment
        fields = ['product', 'adjustment_type', 'quantity', 'reason']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select'}),
            'adjustment_type': forms.Select(attrs={'class': 'form-select'}),
            'quantity': forms.NumberInput(attrs={
                'class': 'form-input',
                'step': '0.001',
                'min': '0.001'
            }),
            'reason': forms.Textarea(attrs={'class': 'form-input', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        # Filtrar solo productos activos
        self.fields['product'].queryset = Product.objects.filter(is_active=True)

    def clean_quantity(self):
        """Validar cantidad"""
        quantity = self.cleaned_data.get('quantity')
        adjustment_type = self.cleaned_data.get('adjustment_type')
        product = self.cleaned_data.get('product')

        if quantity <= 0:
            raise forms.ValidationError("La cantidad debe ser mayor que cero.")

        # Validar que no se quite más stock del disponible
        if adjustment_type == 'remove' and product:
            if quantity > product.stock:
                raise forms.ValidationError(
                    f"No se puede quitar más stock del disponible. "
                    f"Stock actual: {product.stock}"
                )

        return quantity

    def save(self, commit=True):
        adjustment = super().save(commit=False)
        adjustment.adjusted_by = self.user

        # Calcular nuevo stock
        product = adjustment.product
        adjustment.previous_stock = product.stock

        if adjustment.adjustment_type == 'add':
            new_stock = product.stock + adjustment.quantity
        elif adjustment.adjustment_type == 'remove':
            new_stock = product.stock - adjustment.quantity
        elif adjustment.adjustment_type == 'set':
            new_stock = adjustment.quantity

        adjustment.new_stock = new_stock

        if commit:
            with transaction.atomic():
                # Actualizar stock del producto
                product.stock = new_stock
                product.save()

                # Guardar ajuste
                adjustment.save()

        return adjustment


# FORMULARIOS PARA COMBOS (Pendiente - mantener por compatibilidad)

class ProductComboForm(forms.ModelForm):
    """Formulario para crear combos de productos - PENDIENTE"""

    class Meta:
        model = ProductCombo
        fields = ['name', 'description', 'combo_price_bs', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input'}),
            'description': forms.Textarea(attrs={'class': 'form-input', 'rows': 3}),
            'combo_price_bs': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.01'}),
        }


class ComboItemForm(forms.ModelForm):
    """Formulario para ítems de combo - PENDIENTE"""

    class Meta:
        model = ComboItem
        fields = ['product', 'quantity']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.001', 'min': '0.001'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filtrar solo productos activos
        self.fields['product'].queryset = Product.objects.filter(is_active=True)


# Formset para manejo de ítems de combo
ComboItemFormset = forms.inlineformset_factory(
    ProductCombo,
    ComboItem,
    form=ComboItemForm,
    extra=1,
    can_delete=True,
    min_num=1,
    validate_min=True
)