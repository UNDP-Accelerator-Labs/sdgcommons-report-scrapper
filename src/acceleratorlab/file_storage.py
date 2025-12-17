"""File-based storage for AcceleratorLab analysis results"""

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any

from src.config import Settings

logger = logging.getLogger(__name__)

# Reduce Azure SDK logging verbosity
logging.getLogger('azure.core.pipeline.policies.http_logging_policy').setLevel(logging.WARNING)
logging.getLogger('azure.storage.blob').setLevel(logging.WARNING)

# Try to import Azure Blob Storage (optional dependency)
try:
    from azure.storage.blob import BlobServiceClient, ContentSettings, BlobLeaseClient
    AZURE_AVAILABLE = True
except ImportError:
    AZURE_AVAILABLE = False
    logger.debug("Azure Blob Storage not available (azure-storage-blob not installed)")

# Storage paths (local fallback)
BASE_DIR = Path(__file__).parent.parent.parent
DATA_DIR = BASE_DIR / "data" / "acceleratorlab"
COUNTRIES_DIR = DATA_DIR / "countries"
SUMMARY_FILE = DATA_DIR / "summary.json"
STATUS_FILE = DATA_DIR / "scan_status.json"

# Azure Blob Storage client (initialized on first use)
_blob_service_client = None
_scan_lock_lease = None  # Distributed lock lease for scan status

# Automatic environment detection: Use Azure Blob Storage only in production/Azure environment
# Local development uses local file storage regardless of connection string
def _should_use_azure_storage():
    """
    Determine if Azure Blob Storage should be used based on environment.
    
    Returns True only if:
    1. Running in production (ENVIRONMENT=production) OR running on Azure (WEBSITE_INSTANCE_ID exists)
    2. Azure connection string is configured
    3. azure-storage-blob package is installed
    
    For local development (ENVIRONMENT=development), always uses local storage.
    """
    # Check if running on Azure Web App (has WEBSITE_INSTANCE_ID)
    is_azure_webapp = os.getenv("WEBSITE_INSTANCE_ID") is not None
    
    # Check if explicitly set to production
    is_production = Settings.is_production()
    
    # Use Azure storage only if in Azure/production AND configured AND package available
    should_use_azure = (is_azure_webapp or is_production) and Settings.has_azure_storage() and AZURE_AVAILABLE
    
    return should_use_azure

_use_azure_storage = _should_use_azure_storage()

if _use_azure_storage:
    logger.info("🌐 Azure environment detected - Using Azure Blob Storage for data persistence")
else:
    if Settings.has_azure_storage() and AZURE_AVAILABLE and not Settings.is_production():
        logger.info("💻 Local development mode - Using local file storage (Azure Blob Storage available but not used)")
    elif Settings.has_azure_storage() and not AZURE_AVAILABLE:
        logger.warning("⚠️  AZURE_STORAGE_CONNECTION_STRING is set but azure-storage-blob is not installed. Using local storage.")
    else:
        logger.info("📁 Using local file storage for data persistence")


def _get_blob_service_client():
    """Get or create Azure Blob Service Client (lazy initialization)"""
    global _blob_service_client
    
    if not _use_azure_storage:
        return None
    
    if _blob_service_client is None:
        try:
            _blob_service_client = BlobServiceClient.from_connection_string(
                Settings.AZURE_STORAGE_CONNECTION_STRING
            )
            # Ensure container exists
            container_client = _blob_service_client.get_container_client(Settings.AZURE_STORAGE_CONTAINER)
            if not container_client.exists():
                container_client.create_container()
                logger.info(f"Created Azure Blob container: {Settings.AZURE_STORAGE_CONTAINER}")
        except Exception as e:
            logger.error(f"Failed to initialize Azure Blob Storage: {e}")
            return None
    
    return _blob_service_client


def _save_to_blob(blob_name: str, data: Dict[str, Any]):
    """Save JSON data to Azure Blob Storage"""
    try:
        blob_service_client = _get_blob_service_client()
        if not blob_service_client:
            return False
        
        blob_client = blob_service_client.get_blob_client(
            container=Settings.AZURE_STORAGE_CONTAINER,
            blob=blob_name
        )
        
        json_data = json.dumps(data, indent=2, ensure_ascii=False)
        blob_client.upload_blob(
            json_data,
            overwrite=True,
            content_settings=ContentSettings(content_type='application/json')
        )
        
        logger.debug(f"Saved to Azure Blob: {blob_name}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to save to Azure Blob {blob_name}: {e}")
        return False


def _load_from_blob(blob_name: str) -> Dict[str, Any]:
    """Load JSON data from Azure Blob Storage"""
    try:
        blob_service_client = _get_blob_service_client()
        if not blob_service_client:
            return None
        
        blob_client = blob_service_client.get_blob_client(
            container=Settings.AZURE_STORAGE_CONTAINER,
            blob=blob_name
        )
        
        if not blob_client.exists():
            return None
        
        blob_data = blob_client.download_blob().readall()
        data = json.loads(blob_data.decode('utf-8'))
        
        logger.debug(f"Loaded from Azure Blob: {blob_name}")
        return data
        
    except Exception as e:
        logger.error(f"Failed to load from Azure Blob {blob_name}: {e}")
        return None


def _list_blobs_with_prefix(prefix: str) -> List[str]:
    """List blob names with given prefix"""
    try:
        blob_service_client = _get_blob_service_client()
        if not blob_service_client:
            return []
        
        container_client = blob_service_client.get_container_client(Settings.AZURE_STORAGE_CONTAINER)
        
        blob_names = []
        for blob in container_client.list_blobs(name_starts_with=prefix):
            blob_names.append(blob.name)
        
        return blob_names
        
    except Exception as e:
        logger.error(f"Failed to list blobs with prefix {prefix}: {e}")
        return []


def ensure_directories():
    """Create necessary directories if they don't exist (local storage only)"""
    if not _use_azure_storage:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        COUNTRIES_DIR.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Ensured directories exist: {DATA_DIR}, {COUNTRIES_DIR}")


def save_country_data(country_code: str, country_name: str, articles: List[Dict[str, Any]], pending_tasks: Dict[str, Any] = None):
    """
    Save classified articles for a country to JSON file or Azure Blob.
    
    Args:
        country_code: ISO3 country code
        country_name: Country name
        articles: List of article dictionaries with classification results
        pending_tasks: Optional dict with incomplete tasks (blogs_pending, publications_pending, timeout_occurred)
    """
    data = {
        "country_code": country_code,
        "country_name": country_name,
        "total_articles": len(articles),
        "accelerator_lab_count": sum(1 for a in articles if a.get("classification") == "accelerator_lab"),
        "country_office_count": sum(1 for a in articles if a.get("classification") == "country_office"),
        "last_updated": datetime.utcnow().isoformat(),
        "articles": articles,
        "pending_tasks": pending_tasks or {},
        "status": "complete" if not pending_tasks or not any(pending_tasks.values()) else "partial"
    }
    
    if _use_azure_storage:
        # Save to Azure Blob Storage
        blob_name = f"countries/{country_code}.json"
        if _save_to_blob(blob_name, data):
            logger.info(f"Saved {len(articles)} articles for {country_name} to Azure Blob: {blob_name}")
        else:
            logger.error(f"Failed to save country data for {country_code} to Azure Blob")
    else:
        # Save to local file
        ensure_directories()
        country_file = COUNTRIES_DIR / f"{country_code}.json"
        
        try:
            with open(country_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved {len(articles)} articles for {country_name} to {country_file}")
        except Exception as e:
            logger.error(f"Failed to save country data for {country_code}: {e}")


def load_country_data(country_code: str) -> Dict[str, Any]:
    """
    Load classified articles for a country from JSON file or Azure Blob.
    
    Args:
        country_code: ISO3 country code
        
    Returns:
        dict: Country data with articles, or None if not found
    """
    if _use_azure_storage:
        # Load from Azure Blob Storage
        blob_name = f"countries/{country_code}.json"
        data = _load_from_blob(blob_name)
        
        if data:
            logger.debug(f"Loaded {data.get('total_articles', 0)} articles for {country_code} from Azure Blob")
        else:
            logger.warning(f"Country blob not found: {blob_name}")
        
        return data
    else:
        # Load from local file
        country_file = COUNTRIES_DIR / f"{country_code}.json"
        
        if not country_file.exists():
            logger.warning(f"Country file not found: {country_file}")
            return None
        
        try:
            with open(country_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            logger.debug(f"Loaded {data.get('total_articles', 0)} articles for {country_code}")
            return data
        except Exception as e:
            logger.error(f"Failed to load country data for {country_code}: {e}")
            return None


def save_summary(summary_data: Dict[str, Any]):
    """
    Save global summary of all countries and classifications.
    
    Args:
        summary_data: Dict with total counts and country statistics
    """
    summary_data["last_updated"] = datetime.utcnow().isoformat()
    
    if _use_azure_storage:
        # Save to Azure Blob Storage
        blob_name = "summary.json"
        if _save_to_blob(blob_name, summary_data):
            logger.info(f"Saved summary to Azure Blob: {blob_name}")
        else:
            logger.error("Failed to save summary to Azure Blob")
    else:
        # Save to local file
        ensure_directories()
        
        try:
            with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
                json.dump(summary_data, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved summary to {SUMMARY_FILE}")
        except Exception as e:
            logger.error(f"Failed to save summary: {e}")


def load_summary() -> Dict[str, Any]:
    """
    Load global summary.
    
    Returns:
        dict: Summary data or empty dict if not found
    """
    if _use_azure_storage:
        # Load from Azure Blob Storage
        blob_name = "summary.json"
        data = _load_from_blob(blob_name)
        
        if not data:
            logger.debug("Summary blob not found")
            return {}
        
        return data
    else:
        # Load from local file
        if not SUMMARY_FILE.exists():
            logger.debug("Summary file not found")
            return {}
        
        try:
            with open(SUMMARY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data
        except Exception as e:
            logger.error(f"Failed to load summary: {e}")
            return {}


def save_scan_status(status: str, progress: Dict[str, Any], error: str = None):
    """
    Save current scan status for monitoring.
    
    Args:
        status: One of: "idle", "running", "completed", "error", "paused"
        progress: Dict with current_country, countries_completed, total_countries, etc.
        error: Error message if status is "error"
    """
    # Add instance ID to track which instance is running the scan
    instance_id = os.getenv("WEBSITE_INSTANCE_ID", "local")
    
    status_data = {
        "status": status,
        "progress": progress,
        "error": error,
        "instance_id": instance_id,
        "last_updated": datetime.utcnow().isoformat()
    }
    
    if _use_azure_storage:
        # Save to Azure Blob Storage
        blob_name = "scan_status.json"
        if _save_to_blob(blob_name, status_data):
            logger.debug(f"Updated scan status in Azure Blob: {status} (instance: {instance_id})")
        else:
            logger.error("Failed to save scan status to Azure Blob")
    else:
        # Save to local file
        ensure_directories()
        
        try:
            with open(STATUS_FILE, "w", encoding="utf-8") as f:
                json.dump(status_data, f, indent=2, ensure_ascii=False)
            logger.debug(f"Updated scan status: {status}")
        except Exception as e:
            logger.error(f"Failed to save scan status: {e}")


def acquire_scan_lock() -> bool:
    """
    Acquire distributed lock for scan status (Azure only).
    This prevents multiple instances from running scans simultaneously.
    
    Returns:
        bool: True if lock acquired, False otherwise
    """
    global _scan_lock_lease
    
    if not _use_azure_storage:
        # Local environment - no locking needed
        return True
    
    try:
        blob_service_client = _get_blob_service_client()
        if not blob_service_client:
            logger.warning("Cannot acquire lock - blob service unavailable")
            return False
        
        blob_name = "scan_status.json"
        blob_client = blob_service_client.get_blob_client(
            container=Settings.AZURE_STORAGE_CONTAINER,
            blob=blob_name
        )
        
        # Ensure blob exists
        if not blob_client.exists():
            # Create initial status blob
            initial_status = {
                "status": "idle",
                "progress": {},
                "error": None,
                "instance_id": None,
                "last_updated": datetime.utcnow().isoformat()
            }
            blob_client.upload_blob(
                json.dumps(initial_status),
                overwrite=True,
                content_settings=ContentSettings(content_type='application/json')
            )
        
        # Try to acquire lease (60 second lease, auto-renewed during scan)
        lease_client = blob_client.get_blob_lease_client()
        try:
            _scan_lock_lease = lease_client.acquire(lease_duration=60)
            instance_id = os.getenv("WEBSITE_INSTANCE_ID", "local")
            logger.info(f"✅ Acquired distributed scan lock (instance: {instance_id})")
            return True
        except Exception as lease_error:
            # If lease already exists, try to break it if it's been too long
            error_msg = str(lease_error).lower()
            if "already" in error_msg or "lease" in error_msg:
                logger.warning(f"⚠️  Lock already held. Checking if stale...")
                
                # Check status to see if scan is actually running
                status_data = _load_from_blob(blob_name)
                if status_data:
                    current_status = status_data.get("status")
                    last_updated = status_data.get("last_updated")
                    
                    # If status is "error", always break the lock (it's a failed attempt)
                    if current_status == "error":
                        logger.warning(f"⚠️  Lock held with error status. Breaking lease to allow retry...")
                        try:
                            lease_client.break_lease(lease_break_period=0)
                            time.sleep(2)  # Wait for lease to break
                            # Try again
                            _scan_lock_lease = lease_client.acquire(lease_duration=60)
                            instance_id = os.getenv("WEBSITE_INSTANCE_ID", "local")
                            logger.info(f"✅ Acquired distributed scan lock after breaking error lock (instance: {instance_id})")
                            return True
                        except Exception as break_error:
                            logger.error(f"Failed to break error lock: {break_error}")
                            return False
                    
                    # For "running" status, check if stale
                    if last_updated:
                        from datetime import datetime, timezone
                        last_update_time = datetime.fromisoformat(last_updated.replace('Z', '+00:00'))
                        now = datetime.now(timezone.utc)
                        age_seconds = (now - last_update_time.replace(tzinfo=timezone.utc)).total_seconds()
                        
                        # If status hasn't been updated in 2 hours, consider it stale
                        if age_seconds > 7200:
                            logger.warning(f"⚠️  Lock is stale (last updated {age_seconds/3600:.1f} hours ago). Breaking lease...")
                            try:
                                lease_client.break_lease(lease_break_period=0)
                                time.sleep(2)  # Wait for lease to break
                                # Try again
                                _scan_lock_lease = lease_client.acquire(lease_duration=60)
                                instance_id = os.getenv("WEBSITE_INSTANCE_ID", "local")
                                logger.info(f"✅ Acquired distributed scan lock after breaking stale lease (instance: {instance_id})")
                                return True
                            except Exception as break_error:
                                logger.error(f"Failed to break stale lease: {break_error}")
                                return False
                
                logger.error(f"Cannot acquire lock - another scan is actively running")
                return False
            else:
                raise
        
    except Exception as e:
        logger.warning(f"Failed to acquire scan lock: {e}")
        _scan_lock_lease = None
        return False


def force_break_lock() -> tuple[bool, str]:
    """
    Force break the distributed lock (emergency use only).
    Use this when a lock is stuck and blocking all scans.
    
    Returns:
        tuple: (success: bool, message: str)
    """
    if not _use_azure_storage:
        return True, "Local environment - no lock to break"
    
    try:
        blob_service_client = _get_blob_service_client()
        if not blob_service_client:
            return False, "Blob service unavailable"
        
        blob_name = "scan_status.json"
        blob_client = blob_service_client.get_blob_client(
            container=Settings.AZURE_STORAGE_CONTAINER,
            blob=blob_name
        )
        
        if not blob_client.exists():
            return False, "Lock blob does not exist"
        
        # Try to break the lease
        lease_client = blob_client.get_blob_lease_client()
        try:
            lease_client.break_lease(lease_break_period=0)
            logger.info("🔨 Force broke distributed scan lock")
            
            # Reset status to idle
            save_scan_status("idle", {}, error=None)
            
            return True, "Lock broken successfully. Status reset to idle."
        except Exception as e:
            error_msg = str(e).lower()
            if "no lease" in error_msg or "not leased" in error_msg:
                return True, "No active lease found - lock is already free"
            else:
                return False, f"Failed to break lease: {str(e)}"
        
    except Exception as e:
        logger.error(f"Error breaking lock: {e}")
        return False, f"Error: {str(e)}"


def release_scan_lock():
    """
    Release distributed lock for scan status (Azure only).
    """
    global _scan_lock_lease
    
    if not _use_azure_storage or not _scan_lock_lease:
        return
    
    try:
        blob_service_client = _get_blob_service_client()
        if not blob_service_client:
            return
        
        blob_name = "scan_status.json"
        blob_client = blob_service_client.get_blob_client(
            container=Settings.AZURE_STORAGE_CONTAINER,
            blob=blob_name
        )
        
        lease_client = blob_client.get_blob_lease_client(_scan_lock_lease)
        lease_client.release()
        
        instance_id = os.getenv("WEBSITE_INSTANCE_ID", "local")
        logger.info(f"🔓 Released distributed scan lock (instance: {instance_id})")
        _scan_lock_lease = None
        
    except Exception as e:
        logger.warning(f"Failed to release scan lock: {e}")
        _scan_lock_lease = None


def renew_scan_lock():
    """
    Renew distributed lock lease (should be called periodically during long scans).
    """
    global _scan_lock_lease
    
    if not _use_azure_storage or not _scan_lock_lease:
        return True
    
    try:
        blob_service_client = _get_blob_service_client()
        if not blob_service_client:
            return False
        
        blob_name = "scan_status.json"
        blob_client = blob_service_client.get_blob_client(
            container=Settings.AZURE_STORAGE_CONTAINER,
            blob=blob_name
        )
        
        lease_client = blob_client.get_blob_lease_client(_scan_lock_lease)
        lease_client.renew()
        
        logger.debug("Renewed distributed scan lock")
        return True
        
    except Exception as e:
        logger.warning(f"Failed to renew scan lock: {e}")
        return False


def load_scan_status() -> Dict[str, Any]:
    """
    Load current scan status.
    
    Returns:
        dict: Status data with "status", "progress", "error", "last_updated"
    """
    default_status = {
        "status": "idle",
        "progress": {},
        "error": None,
        "last_updated": None
    }
    
    if _use_azure_storage:
        # Load from Azure Blob Storage
        blob_name = "scan_status.json"
        data = _load_from_blob(blob_name)
        
        if not data:
            return default_status
        
        return data
    else:
        # Load from local file
        if not STATUS_FILE.exists():
            return default_status
        
        try:
            with open(STATUS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data
        except Exception as e:
            logger.error(f"Failed to load scan status: {e}")
            return {
                "status": "error",
                "progress": {},
                "error": str(e),
                "last_updated": datetime.utcnow().isoformat()
            }


def get_all_countries() -> List[str]:
    """
    Get list of all country codes that have been processed.
    
    Returns:
        list: Country codes (ISO3)
    """
    if _use_azure_storage:
        # List blobs from Azure Blob Storage
        blob_names = _list_blobs_with_prefix("countries/")
        
        # Extract country codes from blob names (e.g., "countries/USA.json" -> "USA")
        country_codes = []
        for blob_name in blob_names:
            if blob_name.endswith(".json"):
                # Extract filename without path and extension
                country_code = blob_name.split("/")[-1].replace(".json", "")
                country_codes.append(country_code)
        
        return sorted(country_codes)
    else:
        # List files from local storage
        if not COUNTRIES_DIR.exists():
            return []
        
        country_files = list(COUNTRIES_DIR.glob("*.json"))
        country_codes = [f.stem for f in country_files]
        
        return sorted(country_codes)


def calculate_summary():
    """
    Calculate summary statistics from all country files.
    
    Returns:
        dict: Summary with total counts and per-country breakdown
    """
    country_codes = get_all_countries()
    
    total_articles = 0
    total_accelerator_lab = 0
    total_country_office = 0
    
    countries = []
    
    for code in country_codes:
        data = load_country_data(code)
        if data:
            total_articles += data.get("total_articles", 0)
            total_accelerator_lab += data.get("accelerator_lab_count", 0)
            total_country_office += data.get("country_office_count", 0)
            
            countries.append({
                "country_code": code,
                "country_name": data.get("country_name", code),
                "total_articles": data.get("total_articles", 0),
                "accelerator_lab_count": data.get("accelerator_lab_count", 0),
                "country_office_count": data.get("country_office_count", 0)
            })
    
    summary = {
        "total_countries": len(country_codes),
        "total_articles": total_articles,
        "total_accelerator_lab": total_accelerator_lab,
        "total_country_office": total_country_office,
        "countries": countries
    }
    
    return summary


def clear_all_data():
    """
    Clear all processed country data and summary.
    Use this to start a completely fresh scan.
    
    WARNING: This will delete all processed data!
    """
    if _use_azure_storage:
        # Clear Azure Blob Storage
        try:
            blob_service_client = _get_blob_service_client()
            if blob_service_client:
                container_client = blob_service_client.get_container_client(Settings.AZURE_STORAGE_CONTAINER)
                
                # Delete all blobs
                blob_list = container_client.list_blobs()
                for blob in blob_list:
                    container_client.delete_blob(blob.name)
                    logger.info(f"Deleted blob: {blob.name}")
                
                logger.info("✅ Cleared all data from Azure Blob Storage")
        except Exception as e:
            logger.error(f"Failed to clear Azure Blob Storage: {e}")
    else:
        # Clear local files
        try:
            if COUNTRIES_DIR.exists():
                for file in COUNTRIES_DIR.glob("*.json"):
                    file.unlink()
                    logger.debug(f"Deleted: {file}")
            
            if SUMMARY_FILE.exists():
                SUMMARY_FILE.unlink()
            
            if STATUS_FILE.exists():
                STATUS_FILE.unlink()
            
            logger.info("✅ Cleared all local data files")
        except Exception as e:
            logger.error(f"Failed to clear local files: {e}")


def delete_country_data(country_code: str):
    """
    Delete data for a specific country to allow re-processing.
    
    Args:
        country_code: ISO3 country code to delete
    """
    if _use_azure_storage:
        # Delete from Azure Blob Storage
        try:
            blob_service_client = _get_blob_service_client()
            if blob_service_client:
                blob_client = blob_service_client.get_blob_client(
                    container=Settings.AZURE_STORAGE_CONTAINER,
                    blob=f"countries/{country_code}.json"
                )
                blob_client.delete_blob()
                logger.info(f"Deleted country data from Azure Blob: {country_code}")
        except Exception as e:
            logger.error(f"Failed to delete country data from Azure Blob {country_code}: {e}")
    else:
        # Delete from local file
        try:
            country_file = COUNTRIES_DIR / f"{country_code}.json"
            if country_file.exists():
                country_file.unlink()
                logger.info(f"Deleted country data: {country_code}")
            else:
                logger.warning(f"Country data not found: {country_code}")
        except Exception as e:
            logger.error(f"Failed to delete country data {country_code}: {e}")
