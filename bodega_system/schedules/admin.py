# schedules/admin.py

from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Shift, ShiftAssignment, ScheduleException


@admin.register(Shift)
class ShiftAdmin(SimpleHistoryAdmin):
    list_display = ('name', 'start_time', 'end_time')


@admin.register(ShiftAssignment)
class ShiftAssignmentAdmin(SimpleHistoryAdmin):
    list_display = ('date', 'shift', 'employee')
    list_filter = ('shift', 'date')
    search_fields = ('employee__username', 'employee__first_name', 'employee__last_name')
    autocomplete_fields = ['employee']


@admin.register(ScheduleException)
class ScheduleExceptionAdmin(SimpleHistoryAdmin):
    list_display = ('employee', 'exception_type', 'date_start', 'date_end', 'created_by')
    list_filter = ('exception_type',)
    search_fields = ('employee__username', 'employee__first_name', 'employee__last_name', 'reason')
    autocomplete_fields = ['employee']
