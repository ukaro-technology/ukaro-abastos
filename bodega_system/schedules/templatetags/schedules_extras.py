# schedules/templatetags/schedules_extras.py
"""
Filtros y tags para el diseño visual de la planilla de turnos: iniciales/color de avatar por
empleado (para identificarlos de un vistazo sin repetir el nombre completo en cada celda) y el
"tema" visual de cada turno (color + ícono) para que Mañana y Tarde se distingan claramente.

Nota de contraste: todas las combinaciones bg/text de aquí usan fondo -50 con texto -700/-800,
que en la paleta de Tailwind da un contraste bien por encima de 4.5:1 (WCAG AA).
"""

from django import template

register = template.Library()


# Paleta fija para avatares de empleado — el color se elige de forma determinística por el id
# del usuario, así el mismo empleado siempre se ve con el mismo color en toda la app.
AVATAR_PALETTE = [
    {'bg': 'bg-blue-100', 'text': 'text-blue-700'},
    {'bg': 'bg-pink-100', 'text': 'text-pink-700'},
    {'bg': 'bg-emerald-100', 'text': 'text-emerald-700'},
    {'bg': 'bg-purple-100', 'text': 'text-purple-700'},
    {'bg': 'bg-orange-100', 'text': 'text-orange-700'},
    {'bg': 'bg-teal-100', 'text': 'text-teal-700'},
    {'bg': 'bg-rose-100', 'text': 'text-rose-700'},
    {'bg': 'bg-cyan-100', 'text': 'text-cyan-700'},
]

# Tema por turno — además del color, cada uno tiene un ícono distinto (no solo color, para no
# depender únicamente del color como señal — regla de accesibilidad).
SHIFT_THEMES = {
    'mañana': {
        'bg': 'bg-amber-50', 'border': 'border-amber-200', 'text': 'text-amber-800',
        'accent': 'bg-amber-400', 'ring': 'ring-amber-200', 'icon': 'sun',
    },
    'tarde': {
        'bg': 'bg-indigo-50', 'border': 'border-indigo-200', 'text': 'text-indigo-800',
        'accent': 'bg-indigo-400', 'ring': 'ring-indigo-200', 'icon': 'moon',
    },
}
DEFAULT_SHIFT_THEME = {
    'bg': 'bg-gray-50', 'border': 'border-gray-200', 'text': 'text-gray-700',
    'accent': 'bg-gray-400', 'ring': 'ring-gray-200', 'icon': 'clock',
}

EXCEPTION_THEMES = {
    'vacation': {'bg': 'bg-blue-50', 'text': 'text-blue-700', 'border': 'border-blue-400', 'dot': 'bg-blue-400'},
    'permission': {'bg': 'bg-purple-50', 'text': 'text-purple-700', 'border': 'border-purple-400', 'dot': 'bg-purple-400'},
    'sick': {'bg': 'bg-rose-50', 'text': 'text-rose-700', 'border': 'border-rose-400', 'dot': 'bg-rose-400'},
    'other': {'bg': 'bg-gray-50', 'text': 'text-gray-700', 'border': 'border-gray-400', 'dot': 'bg-gray-400'},
}


@register.filter
def initials(user):
    """Hasta 2 iniciales del nombre completo (o del username si no hay nombre cargado)."""
    if not user:
        return '?'
    name = user.get_full_name() or user.username
    parts = [p for p in name.split() if p]
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    if parts:
        return parts[0][:2].upper()
    return '?'


@register.simple_tag
def avatar_theme(user):
    """Color de avatar determinístico por id de usuario — mismo empleado, mismo color siempre."""
    if not user:
        return AVATAR_PALETTE[0]
    return AVATAR_PALETTE[user.pk % len(AVATAR_PALETTE)]


@register.simple_tag
def shift_theme(shift_name):
    """Tema visual (color + ícono) de un turno por nombre. Turnos que no sean Mañana/Tarde
    (si algún día se agrega un tercero) caen en un tema neutro en vez de romper."""
    return SHIFT_THEMES.get((shift_name or '').strip().lower(), DEFAULT_SHIFT_THEME)


@register.simple_tag
def exception_theme(exception_type):
    """Color por tipo de excepción (vacaciones/permiso/enfermedad/otro)."""
    return EXCEPTION_THEMES.get(exception_type, EXCEPTION_THEMES['other'])
