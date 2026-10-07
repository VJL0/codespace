
**Python package manager (uv):**

https://docs.astral.sh/uv/getting-started/installation/

**Deps:**

FastAPI: High-performance Python API framework (handles routing, validation, OpenAPI/docs)

asyncpg: Async PostgreSQL driver (low-level DB communication)

SQLAlchemy[asyncio]: ORM + query builder (maps Python objects to DB tables) (includes async deps)

Alembic: Database migration tool for SQLAlchemy

pydantic-settings: Environment/config management (.env → typed settings)

uvicorn[standard]: Production ASGI server (includes uvloop, httptools for performance)

ruff: Linter + formatter (dev tool)

**Package / Environment (uv)**

uv init                  # initialize project
uv add <pkg>             # add dependency
uv remove <pkg>          # remove dependency
uv sync                  # install deps from lockfile
uv tree                  # view dependency tree

**Run Server**

uvicorn app.main:app --reload                     # dev
uvicorn app.main:app --host 0.0.0.0 --port 8000   # prod

**Alembic (Database Migrations)**

alembic revision --autogenerate -m "msg"     # create migration (review it before committing)
alembic check                                # fail if models and migrations have drifted
alembic upgrade head                         # apply migrations
alembic downgrade -1                         # rollback last migration
alembic history                              # view migration history
alembic current                              # current DB version

**Linting / Formatting**

ruff check .           # lint
ruff format .          # format

**Tests**

uv run pytest                    # all; needs Docker running (no compose step)
uv run pytest tests/unit         # no database, no Docker
uv run pytest tests/integration  # starts a throwaway postgres:18-alpine container (Testcontainers),
                                 # migrates it, removes it at the end; api/ goes through HTTP
uv run pytest --cov              # with branch coverage; fails under 95%

tests/
├── conftest.py      # test environment, set before app/ is imported
├── unit/            # pure logic
├── integration/     # real Postgres container, each test rolled back
│   └── api/         # the HTTP app, in process
└── support/         # helpers and fakes the tests import (not conftest.py)


**Modular Monolith**

backend/
├── app/
│   ├── main.py
│   ├── core/
│   ├── db/
│   ├── api/
│   ├── modules/
│   │   ├── users/
│   │   ├── auth/
│   │   ├── classrooms/
│   └── shared/
├── migrations/
├── tests/
├── pyproject.toml
└── uv.lock

For each module:
router.py          # HTTP layer
schemas.py         # Pydantic DTOs
models.py          # SQLAlchemy models
repository.py      # database queries
service.py         # business logic/use cases
dependencies.py    # FastAPI dependency wiring
exceptions.py      # module-specific errors
