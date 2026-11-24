from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from jobhunter import __version__, paths
from jobhunter.api import applications, companies, config, health, inbox, insight, leads, reachout, runs
from jobhunter.jobs import runner, scheduler


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Scheduler + run workers live and die with the server; JOBHUNTER_NO_SCHEDULER=1 skips them (tests, dev)."""
    managed = os.environ.get("JOBHUNTER_NO_SCHEDULER") != "1"
    if managed:
        scheduler.start()
    try:
        yield
    finally:
        if managed:
            scheduler.shutdown()
            runner.shutdown()


def create_app(serve_web: bool = True) -> FastAPI:
    app = FastAPI(
        title="job-hunter", version=__version__, openapi_url="/api/openapi.json", docs_url="/api/docs",
        lifespan=lifespan,
    )
    for r in (health.router, leads.router, applications.router, inbox.proposals, inbox.outreach,
              runs.router, insight.router, config.router, companies.router, reachout.router):
        app.include_router(r)

    if serve_web and paths.WEB_DIST.is_dir():
        app.mount("/assets", StaticFiles(directory=paths.WEB_DIST / "assets"), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa(full_path: str) -> FileResponse:  # SPA fallback; /api/* matched above
            f = paths.WEB_DIST / full_path
            return FileResponse(f if full_path and f.is_file() else paths.WEB_DIST / "index.html")

    return app


app = create_app()
