from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.accounts.views import (
    ChangePasswordView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    CustomTokenObtainPairView,
    CustomTokenRefreshView,
    LogoutView,
    MeAvatarView,
    MeView,
    ActorTypeListView,
    RegisterView,
    RoleListView,
    UserViewSet,
)

router = DefaultRouter()
router.register('users', UserViewSet, basename='users')

urlpatterns = [
    path('auth/register/', RegisterView.as_view(), name='register'),
    path('auth/login/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/refresh/', CustomTokenRefreshView.as_view(), name='token_refresh'),
    path('auth/logout/', LogoutView.as_view(), name='logout'),
    path('auth/me/', MeView.as_view(), name='me'),
    path('auth/me/avatar/', MeAvatarView.as_view(), name='me-avatar'),
    path('auth/change-password/', ChangePasswordView.as_view(), name='change_password'),
    path('auth/password-reset/request/', PasswordResetRequestView.as_view(), name='password-reset-request'),
    path('auth/password-reset/confirm/', PasswordResetConfirmView.as_view(), name='password-reset-confirm'),
    path('roles/', RoleListView.as_view(), name='roles-list'),
    path('actor-types/', ActorTypeListView.as_view(), name='actor-types-list'),
    path('', include(router.urls)),
]

