"""File upload and URL scraping endpoints"""

import io
import json
import logging
import requests as http_requests
from flask import Blueprint, jsonify, request
from pdfminer.high_level import extract_text
from bs4 import BeautifulSoup

try:
    from docx import Document as DocxDocument
except Exception:
    DocxDocument = None

from src.config import Settings
from src.database import get_db_connection, insert_article_to_db
from src.scraper import setup_selenium, cleanup_selenium, parse_country_report
from .auth import require_api_key

logger = logging.getLogger(__name__)

upload_bp = Blueprint('upload', __name__, url_prefix='/scraper')


def process_uploaded_file(file_bytes, filename):
    """
    Extract content from uploaded file based on file type.
    
    Args:
        file_bytes: File content as bytes
        filename: Original filename
        
    Returns:
        tuple: (content_string, content_source_string)
    """
    content = ""
    content_source = "UPLOAD"
    lower = filename.lower()
    
    try:
        if lower.endswith('.pdf'):
            try:
                content = extract_text(io.BytesIO(file_bytes))
                content_source = "PDF_UPLOAD"
            except Exception as e:
                logger.error(f"Failed to extract uploaded PDF: {e}")
                raise RuntimeError("Failed to extract PDF content")
                
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
            
        return content, content_source
        
    except Exception as e:
        logger.error(f"Error processing file: {e}")
        raise


@upload_bp.route('/upload', methods=['POST'])
def upload_and_save():
    """
    Upload a file (PDF, HTML, DOCX, or text) and optionally save/embed.
    multipart/form-data fields:
      - file: required
      - url: required (used as source URL)
      - report_type: optional string (default "UPLOAD")
      - country: optional string (default "Unknown")
      - save: optional "true"/"false" (default "true")
      - embed: optional JSON string/object
    """
    # API key check (only required for saving)
    save = request.form.get('save', 'true').lower() == 'true'

    if save:
        ok, err = require_api_key()
        if not ok:
            return jsonify({"error": err}), 401

    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files['file']
    report_type = request.form.get('report_type', 'UPLOAD')
    country = request.form.get('country', 'Unknown')
    url = request.form.get('url', None)
    if not url:
        return jsonify({"error": "url is required"}), 400   
    
    user_title = request.form.get('title') or None
    file_bytes = file.read()
    filename = file.filename or "uploaded_file"
    
    try:
        content, content_source = process_uploaded_file(file_bytes, filename)
    except Exception as e:
        return jsonify({"error": f"Error processing file: {str(e)}"}), 500

    # Prepare article_data compatible with insert_article_to_db
    article_data = {
        "title": user_title or f"{report_type} - {country}",
        "content": content or "",
        "content_length": len(content or ""),
        "content_source": content_source,
        "url": url,
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

    # Optionally embed (requires embed params)
    embed_raw = request.form.get('embed')
    embed_json = None
    
    if embed_raw:
        try:
            embed_json = json.loads(embed_raw)
        except Exception:
            return jsonify({"error": "embed must be a valid JSON object"}), 400

    embedded = False
    if embed_json and saved_id:
        from src.utils import call_embedding_service
        embedded = call_embedding_service(saved_id)

    # Return parsed content even if not saved (separated behavior)
    return jsonify({
        "message": "Upload processed",
        "saved_id": saved_id,
        "embedded": embedded,
        "article_data": article_data
    }), 201 if saved_id else 200


@upload_bp.route('/scrape', methods=['POST'])
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
        "embed": { ... } (optional)
      }
    """
    payload = request.get_json(silent=True)
    if not payload or 'url' not in payload:
        return jsonify({"error": "Missing JSON body with 'url'"}), 400

    url = payload['url']
    report_type = payload.get('report_type', None)
    country = payload.get('country', 'Unknown')
    save = payload.get('save', False)
    embed_json = payload.get('embed')
    user_title = payload.get('title') or None

    saved_id = None

    # For parsing we need selenium set up because parse_country_report may use Selenium
    setup_selenium()
    try:
        article_data, raw_html = parse_country_report(
            url, 
            report_type or ("AILA" if "aila" in url else "DRA"), 
            country
        )
    finally:
        cleanup_selenium()

    if not article_data:
        return jsonify({"error": "Failed to parse the URL"}), 500

    # If caller provided a title, prefer it over parsed title
    if user_title:
        article_data['title'] = user_title

    # If caller requested saving, require API key
    if save:
        ok, err = require_api_key()
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

    # Optionally embed
    embedded = False
    if embed_json and saved_id:
        from src.utils import call_embedding_service
        embedded = call_embedding_service(saved_id)

    # Return scraped content + metadata regardless of save
    return jsonify({
        "message": "Scrape completed",
        "parsed_success": article_data.get('success', False),
        "article_data": article_data,
        "saved_id": saved_id,
        "embedded": embedded
    }), 200
