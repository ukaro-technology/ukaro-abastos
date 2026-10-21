# sales/whatsapp.py - COMPROBANTE DE VENTA PARA COMPARTIR POR WHATSAPP
"""
Arma el enlace wa.me con el resumen de una venta. Se usa cuando el módulo
'whatsapp_receipt' está activo (bodega_system/business.py): la tienda trabaja solo con
teléfonos y no tiene impresora, así que el comprobante se envía por WhatsApp.
"""

import re
from urllib.parse import quote

from bodega_system.business import get_business


def normalize_phone(phone):
    """Convierte un teléfono venezolano (0414-1234567, +58 414...) al formato de wa.me
    (584141234567). Devuelve '' si no parece un número válido."""
    digits = re.sub(r'\D', '', phone or '')
    if digits.startswith('58') and len(digits) == 12:
        return digits
    if digits.startswith('0') and len(digits) == 11:
        return '58' + digits[1:]
    if len(digits) == 10:
        return '58' + digits
    return ''


def receipt_text(sale):
    business = get_business()
    lines = [f"*{business['name']}*", f"Comprobante de venta #{sale.id}", sale.date.strftime('%d/%m/%Y %I:%M %p'), '']
    for item in sale.items.select_related('product', 'combo'):
        name = item.product.name if item.product else f"Combo {item.combo.name}"
        qty = f"{item.quantity.normalize():f}"
        lines.append(f"{qty} x {name} — ${item.price_usd * item.quantity:.2f}")
    lines.append('')
    if sale.discount_usd:
        lines.append(f"Subtotal: ${sale.total_usd + sale.discount_usd:.2f}")
        lines.append(f"Descuento efectivo $ ({sale.discount_percent.normalize():f}%): -${sale.discount_usd:.2f}")
    lines.append(f"*Total: ${sale.total_usd:.2f}*")
    lines.append(f"Equivalente: Bs {sale.total_bs:,.2f} (tasa {sale.exchange_rate_used:,.2f})")
    lines.append(f"Pago: {'Crédito' if sale.is_credit else sale.get_payment_method_display()}")
    lines.append('')
    lines.append('¡Gracias por su compra!')
    return '\n'.join(lines)


def receipt_whatsapp_url(sale):
    phone = normalize_phone(sale.customer.phone) if sale.customer else ''
    return f"https://wa.me/{phone}?text={quote(receipt_text(sale))}"
