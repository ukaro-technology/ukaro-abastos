# customers/views.py - CON RESTRICCIONES DE ROLES

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Sum, F, Q
from django.core.paginator import Paginator
from django.db import transaction
from decimal import Decimal

from .models import Customer, CustomerCredit, CreditPayment, CustomerGeneralPayment
from .forms import CustomerForm, CreditForm, CreditPaymentForm, CustomerGeneralPaymentForm
from sales.models import Sale
from utils.decorators import admin_required, employee_or_admin_required, customer_access_required
from utils.models import ExchangeRate

@customer_access_required
def customer_list(request):
    """Vista para listar clientes - Empleados y Administradores"""
    # Filtros
    search_query = request.GET.get('q')
    credit_filter = request.GET.get('credit')
    
    # Consulta base
    customers = Customer.objects.all()
    
    # Aplicar filtros
    if search_query:
        customers = customers.filter(
            Q(name__icontains=search_query) |
            Q(phone__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(cedula__icontains=search_query)
        )
    
    if credit_filter == 'with_credit':
        customers = customers.filter(credit_limit_usd__gt=0)
    elif credit_filter == 'with_pending':
        customers_with_pending = CustomerCredit.objects.filter(
            is_paid=False
        ).values_list('customer_id', flat=True).distinct()
        
        customers = customers.filter(id__in=customers_with_pending)
    
    # Ordenar
    customers = customers.order_by('name')
    
    # Paginación
    paginator = Paginator(customers, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'customers/customer_list.html', {
        'page_obj': page_obj,
        'search_query': search_query,
        'credit_filter': credit_filter,
        'is_admin': request.user.is_admin or request.user.is_superuser,
    })

@customer_access_required
def customer_detail(request, pk):
    """Vista para ver detalles de un cliente - Empleados y Administradores"""
    customer = get_object_or_404(Customer, pk=pk)

    current_rate = ExchangeRate.get_latest_rate()
    rate_value = current_rate.bs_to_usd if current_rate else Decimal('36.00')

    # Obtener créditos y anotar monto Bs a tasa actual
    credits = list(customer.credits.all().order_by('-date_created'))
    for c in credits:
        c.amount_bs_current = round(c.amount_usd * rate_value, 2)

    # Obtener historial de ventas
    sales = Sale.objects.filter(customer=customer).order_by('-date')

    # Si es empleado, solo mostrar sus propias ventas
    if not (request.user.is_admin or request.user.is_superuser):
        sales = sales.filter(user=request.user)

    sales = sales[:10]

    return render(request, 'customers/customer_detail.html', {
        'customer': customer,
        'credits': credits,
        'sales': sales,
        'is_admin': request.user.is_admin or request.user.is_superuser,
        'current_rate': current_rate,
    })

@customer_access_required
def customer_create(request):
    """Vista para crear un nuevo cliente - Empleados y Administradores"""
    if request.method == 'POST':
        form = CustomerForm(request.POST)
        if form.is_valid():
            customer = form.save()
            messages.success(request, f'Cliente "{customer.name}" creado exitosamente.')
            return redirect('customers:customer_detail', pk=customer.pk)
    else:
        form = CustomerForm()
    
    return render(request, 'customers/customer_form.html', {
        'form': form,
        'title': 'Nuevo Cliente'
    })

@customer_access_required
def customer_update(request, pk):
    """Vista para actualizar un cliente - Empleados y Administradores"""
    customer = get_object_or_404(Customer, pk=pk)
    
    if request.method == 'POST':
        form = CustomerForm(request.POST, instance=customer)
        if form.is_valid():
            form.save()
            messages.success(request, f'Cliente "{customer.name}" actualizado exitosamente.')
            return redirect('customers:customer_detail', pk=customer.pk)
    else:
        form = CustomerForm(instance=customer)
    
    return render(request, 'customers/customer_form.html', {
        'form': form,
        'customer': customer,
        'title': 'Editar Cliente'
    })

@admin_required
def customer_delete(request, pk):
    """Vista para eliminar un cliente - Solo Administradores"""
    customer = get_object_or_404(Customer, pk=pk)
    
    # Verificar si hay ventas o créditos asociados
    if Sale.objects.filter(customer=customer).exists() or CustomerCredit.objects.filter(customer=customer).exists():
        messages.error(
            request, 
            f'No se puede eliminar el cliente "{customer.name}" porque tiene ventas o créditos asociados.'
        )
        return redirect('customers:customer_detail', pk=customer.pk)
    
    if request.method == 'POST':
        customer_name = customer.name
        customer.delete()
        messages.success(request, f'Cliente "{customer_name}" eliminado exitosamente.')
        return redirect('customers:customer_list')
    
    return render(request, 'customers/customer_confirm_delete.html', {
        'customer': customer
    })

@admin_required
def credit_list(request):
    """Vista para listar créditos de clientes - Solo Administradores"""
    # Filtros
    customer_id = request.GET.get('customer')
    status = request.GET.get('status')
    
    # Consulta base
    credits = CustomerCredit.objects.all()
    
    # Aplicar filtros
    if customer_id:
        credits = credits.filter(customer_id=customer_id)
    
    if status == 'pending':
        credits = credits.filter(is_paid=False)
    elif status == 'paid':
        credits = credits.filter(is_paid=True)
    elif status == 'overdue':
        today = timezone.now().date()
        credits = credits.filter(is_paid=False, date_due__lt=today)
    
    # Ordenar
    credits = credits.order_by('-date_created')
    
    # Paginación
    paginator = Paginator(credits, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Obtener clientes para el filtro
    customers = Customer.objects.filter(
        is_active=True
    ).order_by('name')

    # ⭐ NUEVO: Calcular montos en Bs a tasa actual
    from utils.models import ExchangeRate
    from decimal import Decimal
    current_rate = ExchangeRate.get_latest_rate()
    rate_value = current_rate.bs_to_usd if current_rate else Decimal('36.00')

    for credit in page_obj:
        # Calcular saldo pendiente en USD
        total_paid_usd = credit.payments.aggregate(total=Sum('amount_usd'))['total'] or Decimal('0.00')
        pending_amount_usd = credit.amount_usd - total_paid_usd
        
        # Calcular equivalentes en Bs
        credit.amount_bs_current = round(credit.amount_usd * rate_value, 2)
        credit.pending_amount_bs_current = round(pending_amount_usd * rate_value, 2)
    
    return render(request, 'customers/credit_list.html', {
        'page_obj': page_obj,
        'customers': customers,
        'selected_customer': int(customer_id) if customer_id else None,
        'status': status,
        'current_rate': current_rate,
    })

@customer_access_required
def credit_detail(request, pk):
    """Vista para ver detalles de un crédito - Empleados y Administradores"""
    credit = get_object_or_404(CustomerCredit, pk=pk)

    # Obtener pagos
    payments = credit.payments.all().order_by('-payment_date')

    # ⭐ CORREGIDO: Calcular saldo pendiente EN USD (fuente de verdad)
    from decimal import Decimal
    total_paid_usd = payments.aggregate(total=Sum('amount_usd'))['total'] or Decimal('0.00')
    pending_amount_usd = credit.amount_usd - total_paid_usd

    # ⭐ NUEVO: Tasa actual para calcular cuántos Bs debe pagar HOY
    from utils.models import ExchangeRate
    current_rate = ExchangeRate.get_latest_rate()

    rate_value = current_rate.bs_to_usd if current_rate else Decimal('36.00')
    pending_amount_bs_current = round(pending_amount_usd * rate_value, 2)
    total_paid_bs = round(total_paid_usd * rate_value, 2)
    credit_amount_bs_current = round(credit.amount_usd * rate_value, 2)

    # Anotar cada pago con su equivalente Bs a tasa actual
    payments_list = list(payments)
    for p in payments_list:
        p.amount_bs_current = round(p.amount_usd * rate_value, 2)

    return render(request, 'customers/credit_detail.html', {
        'credit': credit,
        'payments': payments_list,
        'credit_amount_bs_current': credit_amount_bs_current,
        'total_paid': total_paid_bs,
        'total_paid_bs': total_paid_bs,
        'total_paid_usd': total_paid_usd,
        'pending_amount': pending_amount_bs_current,
        'pending_amount_bs': pending_amount_bs_current,
        'pending_amount_bs_current': pending_amount_bs_current,
        'pending_amount_usd': pending_amount_usd,
        'current_rate': current_rate,
    })

@admin_required
def credit_create(request):
    """Vista para crear un nuevo crédito - Solo Administradores"""
    if request.method == 'POST':
        form = CreditForm(request.POST)
        if form.is_valid():
            credit = form.save(commit=False)
            credit.save()
            messages.success(request, f'Crédito creado exitosamente para {credit.customer.name}.')
            return redirect('customers:credit_detail', pk=credit.pk)
    else:
        customer_id = request.GET.get('customer')
        initial = {}
        if customer_id:
            try:
                customer = Customer.objects.get(pk=customer_id)
                initial['customer'] = customer
            except Customer.DoesNotExist:
                pass
        
        form = CreditForm(initial=initial)
    
    return render(request, 'customers/credit_form.html', {
        'form': form,
        'title': 'Nuevo Crédito'
    })

@customer_access_required
def credit_payment(request, pk):
    """Vista para registrar pago de un crédito - Empleados y Administradores"""
    credit = get_object_or_404(CustomerCredit, pk=pk)

    # Verificar si el crédito ya está pagado
    if credit.is_paid:
        messages.error(request, 'Este crédito ya está completamente pagado.')
        return redirect('customers:credit_detail', pk=credit.pk)

    if request.method == 'POST':
        form = CreditPaymentForm(request.POST, credit=credit)
        if form.is_valid():
            current_rate = ExchangeRate.get_latest_rate()
            rate_value = current_rate.bs_to_usd if current_rate else Decimal('36.00')

            with transaction.atomic():
                # Re-leer el crédito con lock para evitar race condition
                credit = CustomerCredit.objects.select_for_update().get(pk=pk)

                if credit.is_paid:
                    messages.error(request, 'Este crédito ya fue pagado por otra transacción.')
                    return redirect('customers:credit_detail', pk=credit.pk)

                payment = form.save(commit=False)
                payment.credit = credit
                payment.received_by = request.user
                payment.exchange_rate_used = rate_value
                payment.amount_usd = round(payment.amount_bs / rate_value, 2)
                payment.save()

                total_paid_usd = credit.payments.aggregate(
                    total=Sum('amount_usd')
                )['total'] or Decimal('0.00')

                total_paid_rounded = round(total_paid_usd, 2)
                credit_amount_rounded = round(credit.amount_usd, 2)

                if total_paid_rounded >= credit_amount_rounded:
                    credit.is_paid = True
                    credit.date_paid = timezone.now()
                    credit.save()
                    messages.success(request, 'Crédito pagado completamente.')
                else:
                    remaining_usd = credit_amount_rounded - total_paid_rounded
                    remaining_bs_current = remaining_usd * rate_value
                    messages.success(
                        request,
                        f'Pago registrado exitosamente. Saldo pendiente: ${remaining_usd:.2f} USD (Bs {remaining_bs_current:.2f} a tasa actual)'
                    )

            return redirect('customers:customer_detail', pk=credit.customer.pk)
    else:
        form = CreditPaymentForm(credit=credit)

    # Calcular saldo pendiente en USD (fuente de verdad)
    total_paid_usd = credit.payments.aggregate(total=Sum('amount_usd'))['total'] or Decimal('0.00')
    pending_amount_usd = credit.amount_usd - total_paid_usd

    # Tasa actual para calcular cuántos Bs debe pagar HOY
    current_rate = ExchangeRate.get_latest_rate()

    # ⭐ CORREGIDO: Calcular cuántos Bs debe con la tasa ACTUAL (no la del crédito original)
    if current_rate:
        pending_amount_bs_current = round(pending_amount_usd * current_rate.bs_to_usd, 2)
        # También calcular cuánto se ha pagado en total para el template
        total_paid_bs = round(total_paid_usd * current_rate.bs_to_usd, 2)
    else:
        pending_amount_bs_current = round(pending_amount_usd * Decimal('36.00'), 2)
        total_paid_bs = round(total_paid_usd * Decimal('36.00'), 2)

    return render(request, 'customers/credit_payment.html', {
        'form': form,
        'credit': credit,
        'total_paid': total_paid_bs,  # ⭐ CORREGIDO: Bs equivalente del USD pagado con tasa actual
        'total_paid_bs': total_paid_bs,  # ⭐ COMPATIBILIDAD: Mismo valor con nombre alternativo
        'total_paid_usd': total_paid_usd,
        'pending_amount': pending_amount_bs_current,  # ⭐ CORREGIDO: Bs que debe pagar HOY con tasa actual
        'pending_amount_bs': pending_amount_bs_current,  # ⭐ COMPATIBILIDAD: Mismo valor con nombre alternativo
        'pending_amount_bs_current': pending_amount_bs_current,  # ⭐ COMPATIBILIDAD: Mismo valor con nombre original
        'pending_amount_usd': pending_amount_usd,
        'current_rate': current_rate,
        'title': 'Registrar Pago'
    })


# ─────────────────────────────────────────────
# PAGOS GENERALES FIFO
# ─────────────────────────────────────────────

def _apply_fifo_payment(general_payment, customer, rate):
    """Distribuye un pago general FIFO entre créditos pendientes del cliente (oldest first)."""
    remaining_usd = general_payment.amount_usd

    credits = CustomerCredit.objects.select_for_update().filter(
        customer=customer, is_paid=False
    ).order_by('date_created')

    for credit in credits:
        if remaining_usd < Decimal('0.01'):
            break

        paid_usd = credit.payments.aggregate(
            total=Sum('amount_usd')
        )['total'] or Decimal('0')
        owed_usd = round(credit.amount_usd - paid_usd, 2)

        if owed_usd <= 0:
            credit.is_paid = True
            credit.date_paid = timezone.now()
            credit.save()
            continue

        apply_usd = min(remaining_usd, owed_usd)
        apply_bs = round(apply_usd * rate, 2)

        CreditPayment.objects.create(
            credit=credit,
            amount_bs=apply_bs,
            amount_usd=apply_usd,
            exchange_rate_used=rate,
            payment_method=general_payment.payment_method,
            mobile_reference=general_payment.mobile_reference or '',
            received_by=general_payment.received_by,
            notes=general_payment.notes,
            general_payment=general_payment,
        )

        remaining_usd = round(remaining_usd - apply_usd, 2)

        if round(paid_usd + apply_usd, 2) >= round(credit.amount_usd, 2):
            credit.is_paid = True
            credit.date_paid = timezone.now()
            credit.save()


@customer_access_required
def customer_general_payment_create(request, pk):
    """Pago general FIFO contra deuda total de un cliente."""
    customer = get_object_or_404(Customer, pk=pk)
    total_owed_usd = customer.total_credit_used

    if total_owed_usd <= 0:
        messages.info(request, f'{customer.name} no tiene deuda pendiente.')
        return redirect('customers:customer_detail', pk=customer.pk)

    if request.method == 'POST':
        form = CustomerGeneralPaymentForm(request.POST, customer=customer)
        if form.is_valid():
            current_rate = ExchangeRate.get_latest_rate()
            rate_value = current_rate.bs_to_usd if current_rate else Decimal('36.00')
            amount_bs = form.cleaned_data['amount_bs']
            amount_usd = round(amount_bs / rate_value, 2)

            with transaction.atomic():
                gp = CustomerGeneralPayment.objects.create(
                    customer=customer,
                    amount_bs=amount_bs,
                    amount_usd=amount_usd,
                    exchange_rate_used=rate_value,
                    payment_method=form.cleaned_data['payment_method'],
                    mobile_reference=form.cleaned_data.get('mobile_reference') or '',
                    received_by=request.user,
                    notes=form.cleaned_data.get('notes') or '',
                )
                _apply_fifo_payment(gp, customer, rate_value)

            messages.success(request, f'Pago de Bs {amount_bs:.2f} registrado y distribuido exitosamente.')
            return redirect('customers:customer_detail', pk=customer.pk)
    else:
        form = CustomerGeneralPaymentForm(customer=customer)

    current_rate = ExchangeRate.get_latest_rate()
    rate_value = current_rate.bs_to_usd if current_rate else Decimal('36.00')
    total_owed_bs = round(Decimal(str(total_owed_usd)) * rate_value, 2)

    pending_credits = list(
        CustomerCredit.objects.filter(customer=customer, is_paid=False)
        .order_by('date_created')
        .prefetch_related('payments')
    )
    for credit in pending_credits:
        paid = credit.payments.aggregate(total=Sum('amount_usd'))['total'] or Decimal('0')
        credit.owed_usd = max(Decimal('0'), round(credit.amount_usd - Decimal(str(paid)), 2))
        credit.owed_bs = round(credit.owed_usd * rate_value, 2)

    return render(request, 'customers/general_payment_form.html', {
        'form': form,
        'customer': customer,
        'total_owed_usd': total_owed_usd,
        'total_owed_bs': total_owed_bs,
        'pending_credits': pending_credits,
        'current_rate': current_rate,
    })