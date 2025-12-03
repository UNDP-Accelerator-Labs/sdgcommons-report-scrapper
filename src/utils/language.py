"""Language detection utilities"""

import logging
from langdetect import detect, DetectorFactory

# Set seed for consistent language detection
DetectorFactory.seed = 0

logger = logging.getLogger(__name__)


def detect_language(text):
    """
    Detect language of text content.
    
    Args:
        text: Text content to analyze
        
    Returns:
        str: ISO 639-1 language code (e.g., 'en', 'fr') or 'en' as default
    """
    if not text or len(text.strip()) < 50:
        return "en"
    
    try:
        sample_text = text[:1000].strip()
        detected_lang = detect(sample_text)
        logger.debug(f"Detected language: {detected_lang}")
        return detected_lang
    except Exception as e:
        logger.warning(f"Language detection failed: {e}")
        return "en"
