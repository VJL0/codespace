from __future__ import annotations

import os

import pytest

pytest.register_assert_rewrite("tests.support")

from tests.support.environment import app_environment

os.environ.update(app_environment())


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"
