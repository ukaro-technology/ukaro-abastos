from django.urls import path
from . import views, backup_views

app_name = 'utils'

urlpatterns = [
    # Gestión de tasa de cambio
    path('exchange-rate/', views.exchange_rate_management, name='exchange_rate_management'),
    path('exchange-rate/history/', views.exchange_rate_history, name='exchange_rate_history'),
    path('store-settings/', views.store_settings, name='store_settings'),
    path('backups/', backup_views.backup_index, name='backup_index'),
    path('backups/create/', backup_views.backup_create, name='backup_create'),
    path('backups/download/<str:filename>/', backup_views.backup_download, name='backup_download'),
    path('backups/delete/<str:filename>/', backup_views.backup_delete, name='backup_delete'),
    path('backups/restore/', backup_views.backup_restore, name='backup_restore'),
]