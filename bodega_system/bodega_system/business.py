# bodega_system/business.py
"""
Perfil del negocio que corre esta instalación.

El mismo código sirve a varios clientes (bodega de Leida, tienda de repuestos SuperMoto Speed,
...). Cada instalación elige su perfil con la variable de entorno BUSINESS_PROFILE; sin ella
se usa 'bodega', que reproduce exactamente el comportamiento original del sistema.

Un perfil define la marca (nombres, logo, tema de colores, datos del comprobante) y qué
módulos están activos (`features`). El perfil llega a todas las plantillas como `business`
(ver utils.context_processors.business) y al código Python vía get_business() / feature().
"""

import os

PROFILES = {
    'bodega': {
        'name': 'Bodega de Leida',
        'short_name': 'Bodega',
        'system_name': 'Sistema de Bodega',
        'welcome_text': 'Bienvenido al Sistema de Gestión de Bodega de Leida.',
        'logo': None,
        'theme': 'default',
        'city': 'Guanare',
        'phone': '',
        'instagram': '',
        'features': {
            'schedules': True,        # Horarios de empleados
            'performance': True,      # Métricas de rendimiento
            'moto_parts': False,      # Compatibilidad con motos (app parts)
            'cash_usd': False,        # Método "Efectivo $" con descuento configurable
            'camera_scan': False,     # Escanear código de barras con la cámara del teléfono
            'whatsapp_receipt': False,  # Botón de compartir comprobante por WhatsApp
        },
    },
    'motoparts': {
        'name': 'SuperMoto Speed',
        'short_name': 'SuperMoto',
        'system_name': 'SuperMoto Speed',
        'welcome_text': 'Bienvenido al sistema de gestión de SuperMoto Speed.',
        'logo': '/static/img/brands/supermoto/logo.jpg',
        'theme': 'supermoto',
        'city': 'Guanare, Portuguesa',
        'phone': '',
        'instagram': '',
        'features': {
            'schedules': False,
            'performance': False,
            'moto_parts': True,
            'cash_usd': True,
            'camera_scan': True,
            'whatsapp_receipt': True,
        },
    },
}

DEFAULT_PROFILE = 'bodega'


def get_profile_key():
    key = os.environ.get('BUSINESS_PROFILE', DEFAULT_PROFILE)
    return key if key in PROFILES else DEFAULT_PROFILE


def get_business():
    """Devuelve el perfil activo (dict) con su clave en 'key'."""
    key = get_profile_key()
    return {**PROFILES[key], 'key': key}


def feature(name):
    """True si el módulo `name` está activo en el perfil actual."""
    return bool(get_business()['features'].get(name, False))
