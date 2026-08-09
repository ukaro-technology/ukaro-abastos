# inventory/pdf_generators.py — PDFs de auditoría de inventario
# Ver docs/specs/auditoria-inventario.md
#
# Reusa generate_pdf_response de finances (mismo look and feel que el
# resto de reportes del sistema — no reinventar generación de PDF).

from datetime import date

from finances.pdf_generators import generate_pdf_response


def pdf_inventory_count_report(count, items_con_diferencia, totals):
    """PDF del reporte de discrepancias de un conteo físico de inventario."""
    headers = ['Producto', 'Código', 'Sistema', 'Físico', 'Diferencia', 'Valor USD']

    rows = []
    for item in items_con_diferencia:
        rows.append([
            item.product.name[:35],
            item.product.barcode or '-',
            str(item.system_stock),
            str(item.physical_stock),
            str(item.difference),
            f'${float(item.difference_value_usd):.2f}',
        ])

    categoria = count.category.name if count.category else 'Todas las categorías'
    metadata = [
        ('Fecha del conteo', count.date.strftime('%d/%m/%Y %H:%M')),
        ('Categoría', categoria),
        ('Realizado por', count.counted_by.get_full_name() or count.counted_by.username),
    ]
    if count.notes:
        metadata.append(('Notas', count.notes))

    summary = [
        ('Productos contados', str(totals['contados'])),
        ('Con diferencia', str(totals['con_diferencia'])),
        ('Valor de la diferencia (USD)', f"${float(totals['valor_diferencia_usd']):.2f}"),
    ]

    return generate_pdf_response(
        title=f'Auditoría de Inventario — Conteo #{count.pk}',
        headers=headers,
        rows=rows,
        summary=summary,
        metadata=metadata,
        landscape_mode=True,
        filename=f'auditoria_inventario_conteo_{count.pk}_{date.today().strftime("%Y%m%d")}.pdf',
    )


def pdf_inventory_count_sheet(products, category):
    """Planilla PDF EN BLANCO para llevar a la bodega y contar a mano.

    Muestra la cantidad que dice el sistema y deja una casilla para marcar
    si coincide ('☐ Coincide') más una columna en blanco para anotar el
    conteo físico si no coincide — se llena con lápiz en la bodega y
    después se transcribe al formulario digital (inventory_count_create).
    No lee ni escribe InventoryCount — es solo una plantilla de apoyo en
    papel, no un registro.
    """
    # Nota: reportlab con la fuente Helvetica no soporta el glyph Unicode de
    # checkbox (☐, U+2610) — lo dibuja como un cuadrado sólido, que en una
    # planilla para tildar A MANO se confunde con "ya marcado". Se usa un
    # corchete ASCII simple en su lugar, verificado visualmente.
    headers = ['Producto', 'Código', 'Cantidad Sistema', 'Coincide', 'Físico (si difiere)']

    rows = []
    for product in products:
        rows.append([
            product.name[:35],
            product.barcode or '-',
            str(product.stock),
            '[   ]',
            '______________',
        ])

    categoria = category.name if category else 'Todas las categorías'
    metadata = [
        ('Categoría', categoria),
        ('Fecha de impresión', date.today().strftime('%d/%m/%Y')),
    ]

    summary = [
        ('Productos en esta planilla', str(len(rows))),
    ]

    return generate_pdf_response(
        title='Planilla de Conteo Físico — Ukaro Abastos',
        headers=headers,
        rows=rows,
        summary=summary,
        metadata=metadata,
        landscape_mode=True,
        filename=f'planilla_conteo_{category.pk if category else "todas"}_{date.today().strftime("%Y%m%d")}.pdf',
    )


def pdf_product_traceability(product, eventos, date_from, date_to):
    """PDF de la línea de tiempo de trazabilidad de un producto."""
    headers = ['Fecha', 'Tipo', 'Referencia', 'Detalle', 'Cambio', 'Stock resultante']

    rows = []
    for e in eventos:
        rows.append([
            e['date'].strftime('%d/%m/%Y %H:%M'),
            e['tipo'].capitalize(),
            e['referencia'],
            (e['detalle'] or '')[:40],
            f"{'+' if e['delta'] >= 0 else ''}{e['delta']}",
            str(e['stock_after']),
        ])

    metadata = [
        ('Producto', product.name),
        ('Código', product.barcode or '-'),
        ('Stock actual', str(product.stock)),
        ('Rango', f"{date_from.strftime('%d/%m/%Y') if date_from else '—'} a "
                  f"{date_to.strftime('%d/%m/%Y') if date_to else '—'}"),
    ]

    summary = [
        ('Eventos en el rango', str(len(eventos))),
    ]

    return generate_pdf_response(
        title=f'Trazabilidad de Stock — {product.name}',
        headers=headers,
        rows=rows,
        summary=summary,
        metadata=metadata,
        landscape_mode=True,
        filename=f'trazabilidad_{product.barcode or product.pk}_{date.today().strftime("%Y%m%d")}.pdf',
    )
