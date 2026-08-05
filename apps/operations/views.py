from django.db import transaction
from django.db.models import Count, Prefetch, Q
from django.utils import timezone
from rest_framework import decorators, parsers, response, status, viewsets

from apps.accounts.models import UserRole
from apps.core.permissions import RoleBasedActionPermission
from apps.operations.filters import OperationTaskFilter
from apps.operations.models import (
    OperationArea,
    OperationBlockReason,
    OperationExecutor,
    OperationMaintenanceTemplate,
    OperationProject,
    OperationReportExport,
    OperationTask,
    OperationTaskBlock,
    OperationTaskComment,
    OperationTaskEvidence,
    OperationTaskStatus,
    OperationTaskType,
)
from apps.operations.serializers import (
    OperationAreaSerializer,
    OperationAssignSerializer,
    OperationBlockReasonSerializer,
    OperationBlockSerializer,
    OperationCloseSerializer,
    OperationCommentCreateSerializer,
    OperationExecutorSerializer,
    OperationMaintenanceTemplateSerializer,
    OperationProjectSerializer,
    OperationTaskBlockSerializer,
    OperationTaskCommentSerializer,
    OperationTaskDetailSerializer,
    OperationTaskEvidenceSerializer,
    OperationTaskHistorySerializer,
    OperationTaskMapSerializer,
    OperationTaskReadSerializer,
    OperationTaskTypeSerializer,
    OperationTaskWriteSerializer,
    OperationTransitionSerializer,
    OperationUnblockSerializer,
    OperationVerifySerializer,
    operations_choice_payload,
)
from apps.operations.permissions import can_view_costs
from apps.operations.services.geojson import tasks_to_feature_collection
from apps.operations.services.pdf import render_operation_report_pdf
from apps.operations.services.reports import build_report_payload, build_summary
from apps.operations.services.transitions import assign_task, create_history, reopen_task, transition_task, verify_task


class OperationCatalogViewSet(viewsets.ModelViewSet):
    permission_classes = [RoleBasedActionPermission]
    required_roles_per_action = {
        'list': UserRole.CONSULTA,
        'retrieve': UserRole.CONSULTA,
        'create': UserRole.ADMINISTRADOR,
        'update': UserRole.ADMINISTRADOR,
        'partial_update': UserRole.ADMINISTRADOR,
        'destroy': UserRole.ADMINISTRADOR,
    }
    search_fields = ['name', 'slug', 'description']
    filterset_fields = ['is_active']
    ordering_fields = ['sort_order', 'name', 'created_at']

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user, updated_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)


class OperationAreaViewSet(OperationCatalogViewSet):
    queryset = OperationArea.objects.filter(is_deleted=False)
    serializer_class = OperationAreaSerializer


class OperationTaskTypeViewSet(OperationCatalogViewSet):
    queryset = OperationTaskType.objects.filter(is_deleted=False)
    serializer_class = OperationTaskTypeSerializer


class OperationBlockReasonViewSet(OperationCatalogViewSet):
    queryset = OperationBlockReason.objects.filter(is_deleted=False)
    serializer_class = OperationBlockReasonSerializer


class OperationExecutorViewSet(viewsets.ModelViewSet):
    serializer_class = OperationExecutorSerializer
    permission_classes = [RoleBasedActionPermission]
    search_fields = ['name', 'contact', 'notes', 'user__email']
    filterset_fields = ['kind', 'is_active', 'user']
    ordering_fields = ['kind', 'name', 'created_at']

    required_roles_per_action = {
        'list': UserRole.CONSULTA,
        'retrieve': UserRole.CONSULTA,
        'create': UserRole.OPERADOR,
        'update': UserRole.OPERADOR,
        'partial_update': UserRole.OPERADOR,
        'destroy': UserRole.ADMINISTRADOR,
    }

    def get_queryset(self):
        return OperationExecutor.objects.select_related('user').filter(is_deleted=False)

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user, updated_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)


class OperationProjectViewSet(viewsets.ModelViewSet):
    serializer_class = OperationProjectSerializer
    permission_classes = [RoleBasedActionPermission]
    search_fields = ['name', 'description', 'responsible__email', 'responsible__first_name', 'responsible__last_name']
    filterset_fields = ['status', 'is_active', 'responsible']
    ordering_fields = ['name', 'status', 'created_at', 'due_at']

    required_roles_per_action = {
        'list': UserRole.CONSULTA,
        'retrieve': UserRole.CONSULTA,
        'create': UserRole.OPERADOR,
        'update': UserRole.OPERADOR,
        'partial_update': UserRole.OPERADOR,
        'destroy': UserRole.ADMINISTRADOR,
    }

    def get_queryset(self):
        return (
            OperationProject.objects.select_related('responsible')
            .filter(is_deleted=False)
            .annotate(
                tasks_count=Count('tasks', filter=Q(tasks__is_deleted=False)),
                closed_tasks_count=Count('tasks', filter=Q(tasks__is_deleted=False, tasks__status=OperationTaskStatus.CLOSED)),
            )
        )

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user, updated_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)


class OperationMaintenanceTemplateViewSet(viewsets.ModelViewSet):
    serializer_class = OperationMaintenanceTemplateSerializer
    permission_classes = [RoleBasedActionPermission]
    search_fields = ['name', 'description', 'sector', 'geo_asset__title', 'parcela__codigo_parcela']
    filterset_fields = ['task_type', 'area', 'priority', 'frequency', 'is_active', 'geo_asset', 'parcela', 'default_executor']
    ordering_fields = ['next_run_at', 'name', 'created_at']

    required_roles_per_action = {
        'list': UserRole.CONSULTA,
        'retrieve': UserRole.CONSULTA,
        'create': UserRole.ADMINISTRADOR,
        'update': UserRole.ADMINISTRADOR,
        'partial_update': UserRole.ADMINISTRADOR,
        'destroy': UserRole.ADMINISTRADOR,
    }

    def get_queryset(self):
        return (
            OperationMaintenanceTemplate.objects.select_related('task_type', 'area', 'geo_asset', 'parcela', 'default_executor')
            .filter(is_deleted=False)
        )

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user, updated_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)


class OperationTaskViewSet(viewsets.ModelViewSet):
    permission_classes = [RoleBasedActionPermission]
    parser_classes = [parsers.JSONParser, parsers.MultiPartParser, parsers.FormParser]
    filterset_class = OperationTaskFilter
    search_fields = [
        'code',
        'title',
        'description',
        'sector',
        'geo_asset__title',
        'parcela__codigo_parcela',
        'executor__name',
        'executor_user__email',
        'executor_manual_label',
    ]
    ordering_fields = ['detected_at', 'created_at', 'updated_at', 'due_at', 'closed_at', 'priority', 'status']

    required_roles_per_action = {
        'list': UserRole.CONSULTA,
        'retrieve': UserRole.CONSULTA,
        'choices': UserRole.CONSULTA,
        'map': UserRole.CONSULTA,
        'geojson': UserRole.CONSULTA,
        'summary': UserRole.CONSULTA,
        'report_pdf': UserRole.CONSULTA,
        'history': UserRole.CONSULTA,
        'comments': UserRole.CONSULTA,
        'evidences': UserRole.CONSULTA,
        'create': UserRole.OPERADOR,
        'update': UserRole.OPERADOR,
        'partial_update': UserRole.OPERADOR,
        'transition': UserRole.OPERADOR,
        'assign': UserRole.OPERADOR,
        'block': UserRole.OPERADOR,
        'unblock': UserRole.OPERADOR,
        'verify': UserRole.OPERADOR,
        'close': UserRole.OPERADOR,
        'reopen': UserRole.ADMINISTRADOR,
        'cancel': UserRole.OPERADOR,
        'destroy': UserRole.ADMINISTRADOR,
    }

    def get_queryset(self):
        active_blocks = OperationTaskBlock.objects.filter(is_active=True).select_related('reason', 'responsible_user')
        return (
            OperationTask.objects.select_related(
                'task_type',
                'area',
                'parcela',
                'geo_asset',
                'executor',
                'executor_user',
                'registered_by',
                'verified_by',
                'created_by',
                'updated_by',
                'project',
                'parent_task',
            )
            .prefetch_related(Prefetch('blocks', queryset=active_blocks, to_attr='prefetched_active_blocks'))
            .filter(is_deleted=False)
            .annotate(
                evidences_count=Count('evidences', distinct=True),
                comments_count=Count('comments', distinct=True),
                active_blocks_count=Count('blocks', filter=Q(blocks__is_active=True), distinct=True),
            )
            .order_by('-detected_at', '-created_at')
        )

    def get_serializer_class(self):
        if self.action in {'create', 'update', 'partial_update'}:
            return OperationTaskWriteSerializer
        if self.action == 'retrieve':
            return OperationTaskDetailSerializer
        if self.action == 'map':
            return OperationTaskMapSerializer
        return OperationTaskReadSerializer

    def _period_bounds(self):
        filterset = self.filterset_class(data=self.request.query_params, queryset=self.get_queryset(), request=self.request)
        return filterset._period_bounds()

    def _filters_payload(self):
        return {
            key: values if len(values) > 1 else values[0]
            for key, values in self.request.query_params.lists()
        }

    def perform_create(self, serializer):
        task = serializer.save(created_by=self.request.user, updated_by=self.request.user)
        create_history(task, user=self.request.user, action='created', new_status=task.status)

    def perform_update(self, serializer):
        previous = OperationTask.objects.get(pk=serializer.instance.pk)
        task = serializer.save(updated_by=self.request.user)
        changed = {
            field: {'from': getattr(previous, field), 'to': getattr(task, field)}
            for field in ['title', 'status', 'priority', 'due_at', 'executor_id', 'executor_user_id', 'geo_asset_id', 'parcela_id']
            if getattr(previous, field) != getattr(task, field)
        }
        if changed:
            create_history(
                task,
                user=self.request.user,
                action='updated',
                previous_status=previous.status,
                new_status=task.status,
                changed_fields=changed,
            )

    def perform_destroy(self, instance):
        previous_status = instance.status
        instance.is_active = False
        instance.save(update_fields=['is_active', 'updated_at'])
        instance.delete()
        create_history(instance, user=self.request.user, action='deleted', previous_status=previous_status, new_status=instance.status)

    @decorators.action(detail=False, methods=['get'])
    def choices(self, request):
        return response.Response(operations_choice_payload())

    @decorators.action(detail=False, methods=['get'])
    def map(self, request):
        queryset = self.filter_queryset(self.get_queryset()).exclude(Q(geometry__isnull=True) & Q(geo_asset__isnull=True))[:1000]
        serializer = self.get_serializer(queryset, many=True)
        return response.Response(serializer.data)

    @decorators.action(detail=False, methods=['get'])
    def geojson(self, request):
        queryset = self.filter_queryset(self.get_queryset()).exclude(Q(geometry__isnull=True) & Q(geo_asset__isnull=True))[:1000]
        return response.Response(tasks_to_feature_collection(queryset))

    @decorators.action(detail=False, methods=['get'])
    def summary(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        start, end = self._period_bounds()
        return response.Response(build_summary(queryset, start=start, end=end, include_costs=can_view_costs(request.user)))

    @decorators.action(detail=False, methods=['get'], url_path='report-pdf')
    def report_pdf(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        start, end = self._period_bounds()
        filters_payload = self._filters_payload()
        generated_by = getattr(request.user, 'full_name', '') or getattr(request.user, 'email', '') or getattr(request.user, 'username', '')
        payload = build_report_payload(
            queryset,
            filters=filters_payload,
            start=start,
            end=end,
            include_costs=can_view_costs(request.user),
            generated_by=generated_by,
        )
        period_suffix = start.strftime('%Y_%m_%d') if start else timezone.now().strftime('%Y_%m')
        filename = f'informe_operacional_{period_suffix}.pdf'
        OperationReportExport.objects.create(
            user=request.user,
            filters=filters_payload,
            file_name=filename,
            total_tasks=queryset.count(),
            period_start=start.date() if start else None,
            period_end=end.date() if end else None,
        )
        return render_operation_report_pdf(payload, filename=filename)

    @decorators.action(detail=True, methods=['post'])
    def transition(self, request, pk=None):
        task = self.get_object()
        serializer = OperationTransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if 'obtained_result' in serializer.validated_data:
            task.obtained_result = serializer.validated_data.get('obtained_result') or task.obtained_result
        task = transition_task(
            task,
            new_status=serializer.validated_data['new_status'],
            user=request.user,
            comment=serializer.validated_data.get('comment', ''),
            reason=serializer.validated_data.get('reason', ''),
            force=serializer.validated_data.get('force', False),
            changed_fields={'obtained_result': bool(serializer.validated_data.get('obtained_result'))},
        )
        return response.Response(OperationTaskDetailSerializer(task, context={'request': request}).data)

    @decorators.action(detail=True, methods=['post'])
    def assign(self, request, pk=None):
        task = self.get_object()
        serializer = OperationAssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        task = assign_task(task, user=request.user, **serializer.validated_data)
        return response.Response(OperationTaskDetailSerializer(task, context={'request': request}).data)

    @decorators.action(detail=True, methods=['post'])
    def block(self, request, pk=None):
        task = self.get_object()
        serializer = OperationBlockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            block = OperationTaskBlock.objects.create(
                task=task,
                reason=serializer.validated_data.get('reason'),
                description=serializer.validated_data['description'],
                responsible_user=serializer.validated_data.get('responsible_user'),
                estimated_resolution_at=serializer.validated_data.get('estimated_resolution_at'),
                created_by=request.user,
                updated_by=request.user,
            )
            if task.status != OperationTaskStatus.BLOCKED:
                task = transition_task(
                    task,
                    new_status=OperationTaskStatus.BLOCKED,
                    user=request.user,
                    comment=serializer.validated_data['description'],
                    reason=block.reason.name if block.reason_id else '',
                    changed_fields={'block_id': block.id},
                )
            else:
                create_history(task, user=request.user, action='block', previous_status=task.status, new_status=task.status, changed_fields={'block_id': block.id})
        return response.Response(OperationTaskBlockSerializer(block, context={'request': request}).data, status=status.HTTP_201_CREATED)

    @decorators.action(detail=True, methods=['post'])
    def unblock(self, request, pk=None):
        task = self.get_object()
        serializer = OperationUnblockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        block = task.blocks.filter(is_active=True).first()
        if not block:
            return response.Response({'detail': 'La tarea no tiene bloqueo activo.'}, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            block.is_active = False
            block.resolved_at = timezone.now()
            block.resolved_by = request.user
            block.updated_by = request.user
            block.save()
            task = transition_task(
                task,
                new_status=serializer.validated_data['next_status'],
                user=request.user,
                comment=serializer.validated_data.get('comment', ''),
                changed_fields={'resolved_block_id': block.id},
            )
        return response.Response(OperationTaskDetailSerializer(task, context={'request': request}).data)

    @decorators.action(detail=True, methods=['post'])
    def verify(self, request, pk=None):
        task = self.get_object()
        serializer = OperationVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        task = verify_task(task, user=request.user, comment=serializer.validated_data.get('comment', ''))
        return response.Response(OperationTaskDetailSerializer(task, context={'request': request}).data)

    @decorators.action(detail=True, methods=['post'])
    def close(self, request, pk=None):
        task = self.get_object()
        serializer = OperationCloseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        task = transition_task(
            task,
            new_status=OperationTaskStatus.CLOSED,
            user=request.user,
            comment=serializer.validated_data.get('comment', ''),
            force=serializer.validated_data.get('force', False),
            changed_fields={'force': serializer.validated_data.get('force', False)},
        )
        return response.Response(OperationTaskDetailSerializer(task, context={'request': request}).data)

    @decorators.action(detail=True, methods=['post'])
    def reopen(self, request, pk=None):
        task = self.get_object()
        serializer = OperationUnblockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        task = reopen_task(task, user=request.user, comment=serializer.validated_data.get('comment', ''), next_status=serializer.validated_data['next_status'])
        return response.Response(OperationTaskDetailSerializer(task, context={'request': request}).data)

    @decorators.action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        task = self.get_object()
        task = transition_task(
            task,
            new_status=OperationTaskStatus.CANCELLED,
            user=request.user,
            comment=request.data.get('comment', ''),
            reason=request.data.get('reason', ''),
        )
        return response.Response(OperationTaskDetailSerializer(task, context={'request': request}).data)

    @decorators.action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        task = self.get_object()
        serializer = OperationTaskHistorySerializer(task.history.select_related('user'), many=True, context={'request': request})
        return response.Response(serializer.data)

    @decorators.action(detail=True, methods=['get', 'post'])
    def comments(self, request, pk=None):
        task = self.get_object()
        if request.method == 'GET':
            serializer = OperationTaskCommentSerializer(task.comments.select_related('author'), many=True, context={'request': request})
            return response.Response(serializer.data)
        create_serializer = OperationCommentCreateSerializer(data=request.data)
        create_serializer.is_valid(raise_exception=True)
        comment = OperationTaskComment.objects.create(
            task=task,
            author=request.user,
            comment=create_serializer.validated_data['comment'],
            created_by=request.user,
            updated_by=request.user,
        )
        create_history(task, user=request.user, action='comment', previous_status=task.status, new_status=task.status)
        return response.Response(OperationTaskCommentSerializer(comment, context={'request': request}).data, status=status.HTTP_201_CREATED)

    @decorators.action(detail=True, methods=['get', 'post'])
    def evidences(self, request, pk=None):
        task = self.get_object()
        if request.method == 'GET':
            serializer = OperationTaskEvidenceSerializer(task.evidences.select_related('uploaded_by'), many=True, context={'request': request})
            return response.Response(serializer.data)
        serializer = OperationTaskEvidenceSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        evidence = serializer.save(task=task, uploaded_by=request.user, created_by=request.user, updated_by=request.user, stage=request.data.get('stage') or task.status)
        create_history(
            task,
            user=request.user,
            action='evidence',
            previous_status=task.status,
            new_status=task.status,
            changed_fields={'evidence_id': evidence.id},
        )
        return response.Response(OperationTaskEvidenceSerializer(evidence, context={'request': request}).data, status=status.HTTP_201_CREATED)
