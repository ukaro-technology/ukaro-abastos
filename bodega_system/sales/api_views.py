# sales/api_views.py - API CON CÁLCULO USD A BS

import json
from decimal import Decimal, InvalidOperation
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.core.exceptions import PermissionDenied

from .models import Sale, SaleItem
from inventory.models import Product, InventoryAdjustment, ProductCombo
from customers.models import Customer, CustomerCredit
from utils.models import ExchangeRate
from utils.decorators import sales_access_required

@require_POST
@sales_access_required
def create_sale_api(request):
    """API para crear ventas con cálculo automático USD → Bs"""
    try:
        data = json.loads(request.body)
        
        if not data.get('items'):
            return JsonResponse({'error': 'No hay productos en la venta'}, status=400)
        
        # ⭐ OBTENER TASA DE CAMBIO ACTUAL
        current_exchange_rate = ExchangeRate.get_latest_rate()
        if not current_exchange_rate:
            return JsonResponse({
                'error': 'No hay tasa de cambio configurada. Contacte al administrador.'
            }, status=400)
        
        # Obtener cliente si se especificó
        customer = None
        if data.get('customer_id'):
            customer = get_object_or_404(Customer, pk=data['customer_id'])
        
        with transaction.atomic():
            # ⭐ CALCULAR TOTALES EN USD Y BS
            total_usd = Decimal('0.00')
            total_bs = Decimal('0.00')
            
            # Pre-calcular total para validar
            for item_data in data['items']:
                if item_data.get('is_combo', False):
                    # TODO: Implementar combos en USD después
                    combo = get_object_or_404(ProductCombo, pk=item_data['combo_id'])
                    quantity = Decimal(str(item_data.get('combo_quantity', 1)))
                    # Por ahora usar precio en Bs (se actualizará después)
                    item_total_bs = combo.combo_price_bs * quantity
                    total_bs += item_total_bs
                else:
                    product = get_object_or_404(Product, pk=item_data['product_id'])
                    quantity = Decimal(str(item_data['quantity']))

                    # ⭐ CALCULAR PRECIO USD Y BS (respeta precio al mayor y precio estable en Bs)
                    price_usd = product.get_current_price_usd(quantity, exchange_rate=current_exchange_rate)
                    price_bs = product.get_current_price_bs(quantity, exchange_rate=current_exchange_rate)

                    item_total_usd = price_usd * quantity
                    item_total_bs = price_bs * quantity
                    
                    total_usd += item_total_usd
                    total_bs += item_total_bs
            
            # ⭐ CREAR VENTA CON AMBOS TOTALES, TASA UTILIZADA Y MÉTODO DE PAGO
            sale = Sale.objects.create(
                customer=customer,
                user=request.user,
                total_usd=total_usd,
                total_bs=total_bs,
                exchange_rate_used=current_exchange_rate.bs_to_usd,
                is_credit=data.get('is_credit', False),
                notes=data.get('notes', ''),
                payment_method=data.get('payment_method', 'cash'),
                mobile_reference=data.get('mobile_reference') if data.get('payment_method') == 'mobile' else None
            )
            
            # Procesar ítems de venta
            for item_data in data['items']:
                if item_data.get('is_combo', False):
                    # Procesar venta de combo (mantener lógica actual)
                    result = process_combo_sale(sale, item_data, request.user, current_exchange_rate)
                    if not result['success']:
                        transaction.set_rollback(True)
                        return JsonResponse({'error': result['error']}, status=400)
                else:
                    # ⭐ PROCESAR VENTA REGULAR CON USD
                    result = process_regular_sale(sale, item_data, request.user, current_exchange_rate)
                    if not result['success']:
                        transaction.set_rollback(True)
                        return JsonResponse({'error': result['error']}, status=400)
            
            # Si es venta a crédito, crear el registro de crédito
            if sale.is_credit and customer:
                from datetime import datetime, timedelta
                due_date = datetime.now().date() + timedelta(days=30)

                # ⭐ CORREGIDO: Guardar USD y tasa de cambio del crédito
                CustomerCredit.objects.create(
                    customer=customer,
                    sale=sale,
                    amount_bs=sale.total_bs,              # Bs
                    amount_usd=sale.total_usd,            # ✅ USD
                    exchange_rate_used=sale.exchange_rate_used,  # ✅ Tasa utilizada
                    date_due=due_date,
                    notes=f'Crédito por venta #{sale.id}'
                )
            
            return JsonResponse({
                'id': sale.id,
                'message': 'Venta creada exitosamente',
                'total_usd': float(sale.total_usd),
                'total_bs': float(sale.total_bs),
                'exchange_rate': float(sale.exchange_rate_used),
                'user': request.user.get_full_name() or request.user.username
            })
            
    except PermissionDenied:
        return JsonResponse({'error': 'No tienes permisos para crear ventas'}, status=403)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def process_regular_sale(sale, item_data, user, exchange_rate):
    """Procesa venta regular con cálculo USD → Bs"""
    try:
        product = get_object_or_404(Product, pk=item_data['product_id'])
        
        # Convertir cantidad a Decimal
        try:
            if isinstance(item_data['quantity'], str):
                quantity_str = item_data['quantity'].replace(',', '.')
            else:
                quantity_str = str(item_data['quantity'])
            
            quantity = Decimal(quantity_str)
            
        except (InvalidOperation, ValueError):
            return {
                'success': False,
                'error': f'Cantidad inválida para {product.name}: {item_data["quantity"]}'
            }
        
        # Validar cantidad positiva
        if quantity <= 0:
            return {
                'success': False,
                'error': f'La cantidad debe ser mayor que 0 para {product.name}'
            }
        
        # Validar stock
        if product.stock < quantity:
            return {
                'success': False,
                'error': f'Stock insuficiente para {product.name}. '
                        f'Disponible: {product.stock} {product.unit_display}, '
                        f'Requerido: {quantity} {product.unit_display}'
            }
        
        # ⭐ CALCULAR PRECIOS USD Y BS (respeta precio al mayor y precio estable en Bs)
        price_usd = product.get_current_price_usd(quantity, exchange_rate=exchange_rate)
        price_bs = product.get_current_price_bs(quantity, exchange_rate=exchange_rate)
        
        # ⭐ CREAR ÍTEM CON AMBOS PRECIOS
        sale_item = SaleItem.objects.create(
            sale=sale,
            product=product,
            quantity=quantity,
            price_usd=price_usd,
            price_bs=price_bs
        )
        
        # Actualizar inventario
        previous_stock = product.stock
        product.stock -= quantity
        product.save()
        
        # Registrar ajuste de inventario
        InventoryAdjustment.objects.create(
            product=product,
            adjustment_type='remove',
            quantity=quantity,
            previous_stock=previous_stock,
            new_stock=product.stock,
            reason=f'Venta #{sale.id} - {user.get_full_name() or user.username}',
            adjusted_by=user
        )
        
        return {'success': True}
        
    except Exception as e:
        return {'success': False, 'error': str(e)}


def process_combo_sale(sale, item_data, user, exchange_rate):
    """Procesa venta de combo - MANTENER LÓGICA ACTUAL (pendiente actualizar)"""
    try:
        combo = get_object_or_404(ProductCombo, pk=item_data['combo_id'])
        
        # Convertir cantidad de combo a entero
        try:
            combo_quantity = int(item_data.get('combo_quantity', 1))
        except (ValueError, TypeError):
            return {
                'success': False,
                'error': f'Cantidad de combo inválida: {item_data.get("combo_quantity", 1)}'
            }
        
        if combo_quantity <= 0:
            return {
                'success': False,
                'error': 'La cantidad de combo debe ser mayor que 0'
            }
        
        # Validar stock para todos los productos del combo
        for combo_item in combo.items.all():
            required_quantity = combo_item.quantity * combo_quantity
            if combo_item.product.stock < required_quantity:
                return {
                    'success': False,
                    'error': f'Stock insuficiente para {combo_item.product.name} '
                            f'(necesario para combo {combo.name}). '
                            f'Disponible: {combo_item.product.stock}, '
                            f'Requerido: {required_quantity}'
                }
        
        # ⭐ CREAR ÍTEM DE COMBO (mantener precio en Bs por ahora)
        SaleItem.objects.create(
            sale=sale,
            combo=combo,
            quantity=combo_quantity,
            price_usd=Decimal('0.00'),  # TODO: Calcular cuando combos estén en USD
            price_bs=combo.combo_price_bs
        )
        
        # Actualizar inventario para cada producto del combo
        for combo_item in combo.items.all():
            product = combo_item.product
            quantity_to_remove = combo_item.quantity * combo_quantity
            
            previous_stock = product.stock
            product.stock -= quantity_to_remove
            product.save()
            
            # Registrar ajuste de inventario
            InventoryAdjustment.objects.create(
                product=product,
                adjustment_type='remove',
                quantity=quantity_to_remove,
                previous_stock=previous_stock,
                new_stock=product.stock,
                reason=f'Venta combo #{sale.id} - {combo.name} - {user.get_full_name() or user.username}',
                adjusted_by=user
            )
        
        return {'success': True}
        
    except Exception as e:
        return {'success': False, 'error': str(e)}