"""Scraper module for web scraping and PDF extraction"""

from .selenium_driver import setup_selenium, cleanup_selenium, safe_get
from .pdf_extractor import extract_pdf_content, is_pdf_url, download_and_parse_pdf
from .web_scraper import parse_country_report, scrape_reports, extract_country_from_card
from .rescraper import rescrape_high_relevance_articles

__all__ = [
    'setup_selenium',
    'cleanup_selenium',
    'safe_get',
    'extract_pdf_content',
    'is_pdf_url',
    'download_and_parse_pdf',
    'parse_country_report',
    'scrape_reports',
    'extract_country_from_card',
    'rescrape_high_relevance_articles'
]
