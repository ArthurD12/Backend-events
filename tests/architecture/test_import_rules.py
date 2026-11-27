"""CA-7: las reglas de arquitectura detectan un import prohibido.

Copia el código a una carpeta temporal, agrega una violación y comprueba que `lint-imports`
falla nombrando la regla. Así se sabe que las reglas protegen de verdad y no solo pasan.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _lint_imports_with(tmp_path: Path, file: str, line: str) -> subprocess.CompletedProcess[str]:
    shutil.copytree(ROOT / "src", tmp_path / "src")
    shutil.copy(ROOT / ".importlinter", tmp_path / ".importlinter")
    target = tmp_path / "src" / "local_eventos" / file
    target.write_text(target.read_text(encoding="utf-8") + f"\n{line}\n", encoding="utf-8")
    # Busca lint-imports junto al Python del entorno (.venv/bin en Linux, .venv\Scripts en Windows).
    lint_imports = shutil.which("lint-imports", path=str(Path(sys.executable).parent))
    assert lint_imports is not None, "lint-imports no está instalado: ejecuta `just install`"
    return subprocess.run(
        [lint_imports, "--no-cache"],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(tmp_path / "src")},
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(
    ("file", "line", "broken_rule"),
    [
        (
            "modules/catalog/domain/service.py",
            "import fastapi  # noqa: F401",
            "El dominio no depende de frameworks BROKEN",
        ),
        (
            "modules/catalog/domain/category.py",
            "from local_eventos.modules.catalog.application import errors  # noqa: F401",
            "Capas dentro de cada modulo: presentation -> application -> domain BROKEN",
        ),
        (
            "modules/commercial/domain/clients/client.py",
            "from local_eventos.modules.catalog.domain import service  # noqa: F401",
            "Los modulos solo se usan entre si por su public_api BROKEN",
        ),
        (
            "modules/staff/domain/assignment.py",
            "from local_eventos.modules.commercial.domain.events import event  # noqa: F401",
            "Los modulos solo se usan entre si por su public_api BROKEN",
        ),
        (
            "modules/staff/application/assignment_occupancy.py",
            "from local_eventos.modules.commercial.domain.events.event import "
            "EventStatus  # noqa: F401",
            "Los modulos solo se usan entre si por su public_api BROKEN",
        ),
    ],
)
def test_ca7_un_import_prohibido_rompe_la_arquitectura(
    tmp_path: Path, file: str, line: str, broken_rule: str
) -> None:
    result = _lint_imports_with(tmp_path, file, line)

    assert result.returncode != 0
    assert broken_rule in result.stdout


@pytest.mark.parametrize(
    ("line", "broken_rule"),
    [
        (
            "import fastapi  # noqa: F401",
            "El dominio no depende de frameworks BROKEN",
        ),
        (
            "import sqlalchemy  # noqa: F401",
            "El dominio no depende de frameworks BROKEN",
        ),
        (
            "import pydantic  # noqa: F401",
            "El dominio no depende de frameworks BROKEN",
        ),
        (
            "from local_eventos.modules.identity.domain import permissions  # noqa: F401",
            "Los modulos solo se usan entre si por su public_api BROKEN",
        ),
    ],
)
def test_staff_domain_no_importa_frameworks_ni_identity_interna(
    tmp_path: Path, line: str, broken_rule: str
) -> None:
    result = _lint_imports_with(tmp_path, "modules/staff/domain/worker.py", line)

    assert result.returncode != 0
    assert broken_rule in result.stdout


def test_ca7_usar_otro_modulo_por_su_public_api_esta_permitido(tmp_path: Path) -> None:
    result = _lint_imports_with(
        tmp_path,
        "modules/commercial/application/clients/errors.py",
        "from local_eventos.modules.catalog import public_api  # noqa: F401",
    )

    assert result.returncode == 0, result.stdout


def test_staff_usa_commercial_solo_por_su_public_api(tmp_path: Path) -> None:
    result = _lint_imports_with(
        tmp_path,
        "modules/staff/application/assignment_occupancy.py",
        "from local_eventos.modules.commercial import public_api  # noqa: F401",
    )

    assert result.returncode == 0, result.stdout
