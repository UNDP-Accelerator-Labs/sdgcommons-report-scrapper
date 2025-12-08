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


def scan_country_blogs(driver, country_url: str, country_code: str, country_name: str) -> List[Dict[str, Any]]:
    """
    Scan all blogs for a country and classify them.
    
    Args:
        driver: Selenium WebDriver instance
        country_url: Country office homepage URL
        country_code: ISO3 country code
        country_name: Country name
        
    Returns:
        list: Classified articles with metadata
    """
    logger.info(f"Scanning blogs for {country_name} ({country_code})")
    
    results = []
    
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
                        logger.error(f"Error analyzing article {url}: {e}")
                        continue
                
                # Found and processed blogs, stop trying other patterns
                break
                
        except Exception as e:
            logger.warning(f"Could not access {blogs_url}: {e}")
            continue
    
    return results


def scan_country_publications(driver, country_url: str, country_code: str, country_name: str) -> List[Dict[str, Any]]:
    """
    Scan all publications for a country and classify them.
    
    Args:
        driver: Selenium WebDriver instance
        country_url: Country office homepage URL
        country_code: ISO3 country code
        country_name: Country name
        
    Returns:
        list: Classified publications with metadata
    """
    logger.info(f"Scanning publications for {country_name} ({country_code})")
    
    results = []
    
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
                        logger.error(f"Error analyzing publication {url}: {e}")
                        continue
                
                break
                
        except Exception as e:
            logger.warning(f"Could not access {pubs_url}: {e}")
            continue
    
    return results


def run_full_scan():
    """
    Run complete AcceleratorLab scan across all UNDP countries.
    Supports resuming from last processed country if scan was interrupted.
    This is the main entry point for the scanning process.
    """
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
            
            # Update status with accurate progress
            save_scan_status("running", {
                "current_country": country_name,
                "current_country_code": country_iso3,
                "countries_completed": current_completed,
                "total_countries": total_countries,
                "countries_remaining": len(countries_to_process) - idx,
                "resumed": skipped_count > 0,
                "start_time": datetime.utcnow().isoformat()
            })
            
            try:
                # Scan blogs
                blogs = scan_country_blogs(driver, country_url, country_slug, country_name)
                
                # Scan publications
                publications = scan_country_publications(driver, country_url, country_slug, country_name)
                
                # Combine results
                all_articles = blogs + publications
                
                # Save country data using ISO3 code (even if empty, to mark as processed)
                save_country_data(country_iso3, country_name, all_articles)
                if all_articles:
                    logger.info(f"Saved {len(all_articles)} articles for {country_name} ({country_iso3})")
                else:
                    logger.warning(f"No articles found for {country_name} ({country_iso3})")
                
            except Exception as e:
                logger.error(f"Error processing {country_name}: {e}")
                # Save empty data to mark country as attempted (using ISO3 code)
                try:
                    save_country_data(country_iso3, country_name, [])
                except:
                    pass
            
            finally:
                # Always update summary after each country (success or failure)
                # This ensures dashboard shows real-time progress
                try:
                    logger.debug(f"Updating summary after processing {country_name}")
                    summary = calculate_summary()
                    save_summary(summary)
                except Exception as summary_error:
                    logger.warning(f"Failed to update summary: {summary_error}")
        
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
        
        # Start new scan thread
        _scanner_thread = threading.Thread(target=run_full_scan, daemon=True)
        _scanner_thread.start()
        
        logger.info("Started AcceleratorLab scan in background thread")
        return True, "Scan started successfully"


def get_scan_status() -> Dict[str, Any]:
    """
    Get current scan status.
    
    Returns:
        dict: Status information with progress details
    """
    return load_scan_status()


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
