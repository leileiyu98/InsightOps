"""ASGI entrypoint used by Uvicorn."""

from insightops.app import create_app
from insightops.core.config import load_settings

app = create_app(load_settings())
