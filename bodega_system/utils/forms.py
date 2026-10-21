# utils/forms.py - FORMULARIO PARA TASA DE CAMBIO

from django import forms
from django.utils import timezone
from .models import ExchangeRate, StoreSettings


class ExchangeRateForm(forms.ModelForm):
    """Formulario para actualizar la tasa de cambio"""
    
    class Meta:
        model = ExchangeRate
        fields = ['date', 'bs_to_usd']
        widgets = {
            'date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'w-full px-4 py-3 text-base border-2 border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all duration-200 bg-white text-gray-900',
            }),
            'bs_to_usd': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-3 text-base border-2 border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all duration-200 bg-white text-gray-900',
                'step': '0.01',
                'min': '0.01',
                'placeholder': 'Ej: 154.50'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Establecer fecha de hoy por defecto
        if not self.instance.pk:
            self.fields['date'].initial = timezone.now().date()
        
        # Personalizar labels
        self.fields['date'].label = 'Fecha'
        self.fields['bs_to_usd'].label = 'Tasa de Cambio (Bs por 1 USD)'
        
        # Help text
        self.fields['bs_to_usd'].help_text = 'Ejemplo: Si 1 USD = 154.50 Bs, ingrese 154.50'
    
    def clean_bs_to_usd(self):
        """Validar que la tasa sea positiva y razonable"""
        rate = self.cleaned_data.get('bs_to_usd')
        
        if rate <= 0:
            raise forms.ValidationError("La tasa de cambio debe ser mayor que cero.")
        
        if rate < 1:
            raise forms.ValidationError("La tasa de cambio parece demasiado baja. Verifique el valor.")
        
        if rate > 1000000:
            raise forms.ValidationError("La tasa de cambio parece demasiado alta. Verifique el valor.")
        
        return rate
    
    def clean_date(self):
        """Validar que la fecha no sea futura"""
        date = self.cleaned_data.get('date')
        today = timezone.now().date()
        
        if date > today:
            raise forms.ValidationError("No se puede establecer una tasa de cambio para fechas futuras.")
        
        return date
    
    def clean(self):
        """Validaciones adicionales"""
        cleaned_data = super().clean()
        date = cleaned_data.get('date')

        if date:
            # ⭐ CORREGIDO: Verificar si ya existe una tasa para esta fecha
            # Guardar el registro existente para poder actualizarlo después
            existing_rate = ExchangeRate.objects.filter(date=date).exclude(pk=self.instance.pk if self.instance.pk else None).first()
            if existing_rate:
                # Guardar el ID del registro existente para actualizarlo en lugar de crear uno nuevo
                self._existing_rate_to_update = existing_rate

        return cleaned_data

class StoreSettingsForm(forms.ModelForm):
    """Ajustes del negocio editables por el administrador"""

    class Meta:
        model = StoreSettings
        fields = ['cash_usd_discount_percent']
        widgets = {
            'cash_usd_discount_percent': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-3 text-base border-2 border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
                'step': '0.01',
                'min': '0',
                'max': '90',
            }),
        }

    def clean_cash_usd_discount_percent(self):
        value = self.cleaned_data['cash_usd_discount_percent']
        if value < 0 or value > 90:
            raise forms.ValidationError('El descuento debe estar entre 0% y 90%.')
        return value
