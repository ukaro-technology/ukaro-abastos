# customers/forms.py

from django import forms
from django.utils import timezone
from datetime import timedelta
from .models import Customer, CustomerCredit, CreditPayment

class CustomerForm(forms.ModelForm):
    """Formulario para clientes"""

    class Meta:
        model = Customer
        fields = [
            'name', 'cedula', 'phone', 'email', 'address',
            'credit_limit_usd', 'notes', 'is_active'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input'}),
            'cedula': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'V-12345678'}),
            'phone': forms.TextInput(attrs={'class': 'form-input'}),
            'email': forms.EmailInput(attrs={'class': 'form-input'}),
            'address': forms.Textarea(attrs={'class': 'form-input', 'rows': 3}),
            'credit_limit_usd': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.01'}),
            'notes': forms.Textarea(attrs={'class': 'form-input', 'rows': 3}),
        }
        labels = {
            'cedula': 'Cédula',
            'credit_limit_usd': 'Límite de Crédito (USD)',
        }
        help_texts = {
            'credit_limit_usd': 'Límite de crédito en dólares. El equivalente en Bs se calcula automáticamente.',
        }

class CreditForm(forms.ModelForm):
    """Formulario para créditos de clientes"""

    class Meta:
        model = CustomerCredit
        fields = ['customer', 'amount_bs', 'date_due', 'notes']
        widgets = {
            'customer': forms.Select(attrs={'class': 'form-select'}),
            'amount_bs': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.01'}),
            'date_due': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'notes': forms.Textarea(attrs={'class': 'form-input', 'rows': 3}),
        }
        labels = {
            'amount_bs': 'Monto (Bs)',
        }
        help_texts = {
            'amount_bs': 'Monto en bolívares. El equivalente en USD se calcula automáticamente.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Establecer fecha de vencimiento por defecto (30 días)
        if not self.instance.pk and not self.initial.get('date_due'):
            self.initial['date_due'] = (timezone.now() + timedelta(days=30)).date()

        # Filtrar solo clientes con crédito disponible (usar USD)
        self.fields['customer'].queryset = Customer.objects.filter(
            is_active=True,
            credit_limit_usd__gt=0
        )

    def clean(self):
        """Validaciones adicionales"""
        cleaned_data = super().clean()
        customer = cleaned_data.get('customer')
        amount_bs = cleaned_data.get('amount_bs')

        if customer and amount_bs:
            # Validar límite de crédito disponible (usar USD)
            if not self.instance.pk:  # Solo para nuevos créditos
                from utils.models import ExchangeRate
                current_rate = ExchangeRate.get_latest_rate()
                if current_rate:
                    amount_usd = amount_bs / current_rate.bs_to_usd
                    available_credit_usd = customer.available_credit
                    if amount_usd > available_credit_usd:
                        self.add_error('amount_bs',
                            f'El monto excede el crédito disponible. '
                            f'Disponible: ${available_credit_usd:.2f} USD '
                            f'(Bs {available_credit_usd * current_rate.bs_to_usd:.2f})')
        
        return cleaned_data

class CreditPaymentForm(forms.ModelForm):
    """Formulario para pagos de créditos"""

    class Meta:
        model = CreditPayment
        fields = ['amount_bs', 'payment_method', 'mobile_reference', 'notes']
        widgets = {
            'amount_bs': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.01'}),
            'payment_method': forms.Select(attrs={'class': 'form-select'}),
            'mobile_reference': forms.TextInput(attrs={'class': 'form-input'}),
            'notes': forms.Textarea(attrs={'class': 'form-input', 'rows': 2}),
        }
    
    def __init__(self, *args, credit=None, **kwargs):
        self.credit = credit
        super().__init__(*args, **kwargs)

        # mobile_reference es opcional por defecto (solo requerido en clean() si payment_method='mobile')
        self.fields['mobile_reference'].required = False

        if credit:
            # ⭐ CORREGIDO: Calcular monto pendiente usando USD como fuente de verdad
            from django.db.models import Sum
            from decimal import Decimal
            from utils.models import ExchangeRate

            # Calcular saldo pendiente en USD (fuente de verdad)
            total_paid_usd = credit.payments.aggregate(total=Sum('amount_usd'))['total'] or Decimal('0.00')
            pending_amount_usd = credit.amount_usd - total_paid_usd

            # ⭐ CORREGIDO: Calcular en Bs usando la TASA ACTUAL (no la tasa original del crédito)
            current_rate = ExchangeRate.get_latest_rate()
            if current_rate:
                # Redondear a 2 decimales para evitar problemas de precisión
                pending_amount_bs = round(pending_amount_usd * current_rate.bs_to_usd, 2)
                rate_value = current_rate.bs_to_usd
            else:
                pending_amount_bs = round(pending_amount_usd * Decimal('36.00'), 2)
                rate_value = Decimal('36.00')

            # ⭐ IMPORTANTE: Redondear a 2 decimales para que coincida con el JavaScript
            self.fields['amount_bs'].initial = pending_amount_bs
            self.fields['amount_bs'].widget.attrs['max'] = float(pending_amount_bs)

            # Help text con información clara
            self.fields['amount_bs'].help_text = (
                f'Pendiente: ${pending_amount_usd:.2f} USD '
                f'(Bs {pending_amount_bs:.2f} a tasa actual {rate_value}). '
                f'Ingrese monto en Bs, se calculará USD automáticamente.'
            )
    
    def clean_amount_bs(self):
        """Validar monto de pago"""
        amount = self.cleaned_data.get('amount_bs')

        if amount <= 0:
            raise forms.ValidationError('El monto debe ser mayor a cero.')

        if self.credit:
            # ⭐ CORREGIDO: Calcular monto pendiente usando USD con Decimal y tolerancia
            from django.db.models import Sum
            from decimal import Decimal

            total_paid_usd = self.credit.payments.aggregate(total=Sum('amount_usd'))['total'] or Decimal('0.00')
            pending_amount_usd = self.credit.amount_usd - total_paid_usd

            # Convertir monto ingresado a USD para validar
            from utils.models import ExchangeRate
            current_rate = ExchangeRate.get_latest_rate()
            if current_rate:
                # Redondear a 2 decimales para comparación precisa
                amount_usd = round(amount / current_rate.bs_to_usd, 2)
                pending_rounded = round(pending_amount_usd, 2)

                # Permitir tolerancia de 1 centavo para evitar errores de precisión
                if amount_usd > pending_rounded + Decimal('0.01'):
                    raise forms.ValidationError(
                        f'El monto excede el saldo pendiente (${pending_rounded:.2f} USD).')

        return amount

    def clean(self):
        """Validar mobile_reference cuando payment_method es 'mobile'"""
        cleaned_data = super().clean()
        payment_method = cleaned_data.get('payment_method')
        mobile_reference = cleaned_data.get('mobile_reference')

        if payment_method == 'mobile' and not mobile_reference:
            self.add_error('mobile_reference',
                          'La referencia es requerida para pagos móviles.')

        return cleaned_data


class CustomerGeneralPaymentForm(forms.Form):
    amount_bs = forms.DecimalField(
        max_digits=12, decimal_places=2, label="Monto a pagar (Bs)",
        widget=forms.NumberInput(attrs={'class': 'form-input', 'step': '0.01'})
    )
    payment_method = forms.ChoiceField(
        choices=CreditPayment.PAYMENT_METHODS, label="Método de Pago",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    mobile_reference = forms.CharField(
        required=False, label="Referencia de Pago Móvil",
        widget=forms.TextInput(attrs={'class': 'form-input'})
    )
    notes = forms.CharField(
        required=False, label="Notas",
        widget=forms.Textarea(attrs={'class': 'form-input', 'rows': 2})
    )

    def __init__(self, *args, customer=None, **kwargs):
        self.customer = customer
        super().__init__(*args, **kwargs)
        if customer:
            from utils.models import ExchangeRate
            from decimal import Decimal
            rate = ExchangeRate.get_latest_rate()
            bs_rate = rate.bs_to_usd if rate else Decimal('36.00')
            total_usd = customer.total_credit_used
            total_bs = round(total_usd * bs_rate, 2)
            self.fields['amount_bs'].initial = total_bs
            self.fields['amount_bs'].widget.attrs['max'] = float(total_bs)
            self.fields['amount_bs'].help_text = (
                f'Deuda total: ${total_usd:.2f} USD (Bs {total_bs:.2f}). '
                f'No puede exceder este monto.'
            )

    def clean_amount_bs(self):
        amount = self.cleaned_data.get('amount_bs')
        if not amount or amount <= 0:
            raise forms.ValidationError('El monto debe ser mayor a cero.')
        if self.customer:
            from utils.models import ExchangeRate
            from decimal import Decimal
            rate = ExchangeRate.get_latest_rate()
            bs_rate = rate.bs_to_usd if rate else Decimal('36.00')
            amount_usd = round(amount / bs_rate, 2)
            total_owed = round(Decimal(str(self.customer.total_credit_used)), 2)
            if amount_usd > total_owed + Decimal('0.01'):
                raise forms.ValidationError(
                    f'El monto excede la deuda total (${total_owed:.2f} USD).')
        return amount

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('payment_method') == 'mobile' and not cleaned_data.get('mobile_reference'):
            self.add_error('mobile_reference', 'La referencia es requerida para pagos móviles.')
        return cleaned_data