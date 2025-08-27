from flask import Flask, jsonify
import threading
import schedule
import time
import logging
from datetime import datetime, timezone
import os
from main import scrape_reports

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Global variables to track scraper status
last_scrape_time = None
last_scrape_status = "Never run"
is_scraping = False

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
    run_scheduled_scraper()  # Initial run on startup
    # Schedule scraper to run every Monday at 00:00 UTC
    # schedule.every().monday.at("00:00").do(run_scheduled_scraper)

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
        from main import get_db_connection
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

@app.route('/', methods=['GET'])
def root():
    """Root endpoint"""
    return jsonify({
        "message": "SDG Commons Reports Scraper API",
        "version": "1.0.0",
        "server": "gunicorn" if __name__ != "__main__" else "flask-dev",
        "environment": os.getenv("ENVIRONMENT", "development"),
        "endpoints": {
            "health": "/health",
            "scraper_status": "/scraper/status",
            "manual_run": "/scraper/run (POST)"
        }
    })

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