
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

alembic init alembic                         # first-time setup
alembic revision --autogenerate -m "msg"     # create migration
alembic upgrade head                         # apply migrations
alembic downgrade -1                         # rollback last migration
alembic history                              # view migration history
alembic current                              # current DB version

**Linting / Formatting**

ruff check .           # lint
ruff format .          # format


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
├── alembic/
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
