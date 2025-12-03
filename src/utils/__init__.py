"""Utilities module"""

from .geocoding import get_country_info
from .language import detect_language
from .nlp_service import call_embedding_service

__all__ = [
    'get_country_info',
    'detect_language',
    'call_embedding_service'
]
