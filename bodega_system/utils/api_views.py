# utils/api_views.py - API ACTUALIZADA PARA USD

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from .models import ExchangeRate


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def exchange_rate_view(request):
    """API para obtener la tasa de cambio actual"""
    latest_rate = ExchangeRate.get_latest_rate()
    
    if latest_rate:
        return JsonResponse({
            'rate': float(latest_rate.bs_to_usd),
            'date': latest_rate.date.isoformat(),
        })
    else:
        return JsonResponse({
            'error': 'No hay tasa de cambio disponible'
        }, status=404)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def product_by_barcode(request, barcode):
    """API para buscar producto por código de barras - CORREGIDA PARA USD"""
    try:
        # Importación aquí para evitar importación circular
        from inventory.models import Product
        
        product = get_object_or_404(Product, barcode=barcode, is_active=True)
        
        # ⭐ OBTENER TASA DE CAMBIO ACTUAL
        latest_rate = ExchangeRate.get_latest_rate()
        
        # ⭐ CALCULAR PRECIOS EN BS AUTOMÁTICAMENTE
        selling_price_bs = 0
        if latest_rate:
            selling_price_bs = float(product.selling_price_usd * latest_rate.bs_to_usd)
        
        return JsonResponse({
            'id': product.id,
            'name': product.name,
            'barcode': product.barcode,
            'category_id': product.category_id,
            'category_name': product.category.name,
            # ⭐ PRECIO USD (para admin)
            'selling_price_usd': float(product.selling_price_usd),
            # ⭐ PRECIO BS CALCULADO (para ventas)
            'selling_price_bs': selling_price_bs,
            'stock': float(product.stock),
            'unit_type': product.unit_display,
            'unit_code': product.unit_type,  # Código para lógica
            'is_weight_based': product.is_weight_based,
            # Información adicional
            'exchange_rate': float(latest_rate.bs_to_usd) if latest_rate else None,
        })
    except Exception as e:
        return JsonResponse({
            'error': str(e)
        }, status=404)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def customer_search(request):
    """API para buscar clientes por nombre, teléfono o cédula"""
    query = request.GET.get('q', '')

    if not query:
        return JsonResponse({
            'customers': []
        })

    try:
        # Importación aquí para evitar importación circular
        from customers.models import Customer
        from django.db.models import Q

        customers = Customer.objects.filter(
            Q(name__icontains=query) |
            Q(phone__icontains=query) |
            Q(cedula__icontains=query)
        )[:10]  # Limitar a 10 resultados

        result = []
        for customer in customers:
            result.append({
                'id': customer.id,
                'name': customer.name,
                'phone': customer.phone,
                'cedula': customer.cedula or '',
            })
        
        return JsonResponse({
            'customers': result
        })
    except Exception as e:
        return JsonResponse({
            'error': str(e)
        }, status=500)