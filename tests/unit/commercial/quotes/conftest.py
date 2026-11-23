"""Fixture `world` para las pruebas de cotizaciones (ver world.py)."""

import pytest

from .world import World, build_world


@pytest.fixture
async def world() -> World:
    return await build_world()
