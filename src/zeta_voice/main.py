from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast

import click
import uvicorn
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

from zeta_voice.auth import admin_api_key_auth
from zeta_voice.database import create_tables, display_schema
from zeta_voice.routes.admin_router import admin_router
from zeta_voice.routes.app_router import router as app_router
from zeta_voice.routes.lead_extraction import router as lead_extraction_router
from zeta_voice.settings import settings

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Handles application startup and shutdown events."""
    db_url = settings.engine.DATABASE_URL

    db_url_c = cast(str, db_url)

    if db_url_c.startswith("sqlite"):
        db_path = Path(db_url_c.replace("sqlite+pysqlite:///", "", 1))
        db_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"Database tables will be checked/created at: {db_path.resolve()}")
    else:
        print(f"Connecting to database: {db_url_c.split('@')[-1]}")

    create_tables()
    print("Database tables checked/created.")
    yield
    print("Application shutting down.")


app = FastAPI(title="Zeta Voice - Twilio Voice Agent", lifespan=lifespan)
app.include_router(app_router)
app.include_router(lead_extraction_router)

templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

@app.get("/lead-call", include_in_schema=False, response_class=HTMLResponse)
async def lead_call_ui(request: Request):
    return templates.TemplateResponse("lead_call.html", {"request": request})

admin_app = FastAPI(title="Zeta Voice - Admin", dependencies=[Depends(admin_api_key_auth)])
admin_app.include_router(admin_router)

dynamic_recordings_dir = Path(settings.storage.LOCAL_STORAGE_DYNAMIC_CONTAINER_NAME).absolute()
dynamic_recordings_dir.mkdir(parents=True, exist_ok=True)

static_data_dir = Path("data").absolute()

app.mount("/dynamic-recordings", StaticFiles(directory=dynamic_recordings_dir), name="dynamic-recordings")
app.mount("/static-recordings", StaticFiles(directory=static_data_dir), name="static-recordings")


@click.group()
def cli() -> None:
    """Management CLI for Zeta Voice."""
    pass


@cli.command()
@click.option("--host", default="0.0.0.0", help="Host to bind.")  # noqa: S104
@click.option("--port", default=8000, help="Port to listen on.")
def telephony(host: str, port: int) -> None:
    """Runs the FastAPI application using Uvicorn server."""
    uvicorn.run("zeta_voice.main:app", host=host, port=port, reload=True)


@cli.command()
@click.option("--host", default="0.0.0.0", help="Host to bind.")  # noqa: S104
@click.option("--port", default=8001, help="Port to listen on.")
def admin(host: str, port: int) -> None:
    """Runs the Admin server for data export."""
    print("Starting admin server...")
    uvicorn.run("zeta_voice.main:admin_app", host=host, port=port, reload=False)


@cli.command()
def show_schema() -> None:
    """Retrieves and displays the current database schema."""
    display_schema()


if __name__ == "__main__":
    cli()
