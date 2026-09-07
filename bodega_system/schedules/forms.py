# schedules/forms.py

from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q

from .models import Shift, ShiftAssignment, ScheduleException

User = get_user_model()

INPUT_CLASSES = (
    'shadow-sm focus:ring-blue-500 focus:border-blue-500 block w-full sm:text-sm '
    'border-gray-300 rounded-md'
)


def schedulable_employees():
    """Usuarios que pueden aparecer en la planilla — empleados y administradores activos
    (Leida también puede cubrir un turno puntualmente, no se limita a is_employee)."""
    return User.objects.filter(is_active=True).filter(
        Q(is_employee=True) | Q(is_admin=True)
    ).order_by('first_name', 'username')


class ShiftForm(forms.ModelForm):
    """Editar el horario de un turno fijo (Mañana/Tarde)."""

    class Meta:
        model = Shift
        fields = ['name', 'start_time', 'end_time']
        widgets = {
            'name': forms.TextInput(attrs={'class': INPUT_CLASSES}),
            'start_time': forms.TimeInput(attrs={'class': INPUT_CLASSES, 'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'class': INPUT_CLASSES, 'type': 'time'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get('start_time')
        end = cleaned_data.get('end_time')
        if start and end and end <= start:
            self.add_error('end_time', 'La hora de salida debe ser posterior a la de entrada.')
        return cleaned_data


class ShiftAssignmentForm(forms.ModelForm):
    """
    Asigna un empleado a un turno en una fecha. `date` y `shift` se fijan desde la vista (vienen
    de la URL de la celda de la planilla, no los edita el usuario acá).
    """

    class Meta:
        model = ShiftAssignment
        fields = ['employee']
        widgets = {
            'employee': forms.Select(attrs={'class': INPUT_CLASSES}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['employee'].queryset = schedulable_employees()
        self.fields['employee'].empty_label = '— Sin asignar —'
        self.fields['employee'].required = False


class ScheduleExceptionForm(forms.ModelForm):
    """Registrar un día libre / vacaciones / permiso / enfermedad para un empleado."""

    class Meta:
        model = ScheduleException
        fields = ['employee', 'date_start', 'date_end', 'exception_type', 'reason']
        widgets = {
            'employee': forms.Select(attrs={'class': INPUT_CLASSES}),
            'date_start': forms.DateInput(attrs={'class': INPUT_CLASSES, 'type': 'date'}),
            'date_end': forms.DateInput(attrs={'class': INPUT_CLASSES, 'type': 'date'}),
            'exception_type': forms.Select(attrs={'class': INPUT_CLASSES}),
            'reason': forms.TextInput(attrs={
                'class': INPUT_CLASSES,
                'placeholder': 'Detalle opcional (ej. "cita médica", "viaje familiar")'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['employee'].queryset = schedulable_employees()
        self.fields['reason'].required = False

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get('date_start')
        end = cleaned_data.get('date_end')
        if start and end and end < start:
            self.add_error('date_end', "La fecha 'Hasta' no puede ser anterior a la fecha 'Desde'.")
        return cleaned_data
