# schedules/models.py - Planilla de turnos y días libres de empleados
#
# Spec: docs/specs/horarios-empleados.md
#
# No es un sistema de fichaje: no hay entrada/salida marcada por el empleado, no se calculan
# horas trabajadas, y no restringe el acceso al sistema en un día libre — es un calendario de
# referencia para que Leida sepa quién cubre cada turno y quién tiene días libres.

from django.core.exceptions import ValidationError
from django.db import models
from simple_history.models import HistoricalRecords


class Shift(models.Model):
    """
    Turno fijo (ej. Mañana, Tarde) con su horario. Editable por admin — no hardcodeado en el
    código, para no necesitar un deploy solo para ajustar una hora.
    """
    name = models.CharField(max_length=50, verbose_name="Nombre")
    start_time = models.TimeField(verbose_name="Hora de entrada")
    end_time = models.TimeField(verbose_name="Hora de salida")

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Turno"
        verbose_name_plural = "Turnos"
        ordering = ['start_time']

    def __str__(self):
        return f"{self.name} ({self.start_time.strftime('%I:%M %p')}–{self.end_time.strftime('%I:%M %p')})"


class ShiftAssignment(models.Model):
    """
    Asignación de un empleado a un turno en una fecha puntual — la "planilla" que arma Leida
    día a día o semana a semana. Reemplaza la idea de un horario semanal recurrente porque los
    empleados rotan entre turnos sin un patrón semanal fijo (ver spec, sección 2 y 3).
    """
    date = models.DateField(verbose_name="Fecha")
    shift = models.ForeignKey(
        Shift,
        on_delete=models.PROTECT,
        related_name='assignments',
        verbose_name="Turno"
    )
    employee = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='shift_assignments',
        verbose_name="Empleado"
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Asignación de Turno"
        verbose_name_plural = "Asignaciones de Turno"
        unique_together = [('date', 'shift')]
        ordering = ['date', 'shift']

    def __str__(self):
        return f"{self.date} — {self.shift.name} — {self.employee.username}"

    def clean(self):
        """
        No se puede asignar un turno a un empleado en una fecha donde tiene una excepción
        (día libre/vacaciones/permiso/enfermedad) activa — evita datos contradictorios en la
        planilla (spec, tarea 5).
        """
        if self.employee_id and self.date:
            conflict = ScheduleException.objects.filter(
                employee_id=self.employee_id,
                date_start__lte=self.date,
                date_end__gte=self.date,
            ).exists()
            if conflict:
                raise ValidationError(
                    f"{self.employee} tiene registrada una excepción (día libre) para el "
                    f"{self.date.strftime('%d/%m/%Y')} — no se le puede asignar un turno ese día."
                )


class ScheduleException(models.Model):
    """
    Día(s) libres puntuales: vacaciones, permiso, enfermedad u otro motivo. Cubre siempre día(s)
    completos (sin granularidad de medio día — decisión explícita, ver spec sección 3).
    """
    EXCEPTION_TYPES = (
        ('vacation', 'Vacaciones'),
        ('permission', 'Permiso'),
        ('sick', 'Enfermedad'),
        ('other', 'Otro'),
    )

    employee = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='schedule_exceptions',
        verbose_name="Empleado"
    )
    date_start = models.DateField(verbose_name="Desde")
    date_end = models.DateField(verbose_name="Hasta")
    exception_type = models.CharField(
        max_length=20,
        choices=EXCEPTION_TYPES,
        verbose_name="Tipo"
    )
    reason = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Detalle (opcional)"
    )
    created_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        related_name='created_schedule_exceptions',
        verbose_name="Registrado por"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Registrado el")

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Excepción de Horario"
        verbose_name_plural = "Excepciones de Horario"
        ordering = ['-date_start']

    def __str__(self):
        return (
            f"{self.employee} — {self.get_exception_type_display()} "
            f"({self.date_start.strftime('%d/%m/%Y')} a {self.date_end.strftime('%d/%m/%Y')})"
        )

    def clean(self):
        if self.date_start and self.date_end and self.date_end < self.date_start:
            raise ValidationError("La fecha 'Hasta' no puede ser anterior a la fecha 'Desde'.")

    def covers(self, a_date):
        """True si `a_date` cae dentro del rango de esta excepción."""
        return self.date_start <= a_date <= self.date_end
