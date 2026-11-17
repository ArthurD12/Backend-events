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

Copia el archivo de ejemplo y cambia la clave en **las dos líneas** donde aparece (`POSTGRES_PASSWORD` y `DATABASE_URL`):

```bash
copy .env.example .env      # Windows
cp .env.example .env        # Linux/macOS
```

El archivo `.env` está en `.gitignore`: nunca se sube a GitHub.

## 4. Instalar las dependencias

```bash
just install    # uv sync: crea .venv e instala las versiones exactas de uv.lock
```

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
| `docker compose down` | Apaga PostgreSQL (los datos se conservan) |

## Problemas frecuentes

- **`/ready` responde `not_ready`** → PostgreSQL no está levantado (`just up`) o la clave de `DATABASE_URL` no es la misma que `POSTGRES_PASSWORD` en `.env`.
- **`Falta POSTGRES_USER en .env`** al ejecutar `just up` → falta el paso 3.
- **`Field required: database_url`** al ejecutar `just dev` o `just migrate` → falta el paso 3 o se ejecutó fuera de la carpeta del proyecto.
- **`just migrate` falla con `connection was closed in the middle of operation`** → hay otro PostgreSQL instalado en Windows usando el mismo puerto. Compruébalo con `netstat -ano | findstr :5433`: si aparecen dos números de proceso distintos, cambia `POSTGRES_PORT` y el puerto de `DATABASE_URL` en `.env` a otro libre (por ejemplo, 5434) y ejecuta `just up` de nuevo.
- **`error during connect` / `Cannot connect to the Docker daemon`** → Docker Desktop no está abierto.
- **`just check` dice "Would reformat"** → ejecuta `just fmt` y configura la extensión Ruff en VS Code (paso 1).
