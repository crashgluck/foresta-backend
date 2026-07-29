from django.urls import path

from apps.iot.views import (
    NodotechComponentListView,
    NodotechRelayOffView,
    NodotechRelayOnView,
    NodotechRelayPulseView,
)


urlpatterns = [
    path('components/', NodotechComponentListView.as_view(), name='iot-components'),
    path('components', NodotechComponentListView.as_view(), name='iot-components-noslash'),
    path(
        'components/<int:component_id>/on/',
        NodotechRelayOnView.as_view(),
        name='iot-component-on',
    ),
    path(
        'components/<int:component_id>/on',
        NodotechRelayOnView.as_view(),
        name='iot-component-on-noslash',
    ),
    path(
        'components/<int:component_id>/off/',
        NodotechRelayOffView.as_view(),
        name='iot-component-off',
    ),
    path(
        'components/<int:component_id>/off',
        NodotechRelayOffView.as_view(),
        name='iot-component-off-noslash',
    ),
    path(
        'components/<int:component_id>/pulse/',
        NodotechRelayPulseView.as_view(),
        name='iot-component-pulse',
    ),
    path(
        'components/<int:component_id>/pulse',
        NodotechRelayPulseView.as_view(),
        name='iot-component-pulse-noslash',
    ),
]
