# schedules/views.py

from datetime import date, datetime, timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.http import HttpResponseBadRequest
from django.shortcuts import render, redirect, get_object_or_404

from utils.decorators import admin_required, employee_or_admin_required

from .forms import ShiftForm, ScheduleExceptionForm, schedulable_employees
from .models import Shift, ShiftAssignment, ScheduleException

User = get_user_model()


def _monday_of(a_date):
    return a_date - timedelta(days=a_date.weekday())


def _week_from_request(request):
    """Lee ?week=YYYY-MM-DD y devuelve el lunes de esa semana. Si falta o es inválido, usa la
    semana actual — nunca revienta por un parámetro raro en la URL."""
    raw = request.GET.get('week')
    if raw:
        try:
            return _monday_of(datetime.strptime(raw, '%Y-%m-%d').date())
        except ValueError:
            pass
    return _monday_of(date.today())


def _is_admin_user(user):
    return user.is_admin or user.is_superuser


@employee_or_admin_required
def week_view(request):
    """
    Planilla semanal de turnos. Editable para admin (celdas con selector, vía HTMX), de solo
    lectura para empleado — misma vista, misma plantilla, cambia lo que se puede tocar.
    """
    monday = _week_from_request(request)
    days = [monday + timedelta(days=i) for i in range(7)]
    shifts = list(Shift.objects.all())

    assignments = ShiftAssignment.objects.filter(
        date__range=(days[0], days[-1])
    ).select_related('shift', 'employee')
    assignment_map = {(a.date, a.shift_id): a for a in assignments}

    rows = []
    for day in days:
        rows.append({
            'date': day,
            'cells': [
                {'shift': shift, 'assignment': assignment_map.get((day, shift.id))}
                for shift in shifts
            ],
        })

    is_admin_user = _is_admin_user(request.user)

    exceptions = ScheduleException.objects.filter(
        date_end__gte=date.today()
    ).select_related('employee').order_by('date_start')
    if not is_admin_user:
        exceptions = exceptions.filter(employee=request.user)

    return render(request, 'schedules/week_view.html', {
        'monday': monday,
        'sunday': days[-1],
        'prev_week': monday - timedelta(days=7),
        'next_week': monday + timedelta(days=7),
        'current_week': _monday_of(date.today()),
        'today': date.today(),
        'rows': rows,
        'shifts': shifts,
        'employees': schedulable_employees() if is_admin_user else None,
        'is_admin_user': is_admin_user,
        'upcoming_exceptions': exceptions[:20],
    })


@admin_required
def assignment_update(request, date_str, shift_id):
    """
    Endpoint HTMX: asigna (o quita) un empleado de un turno en una fecha puntual. Devuelve solo
    el partial de la celda actualizada — la planilla no recarga completa (spec, tarea 7).
    """
    if request.method != 'POST':
        return HttpResponseBadRequest("Método no permitido")

    try:
        day = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return HttpResponseBadRequest("Fecha inválida")

    shift = get_object_or_404(Shift, pk=shift_id)
    employee_id = request.POST.get('employee') or None
    assignment = ShiftAssignment.objects.filter(date=day, shift=shift).first()
    error = None

    if not employee_id:
        # "— Sin asignar —" elegido: si había alguien asignado, se libera la celda.
        if assignment:
            assignment.delete()
            assignment = None
    else:
        employee = get_object_or_404(schedulable_employees(), pk=employee_id)
        target = assignment or ShiftAssignment(date=day, shift=shift)
        target.employee = employee
        try:
            target.full_clean()
            target.save()
            assignment = target
        except ValidationError as e:
            error = ' '.join(e.messages)
            # No se guardó nada — la celda vuelve a mostrar lo que ya había en la BD.
            assignment = ShiftAssignment.objects.filter(date=day, shift=shift).first()

    return render(request, 'schedules/partials/_shift_cell.html', {
        'shift': shift,
        'date': day,
        'assignment': assignment,
        'error': error,
        'employees': schedulable_employees(),
    })


@admin_required
def shift_list(request):
    """Editar el horario de los turnos fijos (Mañana/Tarde)."""
    shifts = Shift.objects.all()
    return render(request, 'schedules/shift_list.html', {'shifts': shifts})


@admin_required
def shift_update(request, pk):
    """Editar horario de un turno puntual."""
    shift = get_object_or_404(Shift, pk=pk)
    if request.method == 'POST':
        form = ShiftForm(request.POST, instance=shift)
        if form.is_valid():
            form.save()
            messages.success(request, f'Horario de "{shift.name}" actualizado.')
            return redirect('schedules:shift_list')
    else:
        form = ShiftForm(instance=shift)

    return render(request, 'schedules/shift_form.html', {'form': form, 'shift': shift})


@employee_or_admin_required
def exception_list(request):
    """Lista de excepciones (días libres). Admin ve todas; empleado solo las suyas."""
    exceptions = ScheduleException.objects.select_related('employee', 'created_by')
    is_admin_user = _is_admin_user(request.user)
    if not is_admin_user:
        exceptions = exceptions.filter(employee=request.user)

    return render(request, 'schedules/exception_list.html', {
        'exceptions': exceptions,
        'is_admin_user': is_admin_user,
    })


@admin_required
def exception_create(request):
    """Registrar un día libre/vacaciones/permiso/enfermedad para un empleado."""
    if request.method == 'POST':
        form = ScheduleExceptionForm(request.POST)
        if form.is_valid():
            exception = form.save(commit=False)
            exception.created_by = request.user
            exception.save()

            # No bloquea la creación, pero avisa si ese empleado ya tenía turnos asignados en
            # ese rango — para que Leida sepa que hay que reasignar esos turnos a otra persona.
            conflicting = ShiftAssignment.objects.filter(
                employee=exception.employee,
                date__range=(exception.date_start, exception.date_end),
            ).select_related('shift')
            if conflicting.exists():
                dias = ', '.join(
                    f"{a.date.strftime('%d/%m')} ({a.shift.name})" for a in conflicting
                )
                messages.warning(
                    request,
                    f'{exception.employee} ya tenía turnos asignados en este rango: {dias}. '
                    f'Revisá la planilla y reasigná esos turnos a otra persona.'
                )

            messages.success(request, 'Excepción registrada correctamente.')
            return redirect('schedules:exception_list')
    else:
        form = ScheduleExceptionForm()

    return render(request, 'schedules/exception_form.html', {'form': form})


@admin_required
def exception_delete(request, pk):
    """Eliminar una excepción — vía HTMX (hx-delete) desde la fila de la lista."""
    exception = get_object_or_404(ScheduleException, pk=pk)
    if request.method == 'DELETE':
        exception.delete()
        if request.htmx:
            return render(request, 'schedules/partials/_deleted_row.html')
        return redirect('schedules:exception_list')
    return HttpResponseBadRequest("Método no permitido")
