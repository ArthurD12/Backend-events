"""Superficie pública del módulo identity: única vía de uso por otros módulos.

Los demás módulos protegen sus rutas con `require_permission(Permission.X)` y, cuando
necesiten auditar (RN03), reciben al `CurrentUser`. Nunca importan nada interno de identity.
"""

from local_eventos.modules.identity.domain.permissions import Permission
from local_eventos.modules.identity.presentation.dependencies import (
    CurrentUser,
    get_current_user,
    require_permission,
)

__all__ = ["CurrentUser", "Permission", "get_current_user", "require_permission"]
