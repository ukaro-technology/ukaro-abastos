# inventory/views.py - CON RESTRICCIONES DE ROLES (Solo Administradores)

from django import forms
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import F, Sum, Count
from django.core.paginator import Paginator
from django.db import transaction
from decimal import Decimal, InvalidOperation

from .models import Category, Product, InventoryAdjustment, ProductCombo, ComboItem
from .forms import (CategoryForm, ProductForm, InventoryAdjustmentForm,
                   ProductComboForm, ComboItemFormset)
from utils.decorators import admin_required, inventory_access_required

# Vistas de Productos - Empleados y Administradores (Solo Lectura para Empleados)
@inventory_access_required
def product_list(request):
    """Vista para listar productos - Empleados y Administradores (Solo Lectura para Empleados)"""
    # Filtros
    category_id = request.GET.get('category')
    search_query = request.GET.get('q')
    stock_filter = request.GET.get('stock')

    # Consulta base — solo productos activos, con category precargada
    products = Product.objects.select_related('category').filter(is_active=True)

    # Aplicar filtros
    if category_id:
        products = products.filter(category_id=category_id)

    if search_query:
        products = products.filter(
            name__icontains=search_query
        ) | products.filter(
            barcode__icontains=search_query
        ) | products.filter(
            description__icontains=search_query
        )

    if stock_filter == 'low':
        products = products.filter(stock__lte=F('min_stock'))
    elif stock_filter == 'out':
        products = products.filter(stock=0)

    # Ordenar
    products = products.order_by('category__name', 'name')

    # Paginación
    paginator = Paginator(products, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Obtener categorías para filtro
    categories = Category.objects.all().order_by('name')

    # ⭐ NUEVO: Pasar información de permisos
    is_admin = request.user.is_admin or request.user.is_superuser

    return render(request, 'inventory/product_list.html', {
        'page_obj': page_obj,
        'categories': categories,
        'selected_category': int(category_id) if category_id else None,
        'search_query': search_query,
        'stock_filter': stock_filter,
        'is_admin': is_admin,  # ⭐ NUEVO: Para controlar botones de edición
    })

@inventory_access_required
def product_detail(request, pk):
    """Vista para ver detalles de un producto - Empleados y Administradores (Solo Lectura para Empleados)"""
    product = get_object_or_404(Product, pk=pk)

    # Obtener historial de ajustes
    adjustments = product.adjustments.select_related('adjusted_by').order_by('-adjusted_at')[:10]

    # Obtener historial de ventas
    sales = product.sale_items.select_related('sale__customer').order_by('-sale__date')[:10]

    # ⭐ NUEVO: Pasar información de permisos
    is_admin = request.user.is_admin or request.user.is_superuser

    return render(request, 'inventory/product_detail.html', {
        'product': product,
        'adjustments': adjustments,
        'sales': sales,
        'is_admin': is_admin,  # ⭐ NUEVO: Para controlar botones de edición
    })

@admin_required
def product_create(request):
    """Vista para crear un nuevo producto - Solo Administradores"""
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            product = form.save()
            messages.success(request, f'Producto "{product.name}" creado exitosamente.')

            # Registrar ajuste inicial si se especificó stock
            initial_stock = request.POST.get('initial_stock')
            if initial_stock:
                try:
                    initial_stock_decimal = Decimal(str(initial_stock))

                    if initial_stock_decimal > 0:
                        with transaction.atomic():
                            product.stock = initial_stock_decimal
                            product.save()

                            InventoryAdjustment.objects.create(
                                product=product,
                                adjustment_type='set',
                                quantity=initial_stock_decimal,
                                previous_stock=Decimal('0'),
                                new_stock=initial_stock_decimal,
                                reason='Stock inicial',
                                adjusted_by=request.user
                            )
                except (InvalidOperation, ValueError) as e:
                    messages.warning(request, f'El stock inicial "{initial_stock}" no es válido. Se estableció en 0.')

            return redirect('inventory:product_detail', pk=product.pk)
    else:
        form = ProductForm()

    # ⭐ CORREGIDO: Obtener tasa de cambio actual para mostrar equivalente en Bs
    from utils.models import ExchangeRate
    latest_exchange_rate = ExchangeRate.get_latest_rate()

    return render(request, 'inventory/product_form.html', {
        'form': form,
        'title': 'Nuevo Producto',
        'show_initial_stock': True,
        'latest_exchange_rate': latest_exchange_rate,  # ⭐ NUEVO: Para mostrar conversión USD→Bs
    })

@admin_required
def product_update(request, pk):
    """Vista para actualizar un producto - Solo Administradores"""
    product = get_object_or_404(Product, pk=pk)

    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            form.save()
            messages.success(request, f'Producto "{product.name}" actualizado exitosamente.')
            return redirect('inventory:product_detail', pk=product.pk)
    else:
        form = ProductForm(instance=product)

    # ⭐ CORREGIDO: Obtener tasa de cambio actual para mostrar equivalente en Bs
    from utils.models import ExchangeRate
    latest_exchange_rate = ExchangeRate.get_latest_rate()

    return render(request, 'inventory/product_form.html', {
        'form': form,
        'product': product,
        'title': 'Editar Producto',
        'show_initial_stock': False,
        'latest_exchange_rate': latest_exchange_rate,  # ⭐ NUEVO: Para mostrar conversión USD→Bs
    })

@admin_required
def product_delete(request, pk):
    """Vista para eliminar un producto - Solo Administradores"""
    product = get_object_or_404(Product, pk=pk)
    
    if request.method == 'POST':
        product_name = product.name
        product.is_active = False
        product.save()
        
        messages.success(request, f'Producto "{product_name}" desactivado exitosamente.')
        return redirect('inventory:product_list')
    
    return render(request, 'inventory/product_confirm_delete.html', {
        'product': product
    })

# Vistas de Categorías - Empleados y Administradores (Solo Lectura para Empleados)
@inventory_access_required
def category_list(request):
    """Vista para listar categorías - Empleados y Administradores (Solo Lectura para Empleados)"""
    # Una sola query con COUNT en lugar de N+1
    categories_qs = Category.objects.annotate(
        product_count=Count('products')
    ).order_by('name')
    categories_with_count = [
        {'category': c, 'product_count': c.product_count}
        for c in categories_qs
    ]

    # ⭐ NUEVO: Pasar información de permisos
    is_admin = request.user.is_admin or request.user.is_superuser

    return render(request, 'inventory/category_list.html', {
        'categories': categories_with_count,
        'is_admin': is_admin,  # ⭐ NUEVO: Para controlar botones de edición
    })

@inventory_access_required
def category_detail(request, pk):
    """Vista para ver detalles de una categoría - Empleados y Administradores (Solo Lectura para Empleados)"""
    category = get_object_or_404(Category, pk=pk)
    products = Product.objects.filter(category=category).order_by('name')

    # ⭐ NUEVO: Pasar información de permisos
    is_admin = request.user.is_admin or request.user.is_superuser

    return render(request, 'inventory/category_detail.html', {
        'category': category,
        'products': products,
        'is_admin': is_admin,  # ⭐ NUEVO: Para controlar botones de edición
    })

@admin_required
def category_create(request):
    """Vista para crear una nueva categoría - Solo Administradores"""
    if request.method == 'POST':
        form = CategoryForm(request.POST)
        if form.is_valid():
            category = form.save()
            messages.success(request, f'Categoría "{category.name}" creada exitosamente.')
            return redirect('inventory:category_list')
    else:
        form = CategoryForm()
    
    return render(request, 'inventory/category_form.html', {
        'form': form,
        'title': 'Nueva Categoría'
    })

@admin_required
def category_update(request, pk):
    """Vista para actualizar una categoría - Solo Administradores"""
    category = get_object_or_404(Category, pk=pk)
    
    if request.method == 'POST':
        form = CategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            messages.success(request, f'Categoría "{category.name}" actualizada exitosamente.')
            return redirect('inventory:category_list')
    else:
        form = CategoryForm(instance=category)
    
    return render(request, 'inventory/category_form.html', {
        'form': form,
        'category': category,
        'title': 'Editar Categoría'
    })

@admin_required
def category_delete(request, pk):
    """Vista para eliminar una categoría - Solo Administradores"""
    category = get_object_or_404(Category, pk=pk)
    
    if Product.objects.filter(category=category).exists():
        messages.error(request, f'No se puede eliminar la categoría "{category.name}" porque tiene productos asociados.')
        return redirect('inventory:category_list')
    
    if request.method == 'POST':
        category_name = category.name
        category.delete()
        messages.success(request, f'Categoría "{category_name}" eliminada exitosamente.')
        return redirect('inventory:category_list')
    
    return render(request, 'inventory/category_confirm_delete.html', {
        'category': category
    })

# Vistas de Ajustes de Inventario - Solo Administradores
@admin_required
def adjustment_list(request):
    """Vista para listar ajustes de inventario - Solo Administradores"""
    adjustments = InventoryAdjustment.objects.select_related('product', 'adjusted_by').order_by('-adjusted_at')
    
    product_id = request.GET.get('product')
    adjustment_type = request.GET.get('type')
    
    if product_id:
        adjustments = adjustments.filter(product_id=product_id)
    
    if adjustment_type:
        adjustments = adjustments.filter(adjustment_type=adjustment_type)
    
    paginator = Paginator(adjustments, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'inventory/adjustment_list.html', {
        'page_obj': page_obj,
        'selected_product': int(product_id) if product_id else None,
        'selected_type': adjustment_type,
    })

@admin_required
def adjustment_create(request):
    """Vista para crear un nuevo ajuste de inventario - Solo Administradores"""
    if request.method == 'POST':
        form = InventoryAdjustmentForm(request.POST, user=request.user)
        if form.is_valid():
            try:
                adjustment = form.save()
                messages.success(request, 'Ajuste de inventario realizado exitosamente.')
                return redirect('inventory:product_detail', pk=adjustment.product.pk)
            except forms.ValidationError as e:
                messages.error(request, str(e))
    else:
        product_id = request.GET.get('product')
        initial = {}
        if product_id:
            try:
                product = Product.objects.get(pk=product_id)
                initial['product'] = product
            except Product.DoesNotExist:
                pass
        
        form = InventoryAdjustmentForm(initial=initial, user=request.user)
    
    return render(request, 'inventory/adjustment_form.html', {
        'form': form,
        'title': 'Nuevo Ajuste de Inventario'
    })

# Vistas de Combos - Solo Administradores
@admin_required
def combo_list(request):
    """Vista para listar combos de productos - Solo Administradores"""
    search_query = request.GET.get('q')
    active_filter = request.GET.get('active')
    
    combos = ProductCombo.objects.all()
    
    if search_query:
        combos = combos.filter(name__icontains=search_query)
    
    if active_filter == 'active':
        combos = combos.filter(is_active=True)
    elif active_filter == 'inactive':
        combos = combos.filter(is_active=False)
    
    combos = combos.order_by('name')
    
    paginator = Paginator(combos, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'inventory/combo_list.html', {
        'page_obj': page_obj,
        'search_query': search_query,
        'active_filter': active_filter,
    })

@admin_required
def combo_detail(request, pk):
    """Vista para ver detalles de un combo - Solo Administradores"""
    combo = get_object_or_404(ProductCombo, pk=pk)
    items = combo.items.all().select_related('product')
    
    return render(request, 'inventory/combo_detail.html', {
        'combo': combo,
        'items': items,
    })

@admin_required
def combo_create(request):
    """Vista para crear un nuevo combo - Solo Administradores"""
    if request.method == 'POST':
        form = ProductComboForm(request.POST)
        formset = ComboItemFormset(request.POST)
        
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                combo = form.save()
                formset.instance = combo
                formset.save()
                
                messages.success(request, f'Combo "{combo.name}" creado exitosamente.')
                return redirect('inventory:combo_detail', pk=combo.pk)
        else:
            messages.error(request, 'Por favor corrige los errores en el formulario.')
    else:
        form = ProductComboForm()
        formset = ComboItemFormset()
    
    return render(request, 'inventory/combo_form.html', {
        'form': form,
        'formset': formset,
        'title': 'Nuevo Combo de Productos'
    })

@admin_required
def combo_update(request, pk):
    """Vista para actualizar un combo - Solo Administradores"""
    combo = get_object_or_404(ProductCombo, pk=pk)
    
    if request.method == 'POST':
        form = ProductComboForm(request.POST, instance=combo)
        formset = ComboItemFormset(request.POST, instance=combo)
        
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                form.save()
                formset.save()
                
                messages.success(request, f'Combo "{combo.name}" actualizado exitosamente.')
                return redirect('inventory:combo_detail', pk=combo.pk)
        else:
            messages.error(request, 'Por favor corrige los errores en el formulario.')
    else:
        form = ProductComboForm(instance=combo)
        formset = ComboItemFormset(instance=combo)
    
    return render(request, 'inventory/combo_form.html', {
        'form': form,
        'formset': formset,
        'combo': combo,
        'title': 'Editar Combo de Productos'
    })

@admin_required
def combo_delete(request, pk):
    """Vista para eliminar un combo - Solo Administradores"""
    combo = get_object_or_404(ProductCombo, pk=pk)
    
    if request.method == 'POST':
        combo_name = combo.name
        combo.delete()
        messages.success(request, f'Combo "{combo_name}" eliminado exitosamente.')
        return redirect('inventory:combo_list')
    
    return render(request, 'inventory/combo_confirm_delete.html', {
        'combo': combo
    })

@admin_required
def combo_toggle_status(request, pk):
    """Vista para activar/desactivar un combo - Solo Administradores"""
    combo = get_object_or_404(ProductCombo, pk=pk)
    
    combo.is_active = not combo.is_active
    combo.save()
    
    status = "activado" if combo.is_active else "desactivado"
    messages.success(request, f'Combo "{combo.name}" {status} exitosamente.')
    
    return redirect('inventory:combo_detail', pk=combo.pk)