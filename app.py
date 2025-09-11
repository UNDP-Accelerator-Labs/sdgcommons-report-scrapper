from flask import Flask, jsonify, request, Response, send_from_directory, redirect
from flask_swagger_ui import get_swaggerui_blueprint
import threading
import schedule
import time
import logging
from datetime import datetime, timezone
import os
from main import scrape_reports, parse_country_report, insert_article_to_db, get_db_connection, setup_selenium, cleanup_selenium
import io
import requests as http_requests
from pdfminer.high_level import extract_text
from flask_cors import CORS
try:
    from docx import Document as DocxDocument
except Exception:
    DocxDocument = None
import json

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# Global variables to track scraper status
last_scrape_time = None
last_scrape_status = "Never run"
is_scraping = False

# API key env var used to protect endpoints that save to DB
SAVE_API_KEY = os.getenv("SAVE_API_KEY", "")

def _require_api_key():
    """Helper to validate API key for endpoints that save to DB."""
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

    if not SAVE_API_KEY:
        # If no SAVE_API_KEY set on server, deny to avoid accidental writes
        return False, "Server SAVE_API_KEY not configured"
    if key != SAVE_API_KEY:
        return False, "Invalid API key"
    return True, None

def run_scheduled_scraper():
    """Run the scraper and update status"""
    global last_scrape_time, last_scrape_status, is_scraping
    
    try:
        is_scraping = True
        logger.info("Starting scheduled scraping job...")
        
        # Run the scraper
        results = scrape_reports()
        
        last_scrape_time = datetime.now(timezone.utc)
        last_scrape_status = f"Success - {len(results)} reports processed"
        logger.info(f"Scraping completed successfully: {len(results)} reports")
        
    except Exception as e:
        last_scrape_time = datetime.now(timezone.utc)
        last_scrape_status = f"Failed - {str(e)}"
        logger.error(f"Scraping failed: {e}")
    finally:
        is_scraping = False

def scheduler_worker():
    """Background worker for the scheduler"""
    # Schedule scraper to run every Monday at 00:00 UTC
    schedule.every().monday.at("00:00").do(run_scheduled_scraper)

    logger.info("Scheduler started - will run every Monday at 00:00 UTC")

    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute

# Health check endpoint
@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for Azure Web App"""
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
    
    response = {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database": db_status,
        "server": "gunicorn" if __name__ != "__main__" else "flask-dev",
        "environment": os.getenv("ENVIRONMENT", "development"),
        "scraper": {
            "last_run": last_scrape_time.isoformat() if last_scrape_time else None,
            "last_status": last_scrape_status,
            "currently_running": is_scraping
        }
    }
    
    status_code = 200 if db_status == "healthy" else 503
    return jsonify(response), status_code

@app.route('/scraper/status', methods=['GET'])
def scraper_status():
    """Get detailed scraper status"""
    return jsonify({
        "last_run": last_scrape_time.isoformat() if last_scrape_time else None,
        "last_status": last_scrape_status,
        "currently_running": is_scraping,
        "next_scheduled_run": "Every Monday at 00:00 UTC",
        "server": "gunicorn" if __name__ != "__main__" else "flask-dev"
    })

@app.route('/scraper/run', methods=['POST'])
def manual_scraper_run():
    """Manually trigger scraper (for testing)"""
    if is_scraping:
        return jsonify({"error": "Scraper is already running"}), 409
    
    # Run scraper in background thread
    thread = threading.Thread(target=run_scheduled_scraper)
    thread.daemon = True
    thread.start()
    
    return jsonify({"message": "Scraper started manually"}), 202

@app.route('/scraper/upload', methods=['POST'])
def upload_and_save():
    """
    Upload a file (PDF, HTML, DOCX, or text) and optionally save/embed.
    multipart/form-data fields:
      - file: required
      - report_type: optional string (default "UPLOAD")
      - country: optional string (default "Unknown")
      - save: optional "true"/"false" (default "true")
      - embed: optional JSON string/object with { token, write_access, db, prefix, api_url }
    """
    # API key check (only required for saving)
    # Note: we still permit upload+parse without API key when save=false
    save = request.form.get('save', 'true').lower() == 'true'

    if save:
        ok, err = _require_api_key()
        if not ok:
            return jsonify({"error": err}), 401

    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files['file']
    report_type = request.form.get('report_type', 'UPLOAD')
    country = request.form.get('country', 'Unknown')
    # allow user-supplied title to override generated title
    user_title = request.form.get('title') or None
    # embed handled separately below
    file_bytes = file.read()
    content = ""
    content_source = "UPLOAD"

    try:
        filename = file.filename or "uploaded_file"
        lower = filename.lower()
        if lower.endswith('.pdf'):
            try:
                content = extract_text(io.BytesIO(file_bytes))
                content_source = "PDF_UPLOAD"
            except Exception as e:
                logger.error(f"Failed to extract uploaded PDF: {e}")
                return jsonify({"error": "Failed to extract PDF content"}), 500
        elif lower.endswith('.docx') or lower.endswith('.doc'):
            try:
                if DocxDocument is None:
                    raise RuntimeError("python-docx not installed")
                doc = DocxDocument(io.BytesIO(file_bytes))
                paragraphs = [p.text.strip() for p in doc.paragraphs if p.text and p.text.strip()]
                content = "\n".join(paragraphs)
                content_source = "DOCX_UPLOAD"
            except Exception as e:
                logger.error(f"Failed to extract uploaded DOCX/DOC: {e}")
                # fallback to binary decode
                try:
                    content = file_bytes.decode('utf-8', errors='ignore')
                except:
                    content = file_bytes.decode('latin-1', errors='ignore')
                content_source = "DOCX_UPLOAD_FALLBACK"
        elif lower.endswith('.html') or lower.endswith('.htm'):
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(file_bytes.decode('utf-8', errors='ignore'), 'html.parser')
                paragraphs = [p.get_text(strip=True) for p in soup.find_all('p')]
                content = "\n".join(paragraphs)
                content_source = "HTML_UPLOAD"
            except Exception as e:
                logger.error(f"Failed to parse uploaded HTML: {e}")
                content = file_bytes.decode('utf-8', errors='ignore')
                content_source = "HTML_UPLOAD_FALLBACK"
        else:
            # Try to decode as text
            try:
                content = file_bytes.decode('utf-8')
            except:
                content = file_bytes.decode('latin-1', errors='ignore')
            content_source = "TEXT_UPLOAD"
    except Exception as e:
        logger.error(f"Error processing uploaded file: {e}")
        return jsonify({"error": "Error processing file"}), 500

    # Prepare article_data compatible with insert_article_to_db
    article_data = {
        "title": user_title or f"{report_type} - {country} - {filename}",
        "content": content or "",
        "content_length": len(content or ""),
        "content_source": content_source,
        "url": f"upload://{filename}",
        "country": country,
        "report_type": report_type,
    }

    # Save to DB if requested
    saved_id = None
    if save:
        conn = None
        try:
            conn = get_db_connection()
            saved_id = insert_article_to_db(conn, article_data, raw_html=None)
        except Exception as e:
            logger.error(f"Failed to save uploaded document: {e}")
            return jsonify({"error": f"Failed to save: {str(e)}"}), 500
        finally:
            if conn:
                conn.close()

    # Optionally embed (requires embed params). Embedding is strictly separate from saving.
    embed_raw = request.form.get('embed')
    embed_json = None
    # Accept embed object in multipart form (stringified JSON) or in JSON body
    try:
        body_json = request.get_json(silent=True) or {}
        if 'embed' in body_json:
            embed_json = body_json.get('embed')
    except:
        body_json = {}

    # If embed provided as form field (string), attempt to parse JSON
    if embed_raw and not embed_json:
        try:
            embed_json = json.loads(embed_raw)
        except Exception:
            return jsonify({"error": "embed must be a valid JSON object"}), 400

    # If embed present but is a string (from body), parse it
    if isinstance(embed_json, str):
        try:
            embed_json = json.loads(embed_json)
        except Exception:
            return jsonify({"error": "embed must be a valid JSON object"}), 400

    # If embed provided, validate required client fields (no env fallback)
    if embed_json:
        if not isinstance(embed_json, dict):
            return jsonify({"error": "embed must be a JSON object"}), 400
        missing = [k for k in ('token', 'write_access', 'api_url') if not embed_json.get(k)]
        if missing:
            return jsonify({"error": f"embed missing required fields: {', '.join(missing)}"}), 400

    embedded = False
    if embed_json:
        # embedding requires either saved_id (this request) or embed.main_id supplied
        if not saved_id and not embed_json.get('main_id'):
            return jsonify({"error": "Embedding requested but document was not saved. Provide save=true and valid API key or include embed.main_id"}), 400

        try:
            embed_body = {
                "token": embed_json.get('token'),
                "write_access": os.getenv("NLP_WRITE_TOKEN"),
                "db": os.getenv("EMBEDDING_DB"),
                "main_id": f"{embed_json.get('prefix','doc')}:{saved_id}",
            }
            embed_url = os.getenv("NLP_API_URL") 
            resp = http_requests.post(
                f"{embed_url.rstrip('/')}/api/embed/add",
                json=embed_body,
                timeout=30
            )
            if not resp.ok:
                logger.error(f"Embedding failed: {resp.status_code} {resp.text}")
                return jsonify({"error": "Embedding failed", "details": resp.text}), 502
            embedded = True
        except Exception as e:
            logger.error(f"Error embedding document: {e}")
            return jsonify({"error": f"Embedding error: {str(e)}"}), 500

    # Return parsed content even if not saved (separated behavior)
    return jsonify({
        "message": "Upload processed",
        "saved_id": saved_id,
        "embedded": embedded,
        "article_data": article_data
    }), 201 if saved_id else 200

@app.route('/scraper/scrape', methods=['POST'])
def api_scrape_and_save():
    """
    Scrape a URL via API. Caller controls saving and embedding separately.
    JSON body:
      {
        "url": "https://...",
        "report_type": "AILA" (optional),
        "country": "Country Name" (optional),
        "title": "Optional title to use when saving",
        "save": false (default false),
        "embed": { prefix,  } (optional)
      }
    """
    payload = request.get_json(silent=True)
    if not payload or 'url' not in payload:
        return jsonify({"error": "Missing JSON body with 'url'"}), 400

    url = payload['url']
    report_type = payload.get('report_type', None)
    country = payload.get('country', 'Unknown')
    save = payload.get('save', False)   # default: do not save unless explicitly requested
    embed_json = payload.get('embed')
    user_title = payload.get('title') or None

    saved_id = None

    # For parsing we need selenium set up because parse_country_report may use Selenium
    setup_selenium()
    try:
        article_data, raw_html = parse_country_report(url, report_type or ("AILA" if "aila" in url else "DRA"), country)
    finally:
        cleanup_selenium()

    if not article_data:
        return jsonify({"error": "Failed to parse the URL"}), 500

    # If caller provided a title, prefer it over parsed title
    if user_title:
        article_data['title'] = user_title

    # If caller requested saving, require API key
    if save:
        ok, err = _require_api_key()
        if not ok:
            return jsonify({"error": err}), 401

        conn = None
        try:
            conn = get_db_connection()
            saved_id = insert_article_to_db(conn, article_data, raw_html)
        except Exception as e:
            logger.error(f"Failed to save scraped URL: {e}")
            return jsonify({"error": f"Failed to save: {str(e)}"}), 500
        finally:
            if conn:
                conn.close()

    # Optionally embed (requires embed params). Embedding is separate from scraping.
    embedded = False
    if embed_json:
        # embedding requires either saved_id (this request) or embed.main_id supplied
        if not saved_id and not embed_json.get('main_id'):
            return jsonify({"error": "Embedding requested but document was not saved. Provide save=true and valid API key or include embed.main_id"}), 400

        try:
            embed_body = {
                "token": embed_json.get('token'),
                "write_access": os.getenv("NLP_WRITE_TOKEN"),
                "db": os.getenv("EMBEDDING_DB"),
                "main_id": f"{embed_json.get('prefix','doc')}:{saved_id}",
            }
            embed_url = os.getenv("NLP_API_URL")
            resp = http_requests.post(
                f"{embed_url.rstrip('/')}/api/embed/add",
                json=embed_body,
                timeout=30
            )
            if not resp.ok:
                logger.error(f"Embedding failed: {resp.status_code} {resp.text}")
                return jsonify({"error": "Embedding failed", "details": resp.text}), 502
            embedded = True
        except Exception as e:
            logger.error(f"Error embedding document: {e}")
            return jsonify({"error": f"Embedding error: {str(e)}"}), 500

    # Return scraped content + metadata regardless of save
    return jsonify({
        "message": "Scrape completed",
        "parsed_success": article_data.get('success', False),
        "article_data": article_data,
        "saved_id": saved_id,
        "embedded": embedded
    }), 200

# register swagger UI (serves the YAML at /openapi.yaml and UI at /docs)
SWAGGER_URL = "/docs"             # URL for exposing Swagger UI (can be /swagger, /docs, etc.)
API_YAML_URL = "/openapi.yaml"    # URL to the OpenAPI YAML served by this app

swaggerui_blueprint = get_swaggerui_blueprint(
    SWAGGER_URL,
    API_YAML_URL,
    config={ "app_name": "SDG Commons Reports Scraper API" }
)
app.register_blueprint(swaggerui_blueprint, url_prefix=SWAGGER_URL)

# serve the openapi.yaml from the repository root
@app.route('/openapi.yaml', methods=['GET'])
def serve_openapi_yaml():
    # file is expected at project root next to app.py
    root_dir = os.path.dirname(__file__)
    return send_from_directory(root_dir, 'openapi.yaml', mimetype='text/yaml')

@app.route('/', methods=['GET'])
def root():
    """Root endpoint"""
    return redirect('/docs')

# Initialize scheduler when app starts (not just in __main__)
def init_scheduler():
    """Initialize scheduler in production"""
    if os.getenv("ENVIRONMENT") == "production" or __name__ != "__main__":
        scheduler_thread = threading.Thread(target=scheduler_worker, daemon=True)
        scheduler_thread.start()
        logger.info("Production scheduler initialized")

# Initialize scheduler for production
init_scheduler()

if __name__ == '__main__':
    # This only runs in development mode
    logger.warning("Running in DEVELOPMENT mode - do not use in production!")
    
    # Start the scheduler for development
    if not any(thread.name.startswith('Thread-') for thread in threading.enumerate()):
        scheduler_thread = threading.Thread(target=scheduler_worker, daemon=True)
        scheduler_thread.start()
    
    # Start Flask development server
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)