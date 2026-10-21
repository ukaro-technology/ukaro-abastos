from django.contrib import admin

from .models import MotoBrand, MotoModel, PartInfo


class MotoModelInline(admin.TabularInline):
    model = MotoModel
    extra = 1


@admin.register(MotoBrand)
class MotoBrandAdmin(admin.ModelAdmin):
    list_display = ['name']
    search_fields = ['name']
    inlines = [MotoModelInline]


@admin.register(MotoModel)
class MotoModelAdmin(admin.ModelAdmin):
    list_display = ['name', 'brand', 'displacement_cc']
    list_filter = ['brand']
    search_fields = ['name', 'brand__name']


@admin.register(PartInfo)
class PartInfoAdmin(admin.ModelAdmin):
    list_display = ['product', 'part_number', 'part_brand', 'quality', 'location', 'is_universal']
    list_filter = ['quality', 'is_universal']
    search_fields = ['product__name', 'part_number', 'part_brand']
    filter_horizontal = ['compatible_models']
