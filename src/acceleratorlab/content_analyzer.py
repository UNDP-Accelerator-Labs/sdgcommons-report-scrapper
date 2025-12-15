"""Content analysis and classification for AcceleratorLab detection"""

import logging
import re
from datetime import datetime
from bs4 import BeautifulSoup
import requests
from io import BytesIO

from .keywords import ALL_KEYWORDS_FLAT

logger = logging.getLogger(__name__)

# Import PDF extraction utilities
try:
    from pdfminer.high_level import extract_text
    PDF_SUPPORT = True
except ImportError:
    logger.warning("pdfminer not available, PDF extraction disabled")
    PDF_SUPPORT = False


def extract_date_from_article(soup, url):
    """
    Extract publication date from article page.
    
    For publication pages (URLs containing '/publications/'), prioritizes dates from 
    <h6 class="coh-heading"> elements which contain the actual publication date.
    
    Args:
        soup: BeautifulSoup object of the article page
        url: Article URL for logging
        
    Returns:
        datetime or None: Publication date if found and parsed
    """
    date_text = None
    
    # PRIORITY 1: For publications, extract date from <h6 class="coh-heading"> elements
    # These contain the actual publication date (e.g., "October 1, 2014")
    if '/publications/' in url:
        h6_elements = soup.find_all("h6", class_="coh-heading")
        
        for h6 in h6_elements:
            text = h6.get_text(strip=True)
            
            # Try to parse the text as a date
            parsed_date = _parse_date_string(text)
            if parsed_date:
                logger.debug(f"Found date in h6.coh-heading: {text} -> {parsed_date}")
                return parsed_date
        
        logger.debug(f"No date found in h6.coh-heading elements for publication: {url}")
    
    # PRIORITY 2: Common date selectors (HTML metadata)
    date_selectors = [
        {"tag": "time", "attr": "datetime"},
        {"class": ["posted-date", "date", "publish-date", "published", "post-date", "article-date"]},
        {"itemprop": "datePublished"},
        {"property": "article:published_time"}
    ]
    
    # Try time tag with datetime attribute first
    time_tag = soup.find("time")
    if time_tag and time_tag.get("datetime"):
        date_text = time_tag["datetime"]
    
    # Try other selectors
    if not date_text:
        for selector in date_selectors:
            if "tag" in selector and "attr" in selector:
                elem = soup.find(selector["tag"])
                if elem and elem.get(selector["attr"]):
                    date_text = elem[selector["attr"]]
                    break
            elif "class" in selector:
                for cls in selector["class"]:
                    elem = soup.find(class_=cls)
                    if elem:
                        date_text = elem.get_text(strip=True)
                        break
                if date_text:
                    break
            elif "itemprop" in selector:
                elem = soup.find(attrs={"itemprop": selector["itemprop"]})
                if elem:
                    date_text = elem.get("content") or elem.get_text(strip=True)
                    break
            elif "property" in selector:
                elem = soup.find(attrs={"property": selector["property"]})
                if elem:
                    date_text = elem.get("content") or elem.get_text(strip=True)
                    break
    
    if not date_text:
        logger.debug(f"No date found in HTML metadata for {url}")
        return None
    
    # Parse date from metadata
    parsed_date = _parse_date_string(date_text)
    if parsed_date:
        return parsed_date
    
    logger.debug(f"Could not parse date from metadata: {date_text}")
    return None


def _parse_date_string(date_text):
    """
    Parse a date string into a datetime object.
    Tries multiple common date formats.
    
    Args:
        date_text: String potentially containing a date
        
    Returns:
        datetime or None: Parsed date if successful
    """
    if not date_text:
        return None
    
    date_text = date_text.strip()
    
    try:
        # Try ISO format first (2023-01-15T10:30:00Z or 2023-01-15)
        if "T" in date_text or (date_text.count("-") == 2 and date_text[0].isdigit()):
            date_text = date_text.split("T")[0]  # Take date part only
            return datetime.strptime(date_text, "%Y-%m-%d")
        
        # Try common written date formats
        formats = [
            "%B %d, %Y",      # October 1, 2014
            "%b %d, %Y",      # Oct 1, 2014
            "%d %B %Y",       # 1 October 2014
            "%d %b %Y",       # 1 Oct 2014
            "%B %d %Y",       # October 1 2014 (no comma)
            "%b %d %Y",       # Oct 1 2014 (no comma)
            "%d %B, %Y",      # 1 October, 2014
            "%d %b, %Y",      # 1 Oct, 2014
            "%Y-%m-%d",       # 2014-10-01
            "%m/%d/%Y",       # 10/01/2014
            "%d/%m/%Y",       # 01/10/2014
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_text, fmt)
            except ValueError:
                continue
        
        return None
        
    except Exception as e:
        logger.debug(f"Date parsing error: {e} for text: {date_text}")
        return None


def extract_date_from_text(text):
    """
    Extract dates from article text content using regex patterns.
    Looks for common date formats in the first 2000 characters of text.
    
    Args:
        text: Article text content
        
    Returns:
        datetime or None: First date found if valid
    """
    if not text:
        return None
    
    # Search only in first 2000 chars (where dates typically appear)
    search_text = text[:2000]
    
    # Date patterns to match (prioritize year-month-day formats)
    patterns = [
        # ISO format: 2023-01-15, 2023/01/15
        (r'\b(20\d{2})[-/](0[1-9]|1[0-2])[-/](0[1-9]|[12]\d|3[01])\b', '%Y-%m-%d'),
        # Format: January 15, 2023 or Jan 15, 2023
        (r'\b(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[,\s]+(\d{1,2})[,\s]+(20\d{2})\b', None),
        # Format: 15 January 2023
        (r'\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[,\s]+(20\d{2})\b', None),
        # Format: Published: 2023, Updated: 2023, Copyright 2023
        (r'\b(Published|Updated|Copyright|©)[\s:,]+(20\d{2})\b', None),
        # Simple year: just 2023 (last resort)
        (r'\b(20[12]\d)\b', '%Y'),
    ]
    
    for pattern, fmt in patterns:
        matches = re.finditer(pattern, search_text, re.IGNORECASE)
        for match in matches:
            try:
                date_str = match.group(0)
                
                if fmt:
                    # Use provided format
                    if fmt == '%Y-%m-%d':
                        date_str = date_str.replace('/', '-')
                    return datetime.strptime(date_str, fmt)
                else:
                    # Parse manually for complex patterns
                    groups = match.groups()
                    if len(groups) >= 3 and groups[2].startswith('20'):
                        # Month day, year format
                        year = int(groups[2])
                        return datetime(year, 1, 1)  # Return year at least
                    elif len(groups) >= 2 and groups[-1].startswith('20'):
                        # Year only from "Published: 2023" etc
                        year = int(groups[-1])
                        return datetime(year, 1, 1)
            except (ValueError, IndexError):
                continue
    
    return None


def is_after_2019(date_obj):
    """Check if date is 2019 or later"""
    if not date_obj:
        return True  # If no date found, include by default
    return date_obj.year >= 2019


def extract_pdf_links(soup):
    """
    Extract all PDF download links from publication page.
    Prioritizes English PDFs.
    
    Args:
        soup: BeautifulSoup object of the publication page
        
    Returns:
        list: List of dicts with {url, title, size, language}
    """
    pdf_links = []
    
    # Find all download links
    # Pattern 1: Links in download modal
    download_items = soup.find_all("li", class_="chapter-item download-row")
    for item in download_items:
        link = item.find("a", href=True, download=True)
        if link and link["href"].endswith(".pdf"):
            title_elem = item.find("div", class_="chapter-title")
            size_elem = item.find("div", class_="document-size")
            
            pdf_data = {
                "url": link["href"],
                "title": title_elem.get_text(strip=True) if title_elem else "",
                "size": size_elem.get_text(strip=True) if size_elem else "",
                "language": "unknown"
            }
            
            # Detect language from title
            title_lower = pdf_data["title"].lower()
            if "english" in title_lower or "_en" in title_lower:
                pdf_data["language"] = "english"
            elif "french" in title_lower or "français" in title_lower or "_fr" in title_lower:
                pdf_data["language"] = "french"
            elif "spanish" in title_lower or "español" in title_lower or "_es" in title_lower:
                pdf_data["language"] = "spanish"
            elif "report" in title_lower and "language" not in title_lower:
                # If it's just called "report" without language specification, assume English
                pdf_data["language"] = "english"
            
            pdf_links.append(pdf_data)
    
    # Pattern 2: Links in publication card
    if not pdf_links:
        pub_cards = soup.find_all("div", class_="publication-card")
        for card in pub_cards:
            link = card.find("a", href=True, download=True)
            if link and link["href"].endswith(".pdf"):
                pdf_links.append({
                    "url": link["href"],
                    "title": link.get_text(strip=True),
                    "size": "",
                    "language": "english"  # Default to English for simple links
                })
    
    # Pattern 3: Any PDF link on page
    if not pdf_links:
        all_links = soup.find_all("a", href=True)
        for link in all_links:
            if link["href"].endswith(".pdf"):
                pdf_links.append({
                    "url": link["href"],
                    "title": link.get_text(strip=True),
                    "size": "",
                    "language": "english"
                })
    
    # Prioritize English PDFs
    english_pdfs = [p for p in pdf_links if p["language"] == "english"]
    other_pdfs = [p for p in pdf_links if p["language"] != "english"]
    
    return english_pdfs + other_pdfs


def analyze_pdf_content(pdf_url, timeout=30, use_selenium=True):
    """
    Download and extract text content from PDF.
    First tries direct requests.get(), if that fails (403), uses Selenium to load PDF.
    
    Args:
        pdf_url: URL of the PDF to download
        timeout: Request timeout in seconds (default 30, max enforced is 60)
        use_selenium: Whether to fallback to Selenium on failure
        
    Returns:
        str: Extracted text content or empty string if failed
    """
    if not PDF_SUPPORT:
        logger.warning("PDF extraction not available")
        return ""
    
    # Safety: enforce maximum timeout of 60 seconds
    timeout = min(timeout, 60)
    
    # Make URL absolute if needed
    if pdf_url.startswith("/"):
        pdf_url = f"https://www.undp.org{pdf_url}"
    
    logger.info(f"Extracting PDF content from: {pdf_url} (timeout: {timeout}s)")
    
    # Try 1: Direct download with requests (fast, no browser needed)
    try:
        logger.debug(f"Attempting direct download: {pdf_url}")
        response = requests.get(pdf_url, timeout=timeout, allow_redirects=True, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        response.raise_for_status()
        
        # Extract text
        pdf_content = extract_text(BytesIO(response.content))
        logger.info(f"✅ Successfully extracted {len(pdf_content)} characters from PDF via direct download")
        
        return pdf_content
        
    except requests.exceptions.RequestException as e:
        # If we got 403 Forbidden, try Selenium approach
        if "403" in str(e) or "Forbidden" in str(e):
            logger.warning(f"Direct download failed with 403, attempting Selenium load: {pdf_url}")
            
            if not use_selenium:
                logger.error(f"Selenium fallback disabled, cannot extract PDF: {pdf_url}")
                return ""
            
            # Try 2: Load PDF in Selenium browser (handles auth/cookies)
            try:
                from src.scraper.selenium_driver import driver
                
                if not driver:
                    logger.error("Selenium driver not initialized, cannot extract PDF")
                    return ""
                
                # Navigate to PDF URL in browser
                logger.debug(f"Loading PDF in Selenium browser: {pdf_url}")
                driver.get(pdf_url)
                
                # Wait a moment for PDF to load
                import time
                time.sleep(2)
                
                # Get page source - for PDFs, Chrome renders them and we can access via network
                # Instead, we'll use requests with browser cookies
                cookies = driver.get_cookies()
                session = requests.Session()
                for cookie in cookies:
                    session.cookies.set(cookie['name'], cookie['value'])
                
                # Try downloading with browser session (has auth cookies)
                logger.debug(f"Downloading PDF with browser session cookies")
                response = session.get(pdf_url, timeout=timeout, headers={
                    'User-Agent': driver.execute_script("return navigator.userAgent;"),
                    'Referer': 'https://www.undp.org/'
                })
                response.raise_for_status()
                
                # Extract text
                pdf_content = extract_text(BytesIO(response.content))
                logger.info(f"✅ Successfully extracted {len(pdf_content)} characters from PDF via Selenium session")
                
                return pdf_content
                
            except Exception as selenium_error:
                logger.error(f"Selenium fallback also failed for {pdf_url}: {selenium_error}")
                return ""
        else:
            # Other request error (timeout, network, etc.)
            logger.error(f"Failed to download PDF {pdf_url}: {e}")
            return ""
            
    except Exception as e:
        logger.error(f"Failed to extract PDF content {pdf_url}: {e}")
        return ""


def extract_date_from_pdf_metadata(pdf_url, timeout=30):
    """
    Extract creation/modification date from PDF metadata.
    This is used as a fallback when h6.coh-heading date is not found.
    
    Args:
        pdf_url: URL of the PDF
        timeout: Request timeout in seconds
        
    Returns:
        datetime or None: PDF creation/modification date if found
    """
    if not PDF_SUPPORT:
        return None
    
    # Make URL absolute if needed
    if pdf_url.startswith("/"):
        pdf_url = f"https://www.undp.org{pdf_url}"
    
    try:
        # Import PDFInfo for metadata extraction
        from pdfminer.pdfparser import PDFParser
        from pdfminer.pdfdocument import PDFDocument
        
        # Download PDF
        response = requests.get(pdf_url, timeout=timeout, allow_redirects=True, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        response.raise_for_status()
        
        # Parse PDF metadata
        pdf_file = BytesIO(response.content)
        parser = PDFParser(pdf_file)
        doc = PDFDocument(parser)
        
        # Get metadata
        metadata = doc.info
        if not metadata:
            return None
        
        # metadata is a list of dicts, get the first one
        if isinstance(metadata, list) and len(metadata) > 0:
            info = metadata[0]
        else:
            info = metadata
        
        # Try to extract creation date or modification date
        date_fields = [b'CreationDate', b'ModDate', 'CreationDate', 'ModDate']
        
        for field in date_fields:
            if field in info:
                date_value = info[field]
                
                # PDF dates are in format: D:YYYYMMDDHHmmSS
                # Example: D:20141001120000Z or b"D:20141001120000Z"
                if isinstance(date_value, bytes):
                    date_value = date_value.decode('utf-8', errors='ignore')
                
                date_str = str(date_value).strip()
                
                # Extract date parts from PDF date format
                match = re.match(r'D:(\d{4})(\d{2})(\d{2})', date_str)
                if match:
                    year, month, day = match.groups()
                    pdf_date = datetime(int(year), int(month), int(day))
                    logger.debug(f"Extracted date from PDF metadata: {pdf_date}")
                    return pdf_date
        
        return None
        
    except Exception as e:
        logger.debug(f"Could not extract date from PDF metadata {pdf_url}: {e}")
        return None


def analyze_content(soup, url, extract_pdfs=True):
    """
    Extract full content from article/publication page.
    For publications, extracts and analyzes PDF content if available.
    
    Args:
        soup: BeautifulSoup object of the page
        url: Page URL
        extract_pdfs: Whether to extract PDF content (for publications)
        
    Returns:
        dict: Extracted content with title, text, author, date, pdf_urls
    """
    # Check if this is a publication page (has PDF downloads)
    is_publication = bool(soup.find("div", class_="publication-card") or 
                         soup.find("li", class_="chapter-item download-row"))
    
    # Extract PDF links if this is a publication
    pdf_links = []
    pdf_content = ""
    if is_publication and extract_pdfs:
        pdf_links = extract_pdf_links(soup)
        logger.info(f"Found {len(pdf_links)} PDF(s) for {url}")
        
        # Extract content from first (prioritized English) PDF
        if pdf_links:
            pdf_content = analyze_pdf_content(pdf_links[0]["url"])
    
    # Extract title (UNDP uses multiple heading patterns)
    title = None
    title_selectors = [
        soup.find("h2", class_="article-title"),
        soup.find("h1", class_="coh-heading"),
        soup.find("h1", class_="article-title"),
        soup.find("h1"),
        soup.find("h2", class_="coh-heading"),
        soup.find("meta", property="og:title"),
    ]
    
    for elem in title_selectors:
        if elem:
            if elem.name == "meta":
                title = elem.get("content", "")
            else:
                title = elem.get_text(strip=True)
            if title:
                break
    
    # DATE EXTRACTION PRIORITY (for publications):
    # 1. h6.coh-heading elements (most accurate for publications)
    # 2. HTML metadata (time tags, meta tags)
    # 3. PDF metadata (creation/modification date) - FALLBACK
    # 4. Text content extraction - LAST RESORT
    
    pub_date = extract_date_from_article(soup, url)
    
    # If no date found and this is a publication, try PDF metadata as fallback
    if not pub_date and is_publication and pdf_links:
        logger.debug(f"No date in HTML, trying PDF metadata for publication: {url}")
        pub_date = extract_date_from_pdf_metadata(pdf_links[0]["url"])
        if pub_date:
            logger.info(f"✅ Found date in PDF metadata: {pub_date.year}")
    
    # Extract author (UNDP uses author-label divs with h6 tags)
    author = None
    author_selectors = [
        soup.find(class_="author-label"),
        soup.find(class_=re.compile(r"author", re.I)),
        soup.find(attrs={"itemprop": "author"}),
        soup.find(attrs={"rel": "author"}),
        soup.find(class_=re.compile(r"byline", re.I))
    ]
    
    for elem in author_selectors:
        if elem:
            # If author-label div, try to get h6 text first
            if "author-label" in elem.get("class", []):
                h6 = elem.find("h6")
                if h6:
                    author = h6.get_text(strip=True)
                    break
            author = elem.get_text(strip=True)
            break
    
    # Extract main content
    content_text = ""
    
    # Try UNDP-specific and common content containers (prioritize coh-wysiwyg)
    content_containers = [
        soup.find("div", class_="coh-wysiwyg"),
        soup.find("div", class_="layout-content"),
        soup.find("main"),
        soup.find("article"),
        soup.find(class_=re.compile(r"content|article-body|post-content|entry-content", re.I)),
        soup.find("div", class_=re.compile(r"main|body", re.I))
    ]
    
    for container in content_containers:
        if container:
            # Extract all paragraph text
            paragraphs = container.find_all("p")
            content_text = " ".join([p.get_text(strip=True) for p in paragraphs])
            if content_text:  # Only break if we actually got content
                break
    
    # Fallback: get all paragraphs on page
    if not content_text:
        paragraphs = soup.find_all("p")
        content_text = " ".join([p.get_text(strip=True) for p in paragraphs])
    
    # For publications, combine HTML content with PDF content
    if is_publication and pdf_content:
        content_text = f"{content_text} {pdf_content}".strip()
        logger.info(f"Combined HTML ({len(content_text) - len(pdf_content)} chars) and PDF ({len(pdf_content)} chars) content")
    
    # Clean up common UI text
    content_text = content_text.replace("Read more", "").replace("View More", "").replace("Load More", "")
    content_text = re.sub(r'\s+', ' ', content_text).strip()
    
    # LAST RESORT: If still no date found, try extracting from text content
    if not pub_date and content_text:
        logger.debug(f"No date from HTML or PDF metadata, trying text content extraction for: {url}")
        pub_date = extract_date_from_text(content_text)
        if pub_date:
            logger.info(f"✅ Found date in text content: {pub_date.year}")
    
    return {
        "title": title or "Untitled",
        "text": content_text,
        "author": author,
        "date": pub_date.isoformat() if pub_date else None,
        "url": url,
        "pdf_urls": [pdf["url"] for pdf in pdf_links],
        "is_publication": is_publication
    }


def classify_article(content_data):
    """
    Classify article as AcceleratorLab or Country Office based on keyword detection.
    
    Args:
        content_data: Dictionary with article content
        
    Returns:
        str: "accelerator_lab" or "country_office"
    """
    # Combine all searchable text (title + content + author)
    searchable_text = " ".join([
        content_data.get("title", ""),
        content_data.get("text", ""),
        content_data.get("author", "") or ""
    ]).lower()
    
    # Check for any AcceleratorLab keyword
    for keyword in ALL_KEYWORDS_FLAT:
        if keyword in searchable_text:
            logger.debug(f"Found keyword '{keyword}' in {content_data['url']}")
            return "accelerator_lab"
    
    # No keyword found - classify as Country Office
    return "country_office"
