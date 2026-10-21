from django import forms

from .models import MotoBrand, MotoModel, PartInfo

INPUT_CLASS = (
    'w-full px-4 py-3 text-base border-2 border-gray-300 rounded-lg focus:ring-2 '
    'focus:ring-blue-500 focus:border-blue-500 bg-white text-gray-900'
)


class PartInfoForm(forms.ModelForm):
    """Datos de repuesto que se editan junto con el producto (prefijo 'part')."""

    class Meta:
        model = PartInfo
        fields = ['part_number', 'part_brand', 'quality', 'location', 'is_universal', 'compatible_models']
        widgets = {
            'part_number': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Ej.: 43105-KWB-901'}),
            'part_brand': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Ej.: NGK, Genérica'}),
            'quality': forms.Select(attrs={'class': INPUT_CLASS}),
            'location': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Ej.: Estante 3, gaveta B'}),
            'is_universal': forms.CheckboxInput(attrs={'class': 'h-5 w-5 text-blue-600 border-gray-300 rounded'}),
            'compatible_models': forms.CheckboxSelectMultiple(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['compatible_models'].queryset = MotoModel.objects.select_related('brand')

    def models_by_brand(self):
        """Modelos agrupados por marca para pintar las casillas en la plantilla."""
        selected = set()
        if self.is_bound:
            selected = {str(v) for v in self.data.getlist(self.add_prefix('compatible_models'))}
        elif self.instance.pk:
            selected = {str(pk) for pk in self.instance.compatible_models.values_list('pk', flat=True)}
        groups = []
        for brand in MotoBrand.objects.prefetch_related('models'):
            models = [(m, str(m.pk) in selected) for m in brand.models.all()]
            if models:
                groups.append((brand, models))
        return groups


class MotoBrandForm(forms.ModelForm):
    class Meta:
        model = MotoBrand
        fields = ['name']
        widgets = {'name': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Ej.: Bera'})}


class MotoModelForm(forms.ModelForm):
    class Meta:
        model = MotoModel
        fields = ['brand', 'name', 'displacement_cc']
        widgets = {
            'brand': forms.Select(attrs={'class': INPUT_CLASS}),
            'name': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Ej.: SBR 150'}),
            'displacement_cc': forms.NumberInput(attrs={'class': INPUT_CLASS, 'placeholder': '150'}),
        }
