"""Background task scheduler for periodic scraping"""

import os
import json
import shutil
import logging
import schedule
import time
import threading
import traceback
from datetime import datetime, timezone

from src.config import Settings

logger = logging.getLogger(__name__)

# Global scraper status
_is_scraping = False
_last_scrape_time = None
_last_scrape_status = "Never run"


def get_scraping_status():
    """Get current scraping status"""
    global _is_scraping
    return _is_scraping


def set_scraping_status(status):
    """Set current scraping status"""
    global _is_scraping
    _is_scraping = status


def load_scraper_status():
    """
    Load scraper status from persistent file.
    
    Returns:
        dict: Status information with last_run, last_status, currently_running
    """
    try:
        with open(Settings.SCRAPER_STATUS_FILE, "r") as fh:
            return json.load(fh)
    except Exception:
        return {
            "last_run": None,
            "last_status": "Never run",
            "currently_running": False
        }


def save_scraper_status(last_run, last_status, currently_running):
    """
    Save scraper status to persistent file (shared across processes).
    
    Args:
        last_run: datetime or None
        last_status: Status message string
        currently_running: Boolean indicating if scraper is active
    """
    data = {
        "last_run": last_run.isoformat() if last_run else None,
        "last_status": last_status,
        "currently_running": bool(currently_running)
    }
    tmp = Settings.SCRAPER_STATUS_FILE + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(data, fh)
    try:
        os.replace(tmp, Settings.SCRAPER_STATUS_FILE)
    except Exception:
        # fallback if os.replace not available on some platforms
        shutil.move(tmp, Settings.SCRAPER_STATUS_FILE)


def run_scheduled_scraper():
    """Run the scraper and update status"""
    global _is_scraping, _last_scrape_time, _last_scrape_status
    from src.scraper import scrape_reports

    try:
        _is_scraping = True
        _last_scrape_time = datetime.now(timezone.utc)
        _last_scrape_status = "Running"
        save_scraper_status(_last_scrape_time, _last_scrape_status, _is_scraping)

        logger.info("Starting scheduled scraping job...")
        
        # Run the scraper
        results = scrape_reports()
        
        _last_scrape_time = datetime.now(timezone.utc)
        _last_scrape_status = f"Success - {len(results)} reports processed"
        logger.info(f"Scraping completed successfully: {len(results)} reports")
        save_scraper_status(_last_scrape_time, _last_scrape_status, False)
        
    except Exception as e:
        _last_scrape_time = datetime.now(timezone.utc)
        tb = traceback.format_exc()
        logger.error(f"Scraping failed: {e}\n{tb}")
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
        _last_scrape_status = f"Failed - {str(e)} | at {frame_info}"
        save_scraper_status(_last_scrape_time, _last_scrape_status, False)
    finally:
        _is_scraping = False


def scheduler_worker():
    """Background worker for the scheduler"""
    # Schedule scraper to run every Monday at 00:00 UTC
    schedule.every().monday.at("00:00").do(run_scheduled_scraper)

    logger.info("Scheduler started - will run every Monday at 00:00 UTC")

    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute


def init_scheduler():
    """Initialize scheduler in production"""
    if Settings.is_production() or __name__ != "__main__":
        scheduler_thread = threading.Thread(target=scheduler_worker, daemon=True)
        scheduler_thread.start()
        logger.info("Production scheduler initialized")
