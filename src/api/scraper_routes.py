"""Scraper control endpoints"""

import logging
import threading
from flask import Blueprint, jsonify

from src.scheduler import run_scheduled_scraper, get_scraping_status
from .auth import require_api_key

logger = logging.getLogger(__name__)

scraper_bp = Blueprint('scraper', __name__, url_prefix='/scraper')


@scraper_bp.route('/run', methods=['POST'])
def manual_scraper_run():
    """Manually trigger scraper - require API key"""
    is_scraping = get_scraping_status()
    
    if is_scraping:
        return jsonify({"error": "Scraper is already running"}), 409
    
    # Check if AcceleratorLab scan is running (prevent concurrent browser usage)
    try:
        from src.acceleratorlab import get_scan_status
        accel_status = get_scan_status()
        if accel_status.get("status") == "running":
            return jsonify({"error": "AcceleratorLab scan is currently running. Please wait for it to complete."}), 409
    except Exception as e:
        logger.warning(f"Could not check AcceleratorLab scan status: {e}")
    
    ok, err = require_api_key()
    if not ok:
        return jsonify({"error": err}), 401
    
    # Run scraper in background thread
    thread = threading.Thread(target=run_scheduled_scraper)
    thread.daemon = True
    thread.start()

    return jsonify({"message": "Scraper started manually"}), 202


@scraper_bp.route('/rescrape-high-relevance', methods=['POST'])
def rescrape_high_relevance():
    """
    Re-scrape all articles with relevance >= 2 to try to extract PDF content.
    This endpoint requires API key authentication.
    """
    from src.scraper import rescrape_high_relevance_articles
    from src.scheduler import set_scraping_status, save_scraper_status
    from datetime import datetime, timezone
    import traceback
    
    # Check if scraper is already running
    if get_scraping_status():
        return jsonify({"error": "Scraper is already running"}), 409
    
    # Check if AcceleratorLab scan is running (prevent concurrent browser usage)
    try:
        from src.acceleratorlab import get_scan_status
        accel_status = get_scan_status()
        if accel_status.get("status") == "running":
            return jsonify({"error": "AcceleratorLab scan is currently running. Please wait for it to complete."}), 409
    except Exception as e:
        logger.warning(f"Could not check AcceleratorLab scan status: {e}")
    
    # Require API key for this operation
    ok, err = require_api_key()
    if not ok:
        return jsonify({"error": err}), 401
    
    # Run the re-scraping operation in a background thread
    def run_rescrape():
        try:
            set_scraping_status(True)
            last_scrape_time = datetime.now(timezone.utc)
            last_scrape_status = "Running high-relevance re-scrape"
            save_scraper_status(last_scrape_time, last_scrape_status, True)
            
            logger.info("Starting high-relevance articles re-scrape...")
            
            # Run the re-scraper
            results = rescrape_high_relevance_articles()
            
            last_scrape_time = datetime.now(timezone.utc)
            last_scrape_status = f"High-relevance re-scrape success - {len(results)} articles updated"
            logger.info(f"High-relevance re-scrape completed: {len(results)} articles updated")
            save_scraper_status(last_scrape_time, last_scrape_status, False)
            
        except Exception as e:
            last_scrape_time = datetime.now(timezone.utc)
            tb = traceback.format_exc()
            logger.error(f"High-relevance re-scrape failed: {e}\n{tb}")
            try:
                # get last traceback frame for file:line info
                import traceback as _tbmod, sys as _sys
                tb_list = _tbmod.extract_tb(_sys.exc_info()[2])
                if tb_list:
                    last_frame = tb_list[-1]
                    frame_info = f"{last_frame.filename}:{last_frame.lineno} in {last_frame.name}"
                else:
                    frame_info = "no-traceback-frame"
            except Exception:
                frame_info = "traceback-extract-failed"
            # Save concise status with frame info and exception message
            last_scrape_status = f"High-relevance re-scrape failed - {str(e)} | at {frame_info}"
            save_scraper_status(last_scrape_time, last_scrape_status, False)
        finally:
            set_scraping_status(False)
    
    # Start the background thread
    thread = threading.Thread(target=run_rescrape, daemon=True)
    thread.start()
    
    return jsonify({
        "message": "High-relevance articles re-scrape started",
        "description": "Re-scraping all articles with relevance >= 2 to extract PDF content and update NLP embeddings"
    }), 202
