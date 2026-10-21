from .models import ExchangeRate

def exchange_rate(request):
    """
    Agrega la tasa de cambio más reciente al contexto de todas las plantillas
    """
    latest_rate = ExchangeRate.get_latest_rate()
    
    return {
        'latest_exchange_rate': latest_rate,
    }

def business(request):
    """
    Agrega el perfil del negocio (marca, tema y módulos activos) a todas las plantillas.
    Ver bodega_system/business.py.
    """
    from bodega_system.business import get_business

    return {
        'business': get_business(),
    }
