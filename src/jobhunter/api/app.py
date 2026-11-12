from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from jobhunter import __version__, paths
from jobhunter.api import applications, config, health, inbox, insight, leads, runs


def create_app(serve_web: bool = True) -> FastAPI:
    app = FastAPI(title="job-hunter", version=__version__, openapi_url="/api/openapi.json", docs_url="/api/docs")
    for r in (health.router, leads.router, applications.router, inbox.proposals, inbox.outreach,
              runs.router, insight.router, config.router):
        app.include_router(r)

    if serve_web and paths.WEB_DIST.is_dir():
        app.mount("/assets", StaticFiles(directory=paths.WEB_DIST / "assets"), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa(full_path: str) -> FileResponse:  # SPA fallback; /api/* matched above
            f = paths.WEB_DIST / full_path
            return FileResponse(f if full_path and f.is_file() else paths.WEB_DIST / "index.html")

    return app


app = create_app()
