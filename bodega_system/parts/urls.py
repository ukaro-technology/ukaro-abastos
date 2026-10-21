from django.urls import path

from . import views

app_name = 'parts'

urlpatterns = [
    path('motos/', views.moto_list, name='moto_list'),
]
