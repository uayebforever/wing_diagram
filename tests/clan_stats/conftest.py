import asyncio
from pathlib import Path

import pytest

from wing_diagram import config


@pytest.fixture(scope="session")
def wing_diagram_config() -> config.ClanStatsConfig:
    return config.read_config()


@pytest.fixture(scope="session")
def bungie_api_key(wing_diagram_config) -> str:
    return wing_diagram_config.bungie_api_key


# Keep event loop open for all tests to avoid it becoming prematurely closed
# see https://stackoverflow.com/a/72104554
@pytest.fixture(scope="session")
def event_loop():
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
    yield loop
    loop.close()