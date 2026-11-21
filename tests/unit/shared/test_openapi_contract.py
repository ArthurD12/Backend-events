"""AGENTS.md, regla 9: `openapi.json` es el contrato con el frontend y debe estar al día.

Si esta prueba falla, la API cambió y falta ejecutar `just openapi` y subir el archivo.
"""

from pathlib import Path

from local_eventos.tools.export_openapi import openapi_text

ROOT = Path(__file__).resolve().parents[3]


def test_openapi_json_esta_actualizado() -> None:
    committed = (ROOT / "openapi.json").read_text(encoding="utf-8")

    assert committed == openapi_text(), "La API cambió: ejecuta `just openapi` y sube openapi.json"
