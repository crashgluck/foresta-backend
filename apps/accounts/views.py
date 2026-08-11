import secrets

from django.core.cache import cache
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.accounts.models import User, UserActorType, UserRole
from apps.accounts.serializers import (
    ChangePasswordSerializer,
    CurrentUserSerializer,
    CustomTokenObtainPairSerializer,
    RegisterSerializer,
    UserAvatarUploadSerializer,
    UserCreateSerializer,
    UserSerializer,
)
from apps.audits.models import SessionAction
from apps.audits.services import create_session_log
from apps.core.permissions import RoleBasedActionPermission, has_role_at_least
from apps.core.viewsets import CachedModelViewSet


class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(CurrentUserSerializer(user, context={'request': request}).data, status=status.HTTP_201_CREATED)


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)

        identifier = request.data.get('email') or request.data.get('username') or ''
        user = None
        if response.status_code == status.HTTP_200_OK:
            user_id = (response.data or {}).get('user', {}).get('id')
            if user_id:
                user = User.objects.filter(pk=user_id).first()

        create_session_log(
            request=request,
            action=SessionAction.LOGIN,
            success=response.status_code == status.HTTP_200_OK,
            user=user,
            auth_identifier=identifier,
            metadata={'status_code': response.status_code},
        )
        return response


class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        refresh = request.data.get('refresh')
        if not refresh:
            create_session_log(
                request=request,
                action=SessionAction.LOGOUT,
                success=False,
                user=request.user,
                auth_identifier=request.user.email,
                metadata={'reason': 'missing_refresh'},
            )
            return Response({'detail': 'Refresh token requerido'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            token = RefreshToken(refresh)
            token.blacklist()
        except TokenError:
            create_session_log(
                request=request,
                action=SessionAction.LOGOUT,
                success=False,
                user=request.user,
                auth_identifier=request.user.email,
                metadata={'reason': 'invalid_refresh'},
            )
            return Response({'detail': 'Refresh token invalido'}, status=status.HTTP_400_BAD_REQUEST)

        create_session_log(
            request=request,
            action=SessionAction.LOGOUT,
            success=True,
            user=request.user,
            auth_identifier=request.user.email,
            metadata={'status_code': status.HTTP_205_RESET_CONTENT},
        )
        return Response(status=status.HTTP_205_RESET_CONTENT)


class MeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(CurrentUserSerializer(request.user, context={'request': request}).data)


class MeAvatarView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        return self._save_avatar(request)

    def patch(self, request):
        return self._save_avatar(request)

    def _save_avatar(self, request):
        serializer = UserAvatarUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user
        previous_avatar = user.avatar
        user.avatar = serializer.validated_data['avatar']
        user.save(update_fields=['avatar', 'updated_at'])

        if previous_avatar and previous_avatar.name != user.avatar.name:
            previous_avatar.storage.delete(previous_avatar.name)

        return Response(CurrentUserSerializer(user, context={'request': request}).data)


class ChangePasswordView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user
        if not user.check_password(serializer.validated_data['old_password']):
            return Response({'old_password': ['Contrasena actual invalida']}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(serializer.validated_data['new_password'])
        user.save(update_fields=['password', 'updated_at'])
        create_session_log(
            request=request,
            action=SessionAction.PASSWORD_CHANGE,
            success=True,
            user=request.user,
            auth_identifier=request.user.email,
        )
        return Response({'detail': 'Contrasena actualizada'})


class PasswordResetRequestView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = (request.data.get('email') or '').strip().lower()
        if not email:
            return Response({'email': ['Correo requerido']}, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.filter(email__iexact=email).first()
        if not user:
            return Response({'detail': 'Si el correo existe, se enviara un codigo de recuperacion.'})

        token = secrets.token_urlsafe(24)
        cache_key = f'auth:password-reset:{email}:{token}'
        cache.set(cache_key, str(user.id), timeout=60 * 30)
        return Response(
            {
                'detail': 'Codigo de recuperacion generado.',
                'recovery_token': token,
                'expires_in_minutes': 30,
                'channel': 'manual_token',
            }
        )


class PasswordResetConfirmView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = (request.data.get('email') or '').strip().lower()
        token = (request.data.get('token') or '').strip()
        new_password = request.data.get('new_password') or ''
        if not email or not token or not new_password:
            return Response({'detail': 'email, token y new_password son obligatorios.'}, status=status.HTTP_400_BAD_REQUEST)
        if len(new_password) < 8:
            return Response({'new_password': ['Minimo 8 caracteres']}, status=status.HTTP_400_BAD_REQUEST)

        cache_key = f'auth:password-reset:{email}:{token}'
        user_id = cache.get(cache_key)
        if not user_id:
            return Response({'detail': 'Token inválido o expirado.'}, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.filter(id=user_id, email__iexact=email).first()
        if not user:
            return Response({'detail': 'Usuario no encontrado para este token.'}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password)
        user.save(update_fields=['password', 'updated_at'])
        cache.delete(cache_key)
        return Response({'detail': 'Contrasena restablecida correctamente.'})


class UserViewSet(CachedModelViewSet):
    queryset = User.objects.all().order_by('-created_at')
    permission_classes = [permissions.IsAuthenticated, RoleBasedActionPermission]
    search_fields = ['email', 'first_name', 'last_name', 'username']
    filterset_fields = ['role', 'is_active', 'is_staff']
    ordering_fields = ['created_at', 'email', 'role']

    required_roles_per_action = {
        'list': UserRole.ADMINISTRADOR,
        'retrieve': UserRole.ADMINISTRADOR,
        'create': UserRole.ADMINISTRADOR,
        'update': UserRole.ADMINISTRADOR,
        'partial_update': UserRole.ADMINISTRADOR,
        'destroy': UserRole.SUPERADMIN,
        'activate': UserRole.ADMINISTRADOR,
        'deactivate': UserRole.ADMINISTRADOR,
    }

    def get_serializer_class(self):
        if self.action == 'create':
            return UserCreateSerializer
        return UserSerializer

    def perform_create(self, serializer):
        role = serializer.validated_data.get('role', UserRole.CONSULTA)
        requester = self.request.user
        if role == UserRole.SUPERADMIN and not has_role_at_least(requester, UserRole.SUPERADMIN):
            raise permissions.PermissionDenied('Solo superadmin puede crear usuarios superadmin')
        serializer.save()

    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        user = self.get_object()
        user.is_active = True
        user.save(update_fields=['is_active', 'updated_at'])
        return Response({'detail': 'Usuario activado'})

    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        user = self.get_object()
        user.is_active = False
        user.save(update_fields=['is_active', 'updated_at'])
        return Response({'detail': 'Usuario desactivado'})


class RoleListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        data = [{'value': choice[0], 'label': choice[1]} for choice in UserRole.choices]
        return Response(data)


class ActorTypeListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        data = [{'value': choice[0], 'label': choice[1]} for choice in UserActorType.choices]
        return Response(data)


class CustomTokenRefreshView(TokenRefreshView):
    def post(self, request, *args, **kwargs):
        user = None
        identifier = ''
        raw_refresh = request.data.get('refresh')
        if raw_refresh:
            try:
                refresh_token = RefreshToken(raw_refresh)
                user_id = refresh_token.payload.get('user_id')
                if user_id:
                    user = User.objects.filter(pk=user_id).first()
                    identifier = user.email if user else str(user_id)
            except TokenError:
                identifier = ''

        response = super().post(request, *args, **kwargs)
        create_session_log(
            request=request,
            action=SessionAction.REFRESH,
            success=response.status_code == status.HTTP_200_OK,
            user=user,
            auth_identifier=identifier,
            metadata={'status_code': response.status_code},
        )
        return response
