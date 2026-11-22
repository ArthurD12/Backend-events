"""Errores de la capa de aplicación de identidad. `code` es estable para el frontend."""


class IdentityApplicationError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class NotAuthenticatedError(IdentityApplicationError):
    def __init__(self) -> None:
        super().__init__("auth.not_authenticated", "Inicia sesión para continuar.")


class SessionExpiredError(IdentityApplicationError):
    def __init__(self) -> None:
        super().__init__(
            "auth.session_expired", "Tu sesión terminó. Vuelve a iniciar sesión para continuar."
        )


class ForbiddenError(IdentityApplicationError):
    def __init__(self) -> None:
        super().__init__("auth.forbidden", "Tu rol no tiene permiso para esta operación.")


class UserNotFoundError(IdentityApplicationError):
    def __init__(self) -> None:
        super().__init__("user.not_found", "No se encontró un usuario con ese identificador.")


class DuplicateEmailError(IdentityApplicationError):
    def __init__(self) -> None:
        super().__init__("user.email_duplicated", "Ese correo ya está registrado en otra cuenta.")


class LastAdminError(IdentityApplicationError):
    def __init__(self) -> None:
        super().__init__(
            "user.last_admin",
            "Es el único administrador activo: crea o activa otro administrador antes.",
        )
