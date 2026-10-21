# utils/views.py - GESTIÓN DE TASA DE CAMBIO

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Count, Sum
from decimal import Decimal

from .models import ExchangeRate
from .forms import ExchangeRateForm
from utils.decorators import admin_required


@admin_required
def exchange_rate_management(request):
    """Vista para gestionar la tasa de cambio - Solo Administradores"""
    
    # Obtener tasa actual
    current_rate = ExchangeRate.get_latest_rate()
    
    # Obtener historial reciente
    recent_rates = ExchangeRate.objects.all()[:10]
    
    # Estadísticas básicas
    stats = {
        'total_rates': ExchangeRate.objects.count(),
        'this_week_updates': ExchangeRate.objects.filter(
            date__gte=timezone.now().date() - timezone.timedelta(days=7)
        ).count()
    }
    
    if request.method == 'POST':
        form = ExchangeRateForm(request.POST)
        if form.is_valid():
            # ⭐ CORREGIDO: Verificar si existe una tasa para esta fecha y actualizarla
            existing_rate = getattr(form, '_existing_rate_to_update', None)

            if existing_rate:
                # Actualizar el registro existente
                existing_rate.bs_to_usd = form.cleaned_data['bs_to_usd']
                existing_rate.updated_by = request.user
                existing_rate.save()

                messages.success(
                    request,
                    f'Tasa de cambio del {existing_rate.date.strftime("%d/%m/%Y")} actualizada exitosamente a {existing_rate.bs_to_usd} Bs/USD'
                )
            else:
                # Crear nueva tasa de cambio
                new_rate = form.save(commit=False)
                new_rate.updated_by = request.user
                new_rate.save()

                messages.success(
                    request,
                    f'Tasa de cambio registrada exitosamente: {new_rate.bs_to_usd} Bs/USD para {new_rate.date.strftime("%d/%m/%Y")}'
                )

            return redirect('utils:exchange_rate_management')
    else:
        # Pre-rellenar con la fecha de hoy
        initial_data = {'date': timezone.now().date()}
        if current_rate:
            initial_data['bs_to_usd'] = current_rate.bs_to_usd
        
        form = ExchangeRateForm(initial=initial_data)
    
    return render(request, 'utils/exchange_rate_management.html', {
        'form': form,
        'current_rate': current_rate,
        'recent_rates': recent_rates,
        'stats': stats,
    })


@admin_required 
def exchange_rate_history(request):
    """Vista para ver historial completo de tasas de cambio"""
    
    # Filtros opcionales
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    rates = ExchangeRate.objects.all()
    
    if date_from:
        try:
            from django.utils.dateparse import parse_date
            date_from_parsed = parse_date(date_from)
            if date_from_parsed:
                rates = rates.filter(date__gte=date_from_parsed)
        except:
            pass
    
    if date_to:
        try:
            from django.utils.dateparse import parse_date
            date_to_parsed = parse_date(date_to)
            if date_to_parsed:
                rates = rates.filter(date__lte=date_to_parsed)
        except:
            pass
    
    # Paginación
    from django.core.paginator import Paginator
    paginator = Paginator(rates, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'utils/exchange_rate_history.html', {
        'page_obj': page_obj,
        'date_from': date_from,
        'date_to': date_to,
    })

@admin_required
def store_settings(request):
    """Ajustes del negocio (descuento por pago en dólares en efectivo) - Solo Administradores"""
    from bodega_system.business import feature
    from .forms import StoreSettingsForm
    from .models import StoreSettings

    if not feature('cash_usd'):
        return redirect('dashboard')

    settings_obj = StoreSettings.get()
    if request.method == 'POST':
        form = StoreSettingsForm(request.POST, instance=settings_obj)
        if form.is_valid():
            form.save()
            messages.success(request, 'Ajustes guardados.')
            return redirect('utils:store_settings')
    else:
        form = StoreSettingsForm(instance=settings_obj)

    return render(request, 'utils/store_settings.html', {'form': form})
