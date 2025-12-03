"""Web scraping and report parsing utilities"""

import logging
from datetime import datetime, timezone
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import requests

from src.config import Settings
from src.database import get_db_connection, get_existing_article, insert_article_to_db
from src.utils.geocoding import get_country_info
from src.utils.language import detect_language
from src.utils.nlp_service import call_embedding_service
from .selenium_driver import safe_get
from .pdf_extractor import is_pdf_url, extract_pdf_content, download_and_parse_pdf, get_filename_from_url

logger = logging.getLogger(__name__)


def extract_country_from_card(card):
    """
    Extract country name from card HTML.
    
    Args:
        card: BeautifulSoup tag object representing a report card
        
    Returns:
        str: Country name or "Unknown"
    """
    try:
        country_element = card.select_one("h5.coh-heading")
        if country_element:
            country = country_element.get_text(strip=True)
            if country:
                logger.debug(f"Found country in card: {country}")
                return country
        
        h5_elements = card.select("h5")
        if h5_elements:
            for h5 in h5_elements:
                text = h5.get_text(strip=True)
                if text and len(text) < 50:
                    logger.debug(f"Found potential country: {text}")
                    return text
        
        logger.warning("No country found in card")
        return "Unknown"
        
    except Exception as e:
        logger.warning(f"Error extracting country from card: {e}")
        return "Unknown"


def extract_pdf_directly(pdf_url):
    """
    Extract PDF content directly from URL with fallback strategies.
    
    Args:
        pdf_url: URL of the PDF to extract
        
    Returns:
        tuple: (content_string, content_source_string) or (None, error_source)
    """
    try:
        logger.info(f"Extracting PDF directly from: {pdf_url}")
        
        # Try direct requests first
        try:
            pdf_response = requests.get(pdf_url, headers=Settings.DEFAULT_HEADERS, timeout=30)
            pdf_response.raise_for_status()
            content = extract_pdf_content(pdf_response.content)
            logger.info(f"Successfully extracted PDF via requests: {len(content)} characters")
            return content, "PDF_DIRECT_REQUESTS"
        except Exception as e:
            logger.warning(f"Failed to extract PDF via requests: {e}, trying Selenium...")
            
            # Fallback to Selenium download
            pdf_content, pdf_filename = download_and_parse_pdf(pdf_url)
            if pdf_content:
                logger.info(f"Successfully extracted PDF via Selenium: {len(pdf_content)} characters")
                return pdf_content, "PDF_DIRECT_SELENIUM"
            else:
                logger.error(f"Failed to extract PDF via both methods")
                return None, "PDF_DIRECT_FAILED"
                
    except Exception as e:
        logger.error(f"Error in direct PDF extraction: {e}")
        return None, "PDF_DIRECT_ERROR"


def parse_country_report(url, report_type, country):
    """
    Parse a country report page and return article data and metadata.
    
    Args:
        url: URL of the report to parse
        report_type: Type of report (AILA, DRA, etc.)
        country: Country name
        
    Returns:
        tuple: (article_data dict, raw_html string) or (error_dict, None)
    """
    try:
        logger.info(f"Parsing report: {url} (Country: {country})")
        start_time = datetime.now(timezone.utc)
        
        # Handle direct PDF URLs
        if is_pdf_url(url):
            logger.info(f"Direct PDF URL detected: {url}")
            content, content_source = extract_pdf_directly(url)
            
            if content:
                pdf_filename = get_filename_from_url(url)
                title = f"{report_type} Report - {country}"
                
                iso3, lat, lng = get_country_info(country)
                language = detect_language(content)
                
                end_time = datetime.now(timezone.utc)
                processing_time = (end_time - start_time).total_seconds()
                
                article_data = {
                    "title": title,
                    "content": content,
                    "content_length": len(content),
                    "content_source": content_source,
                    "url": url,
                    "country": country,
                    "iso3": iso3,
                    "lat": lat,
                    "lng": lng,
                    "language": language,
                    "report_type": report_type,
                    "pdf_links_found": 1,
                    "pdf_info": [{
                        "url": url,
                        "filename": pdf_filename,
                        "content_length": len(content),
                        "extracted_successfully": True
                    }],
                    "extraction_timestamp": start_time.isoformat(),
                    "processing_time_seconds": round(processing_time, 2),
                    "success": True
                }
                
                return article_data, None
            else:
                article_data = {
                    "title": f"ERROR: Failed to extract PDF - {country}",
                    "content": f"Failed to extract PDF content from {url}",
                    "content_length": 0,
                    "content_source": "PDF_DIRECT_FAILED",
                    "url": url,
                    "country": country,
                    "iso3": None,
                    "lat": None,
                    "lng": None,
                    "language": "en",
                    "report_type": report_type,
                    "pdf_links_found": 1,
                    "pdf_info": [],
                    "extraction_timestamp": start_time.isoformat(),
                    "processing_time_seconds": 0,
                    "success": False
                }
                return article_data, None
        
        # Normal webpage parsing
        response = safe_get(url)
        soup = BeautifulSoup(response.text, "html.parser")

        title_tag = soup.find("h1")
        title = title_tag.get_text(strip=True) if title_tag else None
        
        if not title or title.strip() == "":
            title = f"{report_type} Report - {country}"
        elif country.lower() not in title.lower() and country != "Unknown":
            title = f"{title} - {country}"

        # Look for PDF link in the page
        pdf_link = None
        for a in soup.find_all("a", href=True):
            if a["href"].lower().endswith(".pdf"):
                pdf_link = urljoin(url, a["href"])
                break

        content = ""
        content_source = "NONE"
        pdf_info = []

        if pdf_link:
            logger.info(f"Found PDF link: {pdf_link}")
            try:
                pdf_response = requests.get(pdf_link, headers=Settings.DEFAULT_HEADERS)
                pdf_response.raise_for_status()
                content = extract_pdf_content(pdf_response.content)
                content_source = "PDF"
                pdf_info.append({
                    "url": pdf_link,
                    "content_length": len(content),
                    "extracted_successfully": True
                })
            except Exception as e:
                logger.warning(f"Access denied or failed via requests, retrying via Selenium for {pdf_link}")
                try:
                    pdf_content, pdf_filename = download_and_parse_pdf(pdf_link)
                    if pdf_content:
                        content = pdf_content
                        content_source = "PDF"
                        pdf_info.append({
                            "url": pdf_link,
                            "filename": pdf_filename,
                            "content_length": len(content),
                            "extracted_successfully": True
                        })
                    else:
                        pdf_info.append({
                            "url": pdf_link,
                            "content_length": 0,
                            "extracted_successfully": False
                        })
                except Exception as e2:
                    logger.error(f"Failed to fetch PDF via Selenium: {e2}")
                    content = ""
        else:
            # Extract web content from paragraphs
            paragraphs = [p.get_text(strip=True) for p in soup.find_all("p")]
            content = "\n".join(paragraphs)
            if content and len(content.strip()) > 50:
                content_source = "WEB"
            else:
                content_source = "FAILED"

        iso3, lat, lng = get_country_info(country)
        language = detect_language(content)
        
        end_time = datetime.now(timezone.utc)
        processing_time = (end_time - start_time).total_seconds()

        logger.info(f"Parsed report: {title}")
        
        article_data = {
            "title": title,
            "content": content,
            "content_length": len(content),
            "content_source": content_source,
            "url": url,
            "country": country,
            "iso3": iso3,
            "lat": lat,
            "lng": lng,
            "language": language,
            "report_type": report_type,
            "pdf_links_found": 1 if pdf_link else 0,
            "pdf_info": pdf_info,
            "extraction_timestamp": start_time.isoformat(),
            "processing_time_seconds": round(processing_time, 2),
            "success": content_source in ["PDF", "WEB", "PDF_DIRECT_REQUESTS", "PDF_DIRECT_SELENIUM"]
        }
        
        return article_data, response.text
        
    except Exception as e:
        logger.error(f"Failed to parse report {url}: {e}")
        return {
            "title": f"ERROR: Failed to parse {url}",
            "content": f"Error: {str(e)}",
            "content_length": 0,
            "content_source": "ERROR",
            "url": url,
            "country": country,
            "iso3": None,
            "lat": None,
            "lng": None,
            "language": "en",
            "report_type": report_type,
            "pdf_links_found": 0,
            "pdf_info": [],
            "extraction_timestamp": datetime.now(timezone.utc).isoformat(),
            "processing_time_seconds": 0,
            "success": False
        }, None


def scrape_reports():
    """
    Main scraping function to discover and process all UNDP reports.
    
    Returns:
        list: List of extracted article data dictionaries
    """
    from .selenium_driver import setup_selenium, cleanup_selenium
    
    logger.info("Starting scraping job...")
    
    setup_selenium()
    
    conn = get_db_connection()
    all_extracted_data = []
    
    try:
        for base_url in Settings.REPORT_URLS:
            response = safe_get(base_url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")

            report_cards = []
            for card in soup.select("div.feature__card"):
                label = card.select_one("h6.coh-heading")
                if label and label.get_text(strip=True).lower() == "report":
                    link = card.select_one("a[href]")
                    if link:
                        url = urljoin(base_url, link["href"])
                        country = extract_country_from_card(card)
                        report_cards.append({
                            "url": url,
                            "country": country
                        })
                        logger.info(f"Found report card: {country} - {url}")

            unique_reports = {}
            for report in report_cards:
                if report["url"] not in unique_reports:
                    unique_reports[report["url"]] = report["country"]

            logger.info(f"Found {len(unique_reports)} country report links on {base_url}")

            report_type = "AILA" if "/aila" in base_url else "DRA" if "/dra" in base_url else "publication"

            for i, (report_url, country) in enumerate(unique_reports.items(), 1):
                try:
                    existing = get_existing_article(conn, report_url)
                    if existing:
                        # If stored article_type differs from current report type, update and re-run embedding
                        if (existing.get("article_type") or "").upper() != (report_type or "").upper():
                            logger.info(f"Updating article {existing['id']} type from {existing.get('article_type')} to {report_type}")
                            try:
                                with conn.cursor() as cur:
                                    cur.execute("""
                                        UPDATE articles
                                        SET article_type = %s, updated_at = %s
                                        WHERE id = %s
                                    """, (report_type, datetime.now(), existing["id"]))
                                conn.commit()
                                # call NLP embed API for this existing article id
                                call_embedding_service(existing["id"])
                            except Exception as e:
                                conn.rollback()
                                logger.error(f"Failed to update article type for {existing['id']}: {e}")
                        else:
                            logger.info(f"Article already exists in DB with same type, skipping: {report_url}")
                        continue

                    logger.info(f"Processing {i}/{len(unique_reports)}: {country} - {report_url}")
                    
                    article_data, raw_html = parse_country_report(report_url, report_type, country)
                    if article_data and article_data.get("success"):
                        article_id = insert_article_to_db(conn, article_data, raw_html)
                        article_data["database_id"] = article_id

                        # optional: embed into NLP service if configured
                        call_embedding_service(article_id)

                        all_extracted_data.append(article_data)
                    else:
                        logger.warning(f"✗ No data extracted from {report_url}")
                        if article_data:
                            try:
                                article_id = insert_article_to_db(conn, article_data, raw_html)
                                article_data["database_id"] = article_id
                            except:
                                pass
                            all_extracted_data.append(article_data)
                            
                except Exception as e:
                    logger.error(f"Failed to process {report_url}: {e}")
                    
    finally:
        conn.close()
        cleanup_selenium()
        
    logger.info("Scraping job completed.")
    return all_extracted_data
