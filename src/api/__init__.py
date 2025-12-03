"""API routes module"""

from .health import health_bp
from .scraper_routes import scraper_bp
from .upload_routes import upload_bp

__all__ = ['health_bp', 'scraper_bp', 'upload_bp']
