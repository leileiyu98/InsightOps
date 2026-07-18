"""Optional production hosting for the M1.4 React build."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, PlainTextResponse, Response
from starlette.staticfiles import StaticFiles

DEFAULT_FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


def configure_frontend(application: FastAPI, dist_path: Path | None = None) -> None:
    """Serve a completed Vite build without making it an API startup dependency."""
    resolved_dist = dist_path if dist_path is not None else DEFAULT_FRONTEND_DIST
    index_path = resolved_dist / "index.html"
    assets_path = resolved_dist / "assets"

    if assets_path.is_dir():
        application.mount(
            "/assets",
            StaticFiles(directory=assets_path),
            name="frontend-assets",
        )

    @application.get("/", include_in_schema=False, response_model=None)
    async def frontend_index() -> Response:
        if index_path.is_file():
            return FileResponse(index_path)
        return PlainTextResponse(
            "InsightOps frontend not built. Run `npm run build` in frontend/.",
            status_code=503,
        )
