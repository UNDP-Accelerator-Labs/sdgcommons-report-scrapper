"""API key authentication utilities"""

import logging
from flask import request

from src.config import Settings

logger = logging.getLogger(__name__)


def require_api_key():
    """
    Helper to validate API key for endpoints that save to DB.
    
    Returns:
        tuple: (success: bool, error_message: str or None)
    """
    key = None
    # Accept key in header X-API-KEY or query param api_key
    if 'X-API-KEY' in request.headers:
        key = request.headers.get('X-API-KEY')
    elif 'api_key' in request.args:
        key = request.args.get('api_key')
    else:
        # try json body
        try:
            body = request.get_json(silent=True) or {}
            key = body.get('api_key')
        except:
            key = None

    if not Settings.SAVE_API_KEY:
        # If no SAVE_API_KEY set on server, deny to avoid accidental writes
        return False, "Server SAVE_API_KEY not configured"
    if key != Settings.SAVE_API_KEY:
        return False, "Invalid API key"
    return True, None
