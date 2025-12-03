"""Application settings and environment configuration"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class Settings:
    """Centralized configuration settings"""
    
    # Database configuration
    DB_HOST = os.getenv("DB_HOST", "")
    DB_PORT = os.getenv("DB_PORT", "5432")
    DB_NAME = os.getenv("DB_NAME", "")
    DB_USER = os.getenv("DB_USER", "")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    
    # Application configuration
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
    PORT = int(os.getenv("PORT", "8000"))
    
    # Security
    SAVE_API_KEY = os.getenv("SAVE_API_KEY", "")
    
    # Scraper configuration
    SCRAPER_STATUS_FILE = os.getenv("SCRAPER_STATUS_FILE", "/tmp/sdg_scraper_status.json")
    REPORT_URLS = [
        "https://www.undp.org/digital/aila",
        "https://www.undp.org/digital/dra"
    ]
    
    # Selenium configuration
    CHROMEDRIVER_PATH = os.getenv("CHROMEDRIVER_PATH", None)
    CHROME_BIN = os.getenv("CHROME_BIN", "/usr/bin/chromium")
    
    # Geocoding configuration
    GEOCODING_USER_AGENT = os.getenv("GEOCODING_USER_AGENT", "undp-reports-scraper-this-pama")
    
    # NLP Embedding service (optional)
    NLP_API_URL = os.getenv("NLP_API_URL", None)
    NLP_WRITE_TOKEN = os.getenv("NLP_WRITE_TOKEN", None)
    API_TOKEN = os.getenv("API_TOKEN", None)
    EMBEDDING_DB = os.getenv("EMBEDDING_DB", None)
    
    # HTTP Headers
    DEFAULT_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.undp.org/",
        "Connection": "keep-alive",
    }
    
    @classmethod
    def is_production(cls):
        """Check if running in production mode"""
        return cls.ENVIRONMENT == "production"
    
    @classmethod
    def has_nlp_service(cls):
        """Check if NLP embedding service is configured"""
        return all([cls.NLP_API_URL, cls.NLP_WRITE_TOKEN, cls.API_TOKEN, cls.EMBEDDING_DB])
