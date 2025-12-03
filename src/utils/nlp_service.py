"""NLP embedding service integration"""

import logging
import requests

from src.config import Settings

logger = logging.getLogger(__name__)


def call_embedding_service(article_id):
    """
    Call configured NLP embedding service to embed an article by DB id.
    
    Args:
        article_id: Database ID of the article to embed
        
    Returns:
        bool: True on success, False otherwise
    """
    if not Settings.has_nlp_service():
        logger.debug("Embedding service not configured - skipping embedding")
        return False

    body = {
        "token": Settings.API_TOKEN,
        "write_access": Settings.NLP_WRITE_TOKEN,
        "db": Settings.EMBEDDING_DB,
        "main_id": f"blog:{article_id}"
    }
    
    try:
        embed_url = Settings.NLP_API_URL.rstrip('/')
        r = requests.post(f"{embed_url}/api/embed/add", json=body, timeout=30)
        if r.ok:
            logger.info(f"Embedded article {article_id}")
            return True
        else:
            logger.warning(f"Embedding failed for {article_id}: {r.status_code} {r.text}")
            return False
    except Exception as e:
        logger.exception(f"Embedding error for {article_id}: {e}")
        return False
