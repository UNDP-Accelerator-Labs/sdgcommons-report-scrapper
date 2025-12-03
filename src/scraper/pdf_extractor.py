"""PDF extraction utilities"""

import os
import logging
import requests
from io import BytesIO
from pdfminer.high_level import extract_text
import time

from src.config import Settings

logger = logging.getLogger(__name__)


def is_pdf_url(url):
    """
    Check if URL is a direct PDF link.
    
    Args:
        url: URL to check
        
    Returns:
        bool: True if URL appears to be a PDF
    """
    return url.lower().endswith('.pdf') or '.pdf' in url.lower()


def extract_pdf_content(pdf_bytes):
    """
    Extract text content from PDF bytes.
    
    Args:
        pdf_bytes: PDF file content as bytes
        
    Returns:
        str: Extracted text content
    """
    try:
        content = extract_text(BytesIO(pdf_bytes))
        return content
    except Exception as e:
        logger.error(f"Failed to extract PDF content: {e}")
        return ""


def download_and_parse_pdf(pdf_url):
    """
    Download PDF via Selenium (triggered download) and parse content.
    This is used as a fallback when direct requests fail due to access restrictions.
    
    Args:
        pdf_url: URL of the PDF to download
        
    Returns:
        tuple: (content_string, filename) or (None, None) if failed
    """
    from .selenium_driver import driver, download_dir
    
    if not driver or not download_dir:
        logger.error("Selenium not initialized for PDF download")
        return None, None
    
    try:
        logger.info(f"Downloading PDF via Selenium: {pdf_url}")
        driver.get(pdf_url)
        
        # Wait for download to complete
        file_path = wait_for_download(download_dir, timeout=60)
        
        if file_path:
            with open(file_path, 'rb') as f:
                pdf_content = extract_text(f)
            
            filename = os.path.basename(file_path)
            logger.info(f"Successfully extracted PDF content: {len(pdf_content)} characters")
            return pdf_content, filename
        else:
            logger.error(f"Download timed out for {pdf_url}")
            return None, None
            
    except Exception as e:
        logger.error(f"Failed to download and parse PDF: {e}")
        return None, None


def wait_for_download(download_dir, timeout=60):
    """
    Wait for download to complete and return the file path.
    
    Args:
        download_dir: Directory where files are downloaded
        timeout: Maximum seconds to wait for download
        
    Returns:
        str: Path to downloaded file, or None if timeout
    """
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
        
        time.sleep(1)
    
    logger.warning(f"Download timeout after {timeout} seconds")
    return None


def get_filename_from_url(url, default="unknown.pdf"):
    """
    Extract filename from URL.
    
    Args:
        url: URL to extract filename from
        default: Default filename if extraction fails
        
    Returns:
        str: Extracted or default filename
    """
    try:
        from urllib.parse import urlparse, unquote
        parsed = urlparse(url)
        path = unquote(parsed.path)
        filename = os.path.basename(path)
        return filename if filename else default
    except Exception:
        return default
