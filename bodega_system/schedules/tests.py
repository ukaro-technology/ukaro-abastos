# schedules/tests.py
"""
Tests para el módulo schedules (planilla de turnos y días libres):
- Shift / ShiftAssignment / ScheduleException (modelos, validaciones)
- Vista de planilla semanal (permisos, navegación de semanas)
- Endpoint HTMX de asignación de turno
- Vista de excepciones (crear, listar, eliminar)
"""

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, Client
from django.urls import reverse

from .models import Shift, ShiftAssignment, ScheduleException

User = get_user_model()


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def make_admin(username='sched_admin'):
    return User.objects.create_user(username=username, password='pass123', is_admin=True)


def make_employee(username='sched_emp'):
    return User.objects.create_user(username=username, password='pass123', is_employee=True)


def make_shift(name='Mañana Test', start='07:00', end='15:00'):
    from datetime import time
    h1, m1 = map(int, start.split(':'))
    h2, m2 = map(int, end.split(':'))
    return Shift.objects.create(name=name, start_time=time(h1, m1), end_time=time(h2, m2))


def monday_of(a_date):
    return a_date - timedelta(days=a_date.weekday())


# ─────────────────────────────────────────────
# SHIFT MODEL TESTS
# ─────────────────────────────────────────────

class ShiftModelTest(TestCase):

    def test_default_shifts_seeded_by_migration(self):
        """La data migration debe haber creado Mañana y Tarde"""
        self.assertTrue(Shift.objects.filter(name='Mañana').exists())
        self.assertTrue(Shift.objects.filter(name='Tarde').exists())

    def test_str_representation(self):
        shift = make_shift(name='Test Turno')
        self.assertIn('Test Turno', str(shift))


# ─────────────────────────────────────────────
# SHIFT ASSIGNMENT MODEL TESTS
# ─────────────────────────────────────────────

class ShiftAssignmentModelTest(TestCase):

    def setUp(self):
        self.admin = make_admin()
        self.employee = make_employee()
        self.shift = make_shift()
        self.today = date.today()

    def test_create_assignment(self):
        assignment = ShiftAssignment.objects.create(
            date=self.today, shift=self.shift, employee=self.employee
        )
        self.assertEqual(assignment.employee, self.employee)

    def test_unique_together_date_shift(self):
        """No puede haber dos asignaciones para el mismo (fecha, turno)"""
        ShiftAssignment.objects.create(date=self.today, shift=self.shift, employee=self.employee)
        other_employee = make_employee(username='sched_emp2')
        with self.assertRaises(Exception):
            ShiftAssignment.objects.create(date=self.today, shift=self.shift, employee=other_employee)

    def test_same_employee_can_have_different_shifts_different_days(self):
        """Un mismo empleado puede tener turnos distintos en días distintos, sin problema"""
        ShiftAssignment.objects.create(date=self.today, shift=self.shift, employee=self.employee)
        other_shift = make_shift(name='Tarde Test', start='13:00', end='21:00')
        assignment2 = ShiftAssignment.objects.create(
            date=self.today + timedelta(days=1), shift=other_shift, employee=self.employee
        )
        self.assertEqual(assignment2.employee, self.employee)

    def test_clean_rejects_assignment_during_exception(self):
        """No se puede asignar un turno a un empleado con excepción activa esa fecha"""
        ScheduleException.objects.create(
            employee=self.employee,
            date_start=self.today,
            date_end=self.today + timedelta(days=3),
            exception_type='vacation',
            created_by=self.admin,
        )
        assignment = ShiftAssignment(date=self.today + timedelta(days=1), shift=self.shift, employee=self.employee)
        with self.assertRaises(ValidationError):
            assignment.clean()

    def test_clean_allows_assignment_outside_exception_range(self):
        """Fuera del rango de la excepción, sí se puede asignar normalmente"""
        ScheduleException.objects.create(
            employee=self.employee,
            date_start=self.today,
            date_end=self.today + timedelta(days=3),
            exception_type='vacation',
            created_by=self.admin,
        )
        assignment = ShiftAssignment(date=self.today + timedelta(days=10), shift=self.shift, employee=self.employee)
        assignment.clean()  # no debe lanzar

    def test_clean_allows_other_employee_during_someones_exception(self):
        """La excepción de un empleado no afecta la asignación de otro"""
        ScheduleException.objects.create(
            employee=self.employee,
            date_start=self.today,
            date_end=self.today + timedelta(days=3),
            exception_type='vacation',
            created_by=self.admin,
        )
        other_employee = make_employee(username='sched_emp3')
        assignment = ShiftAssignment(date=self.today, shift=self.shift, employee=other_employee)
        assignment.clean()  # no debe lanzar


# ─────────────────────────────────────────────
# SCHEDULE EXCEPTION MODEL TESTS
# ─────────────────────────────────────────────

class ScheduleExceptionModelTest(TestCase):

    def setUp(self):
        self.admin = make_admin()
        self.employee = make_employee()

    def test_create_exception(self):
        exception = ScheduleException.objects.create(
            employee=self.employee,
            date_start=date.today(),
            date_end=date.today() + timedelta(days=5),
            exception_type='vacation',
            created_by=self.admin,
        )
        self.assertEqual(exception.exception_type, 'vacation')

    def test_clean_rejects_end_before_start(self):
        exception = ScheduleException(
            employee=self.employee,
            date_start=date.today(),
            date_end=date.today() - timedelta(days=1),
            exception_type='sick',
            created_by=self.admin,
        )
        with self.assertRaises(ValidationError):
            exception.clean()

    def test_covers(self):
        exception = ScheduleException.objects.create(
            employee=self.employee,
            date_start=date.today(),
            date_end=date.today() + timedelta(days=2),
            exception_type='permission',
            created_by=self.admin,
        )
        self.assertTrue(exception.covers(date.today() + timedelta(days=1)))
        self.assertFalse(exception.covers(date.today() + timedelta(days=5)))


# ─────────────────────────────────────────────
# WEEK VIEW TESTS
# ─────────────────────────────────────────────

class WeekViewTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.admin = make_admin()
        self.employee = make_employee()
        self.url = reverse('schedules:week_view')

    def test_unauthenticated_redirects_to_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_admin_can_view(self):
        self.client.login(username='sched_admin', password='pass123')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['is_admin_user'])

    def test_employee_can_view_read_only(self):
        self.client.login(username='sched_emp', password='pass123')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['is_admin_user'])

    def test_week_navigation_param(self):
        self.client.login(username='sched_admin', password='pass123')
        target_monday = monday_of(date.today()) + timedelta(days=7)
        response = self.client.get(self.url, {'week': target_monday.strftime('%Y-%m-%d')})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['monday'], target_monday)

    def test_invalid_week_param_falls_back_to_current_week(self):
        self.client.login(username='sched_admin', password='pass123')
        response = self.client.get(self.url, {'week': 'no-es-una-fecha'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['monday'], monday_of(date.today()))

    def test_week_shows_assignments(self):
        shift = Shift.objects.first()
        ShiftAssignment.objects.create(date=date.today(), shift=shift, employee=self.employee)
        self.client.login(username='sched_admin', password='pass123')
        response = self.client.get(self.url)
        rows = response.context['rows']
        todays_row = next(r for r in rows if r['date'] == date.today())
        assigned_employees = [c['assignment'].employee for c in todays_row['cells'] if c['assignment']]
        self.assertIn(self.employee, assigned_employees)


# ─────────────────────────────────────────────
# ASSIGNMENT UPDATE (HTMX) TESTS
# ─────────────────────────────────────────────

class AssignmentUpdateViewTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.admin = make_admin()
        self.employee = make_employee()
        self.shift = Shift.objects.first()
        self.today = date.today()
        self.url = reverse('schedules:assignment_update', args=[self.today.strftime('%Y-%m-%d'), self.shift.pk])

    def test_employee_cannot_assign(self):
        self.client.login(username='sched_emp', password='pass123')
        response = self.client.post(self.url, {'employee': self.employee.pk})
        self.assertEqual(response.status_code, 403)

    def test_admin_assigns_employee(self):
        self.client.login(username='sched_admin', password='pass123')
        response = self.client.post(self.url, {'employee': self.employee.pk})
        self.assertEqual(response.status_code, 200)
        assignment = ShiftAssignment.objects.get(date=self.today, shift=self.shift)
        self.assertEqual(assignment.employee, self.employee)

    def test_admin_unassigns_with_blank_employee(self):
        ShiftAssignment.objects.create(date=self.today, shift=self.shift, employee=self.employee)
        self.client.login(username='sched_admin', password='pass123')
        response = self.client.post(self.url, {'employee': ''})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ShiftAssignment.objects.filter(date=self.today, shift=self.shift).exists())

    def test_admin_reassigns_existing_slot(self):
        ShiftAssignment.objects.create(date=self.today, shift=self.shift, employee=self.employee)
        other_employee = make_employee(username='sched_emp_other')
        self.client.login(username='sched_admin', password='pass123')
        response = self.client.post(self.url, {'employee': other_employee.pk})
        self.assertEqual(response.status_code, 200)
        assignment = ShiftAssignment.objects.get(date=self.today, shift=self.shift)
        self.assertEqual(assignment.employee, other_employee)

    def test_assignment_blocked_during_exception_shows_error(self):
        """El endpoint no debe crashear ni guardar si hay conflicto — debe mostrar el error"""
        ScheduleException.objects.create(
            employee=self.employee,
            date_start=self.today,
            date_end=self.today,
            exception_type='sick',
            created_by=self.admin,
        )
        self.client.login(username='sched_admin', password='pass123')
        response = self.client.post(self.url, {'employee': self.employee.pk})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ShiftAssignment.objects.filter(date=self.today, shift=self.shift).exists())
        self.assertIsNotNone(response.context['error'])


# ─────────────────────────────────────────────
# EXCEPTION VIEWS TESTS
# ─────────────────────────────────────────────

class ExceptionViewsTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.admin = make_admin()
        self.employee = make_employee()
        self.other_employee = make_employee(username='sched_emp_other2')

    def test_employee_sees_only_own_exceptions(self):
        ScheduleException.objects.create(
            employee=self.employee, date_start=date.today(), date_end=date.today(),
            exception_type='vacation', created_by=self.admin,
        )
        ScheduleException.objects.create(
            employee=self.other_employee, date_start=date.today(), date_end=date.today(),
            exception_type='sick', created_by=self.admin,
        )
        self.client.login(username='sched_emp', password='pass123')
        response = self.client.get(reverse('schedules:exception_list'))
        exceptions = list(response.context['exceptions'])
        self.assertEqual(len(exceptions), 1)
        self.assertEqual(exceptions[0].employee, self.employee)

    def test_admin_sees_all_exceptions(self):
        ScheduleException.objects.create(
            employee=self.employee, date_start=date.today(), date_end=date.today(),
            exception_type='vacation', created_by=self.admin,
        )
        ScheduleException.objects.create(
            employee=self.other_employee, date_start=date.today(), date_end=date.today(),
            exception_type='sick', created_by=self.admin,
        )
        self.client.login(username='sched_admin', password='pass123')
        response = self.client.get(reverse('schedules:exception_list'))
        self.assertEqual(len(response.context['exceptions']), 2)

    def test_employee_cannot_create_exception(self):
        self.client.login(username='sched_emp', password='pass123')
        response = self.client.get(reverse('schedules:exception_create'))
        self.assertEqual(response.status_code, 403)

    def test_admin_creates_exception(self):
        self.client.login(username='sched_admin', password='pass123')
        data = {
            'employee': self.employee.pk,
            'date_start': date.today().isoformat(),
            'date_end': (date.today() + timedelta(days=3)).isoformat(),
            'exception_type': 'vacation',
            'reason': 'Vacaciones familiares',
        }
        response = self.client.post(reverse('schedules:exception_create'), data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(ScheduleException.objects.filter(employee=self.employee, reason='Vacaciones familiares').exists())

    def test_admin_create_warns_about_conflicting_assignments(self):
        """Si el empleado ya tenía turnos asignados en ese rango, debe avisar (no bloquear)"""
        shift = Shift.objects.first()
        ShiftAssignment.objects.create(date=date.today(), shift=shift, employee=self.employee)
        self.client.login(username='sched_admin', password='pass123')
        data = {
            'employee': self.employee.pk,
            'date_start': date.today().isoformat(),
            'date_end': (date.today() + timedelta(days=1)).isoformat(),
            'exception_type': 'sick',
            'reason': '',
        }
        response = self.client.post(reverse('schedules:exception_create'), data, follow=True)
        messages = list(response.context['messages'])
        self.assertTrue(any('ya tenía turnos asignados' in str(m) for m in messages))
        # La excepción se crea igual — no se bloquea, solo se avisa.
        self.assertTrue(ScheduleException.objects.filter(employee=self.employee).exists())

    def test_employee_cannot_delete_exception(self):
        exception = ScheduleException.objects.create(
            employee=self.employee, date_start=date.today(), date_end=date.today(),
            exception_type='vacation', created_by=self.admin,
        )
        self.client.login(username='sched_emp', password='pass123')
        response = self.client.delete(reverse('schedules:exception_delete', args=[exception.pk]))
        self.assertEqual(response.status_code, 403)

    def test_admin_deletes_exception(self):
        exception = ScheduleException.objects.create(
            employee=self.employee, date_start=date.today(), date_end=date.today(),
            exception_type='vacation', created_by=self.admin,
        )
        self.client.login(username='sched_admin', password='pass123')
        response = self.client.delete(reverse('schedules:exception_delete', args=[exception.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(ScheduleException.objects.filter(pk=exception.pk).exists())


# ─────────────────────────────────────────────
# SHIFT MANAGEMENT VIEWS TESTS
# ─────────────────────────────────────────────

class ShiftViewsTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.admin = make_admin()
        self.employee = make_employee()

    def test_employee_cannot_access_shift_list(self):
        self.client.login(username='sched_emp', password='pass123')
        response = self.client.get(reverse('schedules:shift_list'))
        self.assertEqual(response.status_code, 403)

    def test_admin_can_edit_shift(self):
        shift = Shift.objects.first()
        self.client.login(username='sched_admin', password='pass123')
        response = self.client.post(reverse('schedules:shift_update', args=[shift.pk]), {
            'name': shift.name,
            'start_time': '08:00',
            'end_time': '16:00',
        })
        self.assertEqual(response.status_code, 302)
        shift.refresh_from_db()
        self.assertEqual(shift.start_time.strftime('%H:%M'), '08:00')

    def test_end_time_must_be_after_start_time(self):
        shift = Shift.objects.first()
        self.client.login(username='sched_admin', password='pass123')
        response = self.client.post(reverse('schedules:shift_update', args=[shift.pk]), {
            'name': shift.name,
            'start_time': '15:00',
            'end_time': '07:00',
        })
        self.assertEqual(response.status_code, 200)  # re-renderiza el form con error
        self.assertFalse(response.context['form'].is_valid())
