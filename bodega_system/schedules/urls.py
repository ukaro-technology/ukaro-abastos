# schedules/urls.py

from django.urls import path
from . import views

app_name = 'schedules'

urlpatterns = [
    path('', views.week_view, name='week_view'),
    path('asignar/<str:date_str>/<int:shift_id>/', views.assignment_update, name='assignment_update'),
    path('turnos/', views.shift_list, name='shift_list'),
    path('turnos/<int:pk>/editar/', views.shift_update, name='shift_update'),
    path('excepciones/', views.exception_list, name='exception_list'),
    path('excepciones/nueva/', views.exception_create, name='exception_create'),
    path('excepciones/<int:pk>/eliminar/', views.exception_delete, name='exception_delete'),
]
