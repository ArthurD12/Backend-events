# Instalación paso a paso (desde cero)

> Guía para instalar el backend en una máquina nueva, sin conocimientos previos del proyecto.
> Cuando un paso depende de algo que aún no existe en el repositorio, está marcado con
> **se verifica en 000-bootstrap** — no sigas ese paso como si el archivo ya existiera.

## 1. Requisitos previos de la máquina

Instala estas herramientas en tu sistema operativo:

| Herramienta | Para qué sirve | Cómo se instala (oficial) |
|---|---|---|
| Python 3.12 o superior | Lenguaje del backend | Desde [python.org](https://www.python.org/downloads/) — verifica con `python --version` |
| `uv` | Instala dependencias y crea el entorno virtual | `pipx install uv` o el instalador oficial de [astral.sh](https://docs.astral.sh/uv/getting-started/installation/) |
| `just` | Ejecuta los atajos de comandos | `pipx install just` o [just.systems](https://just.systems/) |
| Docker + Docker Compose | PostgreSQL local y tests de integración | [docker.com](https://www.docker.com/get-started/) — verifica con `docker compose version` |
| Git | Clonar el repositorio | [git-scm.com](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git) |

> **se verifica en 000-bootstrap**: `pyproject.toml`, `docker-compose.yml`, `.env.example` y una app
> runnable aún NO existen en el repositorio. Los pasos 4 a 7 asumen que ya existen.

## 2. Clonar el repositorio

```bash
git clone <url-del-repo>
cd Backend-events
```

## 3. Crear la base de datos con Docker Compose

PostgreSQL se levanta con Docker Compose, no se instala en la máquina:

```bash
just up                 # docker compose up -d db
```

Por defecto escucha en el puerto local de PostgreSQL (5432). Los datos viven en un volumen de Docker,
para que no se pierdan al reiniciar.

> **se verifica en 000-bootstrap**: `docker-compose.yml` (con el servicio `db` y sus credenciales)
> aún no existe. Hasta entonces no hay base de datos que levantar.

## 4. Variables de entorno

```bash
cp .env.example .env
```

> **se verifica en 000-bootstrap**: `.env.example` aún no existe. Las variables que se esperan —según
> el dominio e infraestructura ya definidos— son, al menos: la URL de conexión a PostgreSQL
> (`DATABASE_URL`) y las claves de JWT de autenticación, más la clave de integración de `reporting`
> cuando se active el servicio de IA. Edita `.env` con tus valores reales; nunca subas `.env` al repo.

## 5. Instalar las dependencias con uv

```bash
just install    # uv sync — crea el entorno virtual e instala todo desde uv.lock
```

## 6. Crear el esquema de base de datos

```bash
just migrate    # alembic upgrade head
```

El esquema se crea **solo** con migraciones Alembic; nunca con SQL suelto a mano.

## 7. Levantar el servidor (modo desarrollo)

```bash
just dev   # uv run fastapi dev src/local_eventos/main.py
```

> **se verifica en 000-bootstrap**: la app runnable (`src/local_eventos/main.py`) aún no existe.

## 8. Verificar la instalación

```bash
just check   # ruff + mypy + lint-imports + pytest
```

Si el comando termina en verde, la instalación es correcta.
Para levantar la documentación local: `just docs` (MkDocs, se verifica en 000-bootstrap:
`mkdocs.yml` aún no existe).

## Problemas frecuentes

- **`docker compose: command not found`** → falta Docker Compose; instala Docker Desktop o el plugin
  de Compose.
- **Puerto 5432 ocupado** → hay otro PostgreSQL corriendo; detenlo o cambia el puerto en
  `docker-compose.yml` (se verifica en 000-bootstrap).
- **`.env` no definido** → falta el paso 4; sin las variables de entorno la app no arranca.
