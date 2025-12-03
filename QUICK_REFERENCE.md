# Quick Reference Guide - Modular Structure

## Common Import Patterns

### Configuration

```python
from src.config import Settings

# Access settings
db_host = Settings.DB_HOST
is_prod = Settings.is_production()
has_nlp = Settings.has_nlp_service()
```

### Database Operations

```python
from src.database import (
    get_db_connection,
    article_exists,
    get_existing_article,
    insert_article_to_db,
    update_article_content
)

# Use in your code
conn = get_db_connection()
if not article_exists(conn, url):
    article_id = insert_article_to_db(conn, article_data, raw_html)
conn.close()
```

### Web Scraping

```python
from src.scraper import (
    setup_selenium,
    cleanup_selenium,
    parse_country_report,
    scrape_reports
)

# Standard pattern
setup_selenium()
try:
    article_data, raw_html = parse_country_report(url, "AILA", "Kenya")
finally:
    cleanup_selenium()
```

### PDF Extraction

```python
from src.scraper import (
    is_pdf_url,
    extract_pdf_content,
    download_and_parse_pdf
)

if is_pdf_url(url):
    content = extract_pdf_content(pdf_bytes)
```

### Utilities

```python
from src.utils import (
    get_country_info,
    detect_language,
    call_embedding_service
)

# Geocoding
iso3, lat, lng = get_country_info("Kenya")

# Language detection
lang = detect_language(text_content)

# NLP embedding
success = call_embedding_service(article_id)
```

### API Development

```python
from flask import Blueprint, jsonify
from src.api.auth import require_api_key

my_bp = Blueprint('myroutes', __name__, url_prefix='/my')

@my_bp.route('/endpoint', methods=['POST'])
def my_endpoint():
    ok, err = require_api_key()
    if not ok:
        return jsonify({"error": err}), 401
    # ... your logic
```

### Scheduler

```python
from src.scheduler import (
    load_scraper_status,
    save_scraper_status,
    get_scraping_status,
    run_scheduled_scraper
)

# Check status
is_running = get_scraping_status()
status = load_scraper_status()

# Update status
from datetime import datetime, timezone
save_scraper_status(datetime.now(timezone.utc), "Success", False)
```

## Module Locations

| Functionality  | Module                           | Key Functions                                        |
| -------------- | -------------------------------- | ---------------------------------------------------- |
| Configuration  | `src/config/settings.py`         | `Settings` class                                     |
| DB Connection  | `src/database/connection.py`     | `get_db_connection()`                                |
| DB Operations  | `src/database/operations.py`     | `insert_article_to_db()`, `update_article_content()` |
| Selenium       | `src/scraper/selenium_driver.py` | `setup_selenium()`, `cleanup_selenium()`             |
| PDF Extraction | `src/scraper/pdf_extractor.py`   | `extract_pdf_content()`, `download_and_parse_pdf()`  |
| Web Scraping   | `src/scraper/web_scraper.py`     | `parse_country_report()`, `scrape_reports()`         |
| Re-scraping    | `src/scraper/rescraper.py`       | `rescrape_high_relevance_articles()`                 |
| Authentication | `src/api/auth.py`                | `require_api_key()`                                  |
| Health Checks  | `src/api/health.py`              | Health endpoints                                     |
| Scraper API    | `src/api/scraper_routes.py`      | `/scraper/run`, `/scraper/rescrape-high-relevance`   |
| Upload API     | `src/api/upload_routes.py`       | `/scraper/upload`, `/scraper/scrape`                 |
| Geocoding      | `src/utils/geocoding.py`         | `get_country_info()`                                 |
| Language       | `src/utils/language.py`          | `detect_language()`                                  |
| NLP Service    | `src/utils/nlp_service.py`       | `call_embedding_service()`                           |
| Scheduler      | `src/scheduler.py`               | `init_scheduler()`, `run_scheduled_scraper()`        |

## Typical Workflows

### Adding a New Scraping Function

1. Create function in `src/scraper/web_scraper.py` or new file
2. Export in `src/scraper/__init__.py`
3. Import where needed: `from src.scraper import my_new_function`

### Adding a New API Endpoint

1. Add route to existing blueprint in `src/api/`
2. Or create new blueprint file
3. Register in `app.py`: `app.register_blueprint(new_bp)`

### Adding a New Configuration

1. Add to `Settings` class in `src/config/settings.py`
2. Set in `.env` file
3. Access via `Settings.YOUR_CONFIG`

### Adding a New Database Operation

1. Add function to `src/database/operations.py`
2. Export in `src/database/__init__.py`
3. Import: `from src.database import my_new_operation`

## File Size Reference

| Module                           | Lines | Purpose                   |
| -------------------------------- | ----- | ------------------------- |
| `src/config/settings.py`         | ~70   | Configuration management  |
| `src/database/connection.py`     | ~25   | DB connections            |
| `src/database/operations.py`     | ~180  | Article CRUD operations   |
| `src/scraper/selenium_driver.py` | ~160  | WebDriver management      |
| `src/scraper/pdf_extractor.py`   | ~150  | PDF extraction utilities  |
| `src/scraper/web_scraper.py`     | ~360  | Main scraping logic       |
| `src/scraper/rescraper.py`       | ~100  | Re-scraping utilities     |
| `src/api/auth.py`                | ~40   | Authentication            |
| `src/api/health.py`              | ~60   | Health endpoints          |
| `src/api/scraper_routes.py`      | ~100  | Scraper control           |
| `src/api/upload_routes.py`       | ~230  | Upload & scrape endpoints |
| `src/utils/geocoding.py`         | ~90   | Geocoding services        |
| `src/utils/language.py`          | ~30   | Language detection        |
| `src/utils/nlp_service.py`       | ~45   | NLP service integration   |
| `src/scheduler.py`               | ~135  | Background scheduler      |

**Total: ~1,879 lines** across 21 files (avg ~90 lines per file)

Compare to original: **1,529 lines** in 2 files (avg ~765 lines per file)

## Benefits

✅ **Smaller files** (avg 90 lines vs 765 lines)
✅ **Clear responsibilities** (one concern per module)
✅ **Easy to find code** (logical organization)
✅ **Testable** (isolated modules)
✅ **Maintainable** (changes are localized)
✅ **Documented** (clear structure)

## Need Help?

- **Architecture details**: See `ARCHITECTURE.md`
- **Restructuring info**: See `RESTRUCTURING_SUMMARY.md`
- **AI agent guidance**: See `.github/copilot-instructions.md`
- **API docs**: Run app and visit `/docs`
