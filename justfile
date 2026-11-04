# Comandos comunes. Requiere: uv, just, Docker (para tests de integración).

default:
    @just --list

install:
    uv sync

lint:
    uv run ruff check .
    uv run ruff format --check .

fmt:
    uv run ruff check --fix .
    uv run ruff format .

types:
    uv run mypy src

arch:
    uv run lint-imports

test:
    uv run pytest

check: lint types arch test

dev:
    uv run fastapi dev src/local_eventos/main.py

migrate:
    uv run alembic upgrade head

migration name:
    uv run alembic revision --autogenerate -m "{{name}}"

openapi:
    uv run python -m local_eventos.tools.export_openapi > openapi.json

docs:
    uv run mkdocs serve

up:
    docker compose up -d db
