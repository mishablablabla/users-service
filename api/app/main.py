import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .infrastructure import orm  # noqa: F401  (registers tables on Base.metadata)
from .infrastructure.db import Base, database_url, engine
from .interface.routes import router


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Standalone/dev mode (SQLite): create tables on start. In Kubernetes the schema is
    # created by the migration Job, so AUTO_CREATE_TABLES=false there.
    default = "true" if database_url().startswith("sqlite") else "false"
    if os.getenv("AUTO_CREATE_TABLES", default).lower() == "true":
        Base.metadata.create_all(engine)
    yield


# Docs live under /api so that an Ingress routing /api -> backend also exposes Swagger UI.
app = FastAPI(
    lifespan=lifespan,
    title="Users Service",
    version="1.0.0",
    description="Simple CRUD REST API for users (CI/CD lab project).",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url=None,
)
app.include_router(router)
