# parts/models.py - COMPATIBILIDAD DE REPUESTOS CON MOTOS
#
# Solo se usa cuando el perfil del negocio tiene activo el módulo 'moto_parts'
# (ver bodega_system/business.py). La app está instalada siempre para que el esquema de la
# base de datos sea el mismo en todas las instalaciones; en la bodega sus tablas quedan vacías.

from django.db import models


class MotoBrand(models.Model):
    """Marca de moto (Bera, Empire Keeway, Suzuki...)"""
    name = models.CharField(max_length=60, unique=True, verbose_name="Marca")

    class Meta:
        verbose_name = "Marca de Moto"
        verbose_name_plural = "Marcas de Moto"
        ordering = ['name']

    def __str__(self):
        return self.name


class MotoModel(models.Model):
    """Modelo de moto de una marca (SBR 150, Horse 150...)"""
    brand = models.ForeignKey(
        MotoBrand,
        on_delete=models.PROTECT,
        related_name='models',
        verbose_name="Marca"
    )
    name = models.CharField(max_length=80, verbose_name="Modelo")
    displacement_cc = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="Cilindrada (cc)"
    )

    class Meta:
        verbose_name = "Modelo de Moto"
        verbose_name_plural = "Modelos de Moto"
        ordering = ['brand__name', 'name']
        unique_together = ['brand', 'name']

    def __str__(self):
        return f"{self.brand.name} {self.name}"


class PartInfo(models.Model):
    """Datos de repuesto de un producto: número de parte, marca, calidad, ubicación y motos
    a las que le sirve. Relación 1 a 1 con inventory.Product, que no cambia."""

    QUALITY_CHOICES = (
        ('original', 'Original'),
        ('alternative', 'Alternativo'),
        ('generic', 'Genérico'),
    )

    product = models.OneToOneField(
        'inventory.Product',
        on_delete=models.CASCADE,
        related_name='part_info',
        verbose_name="Producto"
    )
    part_number = models.CharField(
        max_length=60,
        blank=True,
        verbose_name="Número de parte",
        help_text="Código impreso en la pieza o en su caja (ej.: 43105-KWB-901)"
    )
    part_brand = models.CharField(
        max_length=60,
        blank=True,
        verbose_name="Marca del repuesto",
        help_text="Ej.: NGK, Motul, Genérica"
    )
    quality = models.CharField(
        max_length=15,
        choices=QUALITY_CHOICES,
        blank=True,
        verbose_name="Calidad"
    )
    location = models.CharField(
        max_length=60,
        blank=True,
        verbose_name="Ubicación",
        help_text="Dónde está guardado (ej.: Estante 3, gaveta B)"
    )
    is_universal = models.BooleanField(
        default=False,
        verbose_name="Universal",
        help_text="Le sirve a cualquier moto (aceites, accesorios, herramientas...)"
    )
    compatible_models = models.ManyToManyField(
        MotoModel,
        blank=True,
        related_name='parts',
        verbose_name="Motos compatibles"
    )

    class Meta:
        verbose_name = "Datos de Repuesto"
        verbose_name_plural = "Datos de Repuesto"

    def __str__(self):
        return f"Repuesto: {self.product.name}"

    @property
    def compatibility_display(self):
        """Texto corto de compatibilidad para listas y comprobantes."""
        if self.is_universal:
            return "Universal"
        return ", ".join(str(m) for m in self.compatible_models.all())


def part_summary(product):
    """Datos de repuesto de un producto para las APIs del punto de venta, o None."""
    try:
        part = product.part_info
    except PartInfo.DoesNotExist:
        return None
    return {
        'part_number': part.part_number,
        'part_brand': part.part_brand,
        'quality': part.get_quality_display() if part.quality else '',
        'location': part.location,
        'compatibility': part.compatibility_display,
    }
