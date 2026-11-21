"""CA-9: el repositorio no guarda secretos; la configuración sensible viene del entorno."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_ca9_env_esta_ignorado_y_existe_env_example() -> None:
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert ".env" in ignored
    assert (ROOT / ".env.example").is_file()


def test_ca9_env_example_solo_tiene_una_clave_de_ejemplo() -> None:
    example = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "POSTGRES_PASSWORD=cambia-esta-clave" in example
    assert "DATABASE_URL=" in example
