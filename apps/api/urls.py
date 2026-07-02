from django.urls import include, path, re_path
from rest_framework.routers import DefaultRouter

from apps.access_control.views import AccessRecordViewSet, BlacklistEntryViewSet
from apps.acquisitions.views import RFIDCardViewSet, RemoteControlViewSet, VehicleLogoViewSet
from apps.api.views import DashboardSummaryView
from apps.audits.views import AuditEventLogViewSet, UserSessionLogViewSet
from apps.data_imports.views import ImportIssueViewSet, ImportJobViewSet, ImportRowResultViewSet
from apps.finance.views import (
    CommonExpenseDebtViewSet,
    FinanceConsolidatedView,
    FinanceSummaryView,
    FinancialMovementViewSet,
    PaymentAgreementViewSet,
    ServiceDebtViewSet,
    UnpaidFineViewSet,
)
from apps.maps_app.views import ObjectiveViewSet, OwnersMapView, ParcelOptionsView, ParcelVisitSummaryView, VisitViewSet
from apps.missions.views import DroneFlightViewSet, MissionReportViewSet, MissionViewSet
from apps.notes.views import AdministrativeNoteViewSet
from apps.parcels.views import ParcelViewSet
from apps.people.views import ParcelOwnershipViewSet, ParcelResidentViewSet, PersonViewSet
from apps.supervisor.views import NotificationFineViewSet, RoundViewSet, ShiftViewSet
from apps.utilities.views import ServiceCutViewSet, ServiceHistoryViewSet
from apps.vehicles.views import VehicleViewSet
from apps.works.views import ParcelWorkStatusViewSet

router = DefaultRouter()
router.register('parcelas', ParcelViewSet, basename='parcelas')
router.register('personas', PersonViewSet, basename='personas')
router.register('propietarios', ParcelOwnershipViewSet, basename='propietarios')
router.register('residentes', ParcelResidentViewSet, basename='residentes')
router.register('vehiculos', VehicleViewSet, basename='vehiculos')
router.register('deudas-gc', CommonExpenseDebtViewSet, basename='deudas-gc')
router.register('deudas-servicios', ServiceDebtViewSet, basename='deudas-servicios')
router.register('convenios', PaymentAgreementViewSet, basename='convenios')
router.register('multas', UnpaidFineViewSet, basename='multas')
router.register('movimientos-financieros', FinancialMovementViewSet, basename='movimientos-financieros')
router.register('cortes', ServiceCutViewSet, basename='cortes')
router.register('servicios-historico', ServiceHistoryViewSet, basename='servicios-historico')
router.register('anotaciones', AdministrativeNoteViewSet, basename='anotaciones')
router.register('obras', ParcelWorkStatusViewSet, basename='obras')
router.register('imports/jobs', ImportJobViewSet, basename='import-jobs')
router.register('imports/issues', ImportIssueViewSet, basename='import-issues')
router.register('imports/row-results', ImportRowResultViewSet, basename='import-row-results')
router.register('access/access-records', AccessRecordViewSet, basename='access-records')
router.register('access/blacklist', BlacklistEntryViewSet, basename='access-blacklist')
router.register('maps/objectives', ObjectiveViewSet, basename='map-objectives')
router.register('maps/visits', VisitViewSet, basename='map-visits')
router.register('acquisitions/remote-controls', RemoteControlViewSet, basename='remote-controls')
router.register('acquisitions/rfid-cards', RFIDCardViewSet, basename='rfid-cards')
router.register('acquisitions/vehicle-logos', VehicleLogoViewSet, basename='vehicle-logos')
router.register('missions/missions', MissionViewSet, basename='missions')
router.register('missions/drone-flights', DroneFlightViewSet, basename='drone-flights')
router.register('missions/mission-reports', MissionReportViewSet, basename='mission-reports')
router.register('supervisor/shifts', ShiftViewSet, basename='supervisor-shifts')
router.register('supervisor/rounds', RoundViewSet, basename='supervisor-rounds')
router.register('supervisor/notifications', NotificationFineViewSet, basename='supervisor-notifications')
router.register('audits/events', AuditEventLogViewSet, basename='audit-events')
router.register('audits/sessions', UserSessionLogViewSet, basename='audit-sessions')

urlpatterns = [
    # Backward compatibility:
    # some legacy clients hit POST /imports/jobs/{id}/ expecting detail polling.
    # Accept POST as retrieve to avoid 405 during long-running import monitoring.
    re_path(
        r'^imports/jobs/(?P<pk>[0-9a-fA-F-]{36})/$',
        ImportJobViewSet.as_view({'get': 'retrieve', 'post': 'retrieve'}),
        name='import-jobs-detail-legacy-post',
    ),
    path('', include(router.urls)),
    path('dashboard/resumen/', DashboardSummaryView.as_view(), name='dashboard-resumen'),
    path('finance/summary/', FinanceSummaryView.as_view(), name='finance-summary'),
    path('finance/consolidated/', FinanceConsolidatedView.as_view(), name='finance-consolidated'),
    path('maps/owners-map/', OwnersMapView.as_view(), name='owners-map'),
    path('maps/visit-summary/', ParcelVisitSummaryView.as_view(), name='parcel-visit-summary'),
    path('maps/parcel-options/', ParcelOptionsView.as_view(), name='parcel-options'),
    path('iot/', include('apps.iot.urls')),
    path('', include('apps.accounts.urls')),
]
