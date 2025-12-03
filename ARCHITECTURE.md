# Restructured Codebase Architecture

## Overview

The codebase has been restructured into a modular architecture for better maintainability, readability, and testability. The monolithic `app.py` (588 lines) and `main.py` (941 lines) have been broken down into focused modules.

## New Directory Structure

```
sdgcommons-data-parser/
├── src/
│   ├── __init__.py
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py          # Centralized configuration
│   ├── database/
│   │   ├── __init__.py
│   │   ├── connection.py        # Database connection management
│   │   └── operations.py        # CRUD operations for articles
│   ├── scraper/
│   │   ├── __init__.py
│   │   ├── selenium_driver.py   # Selenium WebDriver management
│   │   ├── pdf_extractor.py     # PDF content extraction
│   │   ├── web_scraper.py       # Web scraping logic
│   │   └── rescraper.py         # Re-scraping high-relevance articles
│   ├── api/
│   │   ├── __init__.py
│   │   ├── auth.py              # API key authentication
│   │   ├── health.py            # Health check endpoints
│   │   ├── scraper_routes.py    # Scraper control endpoints
│   │   └── upload_routes.py     # File upload & URL scraping endpoints
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── geocoding.py         # Country geocoding utilities
│   │   ├── language.py          # Language detection
│   │   └── nlp_service.py       # NLP embedding service integration
│   └── scheduler.py             # Background task scheduler
├── app.py                       # Main Flask application (simplified)
├── main.py                      # Legacy compatibility wrapper
├── app_old.py                   # Backup of original app.py
└── main_old.py                  # Backup of original main.py
```

## Module Responsibilities

### src/config/
**settings.py**: Centralized configuration management
- All environment variables loaded via `python-dotenv`
- Database credentials, API keys, scraper configuration
- HTTP headers and application settings
- Helper methods: `is_production()`, `has_nlp_service()`

### src/database/
**connection.py**: Database connection management
- `get_db_connection()` - Creates PostgreSQL connections

**operations.py**: Article database operations
- `article_exists()` - Check if article exists
- `get_existing_article()` - Retrieve article info
- `insert_article_to_db()` - Create new article with content and raw HTML
- `update_article_content()` - Update existing article content

### src/scraper/
**selenium_driver.py**: WebDriver lifecycle management
- `setup_selenium()` - Initialize headless Chrome with download directory
- `cleanup_selenium()` - Quit driver and clean up temp files
- `safe_get()` - Fetch URLs with error handling

**pdf_extractor.py**: PDF content extraction
- `is_pdf_url()` - Detect direct PDF URLs
- `extract_pdf_content()` - Extract text from PDF bytes
- `download_and_parse_pdf()` - Download PDF via Selenium (fallback)
- `wait_for_download()` - Wait for browser download to complete

**web_scraper.py**: Web scraping and report parsing
- `extract_country_from_card()` - Parse country names from HTML
- `parse_country_report()` - Main parsing logic with PDF/web fallbacks
- `scrape_reports()` - Discover and process all UNDP reports

**rescraper.py**: High-relevance article re-scraping
- `rescrape_high_relevance_articles()` - Re-scrape articles with relevance >= 2

### src/api/
**auth.py**: Authentication utilities
- `require_api_key()` - Validate API key from headers/params/body

**health.py**: Health and status endpoints
- `GET /health` - Database health check, scraper status
- `GET /scraper/status` - Detailed scraper information

**scraper_routes.py**: Scraper control endpoints
- `POST /scraper/run` - Manually trigger scraping
- `POST /scraper/rescrape-high-relevance` - Re-scrape high-value articles

**upload_routes.py**: File processing endpoints
- `POST /scraper/upload` - Upload and parse PDF/DOCX/HTML files
- `POST /scraper/scrape` - Scrape URL on demand

### src/utils/
**geocoding.py**: Country location services
- `get_country_info()` - Get ISO3, lat/lng for countries
- Caching to minimize API calls
- Rate-limited (1 req/sec for OpenStreetMap)

**language.py**: Language detection
- `detect_language()` - Detect ISO 639-1 language codes

**nlp_service.py**: Embedding service integration
- `call_embedding_service()` - Submit articles to NLP API

### src/scheduler.py
Background task scheduling
- `init_scheduler()` - Initialize scheduled scraping (Mondays 00:00 UTC)
- `run_scheduled_scraper()` - Execute scraping job
- `load_scraper_status()` / `save_scraper_status()` - Persistent status management
- `get_scraping_status()` / `set_scraping_status()` - Current status tracking

## Key Benefits

### 1. **Separation of Concerns**
- Each module has a single, well-defined responsibility
- Easy to understand what each file does
- Changes are localized to specific modules

### 2. **Reusability**
- Functions can be imported and used across different parts of the application
- Easier to write unit tests for individual modules
- Common utilities (geocoding, language detection) are centralized

### 3. **Maintainability**
- Smaller files are easier to navigate and modify
- Clear module boundaries reduce cognitive load
- Backward compatibility maintained via `main.py` wrapper

### 4. **Testability**
- Each module can be tested independently
- Mock dependencies easily in unit tests
- Clear interfaces between modules

### 5. **Scalability**
- Easy to add new API endpoints (add routes to api/)
- Easy to add new scraping strategies (extend scraper/)
- Configuration changes isolated to config module

## Migration Guide

### Old Import Patterns
```python
# OLD (deprecated)
from main import scrape_reports, get_db_connection
```

### New Import Patterns
```python
# NEW (recommended)
from src.scraper import scrape_reports
from src.database import get_db_connection
from src.utils import get_country_info
from src.config import Settings
```

### Backward Compatibility
The `main.py` wrapper provides backward compatibility for existing scripts. However, new code should import directly from `src/` modules.

## Running the Application

### Development Mode
```bash
./run-dev.sh  # Port 8080, Flask reloader
```

### Production Mode
```bash
./run-prod.sh  # Port 8000, Gunicorn with Xvfb
```

### Docker
```bash
docker build -t sdg-scraper .
docker run -p 8000:8000 --env-file .env sdg-scraper
```

## Configuration

All configuration is managed through environment variables in `.env`:

- **Database**: `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`
- **Security**: `SAVE_API_KEY`
- **Selenium**: `CHROMEDRIVER_PATH`, `CHROME_BIN`
- **NLP Service** (optional): `NLP_API_URL`, `NLP_WRITE_TOKEN`, `API_TOKEN`, `EMBEDDING_DB`

See `src/config/settings.py` for complete configuration options.

## Testing

With the modular structure, unit tests can target specific modules:

```python
# Test database operations
from src.database import article_exists
def test_article_exists():
    # ... test implementation

# Test geocoding with mocked API
from src.utils import get_country_info
def test_get_country_info():
    # ... test implementation
```

## API Documentation

Interactive API documentation available at `/docs` when the application is running.

## Old Files

Original monolithic files are preserved as:
- `app_old.py` (original 588 lines)
- `main_old.py` (original 941 lines)

These can be removed once the refactored code is verified.
