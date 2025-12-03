"""Database module for PostgreSQL operations"""

from .connection import get_db_connection
from .operations import (
    article_exists,
    get_existing_article,
    insert_article_to_db,
    update_article_content
)

__all__ = [
    'get_db_connection',
    'article_exists',
    'get_existing_article',
    'insert_article_to_db',
    'update_article_content'
]
