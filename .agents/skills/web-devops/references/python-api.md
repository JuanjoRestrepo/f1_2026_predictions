# Python API Reference — Flask & FastAPI

Production Python APIs require more than a working `main.py`. This reference covers framework
selection, project structure, routing patterns, dependency injection, database integration,
async patterns, migrations, auto-documentation, and testing — for both Flask and FastAPI.

**Tooling mandate:** always use `uv` for environment and package management. Never use `pip`
directly. Python 3.12. Static analysis: Ruff (linter + formatter) + mypy (strict type checking).

---

## 1. Framework Selection

| Criterion           | Flask                                               | FastAPI                                         |
| ------------------- | --------------------------------------------------- | ----------------------------------------------- |
| Gateway interface   | WSGI — synchronous by default                       | ASGI — async-first, sync supported              |
| Performance         | Good; single-threaded per worker                    | Excellent; concurrent via async I/O             |
| Built-in validation | None — add marshmallow/webargs manually             | Pydantic v2 — automatic request/response        |
| Auto-documentation  | None — add flasgger/flask-smorest                   | Built-in `/docs` (Swagger) + `/redoc`           |
| Type safety         | Optional                                            | First-class — types drive validation            |
| Learning curve      | Lower — minimal, explicit                           | Moderate — requires understanding Pydantic + DI |
| Best for            | Simple services, prototypes, teams already on Flask | New APIs, high-throughput, type-safe contracts  |

**Decision rule:** choose FastAPI for all new production APIs. Choose Flask only when inheriting
an existing Flask codebase or building a quick internal tool where Pydantic's overhead is
not justified.

---

## 2. Tooling Setup (uv — mandatory)

```bash
# Create project and virtual environment
uv init my-api
cd my-api
uv venv                         # creates .venv/
source .venv/bin/activate       # Linux/macOS
# .venv\Scripts\activate        # Windows

# FastAPI stack
uv add fastapi "uvicorn[standard]" sqlalchemy asyncpg alembic pydantic-settings

# Flask stack
uv add flask sqlalchemy psycopg2-binary alembic pydantic-settings flask-smorest

# Dev dependencies
uv add --dev pytest pytest-asyncio httpx ruff mypy

# Run the server (never use `python main.py` in production)
uvicorn app.main:app --reload                    # FastAPI dev
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4  # FastAPI prod
flask --app app.main run --debug                 # Flask dev
gunicorn "app.main:create_app()" -w 4 -b 0.0.0.0:8000  # Flask prod
```

`pyproject.toml` — always use this; never `requirements.txt` or `setup.py`:

```toml
[project]
name = "my-api"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "sqlalchemy>=2.0",
    "asyncpg>=0.29",
    "alembic>=1.13",
    "pydantic-settings>=2.3",
]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-asyncio>=0.23", "httpx>=0.27", "ruff>=0.6", "mypy>=1.11"]

[tool.ruff]
target-version = "py312"
line-length = 100
select = ["E", "F", "I", "UP", "B", "SIM", "TCH"]

[tool.ruff.format]
quote-style = "double"

[tool.mypy]
python_version = "3.12"
strict = true
ignore_missing_imports = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

---

## 3. FastAPI — Production Project Structure

Two valid layouts depending on scale:

### Layout A — By layer (small-medium APIs, <10 domains)

```
my-api/
├── .github/workflows/
├── alembic/
│   ├── versions/
│   └── env.py
├── app/
│   ├── __init__.py
│   ├── main.py              # app factory + lifespan + router registration
│   ├── config.py            # pydantic-settings — typed env vars
│   ├── database.py          # async SQLAlchemy engine + session factory
│   ├── dependencies.py      # shared Depends() — get_db, get_current_user
│   ├── exceptions.py        # typed exception classes + global handlers
│   ├── middleware.py        # request ID, logging, CORS
│   ├── api/
│   │   ├── __init__.py
│   │   ├── router.py        # aggregates all v1 routers
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── users.py     # thin route handlers — call services only
│   │       ├── posts.py
│   │       └── auth.py
│   ├── models/              # SQLAlchemy ORM models — DB schema source of truth
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── user.py
│   │   └── post.py
│   ├── schemas/             # Pydantic models — request/response contracts
│   │   ├── __init__.py
│   │   ├── user.py          # UserCreate, UserUpdate, UserOut
│   │   └── post.py
│   ├── services/            # business logic — no HTTP context, fully testable
│   │   ├── __init__.py
│   │   ├── user_service.py
│   │   └── post_service.py
│   └── repositories/        # data access — SQLAlchemy queries only
│       ├── __init__.py
│       ├── base.py          # generic CRUD repository
│       └── user_repo.py
├── tests/
│   ├── conftest.py
│   ├── unit/
│   └── integration/
├── .env.example
├── .env                     # gitignored
├── alembic.ini
├── Dockerfile
└── pyproject.toml
```

### Layout B — By domain (large APIs, many bounded contexts)

```
my-api/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── auth/
│   │   ├── router.py
│   │   ├── schemas.py
│   │   ├── models.py
│   │   ├── service.py
│   │   ├── dependencies.py
│   │   ├── exceptions.py
│   │   └── tests/
│   ├── users/
│   │   ├── router.py
│   │   └── ...
│   └── posts/
│       ├── router.py
│       └── ...
```

Layout B scales better for monoliths with many domains — Netflix's Dispatch uses a
similar domain-first structure. Layout A works well for microservices or smaller projects.

---

## 4. FastAPI — Core Patterns

### Application Factory + Lifespan

```python
# app/main.py
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.config import settings
from app.database import engine
from app.exceptions import register_exception_handlers
from app.models.base import Base


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Startup: run DB migrations, warm caches, open connections
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)  # dev only — use Alembic in prod
    yield
    # Shutdown: close connections, flush buffers
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        docs_url="/docs",      # Swagger UI — disable in production if internal only
        redoc_url="/redoc",    # ReDoc — alternative auto-docs
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)
    app.include_router(api_router, prefix="/api/v1")

    return app


app = create_app()
```

### Typed Configuration with pydantic-settings

```python
# app/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    APP_NAME: str = "My API"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str  # required — no default; fails fast if missing
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20

    # Auth
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    # Sentry
    SENTRY_DSN: str | None = None


settings = Settings()  # validates and loads all env vars at startup
```

### Async Database Session (SQLAlchemy 2.0)

```python
# app/database.py
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

# create_async_engine requires an async driver: asyncpg (Postgres), aiosqlite (SQLite)
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    echo=settings.DEBUG,        # logs all SQL in debug mode
    pool_pre_ping=True,         # verify connections before use — handles stale connections
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,     # prevent lazy-load errors after commit
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that yields a database session and ensures cleanup."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

### Dependency Injection Pattern

```python
# app/dependencies.py
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.services.auth_service import verify_access_token

# Type aliases — reduces boilerplate in route signatures
DBSession = Annotated[AsyncSession, Depends(get_db)]

security = HTTPBearer()


async def get_current_user(
    db: DBSession,
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
) -> User:
    user_id = verify_access_token(credentials.credentials)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
```

### Thin Routes — Services Own Business Logic

```python
# app/api/v1/users.py
from fastapi import APIRouter, status

from app.dependencies import CurrentUser, DBSession
from app.schemas.user import UserCreate, UserOut, UserUpdate
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserOut)
async def get_current_user_profile(current_user: CurrentUser) -> UserOut:
    """Routes are thin — they delegate immediately to services."""
    return UserOut.model_validate(current_user)


@router.post("/", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(payload: UserCreate, db: DBSession) -> UserOut:
    service = UserService(db)
    user = await service.create(payload)
    return UserOut.model_validate(user)


@router.patch("/me", response_model=UserOut)
async def update_profile(
    payload: UserUpdate,
    current_user: CurrentUser,
    db: DBSession,
) -> UserOut:
    service = UserService(db)
    updated = await service.update(current_user.id, payload)
    return UserOut.model_validate(updated)
```

### Pydantic Schemas — Separate Input from Output

```python
# app/schemas/user.py
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    """Request body for POST /users — only what the client sends."""
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    full_name: str = Field(min_length=1, max_length=100)


class UserUpdate(BaseModel):
    """All fields optional — PATCH semantics."""
    full_name: str | None = Field(default=None, min_length=1, max_length=100)
    email: EmailStr | None = None


class UserOut(BaseModel):
    """Response schema — never includes password, internal fields."""
    model_config = ConfigDict(from_attributes=True)  # enables ORM → schema conversion

    id: int
    email: EmailStr
    full_name: str
    created_at: datetime
    is_active: bool
```

### Typed Exception Handlers

```python
# app/exceptions.py
import logging
import uuid

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError

logger = logging.getLogger(__name__)


class AppException(Exception):
    def __init__(self, status_code: int, detail: str, error_code: str | None = None) -> None:
        self.status_code = status_code
        self.detail = detail
        self.error_code = error_code


class NotFoundError(AppException):
    def __init__(self, resource: str) -> None:
        super().__init__(status.HTTP_404_NOT_FOUND, f"{resource} not found", "NOT_FOUND")


class ConflictError(AppException):
    def __init__(self, detail: str) -> None:
        super().__init__(status.HTTP_409_CONFLICT, detail, "CONFLICT")


class ForbiddenError(AppException):
    def __init__(self) -> None:
        super().__init__(status.HTTP_403_FORBIDDEN, "Forbidden", "FORBIDDEN")


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.detail, "code": exc.error_code},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = str(uuid.uuid4())
        logger.exception("Unhandled error", extra={"request_id": request_id})
        # Never expose internal details — log server-side, return generic response
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": "An unexpected error occurred", "request_id": request_id},
        )
```

### Router Aggregation

```python
# app/api/router.py
from fastapi import APIRouter

from app.api.v1 import auth, posts, users

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(posts.router)


# app/api/v1/auth.py
from fastapi import APIRouter

router = APIRouter(prefix="/auth", tags=["auth"])
```

---

## 5. FastAPI — Auto-Documentation

FastAPI generates OpenAPI 3.x documentation automatically from type hints and Pydantic schemas.
No additional packages required.

```python
# Enrich auto-docs with descriptions, examples, and response codes
@router.post(
    "/",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    description="Creates a user account. Email must be unique.",
    responses={
        409: {"description": "Email already registered"},
        422: {"description": "Validation error"},
    },
)
async def create_user(payload: UserCreate, db: DBSession) -> UserOut: ...


# Add examples to Pydantic schemas — appear in Swagger UI
class UserCreate(BaseModel):
    email: EmailStr = Field(examples=["user@example.com"])
    password: str = Field(min_length=12, examples=["Str0ng!Pass#2024"])
```

Access at runtime:

- `http://localhost:8000/docs` — Swagger UI (interactive, try-it-out enabled)
- `http://localhost:8000/redoc` — ReDoc (clean, read-only reference)
- `http://localhost:8000/openapi.json` — raw OpenAPI schema (import to Postman, Insomnia)

**Production note:** disable or auth-protect `/docs` and `/redoc` for public-facing APIs:

```python
app = FastAPI(docs_url=None, redoc_url=None)  # disabled in prod
# or restrict to internal IPs via middleware
```

---

## 6. Flask — Production Project Structure

```
my-flask-api/
├── .github/workflows/
├── alembic/
│   └── versions/
├── app/
│   ├── __init__.py          # application factory: create_app()
│   ├── config.py            # pydantic-settings config classes
│   ├── extensions.py        # Flask extensions (SQLAlchemy, Migrate, etc.)
│   ├── api/
│   │   ├── __init__.py
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── users.py     # Blueprint — thin route handlers
│   │       └── auth.py
│   ├── models/              # SQLAlchemy models
│   │   ├── __init__.py
│   │   └── user.py
│   ├── schemas/             # Pydantic or marshmallow schemas
│   │   └── user.py
│   ├── services/            # business logic
│   │   └── user_service.py
│   └── exceptions.py
├── tests/
│   ├── conftest.py
│   ├── unit/
│   └── integration/
├── .env.example
├── alembic.ini
├── Dockerfile
└── pyproject.toml
```

### Flask Application Factory

```python
# app/__init__.py
from flask import Flask

from app.api.v1.auth import auth_bp
from app.api.v1.users import users_bp
from app.config import get_settings
from app.exceptions import register_error_handlers
from app.extensions import db, migrate


def create_app() -> Flask:
    app = Flask(__name__)
    settings = get_settings()
    app.config.from_object(settings)

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)  # flask-migrate for Alembic integration

    # Register blueprints (equivalent to FastAPI's APIRouter)
    app.register_blueprint(auth_bp, url_prefix="/api/v1/auth")
    app.register_blueprint(users_bp, url_prefix="/api/v1/users")

    register_error_handlers(app)

    return app
```

### Flask Blueprint Pattern

```python
# app/api/v1/users.py
from flask import Blueprint, jsonify, request

from app.dependencies import require_auth
from app.schemas.user import UserCreate
from app.services.user_service import UserService

users_bp = Blueprint("users", __name__)


@users_bp.route("/me", methods=["GET"])
@require_auth
def get_profile(current_user):  # type: ignore[no-untyped-def]
    return jsonify(current_user.to_dict())


@users_bp.route("/", methods=["POST"])
def create_user():  # type: ignore[no-untyped-def]
    data = UserCreate.model_validate(request.get_json())  # Pydantic validation
    service = UserService()
    user = service.create(data)
    return jsonify(user.to_dict()), 201
```

### Flask Error Handlers

```python
# app/exceptions.py
import logging
import uuid

from flask import Flask, jsonify
from pydantic import ValidationError
from werkzeug.exceptions import HTTPException

logger = logging.getLogger(__name__)


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(ValidationError)
    def handle_validation_error(exc: ValidationError):  # type: ignore[no-untyped-def]
        return jsonify({"error": "Validation failed", "details": exc.errors()}), 422

    @app.errorhandler(HTTPException)
    def handle_http_exception(exc: HTTPException):  # type: ignore[no-untyped-def]
        return jsonify({"error": exc.description}), exc.code

    @app.errorhandler(Exception)
    def handle_unhandled(exc: Exception):  # type: ignore[no-untyped-def]
        request_id = str(uuid.uuid4())
        logger.exception("Unhandled error", extra={"request_id": request_id})
        return jsonify({"error": "An unexpected error occurred", "request_id": request_id}), 500
```

---

## 7. Alembic — Database Migrations

Alembic is the standard migration tool for SQLAlchemy. Use it in both Flask and FastAPI.
**Never use `Base.metadata.create_all()` in production** — it doesn't track changes.

```bash
# Initial setup (run once per project)
uv run alembic init alembic

# Generate a migration from model changes
uv run alembic revision --autogenerate -m "create users table"

# Apply all pending migrations
uv run alembic upgrade head

# Roll back one migration
uv run alembic downgrade -1

# View migration history
uv run alembic history --verbose
```

```python
# alembic/env.py — configure to read DATABASE_URL from settings
from app.config import settings
from app.models.base import Base  # import all models so Alembic can detect them

config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
target_metadata = Base.metadata
```

**CI/CD integration — run migrations before starting the server:**

```dockerfile
# Dockerfile entrypoint
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
```

Or as a Kubernetes init container / GitHub Actions step before deploy.

---

## 8. Testing

```python
# tests/conftest.py
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import get_db
from app.main import app

# Use an in-memory SQLite database for tests — no Postgres required
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with TestSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncClient:
    # Override the real DB dependency with the test DB
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()
```

```python
# tests/integration/test_users.py
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_user(client: AsyncClient) -> None:
    response = await client.post("/api/v1/users/", json={
        "email": "test@example.com",
        "password": "Str0ng!Pass#2024",
        "full_name": "Test User",
    })
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "test@example.com"
    assert "password" not in data  # never leak password in response


@pytest.mark.asyncio
async def test_create_user_duplicate_email(client: AsyncClient) -> None:
    payload = {"email": "dup@example.com", "password": "Str0ng!Pass#2024", "full_name": "A"}
    await client.post("/api/v1/users/", json=payload)
    response = await client.post("/api/v1/users/", json=payload)
    assert response.status_code == 409
```

Run tests:

```bash
uv run pytest tests/ -v --tb=short
uv run pytest tests/ --cov=app --cov-report=term-missing  # with coverage
```

---

## 9. Key Patterns Summary

| Pattern      | Rule                                                                                       |
| ------------ | ------------------------------------------------------------------------------------------ |
| Routes       | Thin — call service methods only, no business logic                                        |
| Services     | Own business logic — no HTTP imports, no SQLAlchemy sessions directly                      |
| Repositories | Own all DB queries — services call repos, not the session directly                         |
| Schemas      | Separate `Create`, `Update`, `Out` per resource — never reuse input as output              |
| Config       | `pydantic-settings` — fails at startup if required env vars are missing                    |
| Sessions     | Always yield from `get_db()` dependency — never create sessions manually in routes         |
| Errors       | Typed exception hierarchy — never return raw strings or expose internal messages           |
| Migrations   | Alembic — never `create_all()` in production                                               |
| Docs         | FastAPI auto-docs at `/docs` and `/redoc` — enrich with `summary`, `responses`, `examples` |
| Tooling      | `uv` for all package management — never `pip`; `pyproject.toml` — never `requirements.txt` |
