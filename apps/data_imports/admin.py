from django.contrib import admin

from apps.data_imports.models import ImportIssue, ImportJob, ImportRowResult, ImportSheetResult


class ImportSheetResultInline(admin.TabularInline):
    model = ImportSheetResult
    extra = 0
    readonly_fields = ('sheet_name', 'status', 'rows_read', 'inserted', 'updated', 'skipped', 'errors', 'warnings')


@admin.register(ImportJob)
class ImportJobAdmin(admin.ModelAdmin):
    list_display = ('id', 'source_file', 'status', 'dry_run', 'started_at', 'finished_at')
    list_filter = ('status', 'dry_run')
    search_fields = ('source_file', 'source_path')
    inlines = [ImportSheetResultInline]


@admin.register(ImportIssue)
class ImportIssueAdmin(admin.ModelAdmin):
    list_display = ('import_job', 'severity', 'sheet_name', 'row_number', 'error_code')
    list_filter = ('severity', 'sheet_name')
    search_fields = ('message', 'column_name', 'error_code')


@admin.register(ImportRowResult)
class ImportRowResultAdmin(admin.ModelAdmin):
    list_display = ('import_job', 'sheet_name', 'row_number', 'entity', 'record_identifier', 'action')
    list_filter = ('action', 'sheet_name', 'entity')
    search_fields = ('record_identifier', 'message', 'entity')

