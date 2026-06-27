"""Web layer: a single Flask app serving the kid status page and admin UI."""
from .app import create_app

__all__ = ["create_app"]
