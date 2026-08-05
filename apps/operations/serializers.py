import json
import os

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import exceptions, serializers

from apps.accounts.models import User
from apps.geo_operations.models import GeoAsset
from apps.geo_operations.services.geometry import validate_geojson_geometry
from apps.operations.models import (
    OperationApprovalStatus,
    OperationArea,
    OperationBlockReason,
    OperationEvidenceType,
    OperationExecutor,
    OperationExecutorKind,
    OperationMaintenanceTemplate,
    OperationPriority,
    OperationProject,
    OperationReportExport,
    OperationTask,
    OperationTaskBlock,
    OperationTaskComment,
    OperationTaskEvidence,
    OperationTaskHistory,
    OperationTaskStatus,
    OperationTaskType,
)
from apps.operations.permissions import can_manage_costs, can_view_costs
from apps.parcels.models import Parcel


MAX_EVIDENCE_SIZE = 20 * 1024 * 1024
ALLOWED_EVIDENCE_EXTENSIONS = {
    '.jpg',
    '.jpeg',
    '.png',
    '.webp',
    '.pdf',
    '.doc',
    '.docx',
    '.xls',
    '.xlsx',
    '.csv',
    '.txt',
    '.mp4',
    '.mov',
    '.mp3',
    '.m4a',
    '.wav',
}


def _user_label(user):
    return user.full_name if user else ''


def _parse_json_value(value, field_name):
    if value in (None, ''):
        return None
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError as exc:
            raise serializers.ValidationError({field_name: 'Debe ser JSON valido.'}) from exc
    return value


class CostProtectedSerializerMixin:
    cost_fields = ('cost_estimated', 'cost_real', 'budget_estimated', 'budget_real')

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        if request and not can_view_costs(request.user):
            for field_name in self.cost_fields:
                fields.pop(field_name, None)
        return fields


class OperationAreaSerializer(serializers.ModelSerializer):
    class Meta:
        model = OperationArea
        fields = ['id', 'name', 'slug', 'description', 'is_active', 'sort_order', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']


class OperationTaskTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = OperationTaskType
        fields = ['id', 'name', 'slug', 'description', 'is_active', 'sort_order', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']


class OperationBlockReasonSerializer(serializers.ModelSerializer):
    class Meta:
        model = OperationBlockReason
        fields = ['id', 'name', 'slug', 'description', 'is_active', 'sort_order', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']


class OperationExecutorSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.full_name', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)

    class Meta:
        model = OperationExecutor
        fields = ['id', 'kind', 'user', 'user_name', 'user_email', 'name', 'contact', 'notes', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']

    def validate(self, attrs):
        kind = attrs.get('kind', self.instance.kind if self.instance else OperationExecutorKind.MANUAL)
        user = attrs.get('user', self.instance.user if self.instance else None)
        if kind == OperationExecutorKind.USER and not user:
            raise serializers.ValidationError({'user': 'El ejecutor de tipo usuario requiere una cuenta asociada.'})
        if user and not attrs.get('name') and not (self.instance and self.instance.name):
            attrs['name'] = user.full_name
        return attrs


class OperationProjectSerializer(CostProtectedSerializerMixin, serializers.ModelSerializer):
    responsible_name = serializers.CharField(source='responsible.full_name', read_only=True)
    tasks_count = serializers.IntegerField(read_only=True)
    closed_tasks_count = serializers.IntegerField(read_only=True)
    progress_percent = serializers.SerializerMethodField()

    class Meta:
        model = OperationProject
        fields = [
            'id',
            'name',
            'description',
            'responsible',
            'responsible_name',
            'status',
            'starts_at',
            'due_at',
            'ended_at',
            'budget_estimated',
            'budget_real',
            'is_active',
            'tasks_count',
            'closed_tasks_count',
            'progress_percent',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at', 'tasks_count', 'closed_tasks_count', 'progress_percent']

    def get_progress_percent(self, obj):
        total = getattr(obj, 'tasks_count', None)
        closed = getattr(obj, 'closed_tasks_count', None)
        if not total:
            return 0
        return round((closed or 0) * 100 / total, 2)

    def validate(self, attrs):
        request = self.context.get('request')
        cost_fields = {'budget_estimated', 'budget_real'}
        if request and not can_manage_costs(request.user) and cost_fields.intersection(self.initial_data):
            raise exceptions.PermissionDenied('No tienes permiso para gestionar presupuestos.')
        return attrs


class OperationTaskHistorySerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.full_name', read_only=True)

    class Meta:
        model = OperationTaskHistory
        fields = [
            'id',
            'previous_status',
            'new_status',
            'user',
            'user_name',
            'action',
            'comment',
            'reason',
            'changed_fields',
            'snapshot',
            'created_at',
        ]
        read_only_fields = fields


class OperationTaskCommentSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source='author.full_name', read_only=True)

    class Meta:
        model = OperationTaskComment
        fields = ['id', 'task', 'author', 'author_name', 'comment', 'created_at', 'updated_at']
        read_only_fields = ['task', 'author', 'author_name', 'created_at', 'updated_at']


class OperationTaskEvidenceSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.CharField(source='uploaded_by.full_name', read_only=True)
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = OperationTaskEvidence
        fields = [
            'id',
            'task',
            'evidence_type',
            'file',
            'file_url',
            'original_name',
            'content_type',
            'size',
            'comment',
            'uploaded_by',
            'uploaded_by_name',
            'stage',
            'geometry',
            'metadata',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['task', 'original_name', 'content_type', 'size', 'uploaded_by', 'uploaded_by_name', 'created_at', 'updated_at']

    def get_file_url(self, obj):
        if not obj.file:
            return ''
        request = self.context.get('request')
        url = obj.file.url
        return request.build_absolute_uri(url) if request else url

    def validate_file(self, uploaded_file):
        extension = os.path.splitext(uploaded_file.name)[1].lower()
        if extension not in ALLOWED_EVIDENCE_EXTENSIONS:
            raise serializers.ValidationError('Tipo de archivo no permitido para evidencia.')
        if uploaded_file.size > MAX_EVIDENCE_SIZE:
            raise serializers.ValidationError('La evidencia supera el maximo de 20 MB.')
        return uploaded_file

    def validate(self, attrs):
        metadata = _parse_json_value(attrs.get('metadata'), 'metadata')
        geometry = _parse_json_value(attrs.get('geometry'), 'geometry')
        if metadata is not None:
            attrs['metadata'] = metadata
        if geometry is not None:
            try:
                validate_geojson_geometry(geometry, allowed_geometry_type='ANY')
            except DjangoValidationError as exc:
                raise serializers.ValidationError({'geometry': exc.messages})
            attrs['geometry'] = geometry
        return attrs


class OperationTaskBlockSerializer(serializers.ModelSerializer):
    reason_name = serializers.CharField(source='reason.name', read_only=True)
    responsible_user_name = serializers.CharField(source='responsible_user.full_name', read_only=True)
    resolved_by_name = serializers.CharField(source='resolved_by.full_name', read_only=True)

    class Meta:
        model = OperationTaskBlock
        fields = [
            'id',
            'task',
            'reason',
            'reason_name',
            'description',
            'started_at',
            'responsible_user',
            'responsible_user_name',
            'estimated_resolution_at',
            'resolved_at',
            'resolved_by',
            'resolved_by_name',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['task', 'resolved_at', 'resolved_by', 'created_at', 'updated_at']


class OperationTaskReadSerializer(CostProtectedSerializerMixin, serializers.ModelSerializer):
    task_type_name = serializers.CharField(source='task_type.name', read_only=True)
    area_name = serializers.CharField(source='area.name', read_only=True)
    parcela_code = serializers.CharField(source='parcela.codigo_parcela', read_only=True)
    geo_asset_title = serializers.CharField(source='geo_asset.title', read_only=True)
    registered_by_name = serializers.CharField(source='registered_by.full_name', read_only=True)
    executor_user_name = serializers.CharField(source='executor_user.full_name', read_only=True)
    executor_name = serializers.CharField(source='executor.name', read_only=True)
    verified_by_name = serializers.CharField(source='verified_by.full_name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.full_name', read_only=True)
    updated_by_name = serializers.CharField(source='updated_by.full_name', read_only=True)
    project_name = serializers.CharField(source='project.name', read_only=True)
    parent_task_code = serializers.CharField(source='parent_task.code', read_only=True)
    evidences_count = serializers.IntegerField(read_only=True)
    comments_count = serializers.IntegerField(read_only=True)
    active_blocks_count = serializers.IntegerField(read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)
    active_block = serializers.SerializerMethodField()
    effective_geometry = serializers.SerializerMethodField()

    class Meta:
        model = OperationTask
        fields = [
            'id',
            'code',
            'title',
            'description',
            'task_type',
            'task_type_name',
            'area',
            'area_name',
            'priority',
            'status',
            'origin',
            'detected_at',
            'due_at',
            'executed_at',
            'verification_at',
            'closed_at',
            'registered_by',
            'registered_by_name',
            'executor_user',
            'executor_user_name',
            'executor',
            'executor_name',
            'executor_manual_label',
            'verified_by',
            'verified_by_name',
            'project',
            'project_name',
            'parent_task',
            'parent_task_code',
            'parcela',
            'parcela_code',
            'geo_asset',
            'geo_asset_title',
            'sector',
            'geometry',
            'effective_geometry',
            'geometry_type',
            'bbox',
            'center_lng',
            'center_lat',
            'cost_estimated',
            'cost_real',
            'requires_budget',
            'approval_status',
            'expected_result',
            'obtained_result',
            'observations',
            'tags',
            'is_active',
            'is_overdue',
            'evidences_count',
            'comments_count',
            'active_blocks_count',
            'active_block',
            'created_by',
            'created_by_name',
            'updated_by',
            'updated_by_name',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields

    def get_active_block(self, obj):
        block = next((item for item in getattr(obj, 'prefetched_active_blocks', []) if item.is_active), None)
        if not block:
            block = obj.blocks.filter(is_active=True).select_related('reason', 'responsible_user').first()
        return OperationTaskBlockSerializer(block, context=self.context).data if block else None

    def get_effective_geometry(self, obj):
        if obj.geometry:
            return {'source': 'task', 'geometry': obj.geometry}
        if obj.geo_asset_id and obj.geo_asset and obj.geo_asset.geometry:
            return {'source': 'geo_asset', 'geometry': obj.geo_asset.geometry}
        return {'source': '', 'geometry': None}


class OperationTaskDetailSerializer(OperationTaskReadSerializer):
    evidences = OperationTaskEvidenceSerializer(many=True, read_only=True)
    comments = OperationTaskCommentSerializer(many=True, read_only=True)
    history = OperationTaskHistorySerializer(many=True, read_only=True)

    class Meta(OperationTaskReadSerializer.Meta):
        fields = OperationTaskReadSerializer.Meta.fields + ['evidences', 'comments', 'history']
        read_only_fields = fields


class OperationTaskWriteSerializer(serializers.ModelSerializer):
    task_type = serializers.PrimaryKeyRelatedField(queryset=OperationTaskType.objects.filter(is_active=True))
    area = serializers.PrimaryKeyRelatedField(queryset=OperationArea.objects.filter(is_active=True))
    parcela = serializers.PrimaryKeyRelatedField(queryset=Parcel.objects.all(), required=False, allow_null=True)
    geo_asset = serializers.PrimaryKeyRelatedField(queryset=GeoAsset.objects.filter(is_deleted=False), required=False, allow_null=True)
    executor = serializers.PrimaryKeyRelatedField(queryset=OperationExecutor.objects.filter(is_active=True), required=False, allow_null=True)
    executor_user = serializers.PrimaryKeyRelatedField(queryset=User.objects.filter(is_active=True), required=False, allow_null=True)
    registered_by = serializers.PrimaryKeyRelatedField(queryset=User.objects.filter(is_active=True), required=False, allow_null=True)
    verified_by = serializers.PrimaryKeyRelatedField(queryset=User.objects.filter(is_active=True), required=False, allow_null=True)
    project = serializers.PrimaryKeyRelatedField(queryset=OperationProject.objects.filter(is_active=True), required=False, allow_null=True)
    parent_task = serializers.PrimaryKeyRelatedField(queryset=OperationTask.objects.filter(is_deleted=False), required=False, allow_null=True)

    class Meta:
        model = OperationTask
        fields = [
            'id',
            'code',
            'title',
            'description',
            'task_type',
            'area',
            'priority',
            'status',
            'origin',
            'detected_at',
            'due_at',
            'executed_at',
            'verification_at',
            'closed_at',
            'registered_by',
            'executor_user',
            'executor',
            'executor_manual_label',
            'verified_by',
            'project',
            'parent_task',
            'parcela',
            'geo_asset',
            'sector',
            'geometry',
            'cost_estimated',
            'cost_real',
            'requires_budget',
            'approval_status',
            'expected_result',
            'obtained_result',
            'observations',
            'tags',
            'is_active',
        ]
        read_only_fields = ['id', 'code']

    def validate(self, attrs):
        request = self.context.get('request')
        if self.instance and 'status' in self.initial_data and attrs.get('status', self.instance.status) != self.instance.status:
            raise serializers.ValidationError({'status': 'Usa las acciones de transicion para cambiar el estado.'})
        if not self.instance and attrs.get('status', OperationTaskStatus.DETECTED) != OperationTaskStatus.DETECTED:
            raise serializers.ValidationError({'status': 'Las tareas nuevas deben iniciar en Detectado; usa acciones para avanzar el flujo.'})
        if request and not can_manage_costs(request.user) and {'cost_estimated', 'cost_real'}.intersection(self.initial_data):
            raise exceptions.PermissionDenied('No tienes permiso para gestionar costos.')

        geometry = _parse_json_value(attrs.get('geometry'), 'geometry')
        if geometry is not None:
            try:
                validate_geojson_geometry(geometry, allowed_geometry_type='ANY')
            except DjangoValidationError as exc:
                raise serializers.ValidationError({'geometry': exc.messages})
            attrs['geometry'] = geometry
        tags = _parse_json_value(attrs.get('tags'), 'tags')
        if tags is not None:
            attrs['tags'] = tags

        geo_asset = attrs.get('geo_asset', self.instance.geo_asset if self.instance else None)
        if geo_asset and not attrs.get('parcela') and not (self.instance and self.instance.parcela_id):
            attrs['parcela'] = geo_asset.parcela

        status = attrs.get('status', self.instance.status if self.instance else OperationTaskStatus.DETECTED)
        executor = attrs.get('executor', self.instance.executor if self.instance else None)
        executor_user = attrs.get('executor_user', self.instance.executor_user if self.instance else None)
        executor_manual_label = attrs.get('executor_manual_label', self.instance.executor_manual_label if self.instance else '')
        if status in {OperationTaskStatus.ASSIGNED, OperationTaskStatus.IN_PROGRESS} and not (executor or executor_user or executor_manual_label):
            raise serializers.ValidationError({'executor': 'Debes informar un ejecutor para asignar o ejecutar.'})
        if status == OperationTaskStatus.CLOSED and not attrs.get('verification_at', self.instance.verification_at if self.instance else None):
            raise serializers.ValidationError({'status': 'No se puede cerrar sin verificacion.'})
        if status == OperationTaskStatus.EXECUTED and not attrs.get('obtained_result', self.instance.obtained_result if self.instance else ''):
            raise serializers.ValidationError({'obtained_result': 'Debes registrar el resultado ejecutado.'})
        return attrs

    def create(self, validated_data):
        request = self.context.get('request')
        if request and request.user and request.user.is_authenticated:
            validated_data.setdefault('registered_by', request.user)
        return super().create(validated_data)


class OperationTaskMapSerializer(OperationTaskReadSerializer):
    class Meta(OperationTaskReadSerializer.Meta):
        fields = [
            'id',
            'code',
            'title',
            'status',
            'priority',
            'area',
            'area_name',
            'task_type',
            'task_type_name',
            'geo_asset',
            'geo_asset_title',
            'parcela',
            'parcela_code',
            'sector',
            'detected_at',
            'due_at',
            'effective_geometry',
            'is_overdue',
            'updated_at',
        ]
        read_only_fields = fields


class OperationMaintenanceTemplateSerializer(serializers.ModelSerializer):
    task_type_name = serializers.CharField(source='task_type.name', read_only=True)
    area_name = serializers.CharField(source='area.name', read_only=True)
    geo_asset_title = serializers.CharField(source='geo_asset.title', read_only=True)
    parcela_code = serializers.CharField(source='parcela.codigo_parcela', read_only=True)
    default_executor_name = serializers.CharField(source='default_executor.name', read_only=True)

    class Meta:
        model = OperationMaintenanceTemplate
        fields = [
            'id',
            'name',
            'description',
            'task_type',
            'task_type_name',
            'area',
            'area_name',
            'priority',
            'frequency',
            'interval_count',
            'next_run_at',
            'last_generated_at',
            'geo_asset',
            'geo_asset_title',
            'parcela',
            'parcela_code',
            'sector',
            'default_executor',
            'default_executor_name',
            'default_due_days',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['last_generated_at', 'created_at', 'updated_at']


class OperationReportExportSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.full_name', read_only=True)

    class Meta:
        model = OperationReportExport
        fields = ['id', 'user', 'user_name', 'filters', 'file_name', 'total_tasks', 'period_start', 'period_end', 'created_at', 'updated_at']
        read_only_fields = fields


class OperationTransitionSerializer(serializers.Serializer):
    new_status = serializers.ChoiceField(choices=OperationTaskStatus.choices)
    comment = serializers.CharField(required=False, allow_blank=True)
    reason = serializers.CharField(required=False, allow_blank=True)
    force = serializers.BooleanField(required=False, default=False)
    obtained_result = serializers.CharField(required=False, allow_blank=True)


class OperationAssignSerializer(serializers.Serializer):
    executor = serializers.PrimaryKeyRelatedField(queryset=OperationExecutor.objects.filter(is_active=True), required=False, allow_null=True)
    executor_user = serializers.PrimaryKeyRelatedField(queryset=User.objects.filter(is_active=True), required=False, allow_null=True)
    executor_manual_label = serializers.CharField(required=False, allow_blank=True, max_length=180)
    comment = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if not (attrs.get('executor') or attrs.get('executor_user') or attrs.get('executor_manual_label')):
            raise serializers.ValidationError({'executor': 'Debes informar executor, executor_user o executor_manual_label.'})
        return attrs


class OperationBlockSerializer(serializers.Serializer):
    reason = serializers.PrimaryKeyRelatedField(queryset=OperationBlockReason.objects.filter(is_active=True), required=False, allow_null=True)
    description = serializers.CharField()
    responsible_user = serializers.PrimaryKeyRelatedField(queryset=User.objects.filter(is_active=True), required=False, allow_null=True)
    estimated_resolution_at = serializers.DateTimeField(required=False, allow_null=True)


class OperationUnblockSerializer(serializers.Serializer):
    comment = serializers.CharField(required=False, allow_blank=True)
    next_status = serializers.ChoiceField(
        choices=[
            (OperationTaskStatus.EVALUATED, OperationTaskStatus.EVALUATED.label),
            (OperationTaskStatus.ASSIGNED, OperationTaskStatus.ASSIGNED.label),
            (OperationTaskStatus.IN_PROGRESS, OperationTaskStatus.IN_PROGRESS.label),
        ],
        required=False,
        default=OperationTaskStatus.EVALUATED,
    )


class OperationVerifySerializer(serializers.Serializer):
    comment = serializers.CharField(required=False, allow_blank=True)


class OperationCloseSerializer(serializers.Serializer):
    comment = serializers.CharField(required=False, allow_blank=True)
    force = serializers.BooleanField(required=False, default=False)


class OperationCommentCreateSerializer(serializers.Serializer):
    comment = serializers.CharField()


def operations_choice_payload():
    return {
        'statuses': {value: label for value, label in OperationTaskStatus.choices},
        'priorities': {value: label for value, label in OperationPriority.choices},
        'approval_statuses': {value: label for value, label in OperationApprovalStatus.choices},
        'evidence_types': {value: label for value, label in OperationEvidenceType.choices},
        'executor_kinds': {value: label for value, label in OperationExecutorKind.choices},
    }
