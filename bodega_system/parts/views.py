# parts/views.py - GESTIÓN DE MARCAS Y MODELOS DE MOTO

from django.contrib import messages
from django.db.models import Count, Prefetch
from django.shortcuts import get_object_or_404, redirect, render

from utils.decorators import admin_required

from .forms import MotoBrandForm, MotoModelForm
from .models import MotoBrand, MotoModel


@admin_required
def moto_list(request):
    """Lista de marcas y modelos de moto, con formularios para agregar - Solo Administradores"""
    brand_form = MotoBrandForm(prefix='brand')
    model_form = MotoModelForm(prefix='model')

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add_brand':
            brand_form = MotoBrandForm(request.POST, prefix='brand')
            if brand_form.is_valid():
                brand = brand_form.save()
                messages.success(request, f'Marca "{brand.name}" agregada.')
                return redirect('parts:moto_list')
        elif action == 'add_model':
            model_form = MotoModelForm(request.POST, prefix='model')
            if model_form.is_valid():
                moto = model_form.save()
                messages.success(request, f'Modelo "{moto}" agregado.')
                return redirect('parts:moto_list')
        elif action == 'delete_model':
            moto = get_object_or_404(MotoModel, pk=request.POST.get('model_id'))
            name = str(moto)
            moto.delete()
            messages.success(request, f'Modelo "{name}" eliminado.')
            return redirect('parts:moto_list')

    brands = MotoBrand.objects.annotate(model_count=Count('models')).prefetch_related(
        Prefetch('models', queryset=MotoModel.objects.annotate(part_count=Count('parts')))
    )

    return render(request, 'parts/moto_list.html', {
        'brands': brands,
        'brand_form': brand_form,
        'model_form': model_form,
    })
