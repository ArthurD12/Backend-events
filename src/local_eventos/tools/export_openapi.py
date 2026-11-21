"""Exporta el contrato OpenAPI a `openapi.json` (AGENTS.md, regla 9). Uso: `just openapi`.

El frontend genera sus tipos TypeScript a partir de este archivo. Se escribe en UTF-8 y con
las claves ordenadas, así el archivo solo cambia cuando cambia la API.
"""

import json
import sys
from pathlib import Path
from typing import Any

from local_eventos.main import create_app

DEFAULT_PATH = Path("openapi.json")


def openapi_text() -> str:
    spec: dict[str, Any] = create_app().openapi()
    return json.dumps(spec, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PATH
    path.write_text(openapi_text(), encoding="utf-8", newline="\n")
    print(f"Contrato OpenAPI escrito en {path}")


if __name__ == "__main__":
    main()
