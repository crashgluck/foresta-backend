from __future__ import annotations

from django.db.models import Prefetch

from apps.people.models import OwnershipType, ParcelOwnership


PRIMARY_OWNER_PREFETCH_ATTR = 'display_primary_ownerships'


def primary_owner_queryset():
    return ParcelOwnership.objects.select_related('persona').filter(
        tipo=OwnershipType.PRINCIPAL,
        is_active=True,
        is_deleted=False,
    )


def primary_owner_prefetch(lookup: str = 'parcela__ownerships', *, to_attr: str = PRIMARY_OWNER_PREFETCH_ATTR):
    return Prefetch(lookup, queryset=primary_owner_queryset(), to_attr=to_attr)


def get_primary_owner_for_parcel(parcel):
    if not parcel:
        return None

    for attr_name in (PRIMARY_OWNER_PREFETCH_ATTR, 'map_primary_ownerships'):
        prefetched = getattr(parcel, attr_name, None)
        if prefetched is not None:
            ownership = prefetched[0] if prefetched else None
            return ownership.persona if ownership and ownership.persona else None

    ownerships_attr = getattr(parcel, 'ownerships', None)
    ownerships = ownerships_attr.all() if ownerships_attr is not None else []
    principal = next(
        (
            ownership
            for ownership in ownerships
            if not ownership.is_deleted and ownership.is_active and ownership.tipo == OwnershipType.PRINCIPAL and ownership.persona
        ),
        None,
    )
    return principal.persona if principal else None


def get_parcel_owner_display(parcel) -> tuple[str, str]:
    if not parcel:
        return '', ''

    parcel_code = parcel.codigo_parcela
    principal = get_primary_owner_for_parcel(parcel)

    if not principal:
        return parcel_code, parcel_code

    owner_name = principal.nombre_completo
    display = f'{parcel_code} - {owner_name}'.strip(' -')
    return parcel_code, display

