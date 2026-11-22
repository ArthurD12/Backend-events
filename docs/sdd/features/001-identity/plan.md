# Plan: Inicio de sesión, usuarios e historial de accesos

- **Spec**: ./spec.md
- **Estado**: aprobado (César Suclupe, 22/11/2026)

## 1. Módulos y fronteras
- **`identity`**: usuarios, roles, permisos, sesiones e historial de accesos.
- **`identity.public_api`** expone a los demás módulos:
  - `Permission`: los permisos (p. ej. `clients:manage`);
  - `require_permission(permission)`: dependencia de FastAPI que exige sesión y permiso;
  - `CurrentUser`: el usuario de la petición (id, rol, permisos), para auditoría futura (RN03).
- **`commercial`** y **`catalog`**: sus routers usan `require_permission` desde `identity.public_api`. No importan nada interno de `identity`.

## 2. Modelo de dominio (Python puro)
- **`Role`** (enum): `ADMIN`, `EVENTS_MANAGER`, `PURCHASING_MANAGER`.
- **`Permission`** (enum) y **`ROLE_PERMISSIONS`**, tomados de `DOMAIN.md` §9. Solo los que ya se usan:

  | Permiso | Admin | Eventos | Compras |
  |---|:-:|:-:|:-:|
  | `users:manage` | ✔ | – | – |
  | `access_log:read` | ✔ | – | – |
  | `clients:manage` | ✔ | ✔ | – |
  | `catalog:read` | ✔ | ✔ | ✔ |
  | `catalog:manage` | ✔ | – | – |

  Cada módulo nuevo agrega sus permisos aquí.
- **`User`**: `id`, `name` (1–120), `email` (formato válido, guardado en minúsculas), `password_hash`, `role`, `active`. Métodos: `create`, `update`, `set_password_hash`, `deactivate`, `activate`.
- **`check_password_policy(password)`**: mínimo 8 caracteres (R-ID-1), máximo 128.
- **`AccessAttempt`**: `email`, `user_id | None`, `occurred_at` (UTC), `result` ∈ {`SUCCESS`, `INVALID_CREDENTIALS`, `INACTIVE_USER`}.

## 3. Casos de uso
| Caso de uso | Tipo | Entrada | Salida | Errores (`code`) |
|---|---|---|---|---|
| `Login` | command | correo, contraseña | tokens + usuario | `auth.invalid_credentials` (también para usuario inactivo: no revela el motivo) |
| `RefreshSession` | command | refresh token | tokens nuevos (rotación) | `auth.session_expired` |
| `Logout` | command | refresh token | – | – (idempotente) |
| `GetCurrentUser` | query | id del token | usuario + permisos | `auth.session_expired` |
| `CreateUser` | command | nombre, correo, contraseña, rol, activo | usuario | `user.email_duplicated`, `user.*_invalid`, `user.password_too_short` |
| `UpdateUser` | command | id, nombre, correo, rol, contraseña opcional | usuario | `user.not_found`, `user.email_duplicated`, `user.last_admin` |
| `DeactivateUser` / `ActivateUser` | command | id | usuario | `user.not_found`, `user.last_admin` |
| `ListUsers` | query | incluir inactivos | usuarios | – |
| `SearchAccessLog` | query | usuario, desde, hasta, resultado, página | registros + total | – |

`Login` registra **siempre** un `AccessAttempt` (éxito o fallo) en la misma transacción. Cuando el login falla, el registro se guarda igual: el endpoint confirma la transacción antes de responder el error.

Puertos: `UserRepository`, `SessionRepository`, `AccessLogRepository`, `PasswordHasher`, `TokenIssuer`, `Clock`.

## 4. API (OpenAPI)
| Método y ruta | `operationId` | Permiso |
|---|---|---|
| `POST /v1/auth/login` | `auth_login` | público |
| `POST /v1/auth/refresh` | `auth_refresh` | público (con refresh token) |
| `POST /v1/auth/logout` | `auth_logout` | público (con refresh token) |
| `GET /v1/auth/me` | `auth_me` | sesión |
| `POST /v1/users` · `GET /v1/users` | `users_create` · `users_list` | `users:manage` |
| `GET /v1/users/{id}` · `PUT /v1/users/{id}` | `users_get` · `users_update` | `users:manage` |
| `POST /v1/users/{id}/deactivate` · `/activate` | `users_deactivate` · `users_activate` | `users:manage` |
| `GET /v1/access-log` | `access_log_search` | `access_log:read` |

**Rutas existentes que se protegen:** `/v1/clients/*` → `clients:manage`; `GET /v1/catalog/*` → `catalog:read`; el resto de `/v1/catalog/*` → `catalog:manage`. Los cuerpos y respuestas no cambian: solo se agrega la cabecera `Authorization: Bearer <token>`, y las respuestas 401 y 403 con Problem Details (`auth.not_authenticated`, `auth.forbidden`).

**Sesión y 30 minutos de inactividad (CA-01.6):**
- *Access token*: JWT firmado (HS256), dura **15 minutos**, lleva `sub` (id) y `role`. Se envía en cada petición.
- *Refresh token*: valor aleatorio. En PostgreSQL se guarda solo su hash (SHA-256). Vence a los **30 minutos sin usarse** y se **rota** en cada uso. Además, nunca dura más de 12 horas en total.
- *Resultado*: ninguna sesión sobrevive a 30 minutos sin contacto con el servidor. El frontend renueva el access token mientras el usuario trabaja, y además cuenta 30 minutos de inactividad en pantalla para cerrar la sesión.
- *Logout*: revoca el refresh token. Desactivar a un usuario revoca todas sus sesiones (CA-02.4).

## 5. Persistencia (migración Alembic, prefijo `identity_`)
- `identity_users`: `id` uuid PK, `name`, `email`, `password_hash`, `role` (CHECK de los 3 roles), `active`, `created_at`, `updated_at`. Índice **único** sobre `lower(email)` (CA-02.2).
- `identity_sessions`: `id` uuid PK, `user_id` (FK a `identity_users`), `token_hash` único, `created_at`, `last_used_at`, `expires_at`, `revoked_at`.
- `identity_access_log`: `id` bigint, `email`, `user_id` nullable (FK), `result` (CHECK), `occurred_at` (con índice). Un **trigger** rechaza `UPDATE` y `DELETE` (CA-03.4).

## 6. Reglas de negocio aplicadas
RN01, RN02, `DOMAIN.md` §9 y R-ID-1 a R-ID-4 (spec §5). Se agregan a `DOMAIN.md` §11 como decisiones provisionales.

## 7. Estrategia de tests
- **Unit**, sin base de datos y con fakes: entidad `User` y política de contraseña; cada caso de uso, con el registro de acceso en éxito y en fallo, el último administrador y la rotación y el vencimiento por inactividad (reloj falso); API con repositorios en memoria (401, 403, 409, 422).
- **Integración** con PostgreSQL real: repositorios, correo único, trigger que bloquea UPDATE y DELETE, login de punta a punta con el historial guardado aunque el login falle.
- **Arquitectura**: `commercial` y `catalog` solo usan `identity.public_api`.
- Cada prueba lleva su CA en el nombre (p. ej. `test_ca01_2_...`).
- Las pruebas existentes de clientes y catálogo reemplazan el usuario actual (`dependency_overrides`); las de punta a punta crean un administrador e inician sesión.

## 8. Riesgos y ADRs
- **Dependencias**: `pyjwt` y `pwdlib[argon2]`, ya decididas en ADR 0001 (no hace falta un ADR nuevo). Se agregan a `pyproject.toml` y se documentan en `STACK.md`, `README.md` e `INSTALACION.md` (regla 13).
- **Configuración**: nueva variable obligatoria `JWT_SECRET` en `.env` (con su explicación en `.env.example`). Sin ella, la API no arranca: así nunca funciona con una clave por defecto.
- **Primer administrador**: comando `just create-admin` (pide nombre, correo y contraseña).
- **Impacto en el frontend**: la pantalla de clientes necesita el token. Por eso el login del frontend se conecta antes de usarla.
- **Rama**: `feat/identity`, desde `developer-b`, con PR hacia `developer-b`. Las historias estaban asignadas a Harold: se le informa antes de que empiece.

## 9. Impacto en reporting y documentación
Sin cambios en `reporting`. Se actualizan `openapi.json`, `DOMAIN.md` §11, `STACK.md`, `README.md`, `INSTALACION.md` y `.env.example`.
