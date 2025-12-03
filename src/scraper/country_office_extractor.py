"""
Extract country offices and their URLs from UNDP homepage.

This module parses the country switcher modal on https://www.undp.org/
to extract all country offices with their URLs, prioritizing English language pages.
"""

import logging
from typing import List, Dict, Any
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def extract_country_offices_from_html(html_content: str) -> List[Dict[str, Any]]:
    """
    Extract country offices and URLs from UNDP homepage HTML.
    
    The country switcher modal contains a list of all country offices with:
    - Country name
    - Language-specific URLs
    - Region classification
    - Office type (country_office, regional_office, policy_centre, representation_office)
    
    Args:
        html_content: HTML content of the UNDP homepage
        
    Returns:
        list: Country office data dictionaries with structure:
            {
                "name": "Afghanistan",
                "url": "https://www.undp.org/afghanistan",
                "languages": [
                    {"lang": "English", "url": "https://www.undp.org/afghanistan"},
                    {"lang": "Français", "url": "https://www.undp.org/fr/afghanistan"}
                ],
                "region": "asia-and-the-pacific",
                "office_type": "country_office",
                "data_filters": "afghanistan asia-and-the-pacific country_office"
            }
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    country_offices = []
    
    # Find all country-item divs in the modal
    country_items = soup.find_all("div", class_="country-item")
    
    logger.info(f"Found {len(country_items)} country office entries")
    
    for item in country_items:
        try:
            # Extract country name
            country_div = item.find("div", class_="country")
            if not country_div:
                continue
                
            country_name = country_div.get_text(strip=True)
            
            # Extract data-city-filters attribute for region and office type
            data_filters = item.get("data-city-filters", "")
            filters_parts = data_filters.split()
            
            # Parse filters: first part is normalized country name, second is region, third is office type
            region = None
            office_type = None
            if len(filters_parts) >= 2:
                region = filters_parts[1]
            if len(filters_parts) >= 3:
                office_type = filters_parts[2]
            
            # Extract all language links
            languages_div = item.find("div", class_="languages")
            if not languages_div:
                continue
                
            language_links = []
            for link in languages_div.find_all("a", class_="text-link"):
                lang_name = link.get_text(strip=True)
                # Remove "SVG icon" text if present
                if "link is external" in lang_name.lower():
                    lang_name = lang_name.split("(")[0].strip()
                
                url = link.get("href", "")
                
                # Convert relative URLs to absolute
                if url.startswith("/"):
                    url = f"https://www.undp.org{url}"
                
                language_links.append({
                    "lang": lang_name,
                    "url": url
                })
            
            if not language_links:
                logger.warning(f"No language links found for {country_name}")
                continue
            
            # Prioritize English URL
            primary_url = None
            for lang_link in language_links:
                if "english" in lang_link["lang"].lower():
                    primary_url = lang_link["url"]
                    break
            
            # If no English found, use first available
            if not primary_url and language_links:
                primary_url = language_links[0]["url"]
            
            country_office = {
                "name": country_name,
                "url": primary_url,
                "languages": language_links,
                "region": region,
                "office_type": office_type,
                "data_filters": data_filters
            }
            
            country_offices.append(country_office)
            
        except Exception as e:
            logger.error(f"Error extracting country office: {e}", exc_info=True)
            continue
    
    logger.info(f"Successfully extracted {len(country_offices)} country offices")
    return country_offices


def filter_country_offices(
    country_offices: List[Dict[str, Any]],
    regions: List[str] = None,
    office_types: List[str] = None,
    exclude_representation: bool = False
) -> List[Dict[str, Any]]:
    """
    Filter country offices by region and office type.
    
    Args:
        country_offices: List of country office dictionaries
        regions: List of regions to include (e.g., ["africa", "asia-and-the-pacific"])
        office_types: List of office types to include (e.g., ["country_office"])
        exclude_representation: If True, exclude representation offices
        
    Returns:
        list: Filtered country offices
    """
    filtered = country_offices
    
    if regions:
        filtered = [
            office for office in filtered
            if office.get("region") in regions
        ]
    
    if office_types:
        filtered = [
            office for office in filtered
            if office.get("office_type") in office_types
        ]
    
    if exclude_representation:
        filtered = [
            office for office in filtered
            if office.get("office_type") != "representation_office"
        ]
    
    return filtered


def get_country_offices_only(country_offices: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Get only actual country offices (exclude regional, policy centres, representation).
    
    Args:
        country_offices: List of all offices
        
    Returns:
        list: Only country offices
    """
    return filter_country_offices(
        country_offices,
        office_types=["country_office"]
    )


def get_country_office_by_name(
    country_offices: List[Dict[str, Any]],
    country_name: str
) -> Dict[str, Any]:
    """
    Find a specific country office by name (case-insensitive).
    
    Args:
        country_offices: List of country office dictionaries
        country_name: Name to search for
        
    Returns:
        dict: Country office data or None if not found
    """
    country_name_lower = country_name.lower()
    
    for office in country_offices:
        if office["name"].lower() == country_name_lower:
            return office
    
    return None


def print_country_offices_summary(country_offices: List[Dict[str, Any]]) -> None:
    """
    Print a summary of country offices by region and type.
    
    Args:
        country_offices: List of country office dictionaries
    """
    # Count by region
    region_counts = {}
    for office in country_offices:
        region = office.get("region", "unknown")
        region_counts[region] = region_counts.get(region, 0) + 1
    
    # Count by office type
    type_counts = {}
    for office in country_offices:
        office_type = office.get("office_type", "unknown")
        type_counts[office_type] = type_counts.get(office_type, 0) + 1
    
    print("\n" + "="*60)
    print("UNDP COUNTRY OFFICES SUMMARY")
    print("="*60)
    print(f"\nTotal offices: {len(country_offices)}")
    
    print("\nBy Region:")
    for region, count in sorted(region_counts.items()):
        print(f"  {region}: {count}")
    
    print("\nBy Office Type:")
    for office_type, count in sorted(type_counts.items()):
        print(f"  {office_type}: {count}")
    
    print("\n" + "="*60 + "\n")
