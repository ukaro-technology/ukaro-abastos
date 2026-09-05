# inventory/api_views.py - VERSIÓN MEJORADA

import json
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.core.paginator import Paginator
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from .models import Product, ProductCombo, Category, InventoryAdjustment
from django.db.models import F

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def product_detail_api(request, pk):
    """API mejorada para obtener detalles de un producto con información completa"""
    try:
        product = get_object_or_404(Product, pk=pk)
        
        # Calcular información adicional
        recent_adjustments = product.adjustments.all()[:5]
        
        data = {
            'id': product.id,
            'name': product.name,
            'barcode': product.barcode,
            'category_id': product.category_id,
            'category_name': product.category.name,
            'description': product.description,
            'purchase_price_bs': float(product.get_current_purchase_price_bs()),
            'selling_price_bs': float(product.get_current_price_bs()),
            'stock': float(product.stock),
            'min_stock': float(product.min_stock),
            'is_active': product.is_active,
            'image': product.image.url if product.image else None,
            'unit_type': product.unit_type,
            'unit_display': product.get_unit_type_display(),
            'is_weight_based': product.is_weight_based,
            
            # Información de precios al mayor
            'is_bulk_pricing': product.is_bulk_pricing,
            'bulk_min_quantity': float(product.bulk_min_quantity) if product.bulk_min_quantity else None,
            'bulk_price_usd': float(product.bulk_price_usd) if product.bulk_price_usd else None,

            # Análisis de stock
            'stock_status': product.stock_status,
            'stock_level': 'low' if product.stock <= product.min_stock else 'normal',
            
            # Información de márgenes (usa el precio Bs real de venta, ya sea calculado con
            # la tasa o fijo — ver Product.get_current_price_bs)
            'profit_margin': float(product.get_current_price_bs() - product.get_current_purchase_price_bs()),
            'profit_percentage': round(
                (
                    (product.get_current_price_bs() - product.get_current_purchase_price_bs())
                    / product.get_current_purchase_price_bs() * 100
                ), 2
            ) if product.get_current_purchase_price_bs() > 0 else 0,
            
            # Historial reciente
            'recent_adjustments': [
                {
                    'id': adj.id,
                    'type': adj.adjustment_type,
                    'quantity': float(adj.quantity),
                    'reason': adj.reason,
                    'date': adj.adjusted_at.isoformat(),
                    'user': adj.adjusted_by.username if adj.adjusted_by else None
                }
                for adj in recent_adjustments
            ],
            
            # Fechas
            'created_at': product.created_at.isoformat(),
            'updated_at': product.updated_at.isoformat(),
        }
        
        return JsonResponse(data)
        
    except Exception as e:
        return JsonResponse(
            {'error': f'Error al obtener detalles del producto: {str(e)}'}, 
            status=500
        )

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def product_search_api(request):
    """API mejorada para buscar productos con filtros avanzados"""
    try:
        query = request.GET.get('q', '').strip()
        category_id = request.GET.get('category')
        stock_filter = request.GET.get('stock')  # 'low', 'out', 'normal'
        active_only = request.GET.get('active', 'true').lower() == 'true'
        limit = min(int(request.GET.get('limit', 10)), 50)  # Máximo 50 resultados
        
        if not query and not category_id and not stock_filter:
            return JsonResponse({'products': []})
        
        # Consulta base
        products = Product.objects.select_related('category')
        
        if active_only:
            products = products.filter(is_active=True)
        
        # Filtros de búsqueda
        if query:
            products = products.filter(
                Q(name__icontains=query) |
                Q(barcode__icontains=query) |
                Q(description__icontains=query) |
                Q(category__name__icontains=query)
            )
        
        if category_id:
            products = products.filter(category_id=category_id)
        
        if stock_filter:
            if stock_filter == 'low':
                products = products.filter(stock__lte=F('min_stock'))
            elif stock_filter == 'out':
                products = products.filter(stock=0)
            elif stock_filter == 'normal':
                products = products.filter(stock__gt=F('min_stock'))
        
        # Ordenar por relevancia (nombre primero, luego por stock)
        products = products.order_by('name', '-stock')[:limit]
        
        results = []
        for product in products:
            # Determinar el estado del stock
            if product.stock <= 0:
                stock_status = 'out'
                stock_color = 'red'
            elif product.stock <= product.min_stock:
                stock_status = 'low'
                stock_color = 'yellow'
            else:
                stock_status = 'normal'
                stock_color = 'green'
            
            results.append({
                'id': product.id,
                'name': product.name,
                'barcode': product.barcode,
                'category': product.category.name,
                'selling_price_bs': float(product.get_current_price_bs()),
                'selling_price_usd': float(product.selling_price_usd),
                'stock': float(product.stock),
                'min_stock': float(product.min_stock),
                'unit_display': product.get_unit_type_display(),
                'unit_code': product.unit_type,
                'is_weight_based': product.is_weight_based,
                'stock_status': stock_status,
                'stock_color': stock_color,
                'image': product.image.url if product.image else None,
                'is_active': product.is_active,
            })
        
        return JsonResponse({
            'products': results,
            'count': len(results),
            'query': query
        })
        
    except Exception as e:
        return JsonResponse(
            {'error': f'Error en la búsqueda: {str(e)}'}, 
            status=500
        )

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def product_by_barcode_api(request, barcode):
    """
    API mejorada: Obtiene detalles de un producto por su código de barras
    con información completa para el sistema de ventas
    """
    try:
        product = Product.objects.select_related('category').filter(
            barcode=barcode, is_active=True
        ).first()

        if not product:
            return JsonResponse(
                {'error': 'Producto no encontrado o inactivo'}, 
                status=404
            )
        
        # Verificar stock disponible
        stock_available = product.stock > 0

        # Precio al mayor en Bs (calculado con la tasa actual — el modelo solo guarda
        # bulk_price_usd, no existe una columna bulk_price_bs; bug preexistente corregido:
        # antes esta vista intentaba leer product.bulk_price_bs, que no existe, y tiraba
        # AttributeError/500 apenas un producto con precio al mayor pasaba por esta ruta)
        bulk_price_bs = None
        if product.is_bulk_pricing and product.bulk_price_usd:
            from utils.models import ExchangeRate
            latest_rate = ExchangeRate.get_latest_rate()
            if latest_rate:
                bulk_price_bs = float(product.bulk_price_usd * latest_rate.bs_to_usd)

        data = {
            'id': product.id,
            'name': product.name,
            'barcode': product.barcode,
            'category': product.category.name,
            'category_id': product.category_id,
            'description': product.description or '',
            'unit_type': product.get_unit_type_display(),
            'unit_code': product.unit_type,
            'is_weight_based': product.is_weight_based,
            'stock': float(product.stock),
            'min_stock': float(product.min_stock),
            'stock_available': stock_available,
            'image': product.image.url if product.image else None,
            
            # Precios completos para órdenes de compra (selling_price_usd es informativo en
            # modo 'bs_fixed' — ver Product.get_current_price_usd)
            'purchase_price_bs': float(product.get_current_purchase_price_bs()),
            'purchase_price_usd': float(product.purchase_price_usd),
            'selling_price_bs': float(product.get_current_price_bs()),
            'selling_price_usd': float(product.get_current_price_usd()),
            
            # Información para precios al mayor
            'bulk_pricing': {
                'enabled': product.is_bulk_pricing,
                'min_quantity': float(product.bulk_min_quantity) if product.bulk_min_quantity else None,
                'bulk_price': bulk_price_bs
            } if product.is_bulk_pricing else None,
            
            # Estado del stock
            'stock_status': 'out' if product.stock <= 0 
                          else 'low' if product.stock <= product.min_stock 
                          else 'normal',
        }
        
        return JsonResponse(data)
        
    except Exception as e:
        return JsonResponse(
            {'error': f'Error al buscar producto: {str(e)}'}, 
            status=500
        )

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def categories_list_api(request):
    """API para obtener lista de categorías con conteo de productos"""
    try:
        categories = Category.objects.all().order_by('name')
        
        results = []
        for category in categories:
            product_count = Product.objects.filter(category=category, is_active=True).count()
            results.append({
                'id': category.id,
                'name': category.name,
                'description': category.description,
                'product_count': product_count,
                'created_at': None,
            })
        
        return JsonResponse({'categories': results})
        
    except Exception as e:
        return JsonResponse(
            {'error': f'Error al obtener categorías: {str(e)}'}, 
            status=500
        )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def validate_barcode_api(request):
    """API para validar si un código de barras ya existe"""
    try:
        data = json.loads(request.body)
        barcode = data.get('barcode', '').strip()
        product_id = data.get('product_id')  # Para excluir en edición
        
        if not barcode:
            return JsonResponse({'valid': False, 'message': 'Código de barras requerido'})
        
        # Verificar si existe
        query = Product.objects.filter(barcode=barcode)
        if product_id:
            query = query.exclude(id=product_id)
        
        exists = query.exists()
        
        return JsonResponse({
            'valid': not exists,
            'message': 'Código de barras disponible' if not exists else 'Este código de barras ya está en uso'
        })
        
    except Exception as e:
        return JsonResponse(
            {'error': f'Error al validar código de barras: {str(e)}'}, 
            status=500
        )

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def product_stock_summary_api(request):
    """API para obtener resumen de stock del inventario"""
    try:
        from decimal import Decimal
        from django.db.models import Count, Sum, F, Case, When, Value, DecimalField
        from utils.models import ExchangeRate

        # Estadísticas generales
        total_products = Product.objects.filter(is_active=True).count()
        out_of_stock = Product.objects.filter(is_active=True, stock=0).count()
        low_stock = Product.objects.filter(
            is_active=True,
            stock__gt=0,
            stock__lte=F('min_stock')
        ).count()

        # Valor total del inventario — calculado en vivo con la tasa BCV actual, NO leyendo
        # las columnas purchase_price_bs/selling_price_bs (vestigiales, solo se escriben una
        # vez al crear el producto — ver docs/specs/precios-estables-bs.md sección 2 y 7.3).
        # El precio de compra siempre sigue la tasa actual; el de venta respeta el precio
        # estable en Bs de los productos en modo 'bs_fixed'.
        latest_rate = ExchangeRate.get_latest_rate()
        rate = latest_rate.bs_to_usd if latest_rate else Decimal('0')
        money_field = DecimalField(max_digits=20, decimal_places=5)

        total_value = Product.objects.filter(is_active=True).aggregate(
            purchase_value=Sum(
                F('stock') * F('purchase_price_usd') * Value(rate, output_field=money_field),
                output_field=money_field,
            ),
            selling_value=Sum(
                F('stock') * Case(
                    When(pricing_mode=Product.PRICING_MODE_BS_FIXED, then=F('selling_price_bs')),
                    default=F('selling_price_usd') * Value(rate, output_field=money_field),
                    output_field=money_field,
                ),
                output_field=money_field,
            ),
        )

        return JsonResponse({
            'summary': {
                'total_products': total_products,
                'out_of_stock': out_of_stock,
                'low_stock': low_stock,
                'normal_stock': total_products - out_of_stock - low_stock,
                'total_purchase_value': float(total_value['purchase_value'] or 0),
                'total_selling_value': float(total_value['selling_value'] or 0),
            }
        })
        
    except Exception as e:
        return JsonResponse(
            {'error': f'Error al obtener resumen de stock: {str(e)}'}, 
            status=500
        )

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def combo_search_api(request):
    """API mejorada para buscar combos de productos"""
    try:
        query = request.GET.get('q', '').strip()
        active_only = request.GET.get('active', 'true').lower() == 'true'
        limit = min(int(request.GET.get('limit', 10)), 50)
        
        if not query:
            return JsonResponse({'combos': []})
            
        combos = ProductCombo.objects.select_related().filter(
            name__icontains=query
        )
        
        if active_only:
            combos = combos.filter(is_active=True)
            
        combos = combos.order_by('name')[:limit]
        
        results = []
        for combo in combos:
            # Verificar disponibilidad de stock para todos los items
            items_available = all(
                item.product.stock >= item.quantity 
                for item in combo.items.all()
            )
            
            results.append({
                'id': combo.id,
                'name': combo.name,
                'description': combo.description,
                'combo_price_bs': float(combo.combo_price_bs),
                'total_individual_price': None,
                'savings_amount': None,
                'savings_percentage': None,
                'is_active': combo.is_active,
                'stock_available': items_available,
                'item_count': combo.items.count(),
            })
        
        return JsonResponse({
            'combos': results,
            'count': len(results)
        })
        
    except Exception as e:
        return JsonResponse(
            {'error': f'Error en búsqueda de combos: {str(e)}'}, 
            status=500
        )

# Nuevas APIs para funcionalidades avanzadas

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_barcode_api(request):
    """API para generar códigos de barras únicos"""
    try:
        import time
        import random
        
        # Generar código único basado en timestamp y random
        timestamp = str(int(time.time()))[-8:]
        random_num = str(random.randint(100, 999))
        barcode = f"{timestamp}{random_num}"
        
        # Verificar que no exista
        while Product.objects.filter(barcode=barcode).exists():
            random_num = str(random.randint(100, 999))
            barcode = f"{timestamp}{random_num}"
        
        return JsonResponse({
            'barcode': barcode,
            'valid': True
        })
        
    except Exception as e:
        return JsonResponse(
            {'error': f'Error al generar código de barras: {str(e)}'}, 
            status=500
        )

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def product_suggestions_api(request):
    """API para sugerir productos basado en patrones de uso"""
    try:
        # Esta función podría implementar lógica más avanzada
        # Por ahora, devuelve productos más vendidos o con stock bajo
        
        query = request.GET.get('q', '').strip()
        suggestion_type = request.GET.get('type', 'popular')  # 'popular', 'low_stock', 'new'
        limit = min(int(request.GET.get('limit', 5)), 20)
        
        products = Product.objects.filter(is_active=True).select_related('category')
        
        if query:
            products = products.filter(name__icontains=query)
        
        if suggestion_type == 'low_stock':
            products = products.filter(stock__lte=F('min_stock')).order_by('stock')
        elif suggestion_type == 'new':
            products = products.order_by('-created_at')
        else:  # popular - por ahora ordenar por stock alto
            products = products.order_by('-stock')
        
        products = products[:limit]
        
        suggestions = []
        for product in products:
            suggestions.append({
                'id': product.id,
                'name': product.name,
                'barcode': product.barcode,
                'category': product.category.name,
                'stock': float(product.stock),
                'price': float(product.get_current_price_bs()),
                'reason': suggestion_type
            })
        
        return JsonResponse({
            'suggestions': suggestions,
            'type': suggestion_type
        })
        
    except Exception as e:
        return JsonResponse(
            {'error': f'Error al obtener sugerencias: {str(e)}'}, 
            status=500
        )