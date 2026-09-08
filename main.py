"""ASGI compatibility entry point for `uvicorn main:app`."""

from canvasbot.api import app

__all__ = ["app"]
