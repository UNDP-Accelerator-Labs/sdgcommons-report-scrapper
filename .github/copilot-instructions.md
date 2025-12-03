# SDG Commons Report Scraper - AI Coding Instructions

## Architecture Overview

This is a Flask web service that scrapes UNDP country reports (AILA/DRA) from undp.org, extracts content from PDFs/web pages, geocodes countries, and stores everything in PostgreSQL. It runs scheduled scraping every Monday at 00:00 UTC using a background thread with the `schedule` library.

**Modular Architecture:**
The codebase is organized into focused modules under `src/`:
- `src/config/` - Centralized configuration (`Settings` class with all env vars)
- `src/database/` - PostgreSQL operations (connection, CRUD for articles)
- `src/scraper/` - Web scraping (Selenium, PDF extraction, report parsing)
- `src/api/` - Flask blueprints (health, scraper routes, upload routes, auth)
- `src/utils/` - Shared utilities (geocoding, language detection, NLP service)
- `src/scheduler.py` - Background task scheduling

**Legacy Files:**
- `app.py` - Main Flask application (now simplified, uses blueprints)
- `main.py` - Backward compatibility wrapper (imports from src modules)
- `app_old.py` / `main_old.py` - Original monolithic files (backup)

**Database:**
- PostgreSQL tables: `articles`, `article_content`, `raw_html` (relationships via `article_id`)

## Critical Patterns

### 1. Module Imports
Import from `src/` modules, not legacy files:
```python
# Recommended
from src.scraper import setup_selenium, scrape_reports
from src.database import get_db_connection, insert_article_to_db
from src.config import Settings
from src.utils import get_country_info

# Deprecated (works but shows warning)
from main import scrape_reports
```

### 2. Selenium Driver Lifecycle
**Always** call `setup_selenium()` before scraping and `cleanup_selenium()` after. Located in `src/scraper/selenium_driver.py`:

```python
from src.scraper import setup_selenium, cleanup_selenium

setup_selenium()  # Creates global driver, wait, download_dir
try:
    # scraping operations
finally:
    cleanup_selenium()  # Quits driver, removes temp download dir
```

### 3. Database Operations
All database writes use `psycopg2` with explicit transaction control. Operations in `src/database/operations.py`:
```python
from src.database import get_db_connection, insert_article_to_db

conn = get_db_connection()
try:
    with conn.cursor() as cur:
        # SQL operations
    conn.commit()
except Exception as e:
    conn.rollback()
    raise
finally:
    conn.close()
```

Articles require 3 table inserts: `articles` → `article_content` → `raw_html`. Use `insert_article_to_db()` which handles all three. Article IDs are returned via `RETURNING id`.

### 4. Content Extraction Hierarchy
PDF extraction in `src/scraper/pdf_extractor.py` and `web_scraper.py` has multiple fallback strategies:
1. **Direct PDF URL**: Detect via `is_pdf_url()`, extract with `pdfminer` via `requests`
2. **Selenium PDF Download**: If requests fails (403/access denied), use `download_and_parse_pdf()` which triggers browser download
3. **Web Content**: If no PDF found, extract `<p>` tags from HTML

Content source is tracked in `content_source` field: `PDF_DIRECT_REQUESTS`, `PDF_DIRECT_SELENIUM`, `PDF`, `WEB`, `FAILED`.

Main entry point: `parse_country_report(url, report_type, country)` in `src/scraper/web_scraper.py`

### 5. API Key Protection
Endpoints that write to DB (`/scraper/run`, `/scraper/upload`, `/scraper/scrape` with `save=true`) require `SAVE_API_KEY` via:
- Header: `X-API-KEY`
- Query param: `api_key`
- JSON body: `api_key`

Check using `require_api_key()` from `src/api/auth.py` which returns `(bool, error_msg)`:
```python
from src.api.auth import require_api_key

ok, err = require_api_key()
if not ok:
    return jsonify({"error": err}), 401
```

### 6. Scraper Status Persistence
Status is persisted to `/tmp/sdg_scraper_status.json` (configurable via `Settings.SCRAPER_STATUS_FILE`) to share state across gunicorn workers. Functions in `src/scheduler.py`:
```python
from src.scheduler import load_scraper_status, save_scraper_status

status = load_scraper_status()  # Returns dict with last_run, last_status, currently_running
save_scraper_status(datetime.now(), "Success", False)
```

### 7. Geocoding & Country Detection
`get_country_info()` in `src/utils/geocoding.py` uses `pycountry` for ISO3 codes and `geopy.Nominatim` for coordinates. Results are cached in `geocoding_cache` dict. **Always sleep 1 second after geocoding** to respect OpenStreetMap rate limits.

### 8. Configuration Access
All configuration in `src/config/settings.py`. Access via `Settings` class:
```python
from src.config import Settings

# Database
conn = psycopg2.connect(host=Settings.DB_HOST, port=Settings.DB_PORT, ...)

# Check environment
if Settings.is_production():
    # Production-specific logic

# NLP service
if Settings.has_nlp_service():
    # Call embedding API
```

## Development Workflow

### Local Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Edit database credentials
```

### Running Locally
- **Dev mode** (Flask reloader): `./run-dev.sh` → port 8080
- **Prod mode** (Gunicorn): `./run-prod.sh` → port 8000

Dev mode uses Flask's built-in server with `--reload`. Prod mode starts Xvfb for headless Chrome and uses Gunicorn with config from `gunicorn.conf.py`.

### Environment Variables
Required for operation:
- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`: PostgreSQL connection
- `SAVE_API_KEY`: Protection for write endpoints

Optional (for NLP embedding):
- `NLP_API_URL`, `NLP_WRITE_TOKEN`, `API_TOKEN`, `EMBEDDING_DB`

Set via `.env` (loaded automatically) or export in shell.

## Testing & Debugging

### Manual Endpoints
```bash
# Health check
curl http://localhost:8000/health

# Trigger scraper (requires SAVE_API_KEY)
curl -X POST http://localhost:8000/scraper/run \
  -H "X-API-KEY: your_key"

# Upload file for parsing
curl -X POST http://localhost:8000/scraper/upload \
  -F "file=@report.pdf" \
  -F "url=https://example.com/report" \
  -F "country=Kenya" \
  -H "X-API-KEY: your_key"
```

### Common Issues
- **ChromeDriver not found**: Set `CHROMEDRIVER_PATH` env var or install to system PATH. Docker uses `/usr/bin/chromium-driver`.
- **Geocoding timeouts**: Increase timeout in `geolocator.geocode(timeout=10)` or check network.
- **PDF extraction fails**: Check logs for "Access denied" → uses Selenium fallback. Verify Chrome is headless.
- **Database connection**: Verify credentials in `.env` and that PostgreSQL accepts connections from your IP.

## Docker Deployment

Dockerfile installs Chromium (not Chrome) to support ARM64/multi-arch. Key points:
- Uses `python:3.11-slim` base
- Installs `chromium` and `chromium-driver` packages
- Sets `CHROME_BIN=/usr/bin/chromium` for Selenium
- Runs as non-root user `app`
- Exposes port via `PORT` env var (default 8000)
- Health check hits `/health` endpoint

Build and run:
```bash
docker build -t sdg-scraper .
docker run -p 8000:8000 --env-file .env sdg-scraper
```

## API Design Philosophy

The API separates concerns:
- **Parsing**: Extracts content from URLs/files (no auth needed)
- **Saving**: Writes to database (requires API key)
- **Embedding**: Calls external NLP service (optional, requires saved article)

Example: `/scraper/scrape` with `save=false` returns parsed content without DB write. Set `save=true` to persist.

## Scheduled Tasks

The scheduler runs in a daemon thread started by `init_scheduler()`. It uses `schedule.every().monday.at("00:00").do(run_scheduled_scraper)`. 

**Important**: Gunicorn config sets `workers=1` to avoid duplicate scheduled tasks. If increasing workers, move scheduling to a separate process or use distributed locking.

## Code Conventions

- Logging: Use module-level `logger` (configured via `logging.basicConfig`). Info for normal flow, warning for retries/fallbacks, error for failures.
- Error handling: Wrap scraping operations in try/except, log full traceback with `traceback.format_exc()`, save error state to status file.
- Database schema: If adding columns, check existence first with `information_schema.columns` query (see `insert_article_to_db`).
- Content relevance: Articles are tagged with `relevance=2` by default. High-relevance re-scraping targets `relevance >= 2`.

## External Dependencies

- **UNDP websites**: `https://www.undp.org/digital/aila` and `.../dra` - HTML structure uses `.feature__card` divs with `h6.coh-heading` labels.
- **NLP embedding service**: Optional POST to `{NLP_API_URL}/api/embed/add` with body `{token, write_access, db, main_id: "blog:{article_id}"}`.
- **OpenStreetMap**: Geocoding via Nominatim (rate limit: 1 req/sec).

## File Structure Notes

- `app.py`: Main Flask app, registers blueprints from `src/api/`
- `main.py`: Backward compatibility wrapper (imports from src/)
- `app_old.py` / `main_old.py`: Backup of original monolithic files
- `src/`: Modular codebase organized by concern
- `openapi.yaml`: API documentation served at `/docs` via Swagger UI
- `run-*.sh`: Shell scripts for dev/prod startup (make executable with `chmod +x`)
- `gunicorn.conf.py`: Production WSGI config (1 worker, 300s timeout, preload app)
- `ARCHITECTURE.md`: Detailed guide to the modular structure

## Adding New Features

**New API Endpoint:**
1. Create route function in appropriate blueprint (`src/api/health.py`, `scraper_routes.py`, or `upload_routes.py`)
2. Or create new blueprint file and register in `app.py`

**New Scraping Strategy:**
1. Add function to `src/scraper/web_scraper.py` or create new module
2. Import in `src/scraper/__init__.py`

**New Configuration:**
1. Add to `src/config/settings.py` as class variable
2. Set in `.env` file

**New Database Operation:**
1. Add function to `src/database/operations.py`
2. Export in `src/database/__init__.py`
