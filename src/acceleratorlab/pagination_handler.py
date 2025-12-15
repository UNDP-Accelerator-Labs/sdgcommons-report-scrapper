"""Pagination handling for blogs and publications pages"""

import logging
import time
from urllib.parse import urljoin, urlparse, parse_qs
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

logger = logging.getLogger(__name__)


def extract_article_urls(soup, base_url):
    """
    Extract all article URLs from a blogs or publications listing page.
    Handles UNDP-specific structure with content-card divs.
    
    Args:
        soup: BeautifulSoup object of the page
        base_url: Base URL for resolving relative links
        
    Returns:
        list: Article URLs found on the page
    """
    urls = []
    
    # UNDP-specific: Look for content-card divs
    content_cards = soup.find_all("div", class_="content-card")
    if content_cards:
        logger.debug(f"Found {len(content_cards)} content-card elements")
        for card in content_cards:
            link = card.find("a", href=True)
            if link:
                url = urljoin(base_url, link["href"])
                if is_article_url(url):
                    urls.append(url)
    
    # Fallback: Common patterns for article links
    if not urls:
        article_selectors = [
            ("article", "a"),  # Links within article tags
            ("div", {"class": ["post", "blog", "publication", "card", "item"]}),
            ("h2", "a"),  # Titles with links
            ("h3", "a"),
            ("h5", "a"),
        ]
        
        for selector in article_selectors:
            if isinstance(selector, tuple) and len(selector) == 2:
                if isinstance(selector[1], dict):
                    # div with class
                    containers = soup.find_all(selector[0], selector[1])
                    for container in containers:
                        link = container.find("a", href=True)
                        if link:
                            url = urljoin(base_url, link["href"])
                            if is_article_url(url):
                                urls.append(url)
                else:
                    # nested tag search
                    containers = soup.find_all(selector[0])
                    for container in containers:
                        link = container.find(selector[1], href=True)
                        if link:
                            url = urljoin(base_url, link["href"])
                            if is_article_url(url):
                                urls.append(url)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_urls = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)
    
    return unique_urls


def is_article_url(url):
    """Check if URL looks like an article (not pagination, tags, categories, etc.)"""
    parsed = urlparse(url)
    path = parsed.path.lower()
    
    # Exclude pagination and filter URLs
    exclude_patterns = [
        "?page=", "&page=", "/page/", "/tag/", "/category/",
        "/author/", "/search", "/filter"
    ]
    
    for pattern in exclude_patterns:
        if pattern in url.lower():
            return False
    
    # Must have meaningful path
    return len(path) > 10


def handle_pagination(driver, page_url, max_clicks=20, max_articles=500):
    """
    Handle "View More" button pagination (no URL-based pagination).
    UNDP country pages use a "View More" button that loads more content via JavaScript.
    
    Args:
        driver: Selenium WebDriver instance
        page_url: URL of the blogs or publications page
        max_clicks: Maximum number of "View More" clicks (default 20)
        max_articles: Maximum total articles to collect (safety limit, default 500)
        
    Returns:
        list: All article URLs found across all loaded content
    """
    logger.info(f"Starting pagination handling for {page_url} (max_clicks: {max_clicks}, max_articles: {max_articles})")
    all_urls = []
    click_count = 0
    no_new_content_count = 0  # Track consecutive clicks with no new content
    
    try:
        driver.get(page_url)
        time.sleep(2)  # Let page load
        
        # Keep clicking "View More" button until it disappears or max clicks reached
        while click_count < max_clicks:
            # Safety check: stop if we've collected enough articles
            if len(all_urls) >= max_articles:
                logger.warning(f"Reached max articles limit ({max_articles}), stopping pagination")
                break
            
            # Safety check: stop if we've had 3 consecutive clicks with no new content
            if no_new_content_count >= 3:
                logger.warning(f"No new content after {no_new_content_count} consecutive clicks, stopping pagination")
                break
            
            # Get current page HTML and extract URLs
            soup = BeautifulSoup(driver.page_source, "html.parser")
            urls = extract_article_urls(soup, page_url)
            
            # Track newly found URLs
            new_urls = [url for url in urls if url not in all_urls]
            if new_urls:
                logger.debug(f"Found {len(new_urls)} new articles (total: {len(all_urls) + len(new_urls)})")
                all_urls.extend(new_urls)
                no_new_content_count = 0  # Reset counter when we find new content
            else:
                no_new_content_count += 1
                logger.debug(f"No new articles found on this click ({no_new_content_count}/3)")
            
            # Look for "View More" button
            # First, scroll to bottom of page to ensure button is loaded in DOM
            logger.debug(f"Scrolling to bottom to load 'View More' button...")
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)
            
            view_more_found = False
            view_more_selectors = [
                (By.XPATH, "//button[contains(translate(text(), 'VIEWMORE', 'viewmore'), 'view more')]"),
                (By.XPATH, "//a[contains(translate(text(), 'VIEWMORE', 'viewmore'), 'view more')]"),
                (By.CLASS_NAME, "load-more-custom"),
                (By.CLASS_NAME, "load-more"),
                (By.CLASS_NAME, "view-more"),
                (By.XPATH, "//button[contains(translate(text(), 'LOADMORE', 'loadmore'), 'load more')]"),
                (By.XPATH, "//a[contains(translate(text(), 'LOADMORE', 'loadmore'), 'load more')]")
            ]
            
            for by, value in view_more_selectors:
                try:
                    # Check if button exists and is visible
                    button = WebDriverWait(driver, 2).until(
                        EC.presence_of_element_located((by, value))
                    )
                    
                    # Check if button is displayed and enabled
                    if not button.is_displayed():
                        logger.debug(f"Button found but not displayed: {by}={value}")
                        continue
                    
                    # Scroll to button - ensure it's fully in view at the bottom of viewport
                    # This happens EVERY iteration of the while loop
                    logger.info(f"Scrolling to 'View More' button for click #{click_count + 1}...")
                    driver.execute_script("""
                        arguments[0].scrollIntoView({behavior: 'smooth', block: 'end', inline: 'nearest'});
                    """, button)
                    time.sleep(1.5)
                    
                    # Additional check: ensure button is still visible after scroll
                    if not button.is_displayed():
                        logger.debug(f"Button not visible after scroll, trying alternative scroll")
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                        time.sleep(1)
                    
                    # Click using JavaScript (more reliable than .click())
                    logger.info(f"Clicking 'View More' button (click #{click_count + 1})...")
                    driver.execute_script("arguments[0].click();", button)
                    
                    # Wait for new content to load
                    time.sleep(3)
                    
                    view_more_found = True
                    click_count += 1
                    break
                    
                except (TimeoutException, NoSuchElementException) as e:
                    logger.debug(f"Selector {by}={value} not found: {e}")
                    continue
                except Exception as e:
                    logger.debug(f"Error with selector {by}={value}: {e}")
                    continue
            
            # If no "View More" button found, we're done
            if not view_more_found:
                logger.info(f"No more 'View More' button found after {click_count} clicks")
                
                # Final extraction to catch any remaining items
                soup = BeautifulSoup(driver.page_source, "html.parser")
                urls = extract_article_urls(soup, page_url)
                new_urls = [url for url in urls if url not in all_urls]
                if new_urls:
                    all_urls.extend(new_urls)
                
                break
            
    except Exception as e:
        logger.error(f"Error during pagination: {e}")
    
    # Remove duplicates
    unique_urls = list(dict.fromkeys(all_urls))
    logger.info(f"Total unique articles found: {len(unique_urls)}")
    
    return unique_urls
