from apps.accounts.models import UserRole
from apps.core.permissions import has_role_at_least


def can_view_costs(user) -> bool:
    return has_role_at_least(user, UserRole.ADMINISTRADOR)


def can_manage_costs(user) -> bool:
    return has_role_at_least(user, UserRole.ADMINISTRADOR)


def can_force_close(user) -> bool:
    return has_role_at_least(user, UserRole.ADMINISTRADOR)

