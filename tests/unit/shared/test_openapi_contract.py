"""AGENTS.md, regla 9: `openapi.json` es el contrato con el frontend y debe estar al día.

Si esta prueba falla, la API cambió y falta ejecutar `just openapi` y subir el archivo.
"""

import json
from pathlib import Path

from local_eventos.tools.export_openapi import openapi_text

ROOT = Path(__file__).resolve().parents[3]

AVAILABILITY_OPERATIONS = {
    ("/v1/staff/availability", "get"): "staff_availability_get",
    ("/v1/staff/unavailability", "get"): "staff_unavailability_list",
    ("/v1/staff/unavailability", "post"): "staff_unavailability_register",
    ("/v1/staff/unavailability/{unavailability_id}", "put"): "staff_unavailability_update",
    (
        "/v1/staff/unavailability/{unavailability_id}/cancel",
        "post",
    ): "staff_unavailability_cancel",
}

AVAILABILITY_SCHEMAS = (
    "AvailabilityOut",
    "AvailabilityItem",
    "AvailabilityConflict",
    "UnavailabilityCreate",
    "UnavailabilityUpdate",
    "UnavailabilityCancel",
    "UnavailabilityOut",
    "UnavailabilityListOut",
)


def test_openapi_json_esta_actualizado() -> None:
    committed = (ROOT / "openapi.json").read_text(encoding="utf-8")

    assert committed == openapi_text(), "La API cambió: ejecuta `just openapi` y sube openapi.json"


def test_contrato_de_disponibilidad_expone_cinco_operaciones_estables() -> None:
    document = json.loads((ROOT / "openapi.json").read_text(encoding="utf-8"))

    found = {
        (path, method): operation.get("operationId")
        for path, methods in document["paths"].items()
        for method, operation in methods.items()
        if (path, method) in AVAILABILITY_OPERATIONS
    }

    assert found == AVAILABILITY_OPERATIONS
    for schema in AVAILABILITY_SCHEMAS:
        assert schema in document["components"]["schemas"]
