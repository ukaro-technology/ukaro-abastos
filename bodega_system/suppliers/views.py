# suppliers/views.py

# Python standard library
import logging
from decimal import Decimal

# Django core
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.http import JsonResponse
# Django DB
from django.db import transaction, IntegrityError
from django.db.models import Sum, Q
from django.core.paginator import Paginator

# Local imports
from .models import Supplier, SupplierOrder, SupplierOrderItem
from .forms import (
    SupplierForm,
    SupplierOrderForm,
    SupplierOrderItemFormset,
    ReceiveOrderForm
)
from inventory.models import Product, InventoryAdjustment, Category
from utils.decorators import admin_required, require_exchange_rate
from utils.models import ExchangeRate

# Logger
logger = logging.getLogger(__name__)

@login_required
def supplier_list(request):
    """Vista para listar proveedores"""
    # Filtros
    search_query = request.GET.get('q')
    
    # Consulta base
    suppliers = Supplier.objects.all()
    
    # Aplicar filtros
    if search_query:
        suppliers = suppliers.filter(
            Q(name__icontains=search_query) |
            Q(contact_person__icontains=search_query) |
            Q(phone__icontains=search_query) |
            Q(email__icontains=search_query)
        )
    
    # Ordenar
    suppliers = suppliers.order_by('name')
    
    # Paginación
    paginator = Paginator(suppliers, 20)  # 20 proveedores por página
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'suppliers/supplier_list.html', {
        'page_obj': page_obj,
        'search_query': search_query,
    })

@login_required
def supplier_detail(request, pk):
    """Vista para ver detalles de un proveedor"""
    supplier = get_object_or_404(Supplier, pk=pk)
    
    rate = ExchangeRate.get_latest_rate()
    rate_value = rate.bs_to_usd if rate else Decimal('36.00')

    # Obtener órdenes de compra y anotar con Bs actual
    orders = list(supplier.orders.all().order_by('-order_date')[:10])
    for o in orders:
        o.total_bs_current = round(o.total_usd * rate_value, 2)
    
    # Obtener productos suministrados por este proveedor
    product_data = []
    if orders:
        # Obtener los productos más recientes que se han pedido a este proveedor
        products_ordered = SupplierOrderItem.objects.filter(
            order__supplier=supplier
        ).values('product').annotate(
            total_ordered=Sum('quantity')
        ).order_by('-total_ordered')[:10]
        
        for item in products_ordered:
            try:
                product = Product.objects.get(pk=item['product'])
                # Obtener el último precio de compra de este producto a este proveedor
                last_order_item = SupplierOrderItem.objects.filter(
                    order__supplier=supplier,
                    product=product
                ).order_by('-order__order_date').first()
                
                if last_order_item:
                    rate = ExchangeRate.get_latest_rate()
                    rate_value = rate.bs_to_usd if rate else Decimal('36.00')
                    last_price = round(last_order_item.price_usd * rate_value, 2)
                else:
                    last_price = 0

                product_data.append({
                    'product': product,
                    'total_ordered': item['total_ordered'],
                    'last_price': last_price
                })
            except Product.DoesNotExist:
                pass
    
    return render(request, 'suppliers/supplier_detail.html', {
        'supplier': supplier,
        'orders': orders,
        'product_data': product_data,
    })

@login_required
def supplier_create(request):
    """Vista para crear un nuevo proveedor"""
    if request.method == 'POST':
        form = SupplierForm(request.POST)
        if form.is_valid():
            supplier = form.save()
            messages.success(request, f'Proveedor "{supplier.name}" creado exitosamente.')
            return redirect('suppliers:supplier_detail', pk=supplier.pk)
    else:
        form = SupplierForm()
    
    return render(request, 'suppliers/supplier_form.html', {
        'form': form,
        'title': 'Nuevo Proveedor'
    })

@login_required
def supplier_update(request, pk):
    """Vista para actualizar un proveedor"""
    supplier = get_object_or_404(Supplier, pk=pk)
    
    if request.method == 'POST':
        form = SupplierForm(request.POST, instance=supplier)
        if form.is_valid():
            form.save()
            messages.success(request, f'Proveedor "{supplier.name}" actualizado exitosamente.')
            return redirect('suppliers:supplier_detail', pk=supplier.pk)
    else:
        form = SupplierForm(instance=supplier)
    
    return render(request, 'suppliers/supplier_form.html', {
        'form': form,
        'supplier': supplier,
        'title': 'Editar Proveedor'
    })

@login_required
def supplier_delete(request, pk):
    """Vista para eliminar un proveedor"""
    supplier = get_object_or_404(Supplier, pk=pk)
    
    # Verificar si hay órdenes asociadas
    if SupplierOrder.objects.filter(supplier=supplier).exists():
        messages.error(
            request, 
            f'No se puede eliminar el proveedor "{supplier.name}" porque tiene órdenes asociadas.'
        )
        return redirect('suppliers:supplier_detail', pk=supplier.pk)
    
    if request.method == 'POST':
        supplier_name = supplier.name
        supplier.delete()
        messages.success(request, f'Proveedor "{supplier_name}" eliminado exitosamente.')
        return redirect('suppliers:supplier_list')
    
    return render(request, 'suppliers/supplier_confirm_delete.html', {
        'supplier': supplier
    })

@login_required
def order_list(request):
    """Vista para listar órdenes de compra"""
    # Filtros
    supplier_id = request.GET.get('supplier')
    status = request.GET.get('status')

    # Consulta base - ✅ OPTIMIZADO: Pre-cargar supplier y created_by
    orders = SupplierOrder.objects.select_related('supplier', 'created_by')

    # Aplicar filtros
    if supplier_id:
        orders = orders.filter(supplier_id=supplier_id)

    if status:
        orders = orders.filter(status=status)

    # Ordenar
    orders = orders.order_by('-order_date')
    
    # Paginación
    paginator = Paginator(orders, 20)  # 20 órdenes por página
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Obtener proveedores para el filtro
    suppliers = Supplier.objects.filter(
        is_active=True
    ).order_by('name')
    
    current_rate = ExchangeRate.get_latest_rate()
    rate_value = current_rate.bs_to_usd if current_rate else Decimal('36.00')
    for order in page_obj:
        order.total_bs_current = round(order.total_usd * rate_value, 2)

    return render(request, 'suppliers/order_list.html', {
        'page_obj': page_obj,
        'suppliers': suppliers,
        'selected_supplier': int(supplier_id) if supplier_id else None,
        'status': status,
        'current_rate': current_rate,
    })

@login_required
def order_detail(request, pk):
    """Vista para ver detalles de una orden"""
    order = get_object_or_404(
        SupplierOrder.objects.select_related('supplier', 'created_by')
                             .prefetch_related('items__product', 'payments__created_by'),
        pk=pk
    )

    current_rate = ExchangeRate.get_latest_rate()
    rate_value = current_rate.bs_to_usd if current_rate else Decimal('36.00')

    total_usd = order.calculate_total_usd()
    total_bs = round(total_usd * rate_value, 2)

    paid_amount_bs_current = round(order.paid_amount_usd * rate_value, 2)

    # Anotar items con precios Bs a tasa actual
    items = list(order.items.all())
    for item in items:
        item.price_bs_current = round(item.price_usd * rate_value, 2)
        item.subtotal_bs_current = round(item.subtotal_usd * rate_value, 2)

    # Anotar pagos con Bs a tasa actual
    payments = list(order.payments.all().order_by('payment_date'))
    for p in payments:
        p.amount_bs_current = round(p.amount_usd * rate_value, 2)

    return render(request, 'suppliers/order_detail.html', {
        'order': order,
        'items': items,
        'payments': payments,
        'total_usd': total_usd,
        'total_bs': total_bs,
        'paid_amount_bs_current': paid_amount_bs_current,
        'current_rate': current_rate,
    })

@login_required
@require_exchange_rate(redirect_url='suppliers:order_list')
def order_create(request, exchange_rate=None):
    """Vista para crear una nueva orden de compra"""
    if request.method == 'POST':
        form = SupplierOrderForm(request.POST, user=request.user)
        formset = SupplierOrderItemFormset(request.POST)

        logger.debug("Processing order creation", extra={
            'user_id': request.user.id,
            'form_valid': form.is_valid(),
            'formset_valid': formset.is_valid(),
        })

        if not form.is_valid():
            logger.warning("Order form validation failed", extra={
                'errors': str(form.errors),
                'user_id': request.user.id,
            })

        if not formset.is_valid():
            logger.warning("Order formset validation failed", extra={
                'errors': str(formset.errors),
                'non_form_errors': str(formset.non_form_errors()),
                'user_id': request.user.id,
            })

        if form.is_valid():
            if formset.is_valid():
                active_forms = [
                    f for f in formset.forms
                    if f.cleaned_data and not f.cleaned_data.get('DELETE', False)
                ]
                if not active_forms:
                    messages.error(request, 'Debe agregar al menos un producto a la orden.')
                    return render(request, 'suppliers/order_form.html', {
                        'form': form,
                        'formset': formset,
                        'title': 'Nueva Orden de Compra',
                        'current_exchange_rate': exchange_rate,
                        'categories': Category.objects.all().order_by('name'),
                        'unit_choices': Product.UNIT_TYPES,
                    })
                # exchange_rate ya está disponible por el decorator
                try:
                    with transaction.atomic():
                        # Guardar orden
                        order = form.save()

                        logger.info("Order created", extra={
                            'order_id': order.id,
                            'supplier_id': order.supplier_id,
                            'user_id': request.user.id,
                        })

                        # Procesar y guardar ítems de la orden
                        formset.instance = order

                        # Crear productos nuevos antes de guardar el formset
                        for form_item in formset.forms:
                            if form_item.cleaned_data and not form_item.cleaned_data.get('DELETE', False):
                                if form_item.cleaned_data.get('is_new_product'):
                                    barcode = form_item.cleaned_data.get('new_product_barcode', '?')
                                    try:
                                        new_product = _create_product_from_form(form_item, exchange_rate, request.user)
                                    except IntegrityError:
                                        messages.error(
                                            request,
                                            f'El código de barras "{barcode}" ya está registrado. '
                                            'Otro usuario lo creó mientras procesaba esta orden.'
                                        )
                                        return render(request, 'suppliers/order_form.html', {
                                            'form': form,
                                            'formset': formset,
                                            'title': 'Nueva Orden de Compra',
                                            'current_exchange_rate': exchange_rate,
                                            'categories': Category.objects.all().order_by('name'),
                                            'unit_choices': Product.UNIT_TYPES,
                                        })
                                    form_item.instance.product = new_product

                                    logger.info("New product created from order", extra={
                                        'product_id': new_product.id,
                                        'product_name': new_product.name,
                                        'order_id': order.id,
                                    })

                        formset.save()

                        # Calcular totales usando el método del modelo
                        order.update_totals()

                        logger.info("Order totals updated", extra={
                            'order_id': order.id,
                            'total_usd': float(order.total_usd),
                            'total_bs': float(order.total_bs),
                        })

                        # Si la orden se marca como "received", actualizar inventario automáticamente
                        if order.status == 'received':
                            result = _process_received_order(
                                order=order,
                                user=request.user,
                                update_prices=True,
                                notes='Orden creada directamente como recibida'
                            )
                            messages.success(
                                request,
                                f'Orden de compra #{order.id} creada y recibida exitosamente. '
                                f'${order.total_usd} USD. '
                                f'{result["products_count"]} productos actualizados en inventario.'
                            )
                        else:
                            messages.success(
                                request,
                                f'Orden de compra #{order.id} creada exitosamente por ${order.total_usd} USD.'
                            )

                        return redirect('suppliers:order_detail', pk=order.pk)

                except Exception as e:
                    logger.error("Error creating order", exc_info=True, extra={
                        'user_id': request.user.id,
                        'supplier_id': form.cleaned_data.get('supplier').id if form.cleaned_data.get('supplier') else None,
                    })
                    messages.error(request, f'Error al crear la orden: {str(e)}')

            else:
                messages.error(request, 'Error en los productos. Revise los datos de los productos.')
        else:
            messages.error(request, 'Error en los datos de la orden. Revise el proveedor y otros campos.')
    else:
        # Pre-seleccionar proveedor si se pasa por URL
        supplier_id = request.GET.get('supplier')
        initial = {}
        if supplier_id:
            try:
                supplier = Supplier.objects.get(pk=supplier_id)
                initial['supplier'] = supplier
            except Supplier.DoesNotExist:
                pass
        
        form = SupplierOrderForm(initial=initial, user=request.user)
        formset = SupplierOrderItemFormset()
    
    # Obtener categorías y opciones de unidad
    categories = Category.objects.all().order_by('name')
    unit_choices = Product.UNIT_TYPES

    return render(request, 'suppliers/order_form.html', {
        'form': form,
        'formset': formset,
        'title': 'Nueva Orden de Compra',
        'current_exchange_rate': exchange_rate,  # Inyectado por decorator
        'categories': categories,
        'unit_choices': unit_choices,
    })

@login_required
@require_exchange_rate(redirect_url='suppliers:order_list')
def order_update(request, pk, exchange_rate=None):
    """Vista para actualizar una orden de compra"""
    order = get_object_or_404(SupplierOrder, pk=pk)

    # No permitir editar órdenes recibidas
    if order.status == 'received':
        messages.error(request, 'No se puede editar una orden que ya ha sido recibida.')
        return redirect('suppliers:order_detail', pk=order.pk)

    if request.method == 'POST':
        form = SupplierOrderForm(request.POST, instance=order, user=request.user)
        formset = SupplierOrderItemFormset(request.POST, instance=order)

        if form.is_valid() and formset.is_valid():
            # exchange_rate ya está disponible por el decorator

            with transaction.atomic():
                # Guardar orden
                order = form.save()

                # Procesar y guardar ítems de la orden
                # Crear productos nuevos antes de guardar el formset
                for form_item in formset.forms:
                    if form_item.cleaned_data and not form_item.cleaned_data.get('DELETE', False):
                        if form_item.cleaned_data.get('is_new_product'):
                            # Crear el producto nuevo
                            new_product = _create_product_from_form(form_item, exchange_rate, request.user)
                            form_item.instance.product = new_product

                # Guardar ítems de la orden
                formset.save()

                # Actualizar totales usando el método del modelo
                order.update_totals()

                messages.success(request, 'Orden de compra actualizada exitosamente.')
                return redirect('suppliers:order_detail', pk=order.pk)
    else:
        form = SupplierOrderForm(instance=order, user=request.user)
        formset = SupplierOrderItemFormset(instance=order)

    # Obtener categorías y opciones de unidad
    from inventory.models import Category, Product
    import json
    categories = Category.objects.all().order_by('name')
    unit_choices = Product.UNIT_TYPES

    # Serializar ítems existentes para pre-cargar en Alpine.js
    existing_items = []
    for item in order.items.select_related('product', 'product__category').all():
        existing_items.append({
            'itemId': item.id,
            'productId': item.product.id,
            'name': item.product.name,
            'barcode': item.product.barcode or '',
            'quantity': float(item.quantity),
            'purchasePrice': float(item.price_usd),
            'sellingPrice': float(item.selling_price_usd) if item.selling_price_usd else float(item.product.selling_price_usd),
            'category': item.product.category.id if item.product.category else '',
            'unitType': item.product.unit_type,
            'isNew': False,
            'minStock': float(item.product.min_stock),
            'description': item.product.description or '',
        })

    return render(request, 'suppliers/order_form.html', {
        'form': form,
        'formset': formset,
        'order': order,
        'title': 'Editar Orden de Compra',
        'current_exchange_rate': exchange_rate,
        'categories': categories,
        'unit_choices': unit_choices,
        'existing_items_json': json.dumps(existing_items),
    })

@login_required
def order_receive(request, pk):
    """Vista para recibir una orden de compra"""
    order = get_object_or_404(SupplierOrder, pk=pk)

    if order.status == 'received':
        messages.error(request, 'Esta orden ya ha sido recibida.')
        return redirect('suppliers:order_detail', pk=order.pk)

    if request.method == 'POST':
        form = ReceiveOrderForm(request.POST)

        if form.is_valid():
            try:
                with transaction.atomic():
                    # Re-leer con lock para evitar doble recepción por race condition
                    order = SupplierOrder.objects.select_for_update().get(pk=pk)
                    if order.status == 'received':
                        messages.error(request, 'Esta orden ya fue recibida por otra transacción.')
                        return redirect('suppliers:order_detail', pk=order.pk)

                    # Obtener datos del formulario
                    update_prices = form.cleaned_data.get('update_prices', True)
                    notes = form.cleaned_data.get('notes', '').strip()

                    # Procesar la recepción (función unificada)
                    result = _process_received_order(
                        order=order,
                        user=request.user,
                        update_prices=update_prices,
                        notes=notes
                    )

                    # Mensaje de éxito detallado
                    product_names = [p['name'] for p in result['updated_products'][:3]]
                    products_summary = ', '.join(product_names)
                    if result['products_count'] > 3:
                        products_summary += f' y {result["products_count"] - 3} más'

                    messages.success(
                        request,
                        f'Orden #{order.id} recibida exitosamente. '
                        f'Productos actualizados: {products_summary}. '
                        f'Total ítems: {result["total_items_received"]}. '
                        f'Valor: ${order.total_usd} (Bs {order.total_bs})'
                    )

                    return redirect('suppliers:order_detail', pk=order.pk)

            except Exception as e:
                logger.error("Error receiving order", exc_info=True, extra={
                    'order_id': order.id,
                    'user_id': request.user.id,
                })
                messages.error(request, f'Error al recibir la orden: {str(e)}')

    else:
        form = ReceiveOrderForm()
    
    # Obtener ítems de la orden con información adicional
    items = order.items.all().select_related('product')
    
    # Información adicional para el template
    context = {
        'form': form,
        'order': order,
        'items': items,
        'title': f'Recibir Orden #{order.id}',
        'total_items_count': items.count(),
        'total_products_quantity': sum(item.quantity for item in items),
        'estimated_new_total': sum(item.product.stock + item.quantity for item in items),
    }
    
    return render(request, 'suppliers/order_receive.html', context)

@admin_required
def order_cancel(request, pk):
    """Vista para cancelar una orden de compra"""
    order = get_object_or_404(SupplierOrder, pk=pk)
    
    # No permitir cancelar órdenes recibidas
    if order.status == 'received':
        messages.error(request, 'No se puede cancelar una orden que ya ha sido recibida.')
        return redirect('suppliers:order_detail', pk=order.pk)
    
    if request.method == 'POST':
        # Actualizar estado de la orden
        order.status = 'cancelled'
        order.save()
        
        messages.success(request, 'Orden de compra cancelada exitosamente.')
        return redirect('suppliers:order_detail', pk=order.pk)
    
    return render(request, 'suppliers/order_confirm_cancel.html', {
        'order': order
    })

def _process_received_order(order, user, update_prices=True, notes=''):
    """
    Procesa una orden recibida y actualiza el inventario

    Args:
        order (SupplierOrder): La orden a procesar
        user (User): Usuario que procesa la recepción
        update_prices (bool): Si True, actualiza precios de compra de productos
        notes (str): Notas adicionales para los ajustes de inventario

    Returns:
        dict: Resumen de la recepción con productos actualizados y totales
    """
    from decimal import Decimal
    from django.utils import timezone

    # Marcar como recibida si no lo está
    if order.status != 'received':
        order.status = 'received'
        order.received_date = timezone.now()
        order.save()

    # Contadores para el resumen
    updated_products = []
    total_items_received = Decimal('0')

    # Procesar cada ítem de la orden
    for item in order.items.all():
        product = item.product
        previous_stock = product.stock

        # Asegurar que quantity sea Decimal
        quantity_to_add = Decimal(str(item.quantity))

        # Validación defensiva: cantidad debe ser positiva
        if quantity_to_add <= 0:
            raise ValueError(
                f"Cantidad inválida para producto {product.name}: {quantity_to_add}. "
                "Las cantidades deben ser mayores a cero."
            )

        total_items_received += quantity_to_add

        # Actualizar stock (ambos son Decimal)
        product.stock = previous_stock + quantity_to_add

        # Actualizar precios solo si se solicitó
        if update_prices:
            # Verificar si el producto tiene campos USD
            if hasattr(product, 'purchase_price_usd'):
                product.purchase_price_usd = item.price_usd

            # Actualizar precio en Bs
            product.purchase_price_bs = item.price_bs

            # Actualizar precio de venta si fue especificado en la orden
            if item.selling_price_usd is not None and item.selling_price_usd > 0:
                product.selling_price_usd = item.selling_price_usd

        product.save()

        # Registrar producto actualizado
        updated_products.append({
            'name': product.name,
            'quantity': quantity_to_add,
            'previous_stock': previous_stock,
            'new_stock': product.stock
        })

        # Registrar ajuste de inventario
        reason = f'Recepción orden #{order.id}'
        if notes:
            reason += f' - {notes}'

        InventoryAdjustment.objects.create(
            product=product,
            adjustment_type='add',
            quantity=quantity_to_add,
            previous_stock=previous_stock,
            new_stock=product.stock,
            reason=reason,
            adjusted_by=user
        )

        logger.info("Product updated from order reception", extra={
            'order_id': order.id,
            'product_id': product.id,
            'quantity_added': float(quantity_to_add),
            'previous_stock': float(previous_stock),
            'new_stock': float(product.stock),
            'prices_updated': update_prices,
        })

    return {
        'updated_products': updated_products,
        'total_items_received': total_items_received,
        'products_count': len(updated_products)
    }

def _create_product_from_form(form, exchange_rate, created_by=None):
    """
    Helper para crear un producto nuevo desde el formulario

    DEPRECATED: Esta función ahora delega al ProductService.
    Se mantiene por compatibilidad pero usa el service layer internamente.
    """
    from inventory.services import ProductService

    return ProductService.create_product_from_order_form(
        form=form,
        exchange_rate=exchange_rate,
        created_by=created_by
    )


@login_required
def product_lookup_api(request, barcode):
    """API endpoint para buscar productos por código de barras"""
    try:
        product = Product.objects.get(barcode=barcode, is_active=True)
        
        return JsonResponse({
            'exists': True,
            'id': product.id,
            'name': product.name,
            'barcode': product.barcode,
            'category': product.category.id,
            'category_name': product.category.name,
            'unit_type': product.unit_type,
            'purchase_price_usd': str(product.purchase_price_usd),
            'selling_price_usd': str(product.selling_price_usd),
            'stock': str(product.stock),
            'min_stock': str(product.min_stock),
            'description': product.description or '',
        })
    except Product.DoesNotExist:
        return JsonResponse({'exists': False, 'product': None}, status=404)


# ============================================================================
# VISTAS DE PAGOS A PROVEEDORES
# ============================================================================

@login_required
@admin_required
def payment_create(request, order_id):
    """Vista para registrar un nuevo pago a proveedor"""
    from .models import SupplierPayment
    from .forms import SupplierPaymentForm

    order = get_object_or_404(SupplierOrder, pk=order_id)

    # Verificar que la orden tenga saldo pendiente
    if order.payment_status == 'paid':
        messages.warning(request, 'Esta orden ya está completamente pagada.')
        return redirect('suppliers:order_detail', pk=order.pk)

    if request.method == 'POST':
        form = SupplierPaymentForm(request.POST, order=order, user=request.user)

        if form.is_valid():
            try:
                with transaction.atomic():
                    payment = form.save()

                    logger.info("Payment registered", extra={
                        'payment_id': payment.id,
                        'order_id': order.id,
                        'amount_usd': float(payment.amount_usd),
                        'amount_bs': float(payment.amount_bs),
                        'user_id': request.user.id,
                    })

                    messages.success(
                        request,
                        f'Pago registrado exitosamente: ${payment.amount_usd} USD. '
                        f'Saldo pendiente: ${order.outstanding_balance_usd} USD.'
                    )

                    return redirect('suppliers:order_detail', pk=order.pk)

            except Exception as e:
                logger.error("Error creating payment", exc_info=True, extra={
                    'order_id': order.id,
                    'user_id': request.user.id,
                })
                messages.error(request, f'Error al registrar el pago: {str(e)}')

    else:
        # Pre-cargar el monto con el saldo pendiente
        initial_data = {
            'amount_usd': order.outstanding_balance_usd
        }
        form = SupplierPaymentForm(initial=initial_data, order=order, user=request.user)

    context = {
        'form': form,
        'order': order,
        'title': f'Registrar Pago - Orden #{order.id}',
        'outstanding_balance': order.outstanding_balance_usd,
    }

    return render(request, 'suppliers/payment_form.html', context)


@login_required
def payment_list(request, order_id):
    """Vista para listar los pagos de una orden"""
    order = get_object_or_404(SupplierOrder, pk=order_id)

    current_rate = ExchangeRate.get_latest_rate()
    rate_value = current_rate.bs_to_usd if current_rate else Decimal('36.00')

    payments = list(order.payments.all().order_by('-payment_date'))
    for p in payments:
        p.amount_bs_current = round(p.amount_usd * rate_value, 2)

    context = {
        'order': order,
        'payments': payments,
        'current_rate': current_rate,
        'title': f'Pagos - Orden #{order.id}',
    }

    return render(request, 'suppliers/payment_list.html', context)


@login_required
@admin_required
def payment_delete(request, pk):
    """Vista para eliminar un pago"""
    from .models import SupplierPayment

    payment = get_object_or_404(SupplierPayment, pk=pk)
    order = payment.order

    if request.method == 'POST':
        try:
            with transaction.atomic():
                amount = payment.amount_usd
                payment_id = payment.id

                payment.delete()

                logger.info("Payment deleted", extra={
                    'payment_id': payment_id,
                    'order_id': order.id,
                    'amount_usd': float(amount),
                    'user_id': request.user.id,
                })

                messages.success(
                    request,
                    f'Pago de ${amount} USD eliminado exitosamente. '
                    f'Saldo pendiente actualizado: ${order.outstanding_balance_usd} USD.'
                )

        except Exception as e:
            logger.error("Error deleting payment", exc_info=True, extra={
                'payment_id': pk,
                'user_id': request.user.id,
            })
            messages.error(request, f'Error al eliminar el pago: {str(e)}')

        return redirect('suppliers:order_detail', pk=order.pk)

    context = {
        'payment': payment,
        'order': order,
        'title': 'Eliminar Pago',
    }

    return render(request, 'suppliers/payment_confirm_delete.html', context)