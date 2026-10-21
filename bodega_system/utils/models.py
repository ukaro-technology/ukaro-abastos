# utils/models.py

from django.db import models
from django.utils import timezone

class ExchangeRate(models.Model):
    """Modelo para la tasa de cambio Bs/USD"""
    date = models.DateField(default=timezone.now, verbose_name="Fecha")
    bs_to_usd = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        verbose_name="Tasa Bs/USD"
    )
    updated_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        related_name='exchange_rates',
        verbose_name="Actualizado por"
    )
    
    class Meta:
        verbose_name = "Tasa de Cambio"
        verbose_name_plural = "Tasas de Cambio"
        ordering = ['-date']
        get_latest_by = 'date'
    
    def __str__(self):
        return f"{self.date}: {self.bs_to_usd} Bs/USD"
    
    @classmethod
    def get_latest_rate(cls):
        """
        Obtiene la tasa de cambio más reciente

        ✅ OPTIMIZADO: Con caché de 1 hora para reducir queries
        """
        from django.core.cache import cache

        cache_key = 'exchange_rate_latest'
        cached_rate = cache.get(cache_key)

        if cached_rate is not None:
            return cached_rate

        try:
            rate = cls.objects.latest()
            # Cachear por 1 hora (3600 segundos)
            cache.set(cache_key, rate, 3600)
            return rate
        except cls.DoesNotExist:
            # También cachear None para evitar queries repetidas cuando no hay tasa
            cache.set(cache_key, None, 300)  # 5 minutos para None
            return None

    def save(self, *args, **kwargs):
        """Invalidar caché al guardar nueva tasa"""
        from django.core.cache import cache

        super().save(*args, **kwargs)

        # Invalidar caché de latest_rate
        cache.delete('exchange_rate_latest')

    def delete(self, *args, **kwargs):
        """Invalidar caché al eliminar tasa"""
        from django.core.cache import cache

        super().delete(*args, **kwargs)

        # Invalidar caché de latest_rate
        cache.delete('exchange_rate_latest')


class StoreSettings(models.Model):
    """Ajustes del negocio editables desde el sistema (una sola fila, pk=1)."""
    cash_usd_discount_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        verbose_name="Descuento por pago en dólares en efectivo (%)",
        help_text="Se aplica al total de la venta cuando el método de pago es 'Efectivo $'. "
                  "Ej.: 16.67 hace que un producto de $30 quede en $25."
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Actualizado el")

    class Meta:
        verbose_name = "Ajustes del Negocio"
        verbose_name_plural = "Ajustes del Negocio"

    def __str__(self):
        return "Ajustes del negocio"

    @classmethod
    def get(cls):
        settings_obj, _ = cls.objects.get_or_create(pk=1)
        return settings_obj


class Backup(models.Model):
    """Modelo para los respaldos de la base de datos"""
    date = models.DateTimeField(auto_now_add=True, verbose_name="Fecha")
    file_path = models.CharField(max_length=255, verbose_name="Ruta del Archivo")
    file_size = models.PositiveIntegerField(verbose_name="Tamaño (KB)")
    created_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        related_name='backups',
        verbose_name="Creado por"
    )
    notes = models.TextField(blank=True, verbose_name="Notas")
    
    class Meta:
        verbose_name = "Respaldo"
        verbose_name_plural = "Respaldos"
        ordering = ['-date']
    
    def __str__(self):
        return f"Respaldo del {self.date}"