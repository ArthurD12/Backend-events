"""Registro de herramientas del asistente: cada una es una función de consulta controlada.

Una herramienta declara su permiso; el registro lo verifica contra los permisos del usuario
ANTES de ejecutarla (RN28). Todas son de solo lectura (RN30).
"""

import json
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Any

from local_eventos.modules.assistant.application.ports.language_model import ToolSpec

ToolHandler = Callable[[dict[str, Any]], Awaitable[Any]]


class ToolInputError(Exception):
    """Parámetros inválidos: el modelo recibe el mensaje y puede corregirlos."""


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    permission: str  # valor de `Permission` (p. ej. "events:read")
    handler: ToolHandler

    def spec(self) -> ToolSpec:
        return ToolSpec(self.name, self.description, self.input_schema)


@dataclass(frozen=True)
class ToolOutcome:
    content: str  # JSON compacto
    is_error: bool = False


def to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


class ToolRegistry:
    def __init__(self, tools: Iterable[Tool]) -> None:
        self._tools = {tool.name: tool for tool in tools}

    def specs(self) -> list[ToolSpec]:
        return [tool.spec() for tool in self._tools.values()]

    async def execute(
        self, name: str, tool_input: dict[str, Any], permissions: frozenset[str]
    ) -> ToolOutcome:
        tool = self._tools.get(name)
        if tool is None:
            return ToolOutcome(to_json({"error": "herramienta_desconocida"}), True)
        if tool.permission not in permissions:
            return ToolOutcome(to_json({"error": "sin_permiso"}), True)
        try:
            data = await tool.handler(tool_input)
        except ToolInputError as error:
            return ToolOutcome(
                to_json({"error": "parametros_invalidos", "detalle": str(error)}), True
            )
        return ToolOutcome(to_json(data))
