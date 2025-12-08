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
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
import time

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


def dismiss_modals_and_popups():
    """
    Attempt to dismiss common modals, popups, and overlays that block content.
    Handles login prompts, newsletter subscriptions, cookie consents, etc.
    """
    global driver
    
    if not driver:
        return
    
    # Common close button selectors
    close_selectors = [
        # Generic close buttons
        "button[aria-label*='close' i]",
        "button[aria-label*='dismiss' i]",
        "button[class*='close' i]",
        "button[class*='dismiss' i]",
        "[data-testid*='close']",
        "[data-testid*='dismiss']",
        ".modal-close",
        ".popup-close",
        ".close-button",
        
        # Medium specific
        "button[data-testid='close-button']",
        "button[aria-label='close']",
        
        # Cookie consent
        "button[id*='accept']",
        "button[class*='accept']",
        ".cookie-accept",
        "#onetrust-accept-btn-handler",
        
        # Newsletter/login overlays
        "button:has-text('No thanks')",
        "button:has-text('Maybe later')",
        "button:has-text('Skip')",
        "[aria-label='Skip']",
    ]
    
    for selector in close_selectors:
        try:
            # Use short timeout for each attempt
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            for elem in elements:
                if elem.is_displayed() and elem.is_enabled():
                    elem.click()
                    logger.debug(f"Dismissed modal/popup using selector: {selector}")
                    time.sleep(0.5)  # Brief pause after dismissal
                    break
        except Exception:
            continue
    
    # Try pressing ESC key to close modals
    try:
        from selenium.webdriver.common.action_chains import ActionChains
        actions = ActionChains(driver)
        actions.send_keys(Keys.ESCAPE).perform()
        time.sleep(0.3)
    except Exception:
        pass


def handle_cloudflare_challenge():
    """
    Handle Cloudflare challenge pages by waiting for them to complete.
    Does NOT attempt to bypass security - waits for legitimate challenge completion.
    """
    global driver, wait
    
    if not driver:
        return
    
    try:
        # Check if we're on a Cloudflare challenge page
        page_source = driver.page_source.lower()
        
        if "cloudflare" in page_source and ("checking your browser" in page_source or "challenge" in page_source):
            logger.info("Cloudflare challenge detected, waiting for completion...")
            
            # Wait up to 15 seconds for challenge to complete
            # The challenge usually completes within 5 seconds
            time.sleep(5)
            
            # Check if we're still on challenge page
            for _ in range(10):
                current_source = driver.page_source.lower()
                if "checking your browser" not in current_source:
                    logger.info("Cloudflare challenge completed")
                    break
                time.sleep(1)
            
    except Exception as e:
        logger.debug(f"Error checking for Cloudflare challenge: {e}")


def safe_get(url):
    """
    Safely get a URL using Selenium with error handling.
    Handles modals, popups, and security challenges.
    
    Args:
        url: URL to fetch
        
    Returns:
        Response-like object with status_code, text attributes
    """
    global driver, wait
    
    try:
        logger.info(f"Accessing {url} via Selenium")
        driver.get(url)
        
        # Wait for initial page load
        wait.until(EC.presence_of_all_elements_located((By.TAG_NAME, "body")))
        
        # Handle Cloudflare or similar security challenges
        handle_cloudflare_challenge()
        
        # Wait a bit for JavaScript to load content (especially for Medium)
        time.sleep(2)
        
        # Dismiss any modals/popups that may block content
        dismiss_modals_and_popups()
        
        # Get final page source
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
