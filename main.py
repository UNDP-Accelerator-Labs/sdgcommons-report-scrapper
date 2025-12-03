"""
Legacy main.py - DEPRECATED

This file has been refactored into modular components under src/:
- src/config/settings.py - Configuration management
- src/database/ - Database operations
- src/scraper/ - Web scraping and PDF extraction
- src/utils/ - Geocoding, language detection, NLP service
- src/scheduler.py - Background task scheduling

For backward compatibility, this file imports and re-exports the main functions.
New code should import directly from the src modules.
"""

import logging

# Re-export main functions for backward compatibility
from src.scraper import (
    setup_selenium,
    cleanup_selenium,
    scrape_reports,
    parse_country_report,
    rescrape_high_relevance_articles
)
from src.database import (
    get_db_connection,
    article_exists,
    get_existing_article,
    insert_article_to_db,
    update_article_content
)
from src.utils import (
    get_country_info,
    detect_language,
    call_embedding_service
)

logger = logging.getLogger(__name__)

# Warn about deprecated usage
logger.warning(
    "main.py is deprecated. Please import from src modules directly:\n"
    "  from src.scraper import scrape_reports\n"
    "  from src.database import get_db_connection\n"
    "  from src.utils import get_country_info"
)

if __name__ == "__main__":
    logger.info("Running scraper from deprecated main.py")
    scrape_reports()
