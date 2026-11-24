# Imagen del backend para producción (Render u otro servicio con Docker).
# Al arrancar aplica las migraciones y levanta la API en el puerto que da el servicio ($PORT).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app
RUN pip install --no-cache-dir "uv>=0.5"

# Primero solo las dependencias: si el código cambia, esta capa se reutiliza.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY migrations ./migrations
COPY alembic.ini ./
RUN uv sync --frozen --no-dev && useradd --create-home darze
USER darze

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn local_eventos.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
