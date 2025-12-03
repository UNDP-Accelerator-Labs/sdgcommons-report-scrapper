"""Geocoding utilities for country location data"""

import logging
import time
import pycountry
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable

from src.config import Settings

logger = logging.getLogger(__name__)

# Initialize geocoder
geolocator = Nominatim(user_agent=Settings.GEOCODING_USER_AGENT)

# Cache for geocoding results to avoid repeated API calls
geocoding_cache = {}


def get_country_info(country_name):
    """
    Get country ISO3 code, lat, lng from country name using automatic geocoding.
    Results are cached to minimize API calls.
    
    Args:
        country_name: Name of the country to geocode
        
    Returns:
        tuple: (iso3_code, latitude, longitude) or (None, None, None) if failed
    """
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
        # Get ISO3 code from pycountry
        try:
            country = pycountry.countries.search_fuzzy(country_name)[0]
            iso3 = country.alpha_3
            logger.debug(f"Found ISO3 for {country_name}: {iso3}")
        except:
            logger.warning(f"Could not find ISO3 code for: {country_name}")
        
        # Geocode to get coordinates
        try:
            logger.debug(f"Geocoding country: {country_name}")
            location = geolocator.geocode(country_name, timeout=10)
            
            if location:
                lat = location.latitude
                lng = location.longitude
                logger.info(f"Geocoded {country_name}: {lat}, {lng}")
            else:
                logger.warning(f"Could not geocode: {country_name}")
                
            # Respect rate limit: 1 request per second
            time.sleep(1)
            
        except (GeocoderTimedOut, GeocoderUnavailable) as e:
            logger.warning(f"Geocoding failed for {country_name}: {e}")
        except Exception as e:
            logger.error(f"Unexpected geocoding error for {country_name}: {e}")
        
        # Cache the result
        geocoding_cache[clean_name] = {
            "iso3": iso3,
            "lat": lat,
            "lng": lng
        }
        
        return iso3, lat, lng
        
    except Exception as e:
        logger.error(f"Error getting country info for {country_name}: {e}")
        return None, None, None
