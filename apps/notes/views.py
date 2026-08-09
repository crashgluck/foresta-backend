from rest_framework import viewsets

from apps.accounts.models import UserRole
from apps.core.permissions import RoleBasedActionPermission
from apps.core.viewsets import CachedModelViewSet
from apps.notes.models import AdministrativeNote
from apps.notes.serializers import AdministrativeNoteSerializer


class AdministrativeNoteViewSet(CachedModelViewSet):
    queryset = AdministrativeNote.objects.select_related('parcela', 'usuario_registra').all()
    serializer_class = AdministrativeNoteSerializer
    permission_classes = [RoleBasedActionPermission]
    search_fields = ['parcela__codigo_parcela', 'texto']
    filterset_fields = ['parcela', 'tipo', 'usuario_registra']
    ordering_fields = ['fecha_evento', 'created_at']

    required_roles_per_action = {
        'list': UserRole.CONSULTA,
        'retrieve': UserRole.CONSULTA,
        'create': UserRole.OPERADOR,
        'update': UserRole.OPERADOR,
        'partial_update': UserRole.OPERADOR,
        'destroy': UserRole.ADMINISTRADOR,
    }

    def perform_create(self, serializer):
        serializer.save(usuario_registra=self.request.user)

