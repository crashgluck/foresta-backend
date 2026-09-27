from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import BaseDomainModel


class MissionStatus(models.TextChoices):
    PLANNED = 'planned', 'Planificada'
    IN_PROGRESS = 'in_progress', 'En curso'
    DONE = 'done', 'Completada'
    CANCELLED = 'cancelled', 'Cancelada'


class DroneTeam(models.TextChoices):
    SENTRY_32 = 'SENTRY_32', 'Sentry 32'
    SENTRY_33 = 'SENTRY_33', 'Sentry 33'
    SENTRY_ZOOM_31 = 'SENTRY_ZOOM_31', 'Sentry Zoom 31'
    SENTRY_ENTERPRISE_30 = 'SENTRY_ENTERPRISE_30', 'Sentry Enterprise 30'


class DroneMissionCode(models.TextChoices):
    RECO_1 = 'RECO 1', 'RECO 1'
    RECO_2 = 'RECO 2', 'RECO 2'
    RECO_3 = 'RECO 3', 'RECO 3'
    RECO_4 = 'RECO 4', 'RECO 4'
    RECO_5 = 'RECO 5', 'RECO 5'
    RECO_6 = 'RECO 6', 'RECO 6'
    RECO_7 = 'RECO 7', 'RECO 7'
    BRIFO = 'BRIFO', 'BRIFO'
    QRF = 'QRF', 'QRF'


class Mission(BaseDomainModel):
    title = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    mission_type = models.CharField(max_length=80, blank=True)
    parcela = models.ForeignKey('parcels.Parcel', on_delete=models.SET_NULL, null=True, blank=True, related_name='missions')
    persona = models.ForeignKey('people.Person', on_delete=models.SET_NULL, null=True, blank=True, related_name='missions')
    team_name = models.CharField(max_length=120, blank=True)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='missions')
    status = models.CharField(max_length=20, choices=MissionStatus.choices, default=MissionStatus.PLANNED)
    scheduled_for = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-scheduled_for', '-created_at']

    def __str__(self):
        return self.title


class DroneFlight(BaseDomainModel):
    pilot = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='drone_flights')
    parcela = models.ForeignKey('parcels.Parcel', on_delete=models.SET_NULL, null=True, blank=True, related_name='drone_flights')
    persona = models.ForeignKey('people.Person', on_delete=models.SET_NULL, null=True, blank=True, related_name='drone_flights')
    flight_datetime = models.DateTimeField(default=timezone.now)
    mission_code = models.CharField(max_length=40, choices=DroneMissionCode.choices, blank=True)
    team_code = models.CharField(max_length=40, choices=DroneTeam.choices, blank=True)
    battery_code = models.CharField(max_length=40, blank=True)
    takeoff_platform = models.CharField(max_length=80, blank=True)
    notes = models.TextField(blank=True)
    photo_path = models.CharField(max_length=255, blank=True)
    video_path = models.CharField(max_length=255, blank=True)
    legacy_source_id = models.PositiveIntegerField(null=True, blank=True, unique=True)

    class Meta:
        ordering = ['-flight_datetime', '-created_at']

    def __str__(self):
        return f'{self.mission_code or "VUELO"} - {self.flight_datetime:%Y-%m-%d %H:%M}'


class MissionMediaType(models.TextChoices):
    NONE = 'none', 'Ninguno'
    IMAGE = 'image', 'Imagen'
    VIDEO = 'video', 'Video'


class MissionReport(BaseDomainModel):
    mission = models.ForeignKey(Mission, on_delete=models.CASCADE, related_name='reports')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='mission_reports'
    )
    report_date = models.DateField()
    summary = models.TextField()
    media_url = models.URLField(blank=True)
    media_type = models.CharField(max_length=20, choices=MissionMediaType.choices, default=MissionMediaType.NONE)

    class Meta:
        ordering = ['-report_date', '-created_at']

    def __str__(self):
        return f'Reporte {self.mission_id} {self.report_date}'

