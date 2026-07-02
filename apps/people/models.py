from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.core.models import BaseDomainModel
from apps.core.normalizers import normalize_email, normalize_phone, normalize_rut_dv, normalize_rut_number
from apps.core.validators import validate_rut


class Person(BaseDomainModel):
    nombres = models.CharField(max_length=120, blank=True)
    apellidos = models.CharField(max_length=120, blank=True)
    nombre_completo = models.CharField(max_length=255)
    rut = models.CharField(max_length=20, blank=True)
    rut_dv = models.CharField(max_length=2, blank=True)
    rut_normalizado = models.CharField(max_length=20, blank=True, db_index=True)
    telefono_principal = models.CharField(max_length=30, blank=True)
    telefono_secundario = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    direccion_contacto = models.CharField(max_length=255, blank=True)
    activo = models.BooleanField(default=True)
    notas = models.TextField(blank=True)

    class Meta:
        ordering = ['nombre_completo']
        constraints = [
            models.UniqueConstraint(
                fields=['rut_normalizado'],
                condition=Q(rut_normalizado__gt='') & Q(is_deleted=False),
                name='uniq_person_rut_normalizado_alive',
            ),
        ]

    def __str__(self):
        return self.nombre_completo

    def clean(self):
        self.email = normalize_email(self.email)
        self.telefono_principal = normalize_phone(self.telefono_principal)
        self.telefono_secundario = normalize_phone(self.telefono_secundario)
        self.rut_normalizado = normalize_rut_number(self.rut)
        self.rut_dv = normalize_rut_dv(self.rut_dv)

        if self.rut_normalizado and self.rut_dv and not validate_rut(self.rut_normalizado, self.rut_dv):
            raise ValidationError({'rut_dv': 'RUT inválido'})

        if not self.nombre_completo:
            self.nombre_completo = f'{self.nombres} {self.apellidos}'.strip()

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class OwnershipType(models.TextChoices):
    PRINCIPAL = 'PRINCIPAL', 'Propietario principal'
    COPROPIETARIO = 'COPROPIETARIO', 'Copropietario'


class ParcelOwnership(BaseDomainModel):
    parcela = models.ForeignKey('parcels.Parcel', on_delete=models.CASCADE, related_name='ownerships')
    persona = models.ForeignKey('people.Person', on_delete=models.CASCADE, related_name='parcel_ownerships')
    tipo = models.CharField(max_length=20, choices=OwnershipType.choices, default=OwnershipType.COPROPIETARIO)
    is_active = models.BooleanField(default=True)
    fecha_inicio = models.DateField(null=True, blank=True)
    fecha_fin = models.DateField(null=True, blank=True)
    notas = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['parcela'],
                condition=Q(tipo=OwnershipType.PRINCIPAL) & Q(is_active=True) & Q(is_deleted=False),
                name='uniq_active_primary_owner_per_parcel',
            ),
            models.UniqueConstraint(
                fields=['parcela', 'persona', 'tipo'],
                condition=Q(is_active=True) & Q(is_deleted=False),
                name='uniq_active_owner_role_per_parcel_person',
            ),
        ]
        ordering = ['-tipo', 'persona__nombre_completo']

    def __str__(self):
        return f'{self.parcela} - {self.persona} ({self.tipo})'


class ResidentType(models.TextChoices):
    RESIDENTE = 'RESIDENTE', 'Residente'
    CUIDADOR = 'CUIDADOR', 'Cuidador'
    FAMILIAR = 'FAMILIAR', 'Familiar'
    OTRO = 'OTRO', 'Otro'


class ParcelResident(BaseDomainModel):
    parcela = models.ForeignKey('parcels.Parcel', on_delete=models.CASCADE, related_name='residents')
    persona = models.ForeignKey('people.Person', on_delete=models.SET_NULL, null=True, blank=True, related_name='parcel_residencies')
    tipo_residencia = models.CharField(max_length=20, choices=ResidentType.choices, default=ResidentType.RESIDENTE)
    is_active = models.BooleanField(default=True)
    observaciones = models.TextField(blank=True)

    class Meta:
        ordering = ['-is_active', 'persona__nombre_completo']
        constraints = [
            models.UniqueConstraint(
                fields=['parcela', 'persona', 'tipo_residencia'],
                condition=Q(is_active=True) & Q(is_deleted=False),
                name='uniq_active_resident_per_role',
            ),
        ]

    def __str__(self):
        return f'{self.parcela} - {self.persona} ({self.tipo_residencia})'


