# sales/views.py - CON RESTRICCIONES DE ROLES

import io
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.core.paginator import Paginator
from django.db.models import Sum, Avg, Q
from django.utils.dateparse import parse_date

from bodega_system.business import feature, get_business
from .models import Sale, SaleItem
from utils.models import ExchangeRate
from utils.decorators import admin_required, employee_or_admin_required, sales_access_required

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from datetime import datetime, timedelta
from decimal import Decimal
import io

# Reportes PDF
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet

# Modelos locales
from .models import Sale, SaleItem
from inventory.models import Product
from customers.models import Customer
from utils.models import ExchangeRate  # ← IMPORTACIÓN CRÍTICA
from utils.decorators import sales_access_required


@sales_access_required
def sale_list(request):
    """
    Vista para listar ventas - Solo Admin puede ver todas las ventas
    Empleados solo pueden ver sus propias ventas
    """
    sales_qs = Sale.objects.select_related('customer', 'user').all().order_by('-date')
    
    # Si es empleado, solo mostrar sus propias ventas
    if not (request.user.is_admin or request.user.is_superuser):
        sales_qs = sales_qs.filter(user=request.user)

    # --- Aplicar filtros desde la URL (GET) ---
    search_query = request.GET.get('q', '')
    date_from_str = request.GET.get('date_from', '')
    date_to_str = request.GET.get('date_to', '')
    credit_filter = request.GET.get('credit_filter', '')

    if search_query:
        sales_qs = sales_qs.filter(
            Q(customer__name__icontains=search_query) |
            Q(user__username__icontains=search_query) |
            Q(user__first_name__icontains=search_query) |
            Q(user__last_name__icontains=search_query) |
            Q(notes__icontains=search_query) |
            Q(id__icontains=search_query)
        )
    
    if date_from_str:
        date_from = parse_date(date_from_str)
        if date_from:
            sales_qs = sales_qs.filter(date__gte=date_from)
            
    if date_to_str:
        date_to = parse_date(date_to_str)
        if date_to:
            from datetime import timedelta
            sales_qs = sales_qs.filter(date__lt=date_to + timedelta(days=1))

    if credit_filter == 'cash':
        sales_qs = sales_qs.filter(is_credit=False)
    elif credit_filter == 'credit':
        sales_qs = sales_qs.filter(is_credit=True)

    # --- Calcular totales ANTES de la paginación ---
    sales_count = sales_qs.count()
    total_sales = sales_qs.aggregate(total=Sum('total_bs'))['total'] or 0
    average_sale = total_sales / sales_count if sales_count > 0 else 0

    # --- Aplicar Paginación ---
    paginator = Paginator(sales_qs, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'sales_count': sales_count,
        'total_sales': total_sales,
        'average_sale': average_sale,
        'search_query': search_query,
        'date_from': date_from_str,
        'date_to': date_to_str,
        'credit_filter': credit_filter,
        'is_admin': request.user.is_admin or request.user.is_superuser,
    }
    
    return render(request, 'sales/sale_list.html', context)

@sales_access_required
def sale_create(request):
    """Vista para crear una nueva venta - Empleados y Administradores"""
    
    # Obtener tasa de cambio de forma segura
    try:
        latest_rate = ExchangeRate.get_latest_rate()
        exchange_rate = float(latest_rate.bs_to_usd) if latest_rate else 1.0
    except (AttributeError, ValueError, TypeError):
        exchange_rate = 1.0
    
    # Preparar datos JSON seguros para JavaScript
    from utils.models import StoreSettings
    data_for_js = {
        'exchangeRate': exchange_rate,
        # Módulos del perfil del negocio (bodega_system/business.py)
        'features': {
            'motoParts': feature('moto_parts'),
            'cashUsd': feature('cash_usd'),
            'cameraScan': feature('camera_scan'),
            'whatsappReceipt': feature('whatsapp_receipt'),
        },
        'cashUsdDiscountPercent': (
            float(StoreSettings.get().cash_usd_discount_percent) if feature('cash_usd') else 0
        ),
        'csrfToken': None,  # Se obtiene desde el template
        'apiUrls': {
            'createSale': '/sales/api/create/',
            'searchProducts': '/api/products/search/',
            'searchCustomers': '/api/customers/search/',
        }
    }
    
    context = {
        'title': 'Nueva Venta',
        'data_for_js': data_for_js,
        'latest_exchange_rate': latest_rate,  # Mantener para compatibilidad
    }
    
    return render(request, 'sales/sale_form.html', context)

@sales_access_required
def sale_detail(request, pk):
    """
    Vista para ver detalles de una venta
    Empleados solo pueden ver sus propias ventas
    """
    sale = get_object_or_404(Sale, pk=pk)
    
    # Si es empleado, verificar que sea su venta
    if not (request.user.is_admin or request.user.is_superuser):
        if sale.user != request.user:
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied("No tienes permisos para ver esta venta.")
    
    whatsapp_url = None
    if feature('whatsapp_receipt'):
        from .whatsapp import receipt_whatsapp_url
        whatsapp_url = receipt_whatsapp_url(sale)

    return render(request, 'sales/sale_detail.html', {
        'sale': sale, 
        'items': sale.items.all(),
        'is_admin': request.user.is_admin or request.user.is_superuser,
        'whatsapp_url': whatsapp_url,
    })

@sales_access_required
def sale_receipt(request, pk):
    """
    Vista para generar recibo PDF de una venta
    Empleados solo pueden generar recibos de sus propias ventas
    """
    sale = get_object_or_404(Sale, pk=pk)
    
    # Si es empleado, verificar que sea su venta
    if not (request.user.is_admin or request.user.is_superuser):
        if sale.user != request.user:
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied("No tienes permisos para generar el recibo de esta venta.")
    
    items = sale.items.all()
    
    # Obtener tasa de cambio actual
    exchange_rate = ExchangeRate.get_latest_rate()
    
    # Crear un buffer para el PDF
    buffer = io.BytesIO()
    
    # Crear el PDF
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    
    # Estilos para el PDF
    styles = getSampleStyleSheet()
    
    # Título
    p.setFont("Helvetica-Bold", 16)
    p.drawCentredString(width/2, height - 1*inch, get_business()['name'])
    
    p.setFont("Helvetica-Bold", 14)
    p.drawCentredString(width/2, height - 1.3*inch, f"Recibo de Venta #{sale.id}")
    
    # Información de la venta
    p.setFont("Helvetica", 10)
    p.drawString(1*inch, height - 2*inch, f"Fecha: {sale.date.strftime('%d/%m/%Y %H:%M')}")
    p.drawString(1*inch, height - 2.2*inch, f"Atendido por: {sale.user.get_full_name() or sale.user.username}")
    
    if sale.customer:
        p.drawString(1*inch, height - 2.4*inch, f"Cliente: {sale.customer.name}")
        if sale.is_credit:
            p.drawString(1*inch, height - 2.6*inch, "Tipo: CRÉDITO")
    else:
        p.drawString(1*inch, height - 2.4*inch, "Cliente: Consumidor Final")

    # Método de pago
    payment_method_display = sale.get_payment_method_display()
    y_position = height - 2.8*inch if sale.customer and sale.is_credit else height - 2.6*inch
    p.drawString(1*inch, y_position, f"Método de pago: {payment_method_display}")

    # Referencia de pago móvil si aplica
    if sale.payment_method == 'mobile' and sale.mobile_reference:
        y_position -= 0.2*inch
        p.drawString(1*inch, y_position, f"Ref. Pago Móvil: {sale.mobile_reference}")

    # Tabla de productos
    data = [["Producto", "Cantidad", "Precio Unit.", "Subtotal"]]
    
    for item in items:
        product_name = item.product.name if item.product else f"COMBO: {item.combo.name}"
        data.append([
            product_name, 
            str(item.quantity), 
            f"Bs {item.price_bs:.2f}", 
            f"Bs {item.subtotal:.2f}"
        ])
    
    table = Table(data, colWidths=[3*inch, 1*inch, 1.2*inch, 1.2*inch])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (1, 0), (3, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    
    # Dibujar la tabla
    table.wrapOn(p, width, height)
    table.drawOn(p, 0.6*inch, height - 4*inch - len(data)*0.25*inch)
    
    # Total
    totals_y = height - 4.5*inch - len(data)*0.25*inch
    if sale.discount_usd:
        # Venta en dólares en efectivo con descuento: los precios de la tabla son de lista
        p.setFont("Helvetica", 10)
        p.drawRightString(6.4*inch, totals_y + 0.3*inch,
                          f"Descuento efectivo $ ({sale.discount_percent.normalize():f}%): - $ {sale.discount_usd:.2f}")
    p.setFont("Helvetica-Bold", 12)
    p.drawRightString(6.4*inch, totals_y, f"Total: Bs {sale.total_bs:.2f}")
    
    if sale.discount_usd:
        p.setFont("Helvetica-Bold", 11)
        p.drawRightString(6.4*inch, totals_y - 0.3*inch, f"Total en efectivo: $ {sale.total_usd:.2f}")
    elif exchange_rate:
        p.setFont("Helvetica", 10)
        usd_total = sale.total_bs / exchange_rate.bs_to_usd
        p.drawRightString(6.4*inch, totals_y - 0.3*inch, f"Equivalente: $ {usd_total:.2f}")
    
    # Pie de página
    p.setFont("Helvetica", 8)
    p.drawCentredString(width/2, 0.5*inch, "Gracias por su compra")
    
    # Finalizar PDF
    p.showPage()
    p.save()
    
    # Configurar la respuesta
    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'filename=recibo_venta_{sale.id}.pdf'
    
    return response