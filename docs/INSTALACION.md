# Instalación paso a paso (desde cero)

> Guía para levantar el backend en una máquina nueva, sin conocimientos previos del proyecto.
> Los comandos funcionan en Windows (CMD o PowerShell) y en Linux/macOS; donde cambian, se indican los dos.

## 1. Requisitos previos de la máquina

| Herramienta | Para qué sirve | Windows | Verificar |
|---|---|---|---|
| Git | Clonar el repositorio | `winget install --id=Git.Git -e` | `git --version` |
| Docker Desktop | PostgreSQL local y pruebas de integración | [docker.com](https://www.docker.com/products/docker-desktop/) | `docker compose version` |
| `uv` | Instala Python 3.12, crea el entorno e instala las dependencias | `winget install --id=astral-sh.uv -e` | `uv --version` |
| `just` | Atajos de comandos (`just dev`, `just check`…) | `winget install --id=Casey.Just -e` | `just --version` |

En Linux/macOS: `uv` con el [instalador oficial](https://docs.astral.sh/uv/getting-started/installation/) y `just` con `uv tool install rust-just`.

No hace falta instalar Python a mano: `uv` descarga la versión del archivo `.python-version` (3.12).

**Editor (VS Code):** instala la extensión **Ruff** (`charliermarsh.ruff`) y ponla como formateador de Python.
Así el editor usa la misma configuración del proyecto (`pyproject.toml`, líneas de 100 caracteres) y
`just check` no marca archivos para reformatear.

## 2. Clonar el repositorio

```bash
git clone https://github.com/ArthurD12/Backend-events.git
cd Backend-events
```

## 3. Variables de entorno

Copia el archivo de ejemplo y cambia la clave en **las dos líneas** donde aparece (`POSTGRES_PASSWORD` y `DATABASE_URL`). Cambia también `JWT_SECRET`, la clave que firma las sesiones: genera una con el comando que aparece en el mismo archivo:

```bash
copy .env.example .env      # Windows
cp .env.example .env        # Linux/macOS
```

El archivo `.env` está en `.gitignore`: nunca se sube a GitHub.

Para el **PDF de las cotizaciones**, completa en `.env` los datos de Darze (`COMPANY_NAME`, `COMPANY_RUC`, `COMPANY_ADDRESS`, `COMPANY_PHONE`, `COMPANY_EMAIL`). Los que dejes vacíos no se imprimen.

Para el **asistente con IA** (ADR 0005), pon tu clave de Anthropic en `ANTHROPIC_API_KEY` (opcional). Sin ella el asistente aparece "no disponible" y el resto del sistema funciona igual. La clave nunca se sube a GitHub; en producción va en el panel de Render.

## 4. Instalar las dependencias

```bash
just install    # uv sync: crea .venv e instala las versiones exactas de uv.lock
```

Incluye ReportLab (PDF de cotizaciones) y el SDK `anthropic` (asistente con IA): no hace falta instalar nada más en Windows.

## 5. Levantar PostgreSQL

Abre Docker Desktop y espera a que diga que está en ejecución. Luego:

```bash
just up         # docker compose up -d db
```

Los datos viven en el volumen `darze_pgdata`: no se pierden al apagar la computadora.

## 6. Crear el esquema de base de datos

```bash
just migrate    # alembic upgrade head
```

El esquema se crea **solo** con migraciones de Alembic, nunca con SQL a mano.

> **Extensión `btree_gist`.** El esquema de asignaciones de personal (HU17) usa la extensión PostgreSQL `btree_gist` para impedir horarios solapados. La migración la crea con `CREATE EXTENSION IF NOT EXISTS btree_gist` y su `downgrade` **no** la elimina. En local y en CI se usa la imagen `postgres:17-alpine`, que ya la incluye (verificado). Antes de desplegar en staging o producción confirma que el servidor la tenga disponible. Si `CREATE EXTENSION` falla por privilegios, pide al administrador de la base que la habilite (`CREATE EXTENSION btree_gist;`); **no** se debe desactivar la comprobación ni degradar a validación solo en la aplicación, porque el no solape dejaría de estar garantizado.

Después crea el **primer administrador**. Se hace una sola vez: sin él nadie puede crear usuarios.

```bash
just create-admin   # pide nombre, correo y contraseña (mínimo 8 caracteres)
```

## 7. Levantar la API

```bash
just dev        # uv run fastapi dev src/local_eventos/main.py
```

## 8. Verificar la instalación

Con la API en ejecución, abre en el navegador:

| Dirección | Debe mostrar |
|---|---|
| http://localhost:8000/health | `{"status":"ok"}` |
| http://localhost:8000/ready | `{"status":"ready"}` (si dice `not_ready`, PostgreSQL no está levantado o la clave de `.env` no coincide) |
| http://localhost:8000/docs | La documentación interactiva de la API |

En otra terminal, ejecuta las comprobaciones completas:

```bash
just check      # ruff + mypy + import-linter + pruebas unitarias
just test-all   # además, pruebas de integración con PostgreSQL real (Docker en ejecución)
```

Si los dos terminan en verde, la instalación es correcta.

## Comandos del día a día

| Comando | Qué hace |
|---|---|
| `just dev` | Levanta la API y la recarga al guardar cambios |
| `just test` | Pruebas unitarias (rápidas, sin Docker) |
| `just test-all` | Pruebas unitarias y de integración |
| `just check` | Todo lo que revisa GitHub Actions en cada pull request |
| `just fmt` | Corrige el formato y el orden de los imports |
| `just migration "<nombre>"` | Genera una migración a partir de los modelos ORM |
| `just openapi` | Actualiza `openapi.json` (el contrato con el frontend) después de cambiar la API |
| `just create-admin` | Crea un administrador (el primero, al instalar; los demás usuarios se crean desde el sistema) |
| `docker compose down` | Apaga PostgreSQL (los datos se conservan) |

## Problemas frecuentes

- **`/ready` responde `not_ready`** → PostgreSQL no está levantado (`just up`) o la clave de `DATABASE_URL` no es la misma que `POSTGRES_PASSWORD` en `.env`.
- **`Falta POSTGRES_USER en .env`** al ejecutar `just up` → falta el paso 3.
- **`Field required: database_url`** al ejecutar `just dev` o `just migrate` → falta el paso 3 o se ejecutó fuera de la carpeta del proyecto.
- **`just migrate` falla con `connection was closed in the middle of operation`** → hay otro PostgreSQL instalado en Windows usando el mismo puerto. Compruébalo con `netstat -ano | findstr :5433`: si aparecen dos números de proceso distintos, cambia `POSTGRES_PORT` y el puerto de `DATABASE_URL` en `.env` a otro libre (por ejemplo, 5434) y ejecuta `just up` de nuevo.
- **`error during connect` / `Cannot connect to the Docker daemon`** → Docker Desktop no está abierto.
- **`Field required: jwt_secret`** o **`String should have at least 32 characters`** al iniciar sesión → falta `JWT_SECRET` en `.env` o es muy corta (paso 3).
- **`just migrate` falla con `could not open extension control file` o `permission denied to create extension "btree_gist"`** → el usuario de la base no puede crear la extensión. Pide al administrador de PostgreSQL que la habilite (`CREATE EXTENSION btree_gist;`) en esa base antes de reintentar `just migrate`. No la sustituyas por validación solo en la aplicación: el no solape de asignaciones quedaría sin garantía de base (ADR 0005).
- **`just check` dice "Would reformat"** → ejecuta `just fmt` y configura la extensión Ruff en VS Code (paso 1).
