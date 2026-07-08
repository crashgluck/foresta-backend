from rest_framework import serializers

from django.db.models import Count, Sum

from apps.data_imports.models import ImportIssue, ImportJob, ImportRowResult, ImportSheetResult, ImportUploadSession


class ImportIssueSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImportIssue
        fields = '__all__'


class ImportRowResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImportRowResult
        fields = '__all__'


class ImportSheetResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImportSheetResult
        fields = '__all__'


class ImportJobSerializer(serializers.ModelSerializer):
    sheet_results = ImportSheetResultSerializer(many=True, read_only=True)
    issues_count = serializers.SerializerMethodField()
    row_results_count = serializers.SerializerMethodField()
    row_results_sample = serializers.SerializerMethodField()
    summary = serializers.SerializerMethodField()

    def get_issues_count(self, obj):
        return obj.issues.count()

    def get_row_results_count(self, obj):
        return obj.row_results.count()

    def get_row_results_sample(self, obj):
        queryset = obj.row_results.order_by('sheet_name', 'row_number', 'created_at')[:50]
        return ImportRowResultSerializer(queryset, many=True).data

    def get_summary(self, obj):
        details_summary = (obj.details or {}).get('summary')
        if details_summary:
            return details_summary

        sheet_totals = obj.sheet_results.aggregate(rows_read=Sum('rows_read'))
        total_rows_read = sheet_totals['rows_read'] or 0
        action_counts = {
            row['action']: row['total']
            for row in obj.row_results.values('action').annotate(total=Count('id'))
        }
        error_rows = obj.row_results.filter(action='ERROR', row_number__isnull=False).values('sheet_name', 'row_number').distinct().count()
        imported = obj.total_inserted + obj.total_updated
        return {
            'total_rows_read': total_rows_read,
            'total_valid': max(total_rows_read - error_rows, 0),
            'total_imported': imported,
            'total_new': obj.total_inserted,
            'total_updated': obj.total_updated,
            'total_skipped': obj.total_skipped,
            'total_errors': obj.total_errors,
            'total_warnings': obj.total_warnings,
            'row_actions': action_counts,
        }

    class Meta:
        model = ImportJob
        fields = '__all__'


class ImportUploadSessionSerializer(serializers.ModelSerializer):
    preview_job = ImportJobSerializer(read_only=True)
    executed_job = ImportJobSerializer(read_only=True)

    class Meta:
        model = ImportUploadSession
        fields = '__all__'

