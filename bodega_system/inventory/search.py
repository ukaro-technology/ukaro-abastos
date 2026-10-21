# inventory/search.py - BÚSQUEDA DE PRODUCTOS PALABRA POR PALABRA
"""
Búsqueda compartida por el punto de venta (API) y la lista de inventario.

Cada palabra de la búsqueda tiene que aparecer en algún campo del producto, en cualquier
orden: "pastilla sbr" encuentra "Pastillas de freno delanteras" compatible con "Bera SBR 150".
No distingue mayúsculas ni tildes ("bujia" encuentra "Bujía").

Si el módulo 'moto_parts' está activo, también busca en la marca y el número de parte del
repuesto y en las marcas/modelos de moto compatibles (app parts).
"""

import re

from django.db.models import Q

from bodega_system.business import feature

# Letras que se comparan sin importar la tilde. iregex funciona igual en SQLite (Django
# registra REGEXP con el módulo re de Python) y en PostgreSQL (~*).
_ACCENT_VARIANTS = {
    'a': 'aáàä', 'e': 'eéèë', 'i': 'iíìï', 'o': 'oóòö', 'u': 'uúùü', 'n': 'nñ',
}
_BASE_LETTER = {v: base for base, variants in _ACCENT_VARIANTS.items() for v in variants}

BASE_FIELDS = ['name', 'barcode', 'description', 'category__name']
PART_FIELDS = [
    'part_info__part_number',
    'part_info__part_brand',
    'part_info__compatible_models__name',
    'part_info__compatible_models__brand__name',
]


def _token_regex(token):
    pattern = []
    for char in token.lower():
        base = _BASE_LETTER.get(char)
        pattern.append(f'[{_ACCENT_VARIANTS[base]}]' if base else re.escape(char))
    return ''.join(pattern)


def search_fields():
    return BASE_FIELDS + (PART_FIELDS if feature('moto_parts') else [])


def search_products(queryset, query):
    """Filtra `queryset` (de Product) para que cada palabra de `query` aparezca en algún campo."""
    tokens = [t for t in (query or '').split() if t]
    if not tokens:
        return queryset

    fields = search_fields()
    for token in tokens:
        regex = _token_regex(token)
        condition = Q()
        for field in fields:
            condition |= Q(**{f'{field}__iregex': regex})
        queryset = queryset.filter(condition)

    # Los joins con motos compatibles repiten filas.
    return queryset.distinct()
