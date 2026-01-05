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
    # Determine base path prefix (e.g., /es/argentina) to filter out global nav links
    parsed_base = urlparse(base_url)
    base_parts = parsed_base.path.strip('/').split('/')
    if len(base_parts) >= 2:
        base_prefix = '/' + '/'.join(base_parts[:2])
    else:
        base_prefix = parsed_base.path or '/'
    
    # UNDP-specific: Look for content-card divs
    content_cards = soup.find_all("div", class_="content-card")
    if content_cards:
        logger.debug(f"Found {len(content_cards)} content-card elements")
        for card in content_cards:
            link = card.find("a", href=True)
            if link:
                        url = urljoin(base_url, link["href"])
                        parsed_link = urlparse(url)
                        # Only include links under the same country/region prefix
                        if parsed_link.path.startswith(base_prefix) and is_article_url(url):
                            urls.append(url)
                        else:
                            logger.debug(f"Skipping non-matching link: {url} (base_prefix={base_prefix})")
    
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
                                    parsed_link = urlparse(url)
                                    if parsed_link.path.startswith(base_prefix) and is_article_url(url):
                                        urls.append(url)
                                    else:
                                        logger.debug(f"Skipping non-matching link: {url} (base_prefix={base_prefix})")
                else:
                    # nested tag search
                    containers = soup.find_all(selector[0])
                    for container in containers:
                        link = container.find(selector[1], href=True)
                        if link:
                            url = urljoin(base_url, link["href"])
                            parsed_link = urlparse(url)
                            if parsed_link.path.startswith(base_prefix) and is_article_url(url):
                                urls.append(url)
                            else:
                                logger.debug(f"Skipping non-matching link: {url} (base_prefix={base_prefix})")
    
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

            # Primary check: look for explicit load-more/button elements near bottom
            primary_selectors = [
                'button.load-more-custom',
                "button[data-totalresult]",
                "button[data-loadedresult]",
                "button[data-once='load-more-custom']",
                "button.load-more",
            ]
            primary_button = None
            for sel in primary_selectors:
                try:
                    elems = driver.find_elements(By.CSS_SELECTOR, sel)
                    # pick the last visible candidate (often the bottom one)
                    for e in reversed(elems):
                        try:
                            if e.is_displayed():
                                primary_button = e
                                break
                        except Exception:
                            continue
                    if primary_button:
                        logger.debug(f"Found primary load-more element using selector: {sel}")
                        break
                except Exception:
                    continue

            # Helper to parse integer attributes
            def _get_int_attr_elem(elem, *names):
                for n in names:
                    try:
                        v = elem.get_attribute(n)
                        if v:
                            digits = ''.join(c for c in v if c.isdigit())
                            if digits:
                                return int(digits)
                    except Exception:
                        continue
                return None

            # If primary button exists, click it and rely on presence/visibility
            # of that same primary button and the appearance of new article URLs
            # to determine whether to continue. Do NOT rely on data-loadedresult
            # attributes here because they can be stale or not updated.
            if primary_button:
                try:
                    logger.info(f"Clicking primary load-more button (click #{click_count + 1})")
                    driver.execute_script('arguments[0].scrollIntoView({behavior: "smooth", block: "center"});', primary_button)
                    time.sleep(0.6)
                    driver.execute_script('arguments[0].click();', primary_button)
                    time.sleep(2.5)

                    # After clicking, extract new URLs and check progress
                    soup_after = BeautifulSoup(driver.page_source, 'html.parser')
                    urls_after = extract_article_urls(soup_after, page_url)
                    new_after = [u for u in urls_after if u not in all_urls]
                    if new_after:
                        logger.debug(f"Primary click loaded {len(new_after)} new articles")
                        all_urls.extend(new_after)
                        no_new_content_count = 0
                    else:
                        no_new_content_count += 1
                        logger.debug(f"Primary click did not load new articles ({no_new_content_count}/3)")

                    click_count += 1

                    # Re-check if the primary button still exists and is visible; if not, stop
                    try:
                        if not primary_button.is_displayed():
                            logger.info("Primary load-more button no longer displayed; stopping pagination")
                            break
                    except Exception:
                        # Try to locate again; if not found, stop
                        try:
                            elems = driver.find_elements(By.CSS_SELECTOR, 'button.load-more-custom')
                            visible = any(e.is_displayed() for e in elems)
                            if not visible:
                                logger.info("Primary load-more element disappeared after click; stopping pagination")
                                break
                        except Exception:
                            break

                    # Continue clicking primary button in next loop iteration
                    continue
                except Exception as e:
                    logger.debug(f"Error clicking primary button: {e}")
                    break

            
            view_more_found = False
            stop_pagination = False
            # Prioritize attribute/class selectors (reliable machine hooks) before
            # attempting text-based multilingual XPaths which can be affected by
            # browser translation UI.
            attribute_selectors = [
                (By.CSS_SELECTOR, 'button.load-more-custom'),
                (By.CSS_SELECTOR, 'button[data-totalresult]'),
                (By.CSS_SELECTOR, 'button[data-loadedresult]'),
                (By.CSS_SELECTOR, '[data-load-more]'),
                (By.CSS_SELECTOR, '[data-loadmore]'),
                (By.CSS_SELECTOR, '[data-load]'),
                (By.CSS_SELECTOR, '[data-href]'),
                (By.CSS_SELECTOR, '[data-target]'),
                (By.CSS_SELECTOR, '[aria-controls]'),
                (By.CLASS_NAME, "load-more-custom"),
                (By.CLASS_NAME, "load-more"),
                (By.CLASS_NAME, "view-more")
            ]

            # Multilingual phrases (used only if attribute selectors don't find anything)
            multilingual_phrases = [
                'leer más', 'cargar más', 'mostrar más',  # Spanish
                'voir plus', 'charger plus', 'afficher plus',  # French
                'ler mais', 'carregar mais',  # Portuguese
                'leggi di più', 'mostra altro',  # Italian
                'mehr anzeigen', 'mehr laden',  # German
                'load more', 'view more', 'show more', 'see more'
            ]

            text_selectors = []
            for phrase in multilingual_phrases:
                text_selectors.append((By.XPATH, f"//button[contains(translate(normalize-space(text()), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{phrase}')]") )
                text_selectors.append((By.XPATH, f"//a[contains(translate(normalize-space(text()), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{phrase}')]") )

            # Combine selectors: attributes first, then text-based fallbacks
            view_more_selectors = attribute_selectors + text_selectors
            
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

                    # If button exposes data attributes that indicate how many results
                    # are loaded vs total, use them to decide whether to click.
                    def _get_int_attr(elem, *names):
                        for n in names:
                            try:
                                v = elem.get_attribute(n)
                                if v:
                                    # strip non-digits
                                    digits = ''.join(c for c in v if c.isdigit())
                                    if digits:
                                        return int(digits)
                            except Exception:
                                continue
                        return None

                    loaded = _get_int_attr(button, 'data-loadedresult', 'data-loaded-result', 'data-loaded')
                    total = _get_int_attr(button, 'data-totalresult', 'data-total-result', 'data-total')

                    if loaded is not None and total is not None:
                        logger.debug(f"Load-more attributes: loaded={loaded}, total={total}")
                        if loaded >= total:
                            logger.info(f"All results already loaded (loaded={loaded} >= total={total}), stopping pagination")
                            stop_pagination = True
                            view_more_found = False
                            break
                    
                    # Before clicking, capture loaded/total attributes if present
                    def _get_int_attr(elem, *names):
                        for n in names:
                            try:
                                v = elem.get_attribute(n)
                                if v:
                                    digits = ''.join(c for c in v if c.isdigit())
                                    if digits:
                                        return int(digits)
                            except Exception:
                                continue
                        return None

                    loaded_before = _get_int_attr(button, 'data-loadedresult', 'data-loaded-result', 'data-loaded')
                    total = _get_int_attr(button, 'data-totalresult', 'data-total-result', 'data-total')

                    # If attributes indicate nothing left, stop
                    if loaded_before is not None and total is not None and loaded_before >= total:
                        logger.info(f"All results already loaded (loaded={loaded_before} >= total={total}), stopping pagination")
                        stop_pagination = True
                        view_more_found = False
                        break

                    # Click using JavaScript (more reliable than .click())
                    logger.info(f"Clicking 'View More' button (click #{click_count + 1})...")
                    driver.execute_script("arguments[0].click();", button)

                    # Wait for new content to load
                    time.sleep(3)

                    # If loaded_before available, check it increased after click
                    if loaded_before is not None and total is not None:
                        # Re-locate the button (DOM may have changed)
                        try:
                            post_button = driver.find_element(By.CSS_SELECTOR, 'button.load-more-custom')
                            loaded_after = _get_int_attr(post_button, 'data-loadedresult', 'data-loaded-result', 'data-loaded')
                        except Exception:
                            loaded_after = None

                        logger.debug(f"loaded_before={loaded_before}, loaded_after={loaded_after}, total={total}")
                        if loaded_after is None or loaded_after <= loaded_before:
                            logger.warning("Load-more click did not increase loaded count; stopping pagination")
                            stop_pagination = True
                            view_more_found = False
                            break

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

            if stop_pagination:
                break

            # --- Additional fallback: attempt to find and click a plausible load-more button
            # This helps on localized pages where button text doesn't match known phrases
            if not view_more_found:
                try:
                    logger.debug("Attempting generic fallback for load-more button")
                    # Candidate elements: visible buttons/links near bottom of page
                    page_height = driver.execute_script('return document.body.scrollHeight')
                    candidates = driver.find_elements(By.XPATH, "//button|//a")
                    fallback_clicked = False
                    # keywords to look for in attributes or class (English roots often used)
                    attr_keywords = ['more', 'load', 'cargar', 'leer', 'mostrar', 'ver', 'voir', 'carregar', 'ler', 'altro', 'mehr']

                    for el in candidates:
                        try:
                            if not el.is_displayed():
                                continue
                            loc = el.location.get('y', 0) or 0
                            # consider elements positioned in the lower half of the page
                            if loc < page_height * 0.4:
                                continue

                            text = (el.text or '').strip().lower()
                            cls = (el.get_attribute('class') or '').lower()
                            eid = (el.get_attribute('id') or '').lower()
                            onclick = el.get_attribute('onclick') or ''
                            # Check for explicit data attributes first
                            def _get_int_attr(elem, *names):
                                for n in names:
                                    try:
                                        v = elem.get_attribute(n)
                                        if v:
                                            digits = ''.join(c for c in v if c.isdigit())
                                            if digits:
                                                return int(digits)
                                    except Exception:
                                        continue
                                return None

                            loaded = _get_int_attr(el, 'data-loadedresult', 'data-loaded-result', 'data-loaded')
                            total = _get_int_attr(el, 'data-totalresult', 'data-total-result', 'data-total')

                            # If data attrs present, only click when loaded < total
                            if loaded is not None and total is not None:
                                logger.debug(f"Candidate element data attrs: loaded={loaded}, total={total}")
                                if loaded >= total:
                                    logger.info(f"Candidate reports all loaded (loaded={loaded} >= total={total}), will not click")
                                    continue
                                should_click = True
                            else:
                                # Require clear load-more indicators when no data attrs
                                data_once = (el.get_attribute('data-once') or '').strip()
                                has_load_class = any(k in cls for k in ['load-more', 'load_more', 'load-more-custom', 'loadmore', 'view-more', 'more'])
                                has_dataattr = any(el.get_attribute(n) for n in ['data-load-more','data-loadmore','data-load','data-href','data-target'])
                                should_click = bool(data_once or has_load_class or has_dataattr or onclick or (0 < len(text) < 40 and any(k in text for k in attr_keywords)))

                            if should_click:
                                logger.info(f"Fallback clicking candidate element with text='{text}' class='{cls}' id='{eid}'")
                                driver.execute_script('arguments[0].scrollIntoView({behavior: "smooth", block: "center"});', el)
                                time.sleep(0.8)
                                try:
                                    driver.execute_script('arguments[0].click();', el)
                                except Exception:
                                    try:
                                        el.click()
                                    except Exception as e:
                                        logger.debug(f"Fallback element click failed: {e}")
                                        continue
                                time.sleep(2.5)

                                # If data attrs were present, ensure progress was made
                                if loaded is not None and total is not None:
                                    # re-read loaded value
                                    loaded_after = _get_int_attr(el, 'data-loadedresult', 'data-loaded-result', 'data-loaded')
                                    logger.debug(f"loaded before={loaded}, after={loaded_after}")
                                    if loaded_after is None or loaded_after <= loaded:
                                        logger.warning("Fallback click did not increase loaded count; not continuing with fallback clicks")
                                        fallback_clicked = False
                                        # avoid infinite loop by counting as no-new-content
                                        no_new_content_count += 1
                                        continue

                                fallback_clicked = True
                                click_count += 1
                                view_more_found = True
                                break
                        except Exception:
                            continue

                    if fallback_clicked:
                        continue
                except Exception as e:
                    logger.debug(f"Fallback load-more attempt failed: {e}")
            
    except Exception as e:
        logger.error(f"Error during pagination: {e}")
    
    # Remove duplicates
    unique_urls = list(dict.fromkeys(all_urls))
    logger.info(f"Total unique articles found: {len(unique_urls)}")
    
    return unique_urls
