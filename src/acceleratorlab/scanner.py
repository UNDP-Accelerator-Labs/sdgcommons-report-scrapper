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


def scan_country_blogs(driver, country_url: str, country_code: str, country_name: str, max_articles=200, timeout_per_article=30, country_start_time=None) -> tuple[List[Dict[str, Any]], bool]:
    """
    Scan all blogs for a country and classify them.
    
    Args:
        driver: Selenium WebDriver instance
        country_url: Country office homepage URL
        country_code: ISO3 country code
        country_name: Country name
        max_articles: Maximum number of articles to process per country (default 200)
        timeout_per_article: Maximum seconds to spend on each article (default 30)
        country_start_time: Overall country scan start time (for 24h timeout check)
        
    Returns:
        tuple: (list of classified articles, bool indicating if timeout occurred)
    """
    logger.info(f"Scanning blogs for {country_name} ({country_code})")
    
    results = []
    articles_processed = 0
    scan_start_time = time.time()
    timeout_occurred = False
    
    # Use country-level start time if provided (for 24h overall timeout)
    overall_start = country_start_time or scan_start_time
    
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
                    
                    # Safety check: 24-hour country-level timeout protection
                    if time.time() - overall_start > 86400:  # 24 hours max per country total
                        logger.warning(f"⏱️ TIMEOUT: {country_name} has been running for 24 hours. Saving {len(results)} blogs processed so far...")
                        timeout_occurred = True
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
    
    if timeout_occurred:
        logger.warning(f"⚠️ Blog scanning incomplete for {country_name} due to timeout. Processed {len(results)} articles.")
    
    return results, timeout_occurred


def scan_country_publications(driver, country_url: str, country_code: str, country_name: str, max_articles=200, timeout_per_article=30, country_start_time=None) -> tuple[List[Dict[str, Any]], bool]:
    """
    Scan all publications for a country and classify them.
    
    Args:
        driver: Selenium WebDriver instance
        country_url: Country office homepage URL
        country_code: ISO3 country code
        country_name: Country name
        max_articles: Maximum number of articles to process per country (default 200)
        timeout_per_article: Maximum seconds to spend on each article (default 30)
        country_start_time: Overall country scan start time (for 24h timeout check)
        
    Returns:
        tuple: (list of classified publications, bool indicating if timeout occurred)
    """
    logger.info(f"Scanning publications for {country_name} ({country_code})")
    
    results = []
    articles_processed = 0
    scan_start_time = time.time()
    timeout_occurred = False
    
    # Use country-level start time if provided (for 24h overall timeout)
    overall_start = country_start_time or scan_start_time
    
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
                    
                    # Safety check: 24-hour country-level timeout protection
                    if time.time() - overall_start > 86400:  # 24 hours max per country total
                        logger.warning(f"⏱️ TIMEOUT: {country_name} has been running for 24 hours. Saving {len(results)} publications processed so far...")
                        timeout_occurred = True
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
    
    if timeout_occurred:
        logger.warning(f"⚠️ Publication scanning incomplete for {country_name} due to timeout. Processed {len(results)} articles.")
    
    return results, timeout_occurred


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
    
    # DISABLED: Distributed locking not working in Azure Web App
    # from .file_storage import acquire_scan_lock, release_scan_lock
    # 
    # if not acquire_scan_lock():
    #     logger.error("❌ Cannot start scan - another instance is already running a scan")
    #     return {
    #         "success": False,
    #         "error": "Another instance is already running a scan. Please wait for it to complete."
    #     }
    
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
            # Scan blogs (with country-level timeout tracking)
            blogs, blogs_timeout = scan_country_blogs(driver, country_url, country_slug, country_name, max_articles=200, timeout_per_article=30, country_start_time=scan_start)
            
            # Check if we hit timeout during blogs
            if blogs_timeout:
                logger.warning(f"⏱️ Timeout occurred during blog scanning for {country_name}")
                # Save what we have and mark as partial
                pending_tasks = {
                    "blogs_complete": False,
                    "publications_complete": False,
                    "timeout_at": datetime.utcnow().isoformat(),
                    "blogs_processed": len(blogs),
                    "publications_processed": 0
                }
                save_country_data(country_iso3, country_name, blogs, pending_tasks=pending_tasks)
                
                scan_duration = time.time() - scan_start
                return {
                    "success": True,
                    "country": country_name,
                    "country_code": country_iso3,
                    "total_articles": len(blogs),
                    "blogs": len(blogs),
                    "publications": 0,
                    "accelerator_lab_count": sum(1 for a in blogs if a.get("classification") == "accelerator_lab"),
                    "country_office_count": sum(1 for a in blogs if a.get("classification") == "country_office"),
                    "duration_seconds": round(scan_duration, 2),
                    "status": "partial",
                    "warning": "24-hour timeout reached. Only blogs completed. Use resume to continue."
                }
            
            # Scan publications (with country-level timeout tracking)
            publications, pubs_timeout = scan_country_publications(driver, country_url, country_slug, country_name, max_articles=200, timeout_per_article=30, country_start_time=scan_start)
            
            # Combine results
            all_articles = blogs + publications
            
            # Check if we hit timeout during publications
            if pubs_timeout:
                logger.warning(f"⏱️ Timeout occurred during publication scanning for {country_name}")
                pending_tasks = {
                    "blogs_complete": True,
                    "publications_complete": False,
                    "timeout_at": datetime.utcnow().isoformat(),
                    "blogs_processed": len(blogs),
                    "publications_processed": len(publications)
                }
                save_country_data(country_iso3, country_name, all_articles, pending_tasks=pending_tasks)
                
                scan_duration = time.time() - scan_start
                return {
                    "success": True,
                    "country": country_name,
                    "country_code": country_iso3,
                    "total_articles": len(all_articles),
                    "blogs": len(blogs),
                    "publications": len(publications),
                    "accelerator_lab_count": sum(1 for a in all_articles if a.get("classification") == "accelerator_lab"),
                    "country_office_count": sum(1 for a in all_articles if a.get("classification") == "country_office"),
                    "duration_seconds": round(scan_duration, 2),
                    "status": "partial",
                    "warning": "24-hour timeout reached. Publications incomplete. Use resume to continue."
                }
            
            # No timeout - save complete data
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
        # DISABLED: Distributed locking not working in Azure Web App
        # release_scan_lock()
        # Cleanup browser
        cleanup_selenium()


def resume_country_pending_tasks(country_code: str) -> Dict[str, Any]:
    """
    Resume pending tasks for a country that hit the 24-hour timeout.
    
    Args:
        country_code: ISO3 country code (e.g., "ALB", "NGA")
        
    Returns:
        dict: Result with success status and updated article counts
    """
    global _pause_requested
    _pause_requested = False
    
    logger.info(f"Resuming pending tasks for country: {country_code}")
    
    # DISABLED: Distributed locking not working in Azure Web App
    # from .file_storage import acquire_scan_lock, release_scan_lock, load_country_data
    from .file_storage import load_country_data
    # 
    # if not acquire_scan_lock():
    #     logger.error("❌ Cannot resume - another instance is already running a scan")
    #     return {
    #         "success": False,
    #         "error": "Another instance is already running a scan. Please wait for it to complete."
    #     }
    
    try:
        # Setup Selenium
        setup_selenium()
        from src.scraper.selenium_driver import driver
        
        # Load existing country data
        country_data = load_country_data(country_code)
        if not country_data:
            return {
                "success": False,
                "error": f"Country {country_code} not found. Run initial scan first."
            }
        
        # Check if there are pending tasks
        pending_tasks = country_data.get("pending_tasks", {})
        if not pending_tasks or country_data.get("status") == "complete":
            return {
                "success": False,
                "error": f"No pending tasks for {country_code}. Country analysis is already complete."
            }
        
        country_name = country_data["country_name"]
        existing_articles = country_data.get("articles", [])
        
        logger.info(f"Found {len(existing_articles)} existing articles for {country_name}")
        logger.info(f"Pending tasks: {pending_tasks}")
        
        # Discover country URL
        from .country_discovery import discover_countries
        countries = discover_countries()
        
        target_country = None
        for country in countries:
            from src.utils.geocoding import get_country_info
            iso3, _, _ = get_country_info(country["name"])
            if iso3 == country_code or country["name"].lower() == country_name.lower():
                target_country = country
                break
        
        if not target_country:
            return {
                "success": False,
                "error": f"Could not find country URL for {country_name}"
            }
        
        country_url = target_country["url"]
        country_slug = target_country.get("slug", country_name.lower().replace(" ", "-"))
        
        # Update status
        save_scan_status("running", {
            "current_country": country_name,
            "current_country_code": country_code,
            "resume_mode": True,
            "start_time": datetime.utcnow().isoformat()
        })
        
        scan_start = time.time()
        new_articles = []
        
        try:
            # Resume blogs if incomplete
            if not pending_tasks.get("blogs_complete", True):
                logger.info(f"Resuming blog scanning for {country_name}...")
                blogs, blogs_timeout = scan_country_blogs(driver, country_url, country_slug, country_name, max_articles=200, timeout_per_article=30, country_start_time=scan_start)
                new_articles.extend(blogs)
                
                if blogs_timeout:
                    logger.warning(f"⏱️ Timeout again during blog resume for {country_name}")
                    pending_tasks["blogs_complete"] = False
                    pending_tasks["blogs_processed"] = pending_tasks.get("blogs_processed", 0) + len(blogs)
                else:
                    pending_tasks["blogs_complete"] = True
                    pending_tasks["blogs_processed"] = pending_tasks.get("blogs_processed", 0) + len(blogs)
            
            # Resume publications if incomplete (and blogs didn't timeout)
            if not pending_tasks.get("publications_complete", True) and pending_tasks.get("blogs_complete", True):
                logger.info(f"Resuming publication scanning for {country_name}...")
                publications, pubs_timeout = scan_country_publications(driver, country_url, country_slug, country_name, max_articles=200, timeout_per_article=30, country_start_time=scan_start)
                new_articles.extend(publications)
                
                if pubs_timeout:
                    logger.warning(f"⏱️ Timeout again during publication resume for {country_name}")
                    pending_tasks["publications_complete"] = False
                    pending_tasks["publications_processed"] = pending_tasks.get("publications_processed", 0) + len(publications)
                else:
                    pending_tasks["publications_complete"] = True
                    pending_tasks["publications_processed"] = pending_tasks.get("publications_processed", 0) + len(publications)
            
            # Merge new articles with existing ones (avoid duplicates by URL)
            existing_urls = {a.get("url") for a in existing_articles}
            unique_new_articles = [a for a in new_articles if a.get("url") not in existing_urls]
            
            all_articles = existing_articles + unique_new_articles
            
            # Determine if all tasks complete
            all_complete = pending_tasks.get("blogs_complete", True) and pending_tasks.get("publications_complete", True)
            
            # Save updated data
            if all_complete:
                logger.info(f"✅ All tasks completed for {country_name}!")
                save_country_data(country_code, country_name, all_articles, pending_tasks=None)
            else:
                logger.warning(f"⚠️ Some tasks still pending for {country_name}")
                save_country_data(country_code, country_name, all_articles, pending_tasks=pending_tasks)
            
            # Update summary
            from .file_storage import calculate_summary, save_summary
            summary = calculate_summary()
            save_summary(summary)
            
            # Update status
            save_scan_status("completed", {
                "current_country": None,
                "resume_mode": True,
                "end_time": datetime.utcnow().isoformat()
            })
            
            scan_duration = time.time() - scan_start
            
            return {
                "success": True,
                "country": country_name,
                "country_code": country_code,
                "total_articles": len(all_articles),
                "new_articles": len(unique_new_articles),
                "existing_articles": len(existing_articles),
                "accelerator_lab_count": sum(1 for a in all_articles if a.get("classification") == "accelerator_lab"),
                "country_office_count": sum(1 for a in all_articles if a.get("classification") == "country_office"),
                "duration_seconds": round(scan_duration, 2),
                "status": "complete" if all_complete else "partial",
                "pending_tasks": pending_tasks if not all_complete else None
            }
            
        except ScanPausedException:
            logger.info(f"⏸️ Resume paused by user for {country_name}")
            save_scan_status("paused", {
                "current_country": country_name,
                "resume_mode": True,
                "paused_at": datetime.utcnow().isoformat()
            })
            return {
                "success": False,
                "error": "Resume was paused by user",
                "country": country_name
            }
        except Exception as e:
            logger.error(f"Error resuming {country_name}: {e}", exc_info=True)
            save_scan_status("error", {}, error=str(e))
            return {
                "success": False,
                "error": str(e),
                "country": country_name
            }
    
    except Exception as e:
        logger.error(f"Failed to resume country tasks: {e}", exc_info=True)
        save_scan_status("error", {}, error=str(e))
        return {
            "success": False,
            "error": str(e)
        }
    finally:
        # DISABLED: Distributed locking not working in Azure Web App
        # release_scan_lock()
        cleanup_selenium()


def run_full_scan():
    """
    Run complete AcceleratorLab scan across all UNDP countries.
    Supports resuming from last processed country if scan was interrupted.
    This is the main entry point for the scanning process.
    
    IMPORTANT: Browser is restarted after each country to prevent memory issues.
    Uses distributed locking for Azure multi-instance deployments.
    """
    global _pause_requested
    _pause_requested = False  # Reset pause flag at start
    
    logger.info("Starting AcceleratorLab full scan")
    
    # DISABLED: Distributed locking not working in Azure Web App
    # from .file_storage import acquire_scan_lock, release_scan_lock, renew_scan_lock
    # 
    # if not acquire_scan_lock():
    #     logger.error("❌ Cannot start scan - another instance is already running a scan")
    #     save_scan_status("error", {}, error="Another instance is already running a scan")
    #     return
    
    try:
        # Check if there's a previous scan to resume
        from .file_storage import get_all_countries
        processed_countries = set(get_all_countries())
        
        # Discover all countries (no Selenium needed for discovery)
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
        # IMPORTANT: Browser is restarted for each country to prevent memory issues
        for idx, country in enumerate(countries_to_process, 1):
            # Setup Selenium for this country (fresh browser)
            logger.info(f"🌍 Starting browser for country {idx}/{len(countries_to_process)}...")
            setup_selenium()
            from src.scraper.selenium_driver import driver
            
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
                
                # DISABLED: Distributed locking not working in Azure Web App
                # renew_scan_lock()
                
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
                    # Scan blogs (with 24h country-level timeout tracking)
                    blogs, blogs_timeout = scan_country_blogs(driver, country_url, country_slug, country_name, max_articles=200, timeout_per_article=30, country_start_time=country_start_time)
                    
                    # Check if 24-hour timeout occurred during blogs
                    if blogs_timeout:
                        logger.warning(f"⏱️ 24-hour timeout reached for {country_name} during blog scanning")
                        # Save partial results with pending tasks
                        pending_tasks = {
                            "blogs_complete": False,
                            "publications_complete": False,
                            "timeout_at": datetime.utcnow().isoformat(),
                            "blogs_processed": len(blogs),
                            "publications_processed": 0,
                            "reason": "24h_timeout_during_blogs"
                        }
                        save_country_data(country_iso3, country_name, blogs, pending_tasks=pending_tasks)
                        logger.info(f"✅ Saved {len(blogs)} partial results for {country_name}. Skipping publications and moving to next country.")
                    else:
                        # Scan publications (with 24h country-level timeout tracking)
                        publications, pubs_timeout = scan_country_publications(driver, country_url, country_slug, country_name, max_articles=200, timeout_per_article=30, country_start_time=country_start_time)
                        
                        # Combine results
                        all_articles = blogs + publications
                        
                        # Check if timeout occurred during publications
                        if pubs_timeout:
                            logger.warning(f"⏱️ 24-hour timeout reached for {country_name} during publication scanning")
                            pending_tasks = {
                                "blogs_complete": True,
                                "publications_complete": False,
                                "timeout_at": datetime.utcnow().isoformat(),
                                "blogs_processed": len(blogs),
                                "publications_processed": len(publications),
                                "reason": "24h_timeout_during_publications"
                            }
                            save_country_data(country_iso3, country_name, all_articles, pending_tasks=pending_tasks)
                            logger.info(f"✅ Saved {len(all_articles)} partial results for {country_name}. Moving to next country.")
                        else:
                            # Complete scan - no timeout
                            save_country_data(country_iso3, country_name, all_articles)
                            if all_articles:
                                logger.info(f"✅ Saved {len(all_articles)} articles for {country_name} ({country_iso3})")
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
                # Pause was requested - cleanup browser and save state
                cleanup_selenium()
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
            
            finally:
                # CRITICAL: Cleanup browser after each country to prevent memory issues
                logger.info(f"🧹 Cleaning up browser after {country_name}...")
                cleanup_selenium()
        
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
        # DISABLED: Distributed locking not working in Azure Web App
        # release_scan_lock()
        # Final browser cleanup (in case not cleaned up in loop)
        try:
            cleanup_selenium()
        except Exception:
            pass


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
    
    **DISABLED**: This function is intentionally disabled to prevent automatic
    scan restarts on server startup, which causes issues in multi-instance
    Azure deployments. Scans should only be started manually via API or dashboard.
    
    To resume an interrupted scan, use the manual resume endpoint:
    POST /acceleratorlab/scan/continue
    """
    try:
        status = load_scan_status()
        
        # Check if scan was running when server stopped
        if status.get("status") == "running":
            logger.warning("⚠️  Detected interrupted scan status='running' on startup")
            logger.warning("⚠️  Auto-resume is DISABLED. The scan will NOT restart automatically.")
            logger.info("📌 Use POST /acceleratorlab/scan/continue to manually resume the scan if needed")
            
            # DO NOT auto-start! Just log the status
            # Old code that caused issues:
            # save_scan_status("idle", {})
            # success, message = start_scan_async()
        else:
            logger.debug(f"Scan status on startup: {status.get('status')}")
            
    except Exception as e:
        logger.error(f"Error checking scan status: {e}", exc_info=True)


def cleanup_stale_scan_on_startup():
    """
    Clean up stale scan status on application startup.
    This prevents ghost "running" status from blocking new scans.
    
    Called once when the application starts.
    """
    try:
        from .file_storage import load_scan_status, save_scan_status, force_break_lock
        from datetime import datetime, timezone
        
        status = load_scan_status()
        current_status = status.get("status")
        error_msg = status.get("error", "")
        
        # Check if error is lock-related
        is_lock_error = current_status == "error" and "another instance" in error_msg.lower()
        
        if current_status == "running" or is_lock_error:
            last_updated = status.get("last_updated")
            
            if last_updated:
                try:
                    last_update_time = datetime.fromisoformat(last_updated.replace('Z', '+00:00'))
                    now = datetime.now(timezone.utc)
                    age_hours = (now - last_update_time.replace(tzinfo=timezone.utc)).total_seconds() / 3600
                    
                    if age_hours > 1:  # More than 1 hour old
                        logger.warning(f"⚠️  Found stale '{current_status}' status from {age_hours:.1f} hours ago on startup")
                        if is_lock_error:
                            logger.warning(f"   Error was: {error_msg}")
                        logger.info("🧹 Cleaning up stale scan status and breaking lock...")
                        
                        # Break the lock and reset status
                        force_break_lock()
                        save_scan_status("idle", {})
                        
                        logger.info("✅ Stale scan status cleaned up successfully")
                    else:
                        logger.info(f"🔄 Recent {current_status} detected ({age_hours:.1f} hours old) - leaving status unchanged")
                except Exception as e:
                    logger.warning(f"Could not parse last_updated time: {e}")
                    # If we can't parse the time, assume it's stale
                    logger.info("🧹 Cleaning up unparseable scan status...")
                    force_break_lock()
                    save_scan_status("idle", {})
            else:
                # No last_updated field - definitely stale
                logger.warning(f"⚠️  Found '{current_status}' status with no timestamp - cleaning up...")
                force_break_lock()
                save_scan_status("idle", {})
                
        elif current_status in ["error", "paused"]:
            logger.info(f"📌 Scan status on startup: {current_status}")
            if current_status == "error":
                logger.info(f"   Error message: {error_msg}")
        else:
            logger.debug(f"Scan status on startup: {current_status or 'idle'}")
            
    except Exception as e:
        logger.error(f"Error during startup cleanup: {e}", exc_info=True)

