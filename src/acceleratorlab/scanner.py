"""Main scanner orchestration for AcceleratorLab analysis"""

import logging
import threading
import time
from datetime import datetime
from typing import Dict, Any, List

from bs4 import BeautifulSoup
from src.scraper import setup_selenium, cleanup_selenium, safe_get
from .country_discovery import discover_countries
from .pagination_handler import handle_pagination
from .content_analyzer import analyze_content, classify_article, is_after_2019
from .file_storage import (
    save_country_data,
    save_summary,
    save_scan_status,
    load_scan_status,
    calculate_summary
)

logger = logging.getLogger(__name__)

# Global scanner state
_scanner_thread = None
_scanner_lock = threading.Lock()
_pause_requested = False


class ScanPausedException(Exception):
    """Exception raised when scan is paused by user"""
    pass


def check_if_paused():
    """Check if pause was requested and raise exception if so"""
    global _pause_requested
    if _pause_requested:
        raise ScanPausedException("Scan paused by user")


def scan_country_blogs(driver, country_url: str, country_code: str, country_name: str, max_articles=200, timeout_per_article=30) -> List[Dict[str, Any]]:
    """
    Scan all blogs for a country and classify them.
    
    Args:
        driver: Selenium WebDriver instance
        country_url: Country office homepage URL
        country_code: ISO3 country code
        country_name: Country name
        max_articles: Maximum number of articles to process per country (default 200)
        timeout_per_article: Maximum seconds to spend on each article (default 30)
        
    Returns:
        list: Classified articles with metadata
    """
    logger.info(f"Scanning blogs for {country_name} ({country_code})")
    
    results = []
    articles_processed = 0
    scan_start_time = time.time()
    
    # Only scan /blogs page (exclude /news and /stories)
    blogs_patterns = [
        f"{country_url}/blogs",
        f"{country_url}/blog"
    ]
    
    for blogs_url in blogs_patterns:
        try:
            driver.get(blogs_url)
            time.sleep(2)
            
            # Check if page exists (not 404)
            if "404" not in driver.title.lower() and "not found" not in driver.page_source.lower():
                logger.info(f"Found blogs page: {blogs_url}")
                
                # Get all article URLs across all pages
                article_urls = handle_pagination(driver, blogs_url)
                logger.info(f"Found {len(article_urls)} blog articles for {country_name}")
                
                # Analyze each article
                for url in article_urls:
                    # Check if pause was requested
                    check_if_paused()
                    
                    # Safety check: limit number of articles processed
                    if articles_processed >= max_articles:
                        logger.warning(f"Reached max article limit ({max_articles}) for {country_name} blogs, skipping remaining articles")
                        break
                    
                    # Safety check: timeout protection
                    if time.time() - scan_start_time > 86400:  # 24 hours max per country section
                        logger.error(f"Timeout: Blog scanning for {country_name} exceeded 24 hours, stopping")
                        break
                    
                    article_start_time = time.time()
                    try:
                        driver.get(url)
                        time.sleep(1)
                        
                        # Parse HTML
                        soup = BeautifulSoup(driver.page_source, 'html.parser')
                        
                        # Extract content and metadata (no PDF extraction for blogs)
                        content_data = analyze_content(soup, url, extract_pdfs=False)
                        
                        if not content_data:
                            logger.warning(f"No content extracted from {url}")
                            continue
                        
                        # Classify article first (to determine if AcceleratorLab content)
                        classification = classify_article(content_data)
                        
                        # Check date filter (can only check after visiting article page)
                        if content_data.get("date"):
                            from datetime import datetime as dt
                            try:
                                date_obj = dt.fromisoformat(content_data["date"])
                                if not is_after_2019(date_obj):
                                    logger.debug(f"Skipping article from {content_data['date']}: {url}")
                                    continue
                            except:
                                pass  # Include if date parsing fails
                        else:
                            # No date found - only include if it's AcceleratorLab content
                            if classification != "accelerator_lab":
                                logger.debug(f"Skipping undated non-AcceleratorLab article: {url}")
                                continue
                            else:
                                logger.info(f"Including undated AcceleratorLab article: {url}")
                        
                        # Build result
                        article_data = {
                            "url": url,
                            "title": content_data.get("title", ""),
                            "author": content_data.get("author", ""),
                            "date": content_data.get("date", ""),
                            "classification": classification,
                            "content_preview": content_data.get("text", "")[:200],
                            "analyzed_at": datetime.utcnow().isoformat()
                        }
                        
                        results.append(article_data)
                        logger.debug(f"Classified as {classification}: {article_data['title'][:50]}")
                        
                    except Exception as e:
                        article_time = time.time() - article_start_time
                        if article_time > timeout_per_article:
                            logger.error(f"Timeout: Article {url} took {article_time:.1f}s (limit: {timeout_per_article}s)")
                        else:
                            logger.error(f"Error analyzing article {url}: {e}")
                        continue
                    finally:
                        articles_processed += 1
                
                # Found and processed blogs, stop trying other patterns
                break
                
        except Exception as e:
            logger.warning(f"Could not access {blogs_url}: {e}")
            continue
    
    return results


def scan_country_publications(driver, country_url: str, country_code: str, country_name: str, max_articles=200, timeout_per_article=30) -> List[Dict[str, Any]]:
    """
    Scan all publications for a country and classify them.
    
    Args:
        driver: Selenium WebDriver instance
        country_url: Country office homepage URL
        country_code: ISO3 country code
        country_name: Country name
        max_articles: Maximum number of articles to process per country (default 200)
        timeout_per_article: Maximum seconds to spend on each article (default 30)
        
    Returns:
        list: Classified publications with metadata
    """
    logger.info(f"Scanning publications for {country_name} ({country_code})")
    
    results = []
    articles_processed = 0
    scan_start_time = time.time()
    
    # Only scan /publications page
    pubs_patterns = [
        f"{country_url}/publications"
    ]
    
    for pubs_url in pubs_patterns:
        try:
            driver.get(pubs_url)
            time.sleep(2)
            
            # Check if page exists
            if "404" not in driver.title.lower() and "not found" not in driver.page_source.lower():
                logger.info(f"Found publications page: {pubs_url}")
                
                # Get all publication URLs
                article_urls = handle_pagination(driver, pubs_url)
                logger.info(f"Found {len(article_urls)} publications for {country_name}")
                
                # Analyze each publication (extract PDFs and analyze content)
                for url in article_urls:
                    # Check if pause was requested
                    check_if_paused()
                    
                    # Safety check: limit number of articles processed
                    if articles_processed >= max_articles:
                        logger.warning(f"Reached max article limit ({max_articles}) for {country_name} publications, skipping remaining articles")
                        break
                    
                    # Safety check: timeout protection
                    if time.time() - scan_start_time > 86400:  # 24 hours max per country section
                        logger.error(f"Timeout: Publication scanning for {country_name} exceeded 24 hours, stopping")
                        break
                    
                    article_start_time = time.time()
                    try:
                        driver.get(url)
                        time.sleep(1)
                        
                        # Parse HTML
                        soup = BeautifulSoup(driver.page_source, 'html.parser')
                        
                        # Extract PDF content for publications (extract_pdfs=True by default)
                        content_data = analyze_content(soup, url, extract_pdfs=True)
                        
                        if not content_data:
                            continue
                        
                        # Classify first (checks PDF content + HTML content)
                        classification = classify_article(content_data)
                        
                        # Date filter (can only check after visiting article page)
                        if content_data.get("date"):
                            from datetime import datetime as dt
                            try:
                                date_obj = dt.fromisoformat(content_data["date"])
                                if not is_after_2019(date_obj):
                                    logger.info(f"Skipping publication from {content_data['date']}: {url}")
                                    continue
                            except:
                                pass  # Include if date parsing fails
                        else:
                            # No date found - only include if it's AcceleratorLab content
                            if classification != "accelerator_lab":
                                logger.debug(f"Skipping undated non-AcceleratorLab publication: {url}")
                                continue
                            else:
                                logger.info(f"Including undated AcceleratorLab publication: {url}")
                        
                        article_data = {
                            "url": url,
                            "title": content_data.get("title", ""),
                            "author": content_data.get("author", ""),
                            "date": content_data.get("date", ""),
                            "classification": classification,
                            "content_preview": content_data.get("text", "")[:200],
                            "pdf_urls": content_data.get("pdf_urls", []),
                            "is_publication": content_data.get("is_publication", True),
                            "analyzed_at": datetime.utcnow().isoformat()
                        }
                        
                        results.append(article_data)
                        logger.info(f"Classified publication as {classification}: {article_data['title']}")
                        
                    except Exception as e:
                        article_time = time.time() - article_start_time
                        if article_time > timeout_per_article:
                            logger.error(f"Timeout: Publication {url} took {article_time:.1f}s (limit: {timeout_per_article}s)")
                        else:
                            logger.error(f"Error analyzing publication {url}: {e}")
                        continue
                    finally:
                        articles_processed += 1
                
                break
                
        except Exception as e:
            logger.warning(f"Could not access {pubs_url}: {e}")
            continue
    
    return results


def scan_single_country(country_name: str) -> Dict[str, Any]:
    """
    Scan a specific country by name.
    
    Args:
        country_name: Name of the country to scan (e.g., "Albania", "Nigeria")
        
    Returns:
        dict: Result with success status, message, and article counts
    """
    global _pause_requested
    _pause_requested = False  # Reset pause flag
    
    logger.info(f"Starting single country scan for: {country_name}")
    
    try:
        # Setup Selenium
        setup_selenium()
        from src.scraper.selenium_driver import driver
        
        # Discover all countries to find the requested one
        logger.info("Discovering UNDP countries to find target...")
        countries = discover_countries()
        
        # Find the country (case-insensitive search)
        target_country = None
        country_name_lower = country_name.lower()
        
        for country in countries:
            if country["name"].lower() == country_name_lower:
                target_country = country
                break
        
        if not target_country:
            # Try partial match
            for country in countries:
                if country_name_lower in country["name"].lower():
                    target_country = country
                    logger.info(f"Found partial match: {country['name']}")
                    break
        
        if not target_country:
            error_msg = f"Country '{country_name}' not found. Please check the country name."
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "available_countries": [c["name"] for c in countries[:10]]  # Show first 10 as examples
            }
        
        country_name = target_country["name"]
        country_slug = target_country.get("slug", country_name.lower().replace(" ", "-"))
        country_url = target_country["url"]
        
        # Get ISO3 country code
        from src.utils.geocoding import get_country_info
        country_iso3, _, _ = get_country_info(country_name)
        if not country_iso3:
            country_iso3 = country_slug.upper().replace("-", "")[:3]
            logger.warning(f"Could not find ISO3 for {country_name}, using fallback: {country_iso3}")
        
        logger.info(f"Scanning {country_name} ({country_iso3})")
        logger.info(f"Country URL: {country_url}")
        
        # Update status
        save_scan_status("running", {
            "current_country": country_name,
            "current_country_code": country_iso3,
            "countries_completed": 0,
            "total_countries": 1,
            "countries_remaining": 0,
            "single_country_mode": True,
            "start_time": datetime.utcnow().isoformat(),
            "last_heartbeat": datetime.utcnow().isoformat()
        })
        
        scan_start = time.time()
        
        try:
            # Scan blogs
            blogs = scan_country_blogs(driver, country_url, country_slug, country_name, max_articles=200, timeout_per_article=30)
            
            # Scan publications
            publications = scan_country_publications(driver, country_url, country_slug, country_name, max_articles=200, timeout_per_article=30)
            
            # Combine results
            all_articles = blogs + publications
            
            # Save country data
            save_country_data(country_iso3, country_name, all_articles)
            
            scan_duration = time.time() - scan_start
            
            logger.info(f"✅ Successfully scanned {country_name}: {len(all_articles)} articles ({len(blogs)} blogs, {len(publications)} publications) in {scan_duration:.1f}s")
            
            # Count classifications
            accel_count = sum(1 for a in all_articles if a.get("classification") == "accelerator_lab")
            country_office_count = sum(1 for a in all_articles if a.get("classification") == "country_office")
            
            # Update summary
            summary = calculate_summary()
            save_summary(summary)
            
            # Update status to completed
            save_scan_status("completed", {
                "current_country": None,
                "countries_completed": 1,
                "total_countries": 1,
                "single_country_mode": True,
                "start_time": datetime.utcnow().isoformat(),
                "end_time": datetime.utcnow().isoformat()
            })
            
            return {
                "success": True,
                "country": country_name,
                "country_code": country_iso3,
                "total_articles": len(all_articles),
                "blogs": len(blogs),
                "publications": len(publications),
                "accelerator_lab_count": accel_count,
                "country_office_count": country_office_count,
                "duration_seconds": round(scan_duration, 2)
            }
            
        except ScanPausedException:
            logger.info(f"⏸️  Scan paused by user for {country_name}")
            save_scan_status("paused", {
                "current_country": country_name,
                "single_country_mode": True,
                "paused_at": datetime.utcnow().isoformat()
            })
            return {
                "success": False,
                "error": "Scan was paused by user",
                "country": country_name
            }
        except Exception as e:
            logger.error(f"Error scanning {country_name}: {e}", exc_info=True)
            save_scan_status("error", {}, error=str(e))
            return {
                "success": False,
                "error": str(e),
                "country": country_name
            }
        
    except Exception as e:
        logger.error(f"Failed to scan single country: {e}", exc_info=True)
        save_scan_status("error", {}, error=str(e))
        return {
            "success": False,
            "error": str(e)
        }
    finally:
        cleanup_selenium()


def run_full_scan():
    """
    Run complete AcceleratorLab scan across all UNDP countries.
    Supports resuming from last processed country if scan was interrupted.
    This is the main entry point for the scanning process.
    """
    global _pause_requested
    _pause_requested = False  # Reset pause flag at start
    
    logger.info("Starting AcceleratorLab full scan")
    
    try:
        # Check if there's a previous scan to resume
        from .file_storage import get_all_countries
        processed_countries = set(get_all_countries())
        
        # Setup Selenium
        setup_selenium()
        from src.scraper.selenium_driver import driver
        
        # Discover all countries
        logger.info("Discovering UNDP countries...")
        countries = discover_countries()
        total_countries = len(countries)
        
        # Filter out already processed countries for resume capability
        countries_to_process = []
        skipped_count = 0
        
        from src.utils.geocoding import get_country_info
        
        for country in countries:
            country_name = country["name"]
            # Get ISO3 code to check if already processed
            country_iso3, _, _ = get_country_info(country_name)
            if not country_iso3:
                country_slug = country.get("slug", country_name.lower().replace(" ", "-"))
                country_iso3 = country_slug.upper().replace("-", "")[:3]
            
            if country_iso3 in processed_countries:
                skipped_count += 1
                logger.debug(f"Skipping already processed country: {country_name} ({country_iso3})")
            else:
                countries_to_process.append(country)
        
        if skipped_count > 0:
            logger.info(f"📋 Resuming scan: {skipped_count} countries already processed, {len(countries_to_process)} remaining")
        else:
            logger.info(f"🆕 Starting fresh scan: {total_countries} countries to process")
        
        # Update status with resume info
        save_scan_status("running", {
            "current_country": None,
            "countries_completed": skipped_count,
            "total_countries": total_countries,
            "countries_remaining": len(countries_to_process),
            "resumed": skipped_count > 0,
            "start_time": datetime.utcnow().isoformat()
        })
        
        # Process each country (only unprocessed ones)
        for idx, country in enumerate(countries_to_process, 1):
            try:
                # Check if pause was requested
                check_if_paused()
                
                country_name = country["name"]
                country_slug = country.get("slug", country_name.lower().replace(" ", "-"))
                country_url = country["url"]
                
                # Get ISO3 country code for proper storage
                from src.utils.geocoding import get_country_info
                country_iso3, _, _ = get_country_info(country_name)
                if not country_iso3:
                    # Fallback to uppercase slug if ISO3 not found
                    country_iso3 = country_slug.upper().replace("-", "")[:3]
                    logger.warning(f"Could not find ISO3 for {country_name}, using fallback: {country_iso3}")
                
                current_completed = skipped_count + idx - 1
                logger.info(f"Processing ({current_completed + 1}/{total_countries}): {country_name} ({country_iso3})")
                logger.info(f"📊 Progress: {current_completed}/{total_countries} countries, {len(countries_to_process) - idx} remaining")
                
                # Update status with accurate progress
                save_scan_status("running", {
                    "current_country": country_name,
                    "current_country_code": country_iso3,
                    "countries_completed": current_completed,
                    "total_countries": total_countries,
                    "countries_remaining": len(countries_to_process) - idx,
                    "resumed": skipped_count > 0,
                    "start_time": datetime.utcnow().isoformat(),
                    "last_heartbeat": datetime.utcnow().isoformat()
                })
                
                country_start_time = time.time()
                try:
                    # Scan blogs (with timeout and limits)
                    blogs = scan_country_blogs(driver, country_url, country_slug, country_name, max_articles=200, timeout_per_article=30)
                    
                    # Check if we've spent too long on this country
                    country_elapsed = time.time() - country_start_time
                    if country_elapsed > 172800:  # 48 hours max per country total (24h blogs + 24h publications)
                        logger.error(f"CRITICAL TIMEOUT: {country_name} took {country_elapsed/3600:.1f} hours, skipping publications")
                        publications = []
                    else:
                        # Scan publications (with timeout and limits)
                        publications = scan_country_publications(driver, country_url, country_slug, country_name, max_articles=200, timeout_per_article=30)
                    
                    # Combine results
                    all_articles = blogs + publications
                    
                    # Save country data using ISO3 code (even if empty, to mark as processed)
                    save_country_data(country_iso3, country_name, all_articles)
                    if all_articles:
                        logger.info(f"Saved {len(all_articles)} articles for {country_name} ({country_iso3})")
                    else:
                        logger.warning(f"No articles found for {country_name} ({country_iso3})")
                    
                except ScanPausedException:
                    # Re-raise to be caught by outer handler
                    raise
                except Exception as e:
                    logger.error(f"Error processing {country_name}: {e}")
                    logger.error(f"Error details: {type(e).__name__}: {str(e)}", exc_info=True)
                    # Save empty data to mark country as attempted (using ISO3 code)
                    try:
                        save_country_data(country_iso3, country_name, [])
                        logger.info(f"Marked {country_name} as processed despite error")
                    except Exception as save_error:
                        logger.error(f"Failed to save empty data for {country_name}: {save_error}")
                
                finally:
                    # Always update summary after each country (success or failure)
                    # This ensures dashboard shows real-time progress
                    try:
                        logger.debug(f"Updating summary after processing {country_name}")
                        summary = calculate_summary()
                        save_summary(summary)
                    except Exception as summary_error:
                        logger.warning(f"Failed to update summary: {summary_error}")
            
            except ScanPausedException:
                # Pause was requested - save state and exit
                current_completed = skipped_count + idx - 1
                logger.info(f"⏸️  Scan paused by user at {current_completed}/{total_countries} countries")
                save_scan_status("paused", {
                    "current_country": None,
                    "countries_completed": current_completed,
                    "total_countries": total_countries,
                    "countries_remaining": len(countries_to_process) - idx + 1,
                    "resumed": skipped_count > 0,
                    "paused_at": datetime.utcnow().isoformat()
                })
                return  # Exit the scan
        
        # Calculate and save summary
        logger.info("Calculating summary statistics...")
        summary = calculate_summary()
        save_summary(summary)
        
        # Update final status
        save_scan_status("completed", {
            "current_country": None,
            "countries_completed": total_countries,
            "total_countries": total_countries,
            "start_time": datetime.utcnow().isoformat(),
            "end_time": datetime.utcnow().isoformat()
        })
        
        logger.info("AcceleratorLab scan completed successfully")
        
    except Exception as e:
        logger.error(f"Error during full scan: {e}", exc_info=True)
        save_scan_status("error", {}, error=str(e))
        
    finally:
        cleanup_selenium()


def start_scan_async():
    """
    Start the scan in a background thread.
    
    Returns:
        tuple: (success: bool, message: str)
    """
    global _scanner_thread
    
    with _scanner_lock:
        # Check if scan is already running
        status = load_scan_status()
        if status.get("status") == "running":
            return False, "A scan is already in progress"
        
        # Check if regular scraper is running (prevent concurrent browser usage)
        try:
            from src.scheduler import get_scraping_status
            scraper_status = get_scraping_status()
            if scraper_status.get("currently_running", False):
                return False, "Regular scraper is currently running. Please wait for it to complete."
        except Exception as e:
            logger.warning(f"Could not check regular scraper status: {e}")
        
        # Start new scan thread
        _scanner_thread = threading.Thread(target=run_full_scan, daemon=True)
        _scanner_thread.start()
        
        logger.info("Started AcceleratorLab scan in background thread")
        return True, "Scan started successfully"


def start_single_country_scan_async(country_name: str):
    """
    Start a single country scan in a background thread.
    
    Args:
        country_name: Name of the country to scan
        
    Returns:
        tuple: (success: bool, message: str or dict)
    """
    global _scanner_thread
    
    with _scanner_lock:
        # Check if scan is already running
        status = load_scan_status()
        if status.get("status") == "running":
            return False, "A scan is already in progress"
        
        # Check if regular scraper is running
        try:
            from src.scheduler import get_scraping_status
            scraper_status = get_scraping_status()
            if scraper_status.get("currently_running", False):
                return False, "Regular scraper is currently running. Please wait for it to complete."
        except Exception as e:
            logger.warning(f"Could not check regular scraper status: {e}")
        
        # Start scan in background thread
        def run_scan():
            result = scan_single_country(country_name)
            # Store result in status for retrieval
            logger.info(f"Single country scan completed: {result}")
        
        _scanner_thread = threading.Thread(target=run_scan, daemon=True)
        _scanner_thread.start()
        
        logger.info(f"Started single country scan for {country_name} in background thread")
        return True, f"Scan started for {country_name}"


def get_scan_status() -> Dict[str, Any]:
    """
    Get current scan status.
    
    Returns:
        dict: Status information with progress details
    """
    return load_scan_status()


def pause_scan() -> tuple[bool, str]:
    """
    Request to pause the currently running scan.
    
    Returns:
        tuple: (success: bool, message: str)
    """
    global _pause_requested
    
    with _scanner_lock:
        status = load_scan_status()
        current_status = status.get("status")
        
        if current_status != "running":
            return False, f"Cannot pause: scan is not running (current status: {current_status})"
        
        # Set pause flag
        _pause_requested = True
        logger.info("⏸️  Pause requested - scan will stop immediately after current article")
        
        return True, "Pause requested - scan will stop immediately after current article completes"


def auto_resume_scan_if_needed():
    """
    Check if a scan was interrupted and automatically resume it.
    Called on server startup.
    """
    try:
        status = load_scan_status()
        
        # Check if scan was running when server stopped
        if status.get("status") == "running":
            logger.info("🔄 Detected interrupted scan - auto-resuming...")
            
            # Reset status to idle first (prevents "scan already running" error)
            save_scan_status("idle", {})
            
            # Start the scan (will automatically resume from where it left off)
            success, message = start_scan_async()
            
            if success:
                logger.info(f"✅ Auto-resume successful: {message}")
            else:
                logger.warning(f"⚠️  Auto-resume failed: {message}")
        else:
            logger.debug(f"No interrupted scan detected (status: {status.get('status')})")
            
    except Exception as e:
        logger.error(f"Error during auto-resume check: {e}", exc_info=True)
