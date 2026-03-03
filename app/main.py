"""FastAPI application entry point for Evergreen v3."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import SQLModel, create_engine, Session
from dotenv import load_dotenv
import os

load_dotenv()

# ---------------------------------------------------------------------------
# Database setup
# ---------------------------------------------------------------------------

# Use EVERGREEN_DB_URL to avoid Replit Cloud Run injecting a postgres
# DATABASE_URL that we have no driver for.
DATABASE_URL = os.getenv("EVERGREEN_DB_URL", "sqlite:///./evergreen.db")

# check_same_thread is SQLite-only; omit it for other dialects
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args)


def get_db():
    """Dependency: yields a SQLModel Session."""
    with Session(engine) as session:
        yield session


# ---------------------------------------------------------------------------
# App lifespan: init DB + warm catalog cache
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    SQLModel.metadata.create_all(engine)
    from app.core.catalog import load_catalog
    load_catalog()
    yield


# ---------------------------------------------------------------------------
# App instance
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Evergreen v3",
    description="AI evaluation platform for government teams",
    lifespan=lifespan,
)

# Static files
_static_dir = Path(__file__).parent / "static"
_static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

# Templates (shared across routers via import)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

from app.routes import benchmarks, runs, builder  # noqa: E402

app.include_router(benchmarks.router)
app.include_router(runs.router)
app.include_router(builder.router)
