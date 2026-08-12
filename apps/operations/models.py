import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from apps.core.models import BaseDomainModel, TimeStampedModel
from apps.geo_operations.services.geometry import validate_geojson_geometry


def operation_evidence_upload_to(instance, filename):
    return f'operations/tasks/{instance.task_id or "new"}/evidence/{filename}'


class OperationTaskStatus(models.TextChoices):
    DETECTED = 'DETECTED', 'Detectado'
    EVALUATED = 'EVALUATED', 'Evaluado'
    ASSIGNED = 'ASSIGNED', 'Asignado'
    IN_PROGRESS = 'IN_PROGRESS', 'En ejecucion'
    EXECUTED = 'EXECUTED', 'Ejecutado'
    VERIFICATION = 'VERIFICATION', 'En verificacion'
    CLOSED = 'CLOSED', 'Cerrado'
    BLOCKED = 'BLOCKED', 'Bloqueado'
    CANCELLED = 'CANCELLED', 'Cancelado'


class OperationPriority(models.TextChoices):
    LOW = 'LOW', 'Baja'
    MEDIUM = 'MEDIUM', 'Media'
    HIGH = 'HIGH', 'Alta'
    CRITICAL = 'CRITICAL', 'Critica'


class OperationApprovalStatus(models.TextChoices):
    NOT_REQUIRED = 'NOT_REQUIRED', 'No requiere'
    PENDING = 'PENDING', 'Pendiente'
    APPROVED = 'APPROVED', 'Aprobado'
    REJECTED = 'REJECTED', 'Rechazado'


class OperationOrigin(models.TextChoices):
    MANUAL = 'MANUAL', 'Manual'
    MAP = 'MAP', 'Mapa'
    INSPECTION = 'INSPECTION', 'Inspeccion'
    MAINTENANCE_TEMPLATE = 'MAINTENANCE_TEMPLATE', 'Mantenimiento programado'
    OWNER_REQUEST = 'OWNER_REQUEST', 'Solicitud propietario'
    SYSTEM = 'SYSTEM', 'Sistema'


class OperationExecutorKind(models.TextChoices):
    USER = 'USER', 'Usuario'
    INTERNAL_WORKER = 'INTERNAL_WORKER', 'Trabajador interno'
    CREW = 'CREW', 'Cuadrilla'
    PROVIDER = 'PROVIDER', 'Proveedor'
    MANUAL = 'MANUAL', 'Manual'


class OperationEvidenceType(models.TextChoices):
    PHOTO = 'PHOTO', 'Foto'
    DOCUMENT = 'DOCUMENT', 'Documento'
    AUDIO = 'AUDIO', 'Audio'
    VIDEO = 'VIDEO', 'Video'
    OTHER = 'OTHER', 'Otro'


class OperationTemplateFrequency(models.TextChoices):
    DAILY = 'DAILY', 'Diaria'
    WEEKLY = 'WEEKLY', 'Semanal'
    MONTHLY = 'MONTHLY', 'Mensual'
    QUARTERLY = 'QUARTERLY', 'Trimestral'
    YEARLY = 'YEARLY', 'Anual'


class OperationProjectStatus(models.TextChoices):
    PLANNED = 'PLANNED', 'Planificado'
    ACTIVE = 'ACTIVE', 'Activo'
    PAUSED = 'PAUSED', 'Pausado'
    COMPLETED = 'COMPLETED', 'Completado'
    CANCELLED = 'CANCELLED', 'Cancelado'


class OperationArea(BaseDomainModel):
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    sort_order = models.PositiveIntegerField(default=100, db_index=True)

    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name = 'Area operacional'
        verbose_name_plural = 'Areas operacionales'

    def __str__(self):
        return self.name

    def clean(self):
        if not self.slug:
            self.slug = slugify(self.name)[:140]

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class OperationTaskType(BaseDomainModel):
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    sort_order = models.PositiveIntegerField(default=100, db_index=True)

    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name = 'Tipo de tarea operacional'
        verbose_name_plural = 'Tipos de tareas operacionales'

    def __str__(self):
        return self.name

    def clean(self):
        if not self.slug:
            self.slug = slugify(self.name)[:140]

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class OperationBlockReason(BaseDomainModel):
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    sort_order = models.PositiveIntegerField(default=100, db_index=True)

    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name = 'Motivo de bloqueo operacional'
        verbose_name_plural = 'Motivos de bloqueo operacional'

    def __str__(self):
        return self.name

    def clean(self):
        if not self.slug:
            self.slug = slugify(self.name)[:140]

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class OperationExecutor(BaseDomainModel):
    kind = models.CharField(max_length=30, choices=OperationExecutorKind.choices, default=OperationExecutorKind.MANUAL, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='operation_executor_profiles',
    )
    name = models.CharField(max_length=180)
    contact = models.CharField(max_length=180, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ['kind', 'name']
        indexes = [
            models.Index(fields=['kind', 'is_active']),
            models.Index(fields=['name']),
        ]
        verbose_name = 'Ejecutor operacional'
        verbose_name_plural = 'Ejecutores operacionales'

    def __str__(self):
        return self.name

    def clean(self):
        if self.kind == OperationExecutorKind.USER and not self.user_id:
            raise ValidationError({'user': 'El ejecutor de tipo usuario requiere una cuenta asociada.'})
        if self.user_id and not self.name:
            self.name = self.user.full_name
        if not self.name:
            raise ValidationError({'name': 'El nombre del ejecutor es obligatorio.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class OperationProject(BaseDomainModel):
    name = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='operation_projects_responsible',
    )
    status = models.CharField(max_length=20, choices=OperationProjectStatus.choices, default=OperationProjectStatus.PLANNED, db_index=True)
    starts_at = models.DateField(null=True, blank=True)
    due_at = models.DateField(null=True, blank=True)
    ended_at = models.DateField(null=True, blank=True)
    budget_estimated = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    budget_real = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'is_active']),
            models.Index(fields=['due_at']),
        ]
        verbose_name = 'Proyecto operacional'
        verbose_name_plural = 'Proyectos operacionales'

    def __str__(self):
        return self.name


class OperationTask(BaseDomainModel):
    code = models.CharField(max_length=40, unique=True, db_index=True, blank=True)
    title = models.CharField(max_length=220)
    description = models.TextField(blank=True)
    task_type = models.ForeignKey(OperationTaskType, on_delete=models.PROTECT, related_name='tasks')
    area = models.ForeignKey(OperationArea, on_delete=models.PROTECT, related_name='tasks')
    priority = models.CharField(max_length=20, choices=OperationPriority.choices, default=OperationPriority.MEDIUM, db_index=True)
    status = models.CharField(max_length=20, choices=OperationTaskStatus.choices, default=OperationTaskStatus.DETECTED, db_index=True)
    origin = models.CharField(max_length=30, choices=OperationOrigin.choices, default=OperationOrigin.MANUAL, db_index=True)

    detected_at = models.DateTimeField(default=timezone.now, db_index=True)
    due_at = models.DateTimeField(null=True, blank=True, db_index=True)
    executed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    verification_at = models.DateTimeField(null=True, blank=True, db_index=True)
    closed_at = models.DateTimeField(null=True, blank=True, db_index=True)

    registered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='operation_tasks_registered',
    )
    executor_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='operation_tasks_to_execute',
    )
    executor = models.ForeignKey(OperationExecutor, on_delete=models.SET_NULL, null=True, blank=True, related_name='tasks')
    executor_manual_label = models.CharField(max_length=180, blank=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='operation_tasks_verified',
    )

    project = models.ForeignKey(OperationProject, on_delete=models.SET_NULL, null=True, blank=True, related_name='tasks')
    parent_task = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='subtasks')
    parcela = models.ForeignKey('parcels.Parcel', on_delete=models.SET_NULL, null=True, blank=True, related_name='operation_tasks')
    geo_asset = models.ForeignKey('geo_operations.GeoAsset', on_delete=models.SET_NULL, null=True, blank=True, related_name='operation_tasks')
    sector = models.CharField(max_length=120, blank=True, db_index=True)

    geometry = models.JSONField(null=True, blank=True)
    geometry_type = models.CharField(max_length=20, blank=True, db_index=True)
    bbox = models.JSONField(default=list, blank=True)
    min_lng = models.FloatField(null=True, blank=True, db_index=True)
    min_lat = models.FloatField(null=True, blank=True, db_index=True)
    max_lng = models.FloatField(null=True, blank=True, db_index=True)
    max_lat = models.FloatField(null=True, blank=True, db_index=True)
    center_lng = models.FloatField(null=True, blank=True)
    center_lat = models.FloatField(null=True, blank=True)
    length_m = models.FloatField(default=0)
    perimeter_m = models.FloatField(default=0)
    area_m2 = models.FloatField(default=0)
    vertex_count = models.PositiveIntegerField(default=0)

    cost_estimated = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    cost_real = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    requires_budget = models.BooleanField(default=False, db_index=True)
    approval_status = models.CharField(
        max_length=20,
        choices=OperationApprovalStatus.choices,
        default=OperationApprovalStatus.NOT_REQUIRED,
        db_index=True,
    )

    expected_result = models.TextField(blank=True)
    obtained_result = models.TextField(blank=True)
    observations = models.TextField(blank=True)
    tags = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ['-detected_at', '-created_at']
        indexes = [
            models.Index(fields=['status', 'priority']),
            models.Index(fields=['area', 'status']),
            models.Index(fields=['task_type', 'status']),
            models.Index(fields=['detected_at', 'status']),
            models.Index(fields=['closed_at', 'status']),
            models.Index(fields=['created_at']),
            models.Index(fields=['updated_at']),
            models.Index(fields=['geo_asset', 'status']),
            models.Index(fields=['parcela', 'status']),
            models.Index(fields=['executor', 'status']),
            models.Index(fields=['executor_user', 'status']),
            models.Index(fields=['project', 'status']),
            models.Index(fields=['min_lng', 'min_lat', 'max_lng', 'max_lat']),
        ]
        verbose_name = 'Tarea operacional'
        verbose_name_plural = 'Tareas operacionales'

    def __str__(self):
        return f'{self.code or "OP"} - {self.title}'

    @property
    def is_overdue(self):
        return bool(self.due_at and self.status not in {OperationTaskStatus.CLOSED, OperationTaskStatus.CANCELLED} and self.due_at < timezone.now())

    def has_executor(self):
        return bool(self.executor_user_id or self.executor_id or self.executor_manual_label)

    def clean(self):
        if self.geometry:
            summary = validate_geojson_geometry(self.geometry, allowed_geometry_type='ANY')
            self.geometry_type = summary.geometry_type
            self.bbox = list(summary.bbox)
            self.min_lng, self.min_lat, self.max_lng, self.max_lat = summary.bbox
            self.center_lng, self.center_lat = summary.center
            self.length_m = summary.length_m
            self.perimeter_m = summary.perimeter_m
            self.area_m2 = summary.area_m2
            self.vertex_count = summary.vertex_count
        else:
            self.geometry_type = ''
            self.bbox = []
            self.min_lng = None
            self.min_lat = None
            self.max_lng = None
            self.max_lat = None
            self.center_lng = None
            self.center_lat = None
            self.length_m = 0
            self.perimeter_m = 0
            self.area_m2 = 0
            self.vertex_count = 0

        if self.status in {OperationTaskStatus.ASSIGNED, OperationTaskStatus.IN_PROGRESS} and not self.has_executor():
            raise ValidationError({'executor': 'La tarea requiere ejecutor para quedar asignada o en ejecucion.'})
        if self.status == OperationTaskStatus.CLOSED and not self.verification_at:
            raise ValidationError({'status': 'No se puede cerrar una tarea sin verificacion.'})
        if self.requires_budget and self.approval_status == OperationApprovalStatus.NOT_REQUIRED:
            self.approval_status = OperationApprovalStatus.PENDING
        if self.parent_task_id and self.parent_task_id == self.pk:
            raise ValidationError({'parent_task': 'Una tarea no puede depender de si misma.'})

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = f'OP-{timezone.now():%Y%m%d}-{uuid.uuid4().hex[:6].upper()}'
        self.full_clean()
        super().save(*args, **kwargs)


class OperationTaskComment(BaseDomainModel):
    task = models.ForeignKey(OperationTask, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='operation_task_comments')
    comment = models.TextField()

    class Meta:
        ordering = ['created_at']
        indexes = [models.Index(fields=['task', 'created_at'])]
        verbose_name = 'Comentario de tarea operacional'
        verbose_name_plural = 'Comentarios de tareas operacionales'

    def __str__(self):
        return f'Comentario {self.task_id}'


class OperationTaskEvidence(BaseDomainModel):
    task = models.ForeignKey(OperationTask, on_delete=models.CASCADE, related_name='evidences')
    evidence_type = models.CharField(max_length=20, choices=OperationEvidenceType.choices, default=OperationEvidenceType.PHOTO, db_index=True)
    file = models.FileField(upload_to=operation_evidence_upload_to)
    original_name = models.CharField(max_length=255, blank=True)
    content_type = models.CharField(max_length=120, blank=True)
    size = models.PositiveIntegerField(default=0)
    comment = models.TextField(blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='operation_evidences')
    stage = models.CharField(max_length=20, choices=OperationTaskStatus.choices, blank=True)
    geometry = models.JSONField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['task', 'evidence_type']),
            models.Index(fields=['uploaded_by', 'created_at']),
        ]
        verbose_name = 'Evidencia de tarea operacional'
        verbose_name_plural = 'Evidencias de tareas operacionales'

    def __str__(self):
        return self.original_name or f'Evidencia {self.pk}'

    def clean(self):
        if self.geometry:
            validate_geojson_geometry(self.geometry, allowed_geometry_type='ANY')

    def save(self, *args, **kwargs):
        if self.file:
            self.original_name = self.original_name or getattr(self.file, 'name', '')
            self.content_type = self.content_type or getattr(self.file, 'content_type', '')
            self.size = self.size or getattr(self.file, 'size', 0)
        self.full_clean()
        super().save(*args, **kwargs)


class OperationTaskHistory(models.Model):
    task = models.ForeignKey(OperationTask, on_delete=models.CASCADE, related_name='history')
    previous_status = models.CharField(max_length=20, choices=OperationTaskStatus.choices, blank=True)
    new_status = models.CharField(max_length=20, choices=OperationTaskStatus.choices, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='operation_task_history')
    action = models.CharField(max_length=60, db_index=True)
    comment = models.TextField(blank=True)
    reason = models.TextField(blank=True)
    changed_fields = models.JSONField(default=dict, blank=True)
    snapshot = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['task', 'created_at']),
            models.Index(fields=['action', 'created_at']),
            models.Index(fields=['previous_status', 'new_status']),
        ]
        verbose_name = 'Historial de tarea operacional'
        verbose_name_plural = 'Historial de tareas operacionales'

    def __str__(self):
        return f'{self.task_id} {self.action}'


class OperationTaskBlock(BaseDomainModel):
    task = models.ForeignKey(OperationTask, on_delete=models.CASCADE, related_name='blocks')
    reason = models.ForeignKey(OperationBlockReason, on_delete=models.SET_NULL, null=True, blank=True, related_name='task_blocks')
    description = models.TextField()
    started_at = models.DateTimeField(default=timezone.now, db_index=True)
    responsible_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='operation_blocks_responsible',
    )
    estimated_resolution_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True, db_index=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='operation_blocks_resolved',
    )
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['task', 'is_active']),
            models.Index(fields=['reason', 'is_active']),
        ]
        verbose_name = 'Bloqueo de tarea operacional'
        verbose_name_plural = 'Bloqueos de tareas operacionales'

    def __str__(self):
        return f'Bloqueo {self.task_id}'


class OperationMaintenanceTemplate(BaseDomainModel):
    name = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    task_type = models.ForeignKey(OperationTaskType, on_delete=models.PROTECT, related_name='maintenance_templates')
    area = models.ForeignKey(OperationArea, on_delete=models.PROTECT, related_name='maintenance_templates')
    priority = models.CharField(max_length=20, choices=OperationPriority.choices, default=OperationPriority.MEDIUM)
    frequency = models.CharField(max_length=20, choices=OperationTemplateFrequency.choices, default=OperationTemplateFrequency.MONTHLY)
    interval_count = models.PositiveIntegerField(default=1)
    next_run_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_generated_at = models.DateTimeField(null=True, blank=True)
    geo_asset = models.ForeignKey('geo_operations.GeoAsset', on_delete=models.SET_NULL, null=True, blank=True, related_name='maintenance_templates')
    parcela = models.ForeignKey('parcels.Parcel', on_delete=models.SET_NULL, null=True, blank=True, related_name='maintenance_templates')
    sector = models.CharField(max_length=120, blank=True)
    default_executor = models.ForeignKey(OperationExecutor, on_delete=models.SET_NULL, null=True, blank=True, related_name='maintenance_templates')
    default_due_days = models.PositiveIntegerField(default=7)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ['next_run_at', 'name']
        indexes = [
            models.Index(fields=['is_active', 'next_run_at']),
            models.Index(fields=['task_type', 'area']),
        ]
        verbose_name = 'Plantilla de mantenimiento operacional'
        verbose_name_plural = 'Plantillas de mantenimiento operacional'

    def __str__(self):
        return self.name


class OperationReportExport(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='operation_report_exports')
    filters = models.JSONField(default=dict, blank=True)
    file_name = models.CharField(max_length=180)
    total_tasks = models.PositiveIntegerField(default=0)
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['period_start', 'period_end']),
        ]
        verbose_name = 'Exportacion PDF operacional'
        verbose_name_plural = 'Exportaciones PDF operacionales'

    def __str__(self):
        return self.file_name
