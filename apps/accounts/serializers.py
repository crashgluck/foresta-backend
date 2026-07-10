from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.accounts.models import User, UserActorType, UserRole


class UserSerializer(serializers.ModelSerializer):
    avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id',
            'email',
            'username',
            'first_name',
            'last_name',
            'phone',
            'role',
            'actor_type',
            'avatar_url',
            'is_active',
            'is_staff',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_avatar_url(self, obj):
        if not obj.avatar:
            return ''
        request = self.context.get('request')
        url = obj.avatar.url
        return request.build_absolute_uri(url) if request else url


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = [
            'id',
            'email',
            'username',
            'first_name',
            'last_name',
            'phone',
            'role',
            'actor_type',
            'is_active',
            'password',
        ]
        read_only_fields = ['id']

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User.objects.create_user(password=password, **validated_data)
        return user


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name', 'phone', 'password']
        read_only_fields = ['id']

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User.objects.create_user(
            password=password,
            role=UserRole.CONSULTA,
            actor_type=UserActorType.CONSULTA_EJECUTIVA,
            is_active=False,
            **validated_data,
        )
        return user


class CurrentUserSerializer(serializers.ModelSerializer):
    avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name', 'phone', 'role', 'actor_type', 'avatar_url', 'is_active']

    def get_avatar_url(self, obj):
        if not obj.avatar:
            return ''
        request = self.context.get('request')
        url = obj.avatar.url
        return request.build_absolute_uri(url) if request else url


class UserAvatarUploadSerializer(serializers.Serializer):
    avatar = serializers.FileField(write_only=True)

    allowed_content_types = {'image/jpeg', 'image/png', 'image/webp'}
    allowed_extensions = {'jpg', 'jpeg', 'png', 'webp'}
    max_size_bytes = 2 * 1024 * 1024

    def validate_avatar(self, value):
        content_type = getattr(value, 'content_type', '')
        extension = (value.name.rsplit('.', 1)[-1] if '.' in value.name else '').lower()
        if content_type not in self.allowed_content_types or extension not in self.allowed_extensions:
            raise serializers.ValidationError('Solo se permiten imagenes JPG, PNG o WEBP.')
        if value.size > self.max_size_bytes:
            raise serializers.ValidationError('La imagen no debe superar 2 MB.')
        return value


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, min_length=8)


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    username_field = 'email'

    def validate(self, attrs):
        data = super().validate(attrs)
        data['user'] = CurrentUserSerializer(self.user).data
        return data


