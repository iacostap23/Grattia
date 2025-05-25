from django.db import models
from django.utils import timezone

class Empleado(models.Model):
    nombre = models.CharField(max_length=100, blank=True, default="")
    correo = models.EmailField(unique=True, null=True, blank=True)
    cedula = models.CharField(max_length=20,null=True, blank=True)
    cargo = models.CharField(max_length=100, null=True, blank=True)
    rostro_registrado = models.BooleanField(default=False)


    def __str__(self):
        return f"{self.correo} - {self.cargo}"


class EventosAsistencia(models.Model):
    TIPO_CHOICES = [
        ('entrada', 'Entrada'),
        ('salida', 'Salida'),
    ]
    empleado = models.ForeignKey(Empleado, on_delete=models.CASCADE)
    fecha = models.DateField(default=timezone.now)
    hora = models.TimeField(null=True, blank=True)
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES)

    def __str__(self):
        return f"{self.empleado} - {self.fecha} - {self.tipo.capitalize()}"
