from django.contrib import admin

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
    OperationTaskHistory,
    OperationTaskType,
)


@admin.register(OperationArea, OperationTaskType, OperationBlockReason)
class OperationCatalogAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'is_active', 'sort_order')
    search_fields = ('name', 'slug', 'description')
    list_filter = ('is_active',)


@admin.register(OperationExecutor)
class OperationExecutorAdmin(admin.ModelAdmin):
    list_display = ('name', 'kind', 'user', 'is_active')
    search_fields = ('name', 'contact', 'user__email')
    list_filter = ('kind', 'is_active')


@admin.register(OperationProject)
class OperationProjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'status', 'responsible', 'due_at', 'is_active')
    search_fields = ('name', 'description', 'responsible__email')
    list_filter = ('status', 'is_active')


class OperationTaskEvidenceInline(admin.TabularInline):
    model = OperationTaskEvidence
    extra = 0
    readonly_fields = ('original_name', 'content_type', 'size', 'uploaded_by', 'created_at')


class OperationTaskBlockInline(admin.TabularInline):
    model = OperationTaskBlock
    extra = 0


@admin.register(OperationTask)
class OperationTaskAdmin(admin.ModelAdmin):
    list_display = ('code', 'title', 'status', 'priority', 'area', 'task_type', 'detected_at', 'due_at')
    search_fields = ('code', 'title', 'description', 'sector')
    list_filter = ('status', 'priority', 'area', 'task_type', 'origin')
    date_hierarchy = 'detected_at'
    inlines = [OperationTaskEvidenceInline, OperationTaskBlockInline]


@admin.register(OperationTaskHistory)
class OperationTaskHistoryAdmin(admin.ModelAdmin):
    list_display = ('task', 'action', 'previous_status', 'new_status', 'user', 'created_at')
    search_fields = ('task__code', 'task__title', 'action', 'comment', 'reason')
    list_filter = ('action', 'previous_status', 'new_status')
    readonly_fields = ('task', 'previous_status', 'new_status', 'user', 'action', 'comment', 'reason', 'changed_fields', 'snapshot', 'created_at')


admin.site.register(OperationTaskComment)
admin.site.register(OperationTaskEvidence)
admin.site.register(OperationTaskBlock)
admin.site.register(OperationMaintenanceTemplate)
admin.site.register(OperationReportExport)
