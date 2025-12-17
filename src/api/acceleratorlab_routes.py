"""API routes for AcceleratorLab scanner"""

import logging
from flask import Blueprint, jsonify, request

from src.acceleratorlab import (
    start_scan_async,
    get_scan_status,
    load_country_data,
    get_all_countries,
    calculate_summary,
    load_summary,
    pause_scan,
    start_single_country_scan_async,
    resume_country_pending_tasks,
    force_break_lock
)
from src.api.auth import require_api_key

logger = logging.getLogger(__name__)

acceleratorlab_bp = Blueprint("acceleratorlab", __name__, url_prefix="/acceleratorlab")


@acceleratorlab_bp.route("/scan/start", methods=["POST"])
def start_scan():
    """
    Start a new AcceleratorLab scan.
    
    POST /acceleratorlab/scan/start
    Requires: API key authentication
    
    Returns:
        JSON response with success status and message
    """
    # Check API key
    ok, err = require_api_key()
    if not ok:
        return jsonify({"error": err}), 401
    
    logger.info("Received request to start AcceleratorLab scan")
    
    try:
        success, message = start_scan_async()
        
        if success:
            return jsonify({
                "success": True,
                "message": message
            }), 200
        else:
            return jsonify({
                "success": False,
                "error": message
            }), 400
            
    except Exception as e:
        logger.error(f"Error starting scan: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@acceleratorlab_bp.route("/scan/status", methods=["GET"])
def scan_status():
    """
    Get current scan status and progress.
    
    GET /acceleratorlab/scan/status
    
    Returns:
        JSON response with status, progress, and error (if any)
    """
    try:
        status = get_scan_status()
        return jsonify(status), 200
        
    except Exception as e:
        logger.error(f"Error getting scan status: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500


@acceleratorlab_bp.route("/scan/continue", methods=["POST"])
def continue_scan():
    """
    Manually continue/resume an interrupted scan.
    
    POST /acceleratorlab/scan/continue
    Requires: API key authentication
    
    Returns:
        JSON response with success status and message
    """
    # Check API key
    ok, err = require_api_key()
    if not ok:
        return jsonify({"error": err}), 401
    
    logger.info("Received request to continue/resume scan")
    
    try:
        from src.acceleratorlab.file_storage import save_scan_status
        
        # Get current status
        status = get_scan_status()
        current_status = status.get("status")
        
        # If already running, return error
        if current_status == "running":
            return jsonify({
                "success": False,
                "error": "Scan is already running"
            }), 400
        
        # Reset status to idle to allow resume
        if current_status in ["completed", "error", "paused"]:
            logger.info(f"Resetting status from '{current_status}' to 'idle' for resume")
            save_scan_status("idle", {})
        
        # Start scan (will automatically resume from where it left off)
        success, message = start_scan_async()
        
        if success:
            return jsonify({
                "success": True,
                "message": f"Scan resumed successfully. {message}"
            }), 200
        else:
            return jsonify({
                "success": False,
                "error": message
            }), 400
            
    except Exception as e:
        logger.error(f"Error continuing scan: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@acceleratorlab_bp.route("/scan/pause", methods=["POST"])
def pause_scan_endpoint():
    """
    Pause the currently running scan.
    
    POST /acceleratorlab/scan/pause
    Requires: API key authentication
    
    Returns:
        JSON response with success status and message
    """
    # Check API key
    ok, err = require_api_key()
    if not ok:
        return jsonify({"error": err}), 401
    
    logger.info("Received request to pause scan")
    
    try:
        success, message = pause_scan()
        
        if success:
            return jsonify({
                "success": True,
                "message": message
            }), 200
        else:
            return jsonify({
                "success": False,
                "error": message
            }), 400
            
    except Exception as e:
        logger.error(f"Error pausing scan: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@acceleratorlab_bp.route("/scan/break-lock", methods=["POST"])
def break_lock():
    """
    Force break the distributed lock (emergency use only).
    
    POST /acceleratorlab/scan/break-lock
    Requires: API key authentication
    
    Use this when a lock is stuck and blocking all scans.
    
    Returns:
        JSON response with success status and message
    """
    # Check API key
    ok, err = require_api_key()
    if not ok:
        return jsonify({"error": err}), 401
    
    logger.warning("⚠️  Received request to force break scan lock")
    
    try:
        success, message = force_break_lock()
        
        if success:
            return jsonify({
                "success": True,
                "message": message
            }), 200
        else:
            return jsonify({
                "success": False,
                "error": message
            }), 400
            
    except Exception as e:
        logger.error(f"Error breaking lock: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@acceleratorlab_bp.route("/scan/country", methods=["POST"])
def scan_single_country():
    """
    Scan a specific country by name.
    
    POST /acceleratorlab/scan/country
    Requires: API key authentication
    
    Request body:
        {
            "country": "Albania"  // or "Nigeria", "Kenya", etc.
        }
    
    Returns:
        JSON response with success status and scan results
    """
    # Check API key
    ok, err = require_api_key()
    if not ok:
        return jsonify({"error": err}), 401
    
    # Get country name from request
    data = request.get_json()
    if not data or "country" not in data:
        return jsonify({
            "success": False,
            "error": "Missing 'country' field in request body"
        }), 400
    
    country_name = data["country"].strip()
    if not country_name:
        return jsonify({
            "success": False,
            "error": "Country name cannot be empty"
        }), 400
    
    logger.info(f"Received request to scan single country: {country_name}")
    
    try:
        success, message = start_single_country_scan_async(country_name)
        
        if success:
            return jsonify({
                "success": True,
                "message": message,
                "country": country_name
            }), 200
        else:
            return jsonify({
                "success": False,
                "error": message
            }), 400
            
    except Exception as e:
        logger.error(f"Error starting single country scan: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@acceleratorlab_bp.route("/country/<country_code>/resume", methods=["POST"])
def resume_country(country_code):
    """
    Resume pending tasks for a country that hit the 24-hour timeout.
    
    POST /acceleratorlab/country/<country_code>/resume
    Requires: API key authentication
    
    Args:
        country_code: ISO3 country code (e.g., "ALB", "NGA")
        
    Returns:
        JSON response with resume results and updated article counts
    """
    # Check API key
    ok, err = require_api_key()
    if not ok:
        return jsonify({"error": err}), 401
    
    country_code = country_code.upper()
    logger.info(f"Received request to resume pending tasks for: {country_code}")
    
    try:
        result = resume_country_pending_tasks(country_code)
        
        if result.get("success"):
            return jsonify(result), 200
        else:
            return jsonify(result), 400
            
    except Exception as e:
        logger.error(f"Error resuming country tasks: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@acceleratorlab_bp.route("/country/<country_code>", methods=["GET"])
def get_country(country_code):
    """
    Get classification results for a specific country.
    
    GET /acceleratorlab/country/<country_code>
    
    Args:
        country_code: ISO3 country code (e.g., "KEN")
        
    Returns:
        JSON response with country data and classified articles
    """
    try:
        data = load_country_data(country_code.upper())
        
        if data:
            return jsonify(data), 200
        else:
            return jsonify({
                "error": f"Country {country_code} not found"
            }), 404
            
    except Exception as e:
        logger.error(f"Error loading country data: {e}", exc_info=True)
        return jsonify({
            "error": str(e)
        }), 500


@acceleratorlab_bp.route("/countries", methods=["GET"])
def list_countries():
    """
    Get list of all processed countries.
    
    GET /acceleratorlab/countries
    
    Returns:
        JSON response with list of country codes
    """
    try:
        countries = get_all_countries()
        return jsonify({
            "countries": countries,
            "total": len(countries)
        }), 200
        
    except Exception as e:
        logger.error(f"Error listing countries: {e}", exc_info=True)
        return jsonify({
            "error": str(e)
        }), 500


@acceleratorlab_bp.route("/summary", methods=["GET"])
def get_summary():
    """
    Get global summary of all classifications.
    
    GET /acceleratorlab/summary
    
    Query params:
        refresh: If "true", recalculate summary from country files
        
    Returns:
        JSON response with total counts and per-country breakdown
    """
    try:
        refresh = request.args.get("refresh", "false").lower() == "true"
        
        if refresh:
            # Recalculate summary
            summary = calculate_summary()
            from src.acceleratorlab.file_storage import save_summary
            save_summary(summary)
        else:
            # Load cached summary
            summary = load_summary()
            
            # If no summary exists, calculate it
            if not summary:
                summary = calculate_summary()
                from src.acceleratorlab.file_storage import save_summary
                save_summary(summary)
        
        return jsonify(summary), 200
        
    except Exception as e:
        logger.error(f"Error getting summary: {e}", exc_info=True)
        return jsonify({
            "error": str(e)
        }), 500


@acceleratorlab_bp.route("/scan/reset", methods=["POST"])
def reset_scan():
    """
    Clear all processed data to start fresh scan.
    
    POST /acceleratorlab/scan/reset
    Requires: API key authentication
    
    WARNING: This deletes all processed country data!
    
    Returns:
        JSON response with success status
    """
    # Check API key
    ok, err = require_api_key()
    if not ok:
        return jsonify({"error": err}), 401
    
    try:
        from src.acceleratorlab.file_storage import clear_all_data
        
        clear_all_data()
        
        return jsonify({
            "success": True,
            "message": "All scan data cleared. Ready for fresh scan."
        }), 200
        
    except Exception as e:
        logger.error(f"Error resetting scan: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@acceleratorlab_bp.route("/country/<country_code>", methods=["DELETE"])
def delete_country(country_code):
    """
    Delete data for a specific country to allow re-processing.
    
    DELETE /acceleratorlab/country/<country_code>
    Requires: API key authentication
    
    Args:
        country_code: ISO3 country code (e.g., "KEN")
        
    Returns:
        JSON response with success status
    """
    # Check API key
    ok, err = require_api_key()
    if not ok:
        return jsonify({"error": err}), 401
    
    try:
        from src.acceleratorlab.file_storage import delete_country_data
        
        delete_country_data(country_code.upper())
        
        # Recalculate summary after deletion
        from src.acceleratorlab.file_storage import calculate_summary, save_summary
        summary = calculate_summary()
        save_summary(summary)
        
        return jsonify({
            "success": True,
            "message": f"Country {country_code} deleted. Can be re-processed in next scan."
        }), 200
        
    except Exception as e:
        logger.error(f"Error deleting country: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@acceleratorlab_bp.route("/health", methods=["GET"])
def health():
    """
    Health check for AcceleratorLab module.
    
    GET /acceleratorlab/health
    
    Returns:
        JSON response with module status
    """
    return jsonify({
        "module": "acceleratorlab",
        "status": "ok"
    }), 200
