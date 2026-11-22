"""Roles fijos de Darze y sus permisos (DOMAIN.md §9).

Se autoriza por permiso, no por nombre de rol: así un rol puede ganar o perder una capacidad
cambiando solo esta tabla. Cada módulo nuevo agrega aquí sus permisos.
"""

from enum import StrEnum


class Role(StrEnum):
    ADMIN = "ADMIN"
    EVENTS_MANAGER = "EVENTS_MANAGER"
    PURCHASING_MANAGER = "PURCHASING_MANAGER"


class Permission(StrEnum):
    USERS_MANAGE = "users:manage"
    ACCESS_LOG_READ = "access_log:read"
    CLIENTS_MANAGE = "clients:manage"
    CATALOG_READ = "catalog:read"
    CATALOG_MANAGE = "catalog:manage"
    QUOTES_MANAGE = "quotes:manage"
    DASHBOARD_READ = "dashboard:read"
    CONTRACTS_MANAGE = "contracts:manage"
    PAYMENTS_RECORD = "payments:record"


ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.ADMIN: frozenset(Permission),
    Role.EVENTS_MANAGER: frozenset(
        {
            Permission.CLIENTS_MANAGE,
            Permission.CATALOG_READ,
            Permission.QUOTES_MANAGE,
            Permission.CONTRACTS_MANAGE,
            Permission.PAYMENTS_RECORD,  # R-CON-4: el Product Owner lo autorizó (22/11/2026)
        }
    ),
    Role.PURCHASING_MANAGER: frozenset({Permission.CATALOG_READ}),
}


def permissions_of(role: Role) -> frozenset[Permission]:
    return ROLE_PERMISSIONS[role]
