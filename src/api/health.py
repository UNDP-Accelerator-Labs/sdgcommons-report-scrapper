"""Health check and status endpoints"""

import os
import logging
from datetime import datetime, timezone
from flask import Blueprint, jsonify

from src.database import get_db_connection
from src.scheduler import load_scraper_status

logger = logging.getLogger(__name__)

health_bp = Blueprint('health', __name__)


@health_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for Azure Web App and monitoring"""
    try:
        # Check database connection
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        conn.close()
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"
    
    scraper_status = load_scraper_status()

    response = {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database": db_status,
        "server": "gunicorn" if __name__ != "__main__" else "flask-dev",
        "environment": os.getenv("ENVIRONMENT", "development"),
        "scraper": {
            "last_run": scraper_status.get("last_run"),
            "last_status": scraper_status.get("last_status"),
            "currently_running": scraper_status.get("currently_running")
        }
    }
    
    status_code = 200 if db_status == "healthy" else 503
    return jsonify(response), status_code


@health_bp.route('/scraper/status', methods=['GET'])
def scraper_status():
    """Get detailed scraper status"""
    s = load_scraper_status()
    return jsonify({
        "last_run": s.get("last_run"),
        "last_status": s.get("last_status"),
        "currently_running": s.get("currently_running"),
        "next_scheduled_run": "Every Monday at 00:00 UTC",
        "server": "gunicorn" if __name__ != "__main__" else "flask-dev"
    })
