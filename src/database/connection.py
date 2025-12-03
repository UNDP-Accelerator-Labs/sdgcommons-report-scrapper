"""Database connection management"""

import logging
import psycopg2
from src.config import Settings

logger = logging.getLogger(__name__)


def get_db_connection():
    """
    Create and return a PostgreSQL database connection.
    
    Returns:
        psycopg2.connection: Database connection object
    """
    try:
        conn = psycopg2.connect(
            host=Settings.DB_HOST,
            port=Settings.DB_PORT,
            dbname=Settings.DB_NAME,
            user=Settings.DB_USER,
            password=Settings.DB_PASSWORD
        )
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        raise
