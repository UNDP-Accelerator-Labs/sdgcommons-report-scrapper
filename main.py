import os
import re
import logging
import psycopg2
import schedule
import time
import json
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from datetime import datetime, timezone, date
from pdfminer.high_level import extract_text
from io import BytesIO
import requests
import tempfile
import shutil
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from langdetect import detect, DetectorFactory
import pycountry
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable
import time as time_module
import glob
import stat

# Set seed for consistent language detection
DetectorFactory.seed = 0

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database connection
DB_HOST = os.getenv("DB_HOST", "")
DB_PORT = os.getenv("DB_PORT", "")
DB_NAME = os.getenv("DB_NAME", "")
DB_USER = os.getenv("DB_USER", "")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

def get_db_connection():
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )
    return conn

REPORT_URLS = [
    "https://www.undp.org/digital/aila",
    "https://www.undp.org/digital/dra"
]

# Initialize geocoder
geolocator = Nominatim(user_agent="undp-reports-scraper-this-pama")

# Cache for geocoding results to avoid repeated API calls
geocoding_cache = {}

# Selenium setup
chrome_options = Options()
chrome_options.add_argument('--headless=new')
chrome_options.add_argument('--disable-gpu')
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--disable-dev-shm-usage')
chrome_options.add_argument('window-size=1920,1080')
chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0 Safari/537.36')

# Global variables for driver management
driver = None
wait = None
download_dir = None

def setup_selenium():
    """Create and set global Selenium Chrome webdriver with a reliable chromedriver path."""
    global driver, wait, download_dir

    # prepare download dir early so it can be applied to chrome prefs
    download_dir = tempfile.mkdtemp(prefix="sdg_scraper_dl_")

    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1280,1024")
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                                'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36')

    prefs = {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "plugins.always_open_pdf_externally": True
    }
    chrome_options.add_experimental_option("prefs", prefs)

    # Install via webdriver-manager
    driver_path = ChromeDriverManager().install()

    # If install returned a directory or non-executable file, try to find the real binary
    if os.path.isdir(driver_path):
        candidates = glob.glob(os.path.join(driver_path, "**", "chromedriver*"), recursive=True)
    else:
        parent = os.path.dirname(driver_path)
        candidates = glob.glob(os.path.join(parent, "chromedriver*"))
        candidates += glob.glob(os.path.join(parent, "**", "chromedriver*"), recursive=True)

    candidates = sorted(set(candidates))

    selected = None
    for c in candidates:
        bn = os.path.basename(c).lower()
        if bn.startswith("third_party_notices"):
            continue
        if os.path.isfile(c):
            try:
                st = os.stat(c)
                if not (st.st_mode & stat.S_IXUSR):
                    os.chmod(c, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            except Exception:
                pass
            if os.access(c, os.X_OK):
                selected = c
                break

    if selected is None and os.path.isfile(driver_path) and os.access(driver_path, os.X_OK):
        selected = driver_path

    if selected is None:
        raise RuntimeError(
            "Could not locate an executable chromedriver binary from webdriver-manager output. "
            "Try clearing webdriver-manager cache: rm -rf ~/.wdm/drivers/chromedriver"
        )

    service = Service(selected)
    driver = webdriver.Chrome(service=service, options=chrome_options)
    wait = WebDriverWait(driver, 20)

    logger.info(f"Selenium started using chromedriver: {selected} (download_dir={download_dir})")
    return driver

def cleanup_selenium():
    """Cleanup Selenium driver and temp files"""
    global driver, download_dir
    
    if driver:
        driver.quit()
        driver = None
        
    # Clean up download directory
    if download_dir and os.path.exists(download_dir):
        try:
            shutil.rmtree(download_dir)
            logger.info(f"Cleaned up download directory: {download_dir}")
        except Exception as e:
            logger.warning(f"Failed to clean up download directory: {e}")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.undp.org/",
    "Connection": "keep-alive",
}

def safe_get(url):
    try:
        logger.info(f"Accessing {url} via Selenium")
        driver.get(url)
        wait.until(EC.presence_of_all_elements_located((By.TAG_NAME, "body")))
        html = driver.page_source
        class Response:
            status_code = 200
            text = html
            def raise_for_status(self): pass
        return Response()
    except Exception as e:
        logger.error(f"Failed to load {url} via Selenium: {e}")
        raise

def is_pdf_url(url):
    """Check if URL is a direct PDF link"""
    return url.lower().endswith('.pdf') or '.pdf' in url.lower()

def get_country_info(country_name):
    """Get country ISO3 code, lat, lng from country name using automatic geocoding"""
    if not country_name or country_name.lower() == "unknown":
        return None, None, None
    
    clean_name = country_name.lower().strip()
    
    if clean_name in geocoding_cache:
        cached = geocoding_cache[clean_name]
        return cached["iso3"], cached["lat"], cached["lng"]
    
    iso3 = None
    lat = None
    lng = None
    
    try:
        try:
            country = pycountry.countries.search_fuzzy(country_name)[0]
            iso3 = country.alpha_3
            logger.debug(f"Found ISO3 for {country_name}: {iso3}")
        except:
            logger.warning(f"Could not find ISO3 code for: {country_name}")
        
        try:
            logger.debug(f"Geocoding country: {country_name}")
            location = geolocator.geocode(country_name, timeout=10)
            
            if location:
                lat = location.latitude
                lng = location.longitude
                logger.info(f"Geocoded {country_name}: {lat}, {lng}")
            else:
                logger.warning(f"Could not geocode: {country_name}")
                
            time_module.sleep(1)
            
        except (GeocoderTimedOut, GeocoderUnavailable) as e:
            logger.warning(f"Geocoding failed for {country_name}: {e}")
        except Exception as e:
            logger.error(f"Unexpected geocoding error for {country_name}: {e}")
        
        geocoding_cache[clean_name] = {
            "iso3": iso3,
            "lat": lat,
            "lng": lng
        }
        
        return iso3, lat, lng
        
    except Exception as e:
        logger.error(f"Error getting country info for {country_name}: {e}")
        return None, None, None

def detect_language(text):
    """Detect language of text content"""
    if not text or len(text.strip()) < 50:
        return "en"
    
    try:
        sample_text = text[:1000].strip()
        detected_lang = detect(sample_text)
        logger.debug(f"Detected language: {detected_lang}")
        return detected_lang
    except Exception as e:
        logger.warning(f"Language detection failed: {e}")
        return "en"

def article_exists(conn, url):
    """Check if article already exists in database"""
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM articles WHERE url = %s", (url,))
        return cur.fetchone() is not None

def get_existing_article(conn, url):
    """Return existing article id and article_type for a url, or None"""
    with conn.cursor() as cur:
        cur.execute("SELECT id, article_type FROM articles WHERE url = %s", (url,))
        row = cur.fetchone()
        if row:
            return {"id": row[0], "article_type": row[1]}
        return None

def insert_article_to_db(conn, article_data, raw_html):
    """Insert article into database including country name"""
    try:
        with conn.cursor() as cur:
            conn.rollback()
            
            iso3, lat, lng = get_country_info(article_data["country"])
            language = detect_language(article_data["content"])
            
            current_date = date.today()
            current_timestamp = datetime.now()
            
            # Check if country column exists, add if not
            try:
                cur.execute("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'articles' AND column_name = 'country'
                """)
                if not cur.fetchone():
                    cur.execute("ALTER TABLE articles ADD COLUMN country VARCHAR(100)")
                    logger.info("Added country column to articles table")
            except Exception as e:
                logger.warning(f"Error checking/adding country column: {e}")
            
            # Insert into articles table including country
            cur.execute("""
                INSERT INTO articles (
                    url, language, title, posted_date, posted_date_str, 
                    article_type, created_at, updated_at, deleted, has_lab,
                    lat, lng, privilege, rights, tags, country,
                    parsed_date, relevance, iso3
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                article_data["url"],
                language,
                article_data["title"],
                current_date,
                current_date.strftime('%Y-%m-%d'),
                article_data["report_type"],
                current_timestamp,
                current_timestamp,
                False,
                False,
                lat,
                lng,
                1,
                1,
                [article_data["report_type"], article_data["country"]],
                article_data["country"],  # Added country field
                current_timestamp,
                2,
                iso3
            ))
            
            article_id = cur.fetchone()[0]
            
            # Insert content
            cur.execute("""
                INSERT INTO article_content (article_id, content, created_at, updated_at)
                VALUES (%s, %s, %s, %s)
            """, (
                article_id,
                article_data["content"],
                current_timestamp,
                current_timestamp
            ))
            
            # Insert raw HTML
            cur.execute("""
                INSERT INTO raw_html (article_id, raw_html, created_at, updated_at)
                VALUES (%s, %s, %s, %s)
            """, (
                article_id,
                raw_html if raw_html is not None else article_data.get("content"),
                current_timestamp,
                current_timestamp
            ))
            
            conn.commit()
            logger.info(f"Successfully inserted article ID {article_id}: {article_data['title'][:50]}...")
            return article_id
            
    except Exception as e:
        logger.error(f"Failed to insert article into database: {e}")
        conn.rollback()
        raise

def call_embedding_service(article_id):
    """Call configured NLP embedding service to embed an article by DB id.
       Returns True on success, False otherwise."""
    embed_url = os.getenv("NLP_API_URL")
    write_token = os.getenv("NLP_WRITE_TOKEN")
    token = os.getenv("API_TOKEN")
    embedding_db = os.getenv("EMBEDDING_DB")

    if not all([embed_url, write_token, token, embedding_db]):
        logger.debug("Embedding service not configured - skipping embedding")
        return False

    body = {
        "token": token,
        "write_access": write_token,
        "db": embedding_db,
        "main_id": f"blog:{article_id}"
    }
    try:
        r = requests.post(f"{embed_url.rstrip('/')}/api/embed/add", json=body, timeout=30)
        if r.ok:
            logger.info(f"Embedded article {article_id}")
            return True
        else:
            logger.warning(f"Embedding failed for {article_id}: {r.status_code} {r.text}")
            return False
    except Exception as e:
        logger.exception(f"Embedding error for {article_id}: {e}")
        return False

def extract_country_from_card(card):
    """Extract country name from card HTML"""
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

def wait_for_download(download_dir, timeout=60):
    """Wait for download to complete and return the file path"""
    logger.info(f"Waiting for download in {download_dir}")
    
    for i in range(timeout):
        try:
            files = [f for f in os.listdir(download_dir) if not f.startswith('.')]
        except OSError:
            files = []
        
        if files:
            downloading_files = [f for f in files if f.endswith('.crdownload') or f.endswith('.tmp')]
            if not downloading_files:
                completed_files = [f for f in files if f.endswith('.pdf')]
                if completed_files:
                    file_path = os.path.join(download_dir, completed_files[0])
                    if os.path.getsize(file_path) > 0:
                        logger.info(f"Download completed: {file_path}")
                        return file_path
        
        time_module.sleep(1)
    
    logger.error(f"Download timeout after {timeout} seconds")
    return None

def download_and_parse_pdf(pdf_url):
    """Download PDF and extract text content"""
    try:
        logger.info(f"Downloading PDF: {pdf_url}")
        
        try:
            for file in os.listdir(download_dir):
                file_path = os.path.join(download_dir, file)
                try:
                    os.remove(file_path)
                except:
                    pass
        except OSError:
            pass
        
        driver.get(pdf_url)
        downloaded_file = wait_for_download(download_dir)
        
        if downloaded_file and os.path.exists(downloaded_file):
            try:
                text_content = extract_text(downloaded_file)
                logger.info(f"Successfully extracted text from PDF: {len(text_content)} characters")
                return text_content, os.path.basename(downloaded_file)
            except Exception as e:
                logger.error(f"Failed to extract text from PDF {downloaded_file}: {e}")
                return None, None
        else:
            logger.error(f"Failed to download PDF from {pdf_url}")
            return None, None
            
    except Exception as e:
        logger.error(f"Error downloading/parsing PDF {pdf_url}: {e}")
        return None, None

def extract_pdf_directly(pdf_url):
    """Extract PDF content directly from URL"""
    try:
        logger.info(f"Extracting PDF directly from: {pdf_url}")
        
        try:
            pdf_response = requests.get(pdf_url, headers=HEADERS, timeout=30)
            pdf_response.raise_for_status()
            content = extract_text(BytesIO(pdf_response.content))
            logger.info(f"Successfully extracted PDF via requests: {len(content)} characters")
            return content, "PDF_DIRECT_REQUESTS"
        except Exception as e:
            logger.warning(f"Failed to extract PDF via requests: {e}, trying Selenium...")
            
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

def safe_split(s, sep=None, maxsplit=-1):
    """Return list from s.split(...) but return [] if s is None."""
    if s is None:
        return []
    try:
        return s.split(sep, maxsplit)
    except Exception:
        return []

def get_filename_from_url(url, default="unknown.pdf"):
    """Return a safe basename for a URL (guards against None)."""
    try:
        if not url:
            return default
        # use safe_split to avoid None errors
        raw = safe_split(url, '?', 1)[0] if safe_split(url, '?', 1) else url
        name = os.path.basename(raw)
        return name if name else default
    except Exception:
        return default

def parse_country_report(url, report_type, country):
    """Parse a country report page and return article data and metadata"""
    try:
        logger.info(f"Parsing report: {url} (Country: {country})")
        start_time = datetime.now(timezone.utc)
        
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
                pdf_response = requests.get(pdf_link, headers=HEADERS)
                pdf_response.raise_for_status()
                content = extract_text(BytesIO(pdf_response.content))
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
    """Main scraping function"""
    logger.info("Starting scraping job...")
    
    setup_selenium()
    
    conn = get_db_connection()
    all_extracted_data = []
    
    try:
        for base_url in REPORT_URLS:
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
                                    # add report_type to tags if tags column is an array (guarded update)
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

if __name__ == "__main__":
    scrape_reports()