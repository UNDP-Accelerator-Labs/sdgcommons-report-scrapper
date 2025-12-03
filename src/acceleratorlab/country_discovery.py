"""Country discovery from UNDP global website"""

import logging
import re
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

from src.scraper import safe_get
from src.scraper.selenium_driver import driver, safe_get as safe_get_selenium

logger = logging.getLogger(__name__)

UNDP_BASE_URL = "https://www.undp.org/"


def discover_countries():
    """
    Dynamically discover all UNDP country offices from the global UNDP website.
    Uses the country office modal on the UNDP homepage.
    
    Returns:
        list: List of country dictionaries with name, slug, url
    """
    logger.info("Starting country discovery from UNDP website...")
    countries = []
    
    try:
        # Load UNDP homepage with Selenium to get the country office modal HTML
        safe_get_selenium(UNDP_BASE_URL)
        
        # Get page source after JavaScript has loaded
        page_source = driver.page_source
        soup = BeautifulSoup(page_source, "html.parser")
        
        # Find all country-item divs in the modal (same structure we documented)
        country_items = soup.find_all("div", class_="country-item")
        
        if not country_items:
            logger.warning("No country-item divs found, using fallback country list")
            return get_fallback_countries()
        
        logger.info(f"Found {len(country_items)} country office entries in modal")
        
        # Extract country offices
        for item in country_items:
            try:
                # Extract country name
                country_div = item.find("div", class_="country")
                if not country_div:
                    continue
                    
                country_name = country_div.get_text(strip=True)
                
                # Extract data-city-filters to check if it's a country office
                data_filters = item.get("data-city-filters", "")
                
                # Only include country offices (not regional offices)
                if "country_office" not in data_filters:
                    logger.debug(f"Skipping {country_name} - not a country office")
                    continue
                
                # Extract English URL (priority) from language links
                languages_div = item.find("div", class_="languages")
                if not languages_div:
                    continue
                
                country_url = None
                for link in languages_div.find_all("a", class_="text-link"):
                    lang_name = link.get_text(strip=True)
                    url = link.get("href", "")
                    
                    # Convert relative URLs to absolute
                    if url.startswith("/"):
                        url = f"https://www.undp.org{url}"
                    
                    # Prioritize English
                    if "english" in lang_name.lower():
                        country_url = url
                        break
                
                # If no English found, use first link
                if not country_url:
                    first_link = languages_div.find("a", class_="text-link")
                    if first_link:
                        url = first_link.get("href", "")
                        if url.startswith("/"):
                            url = f"https://www.undp.org{url}"
                        country_url = url
                
                if not country_url:
                    logger.warning(f"No URL found for {country_name}")
                    continue
                
                # Extract slug from URL
                parsed = urlparse(country_url)
                slug = parsed.path.strip("/").split("/")[0]
                
                # Add to countries list
                countries.append({
                    "name": country_name,
                    "slug": slug,
                    "url": country_url,
                    "blogs_url": f"{country_url}/blogs",
                    "publications_url": f"{country_url}/publications"
                })
                
            except Exception as e:
                logger.warning(f"Error parsing country item: {e}")
                continue
        
        logger.info(f"Discovered {len(countries)} country offices from modal")
        return countries
        
    except Exception as e:
        logger.error(f"Failed to discover countries: {e}")
        # Fallback: return a known sample set if discovery fails
        logger.warning("Using fallback sample country list")
        return get_fallback_countries()


def get_fallback_countries():
    """Fallback list of major UNDP country offices if discovery fails"""
    sample_countries = [
        "afghanistan", "albania", "algeria", "argentina", "armenia",
        "bangladesh", "bolivia", "brazil", "cambodia", "chile",
        "china", "colombia", "egypt", "ethiopia", "georgia",
        "ghana", "guatemala", "india", "indonesia", "iraq",
        "jordan", "kenya", "kyrgyzstan", "lebanon", "malawi",
        "mexico", "moldova", "mongolia", "morocco", "mozambique",
        "myanmar", "nepal", "nigeria", "pakistan", "palestine",
        "peru", "philippines", "rwanda", "senegal", "serbia",
        "somalia", "south-africa", "sudan", "tanzania", "thailand",
        "tunisia", "turkey", "uganda", "ukraine", "uzbekistan",
        "vietnam", "yemen", "zambia", "zimbabwe"
    ]
    
    countries = []
    for slug in sample_countries:
        name = slug.replace("-", " ").title()
        url = f"{UNDP_BASE_URL}{slug}"
        countries.append({
            "name": name,
            "slug": slug,
            "url": url,
            "blogs_url": f"{url}/blogs",
            "publications_url": f"{url}/publications"
        })
    
    return countries
