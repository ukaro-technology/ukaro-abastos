from datetime import time

from django.db import migrations


def seed_shifts(apps, schema_editor):
    Shift = apps.get_model('schedules', 'Shift')
    Shift.objects.get_or_create(
        name='Mañana',
        defaults={'start_time': time(7, 0), 'end_time': time(15, 0)},
    )
    Shift.objects.get_or_create(
        name='Tarde',
        defaults={'start_time': time(13, 0), 'end_time': time(21, 0)},
    )


def remove_shifts(apps, schema_editor):
    Shift = apps.get_model('schedules', 'Shift')
    Shift.objects.filter(name__in=['Mañana', 'Tarde']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('schedules', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_shifts, remove_shifts),
    ]
