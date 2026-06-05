# bodega_system/views.py - VISTAS PRINCIPALES DEL DASHBOARD

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db import connection
from django.db.models import Sum, Count, Q, F
from django.db.models.functions import TruncDate
from django.utils import timezone
from datetime import timedelta

from utils.decorators import is_admin, admin_required

def health(request):
    try:
        connection.ensure_connection()
        db_ok = True
    except Exception:
        db_ok = False
    status = 200 if db_ok else 503
    return JsonResponse({'status': 'ok' if db_ok else 'error', 'db': db_ok}, status=status)


@admin_required
def dashboard(request):
    """
    Vista del dashboard - Solo para administradores
    """
    today = timezone.now().date()
    
    # Determinar si el usuario es administrador
    user_is_admin = is_admin(request.user)
    
    # Importar modelos aquí para evitar circular imports
    from sales.models import Sale
    from inventory.models import Product
    from customers.models import Customer, CustomerCredit
    
    # MÉTRICAS DE VENTAS
    if user_is_admin:
        # Administradores ven todas las ventas
        sales_today = Sale.objects.filter(date__date=today)
    else:
        # Empleados solo ven sus propias ventas
        sales_today = Sale.objects.filter(date__date=today, user=request.user)
    
    # Calcular totales de ventas
    sales_count = sales_today.count()
    sales_total = sales_today.aggregate(total=Sum('total_bs'))['total'] or 0
    
    # MÉTRICAS DE CLIENTES
    total_customers = Customer.objects.filter(is_active=True).count()
    
    if user_is_admin:
        # Solo administradores ven métricas de créditos
        pending_credits = CustomerCredit.objects.filter(is_paid=False).count()
        context_data = {
            'sales_total': sales_total,
            'sales_count': sales_count,
            'total_customers': total_customers,
            'pending_credits': pending_credits,
        }
        
        # MÉTRICAS DE INVENTARIO - Solo para administradores
        total_products = Product.objects.filter(is_active=True).count()
        low_stock_products = Product.objects.filter(
            is_active=True,
            stock__lte=F('min_stock')
        ).count()
        
        context_data.update({
            'total_products': total_products,
            'low_stock_products': low_stock_products,
        })

        # Datos de ventas de los últimos 7 días para el gráfico
        DAYS_ES = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']
        last_7_days = today - timedelta(days=6)
        daily_sales_qs = (
            Sale.objects.filter(date__date__gte=last_7_days)
            .annotate(day=TruncDate('date'))
            .values('day')
            .annotate(total=Sum('total_bs'))
            .order_by('day')
        )
        daily_dict = {item['day']: float(item['total'] or 0) for item in daily_sales_qs}
        chart_labels, chart_values = [], []
        for i in range(7):
            day = last_7_days + timedelta(days=i)
            chart_labels.append(f"{DAYS_ES[day.weekday()]} {day.day}")
            chart_values.append(daily_dict.get(day, 0))
        context_data['chart_labels'] = chart_labels
        context_data['chart_values'] = chart_values

        # Top vendedores hoy (mini-widget)
        today_sellers = (
            Sale.objects.filter(date__date=today)
            .values('user__username')
            .annotate(count=Count('id'), total_usd=Sum('total_usd'))
            .order_by('-total_usd')[:5]
        )
        context_data['today_sellers'] = today_sellers

    else:
        # Para empleados, calcular clientes únicos atendidos hoy
        customers_served_today = sales_today.filter(
            customer__isnull=False
        ).values('customer').distinct().count()
        
        context_data = {
            'sales_total': sales_total,
            'sales_count': sales_count,
            'total_customers': total_customers,
            'customers_served_today': customers_served_today,
        }
    
    # Agregar información del usuario
    context_data.update({
        'user_is_admin': user_is_admin,
        'user_role': request.user.role,
    })
    
    return render(request, 'dashboard.html', context_data)

# Vista adicional para mostrar estadísticas detalladas (solo admin)
@login_required
def dashboard_analytics(request):
    """
    Vista con analytics detallados - Solo administradores
    """
    if not is_admin(request.user):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied("Solo los administradores pueden ver analytics detallados.")
    
    from sales.models import Sale
    from inventory.models import Product
    from customers.models import Customer
    
    today = timezone.now().date()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)
    
    # Ventas por período
    sales_today = Sale.objects.filter(date__date=today)
    sales_week = Sale.objects.filter(date__date__gte=week_ago)
    sales_month = Sale.objects.filter(date__date__gte=month_ago)
    
    # Productos más vendidos (últimos 30 días)
    top_products = Product.objects.filter(
        sale_items__sale__date__date__gte=month_ago
    ).annotate(
        total_sold=Sum('sale_items__quantity'),
        revenue=Sum(F('sale_items__quantity') * F('sale_items__price_bs'))
    ).order_by('-total_sold')[:10]
    
    # Clientes con más compras
    top_customers = Customer.objects.filter(
        sales__date__date__gte=month_ago
    ).annotate(
        total_purchases=Count('sales'),
        total_spent=Sum('sales__total_bs')
    ).order_by('-total_spent')[:10]
    
    context = {
        'sales_today_count': sales_today.count(),
        'sales_today_total': sales_today.aggregate(total=Sum('total_bs'))['total'] or 0,
        'sales_week_count': sales_week.count(),
        'sales_week_total': sales_week.aggregate(total=Sum('total_bs'))['total'] or 0,
        'sales_month_count': sales_month.count(),
        'sales_month_total': sales_month.aggregate(total=Sum('total_bs'))['total'] or 0,
        'top_products': top_products,
        'top_customers': top_customers,
    }
    
    return render(request, 'dashboard_analytics.html', context)

# Vista para empleados con estadísticas personales
@login_required
def my_stats(request):
    """
    Vista con estadísticas personales del empleado
    """
    if is_admin(request.user):
        # Los administradores no necesitan esta vista
        from django.shortcuts import redirect
        return redirect('dashboard')
    
    from sales.models import Sale
    from inventory.models import Product
    
    today = timezone.now().date()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)
    
    # Ventas del empleado por período
    my_sales_today = Sale.objects.filter(user=request.user, date__date=today)
    my_sales_week = Sale.objects.filter(user=request.user, date__date__gte=week_ago)
    my_sales_month = Sale.objects.filter(user=request.user, date__date__gte=month_ago)
    
    # Clientes únicos atendidos
    customers_today = my_sales_today.filter(
        customer__isnull=False
    ).values('customer').distinct().count()
    
    customers_week = my_sales_week.filter(
        customer__isnull=False
    ).values('customer').distinct().count()
    
    customers_month = my_sales_month.filter(
        customer__isnull=False
    ).values('customer').distinct().count()
    
    # Productos más vendidos por el empleado
    my_top_products = Product.objects.filter(
        sale_items__sale__user=request.user,
        sale_items__sale__date__date__gte=month_ago
    ).annotate(
        total_sold=Sum('sale_items__quantity')
    ).order_by('-total_sold')[:5]
    
    context = {
        'sales_today_count': my_sales_today.count(),
        'sales_today_total': my_sales_today.aggregate(total=Sum('total_bs'))['total'] or 0,
        'sales_week_count': my_sales_week.count(),
        'sales_week_total': my_sales_week.aggregate(total=Sum('total_bs'))['total'] or 0,
        'sales_month_count': my_sales_month.count(),
        'sales_month_total': my_sales_month.aggregate(total=Sum('total_bs'))['total'] or 0,
        'customers_today': customers_today,
        'customers_week': customers_week,
        'customers_month': customers_month,
        'my_top_products': my_top_products,
    }
    
    return render(request, 'my_stats.html', context)