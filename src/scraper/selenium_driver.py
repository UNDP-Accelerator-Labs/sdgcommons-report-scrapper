"""Selenium WebDriver management"""

import os
import logging
import tempfile
import shutil
import glob
import stat
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

from src.config import Settings

logger = logging.getLogger(__name__)

# Global variables for driver management
driver = None
wait = None
download_dir = None


def setup_selenium():
    """
    Create and set global Selenium Chrome webdriver with a reliable chromedriver path.
    Sets up headless Chrome with download directory for PDF extraction.
    
    Returns:
        selenium.webdriver.Chrome: Configured Chrome WebDriver instance
    """
    global driver, wait, download_dir

    # Prepare download dir early so it can be applied to chrome prefs
    download_dir = tempfile.mkdtemp(prefix="sdg_scraper_dl_")

    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1280,1024")
    chrome_options.add_argument(
        '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36'
    )

    prefs = {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "plugins.always_open_pdf_externally": True
    }
    chrome_options.add_experimental_option("prefs", prefs)

    # Install via webdriver-manager
    try:
        driver_path = ChromeDriverManager().install()
    except Exception as e:
        logger.warning(f"webdriver-manager failed to download chromedriver: {e}")
        # Fallbacks: env var, PATH, common system locations
        driver_path = Settings.CHROMEDRIVER_PATH or shutil.which("chromedriver")
        common_paths = ["/usr/local/bin/chromedriver", "/usr/bin/chromedriver", "/opt/chromedriver"]
        for p in common_paths:
            if not driver_path and os.path.exists(p) and os.access(p, os.X_OK):
                driver_path = p
                break
        if not driver_path:
            raise RuntimeError(
                "Could not obtain chromedriver via webdriver-manager and no fallback chromedriver found. "
                "Set CHROMEDRIVER_PATH env var or install chromedriver on the system."
            ) from e

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


def safe_get(url):
    """
    Safely get a URL using Selenium with error handling.
    
    Args:
        url: URL to fetch
        
    Returns:
        Response-like object with status_code, text attributes
    """
    global driver, wait
    
    try:
        logger.info(f"Accessing {url} via Selenium")
        driver.get(url)
        wait.until(EC.presence_of_all_elements_located((By.TAG_NAME, "body")))
        html = driver.page_source
        
        class Response:
            status_code = 200
            text = html
            def raise_for_status(self):
                pass
                
        return Response()
    except Exception as e:
        logger.error(f"Failed to load {url} via Selenium: {e}")
        raise
