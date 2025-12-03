"""Re-scraping utilities for updating existing articles"""

import logging
from datetime import datetime

from src.database import get_db_connection, update_article_content
from src.utils.nlp_service import call_embedding_service
from .selenium_driver import setup_selenium, cleanup_selenium
from .web_scraper import parse_country_report

logger = logging.getLogger(__name__)


def rescrape_high_relevance_articles():
    """
    Find all articles with relevance >= 2, re-scrape them to try to get PDF content,
    and update the database and NLP embeddings if successful.
    
    Returns:
        list: List of updated article information dictionaries
    """
    logger.info("Starting re-scrape of high relevance articles...")
    
    # Setup selenium for PDF extraction
    setup_selenium()
    
    conn = get_db_connection()
    updated_articles = []
    
    try:
        with conn.cursor() as cur:
            # Find articles with relevance >= 2
            cur.execute("""
                SELECT a.id, a.url, a.country, a.article_type, ac.content
                FROM articles a
                LEFT JOIN article_content ac ON a.id = ac.article_id
                WHERE a.relevance >= 2 
                AND a.article_type IN ('publications')
                AND a.deleted = FALSE
                ORDER BY a.id
            """)
            
            articles = cur.fetchall()
            logger.info(f"Found {len(articles)} articles with relevance >= 2 to re-scrape")
            
            for i, (article_id, url, country, article_type, current_content) in enumerate(articles, 1):
                try:
                    logger.info(f"Processing {i}/{len(articles)}: Article ID {article_id} - {url}")
                    
                    # Check if content is already substantial (likely from PDF)
                    current_content_str = str(current_content or "")
                    if current_content and len(current_content_str.strip()) > 5000:
                        logger.info(f"Article {article_id} already has substantial content ({len(current_content_str)} chars), skipping")
                        continue
                    
                    # Re-scrape the article
                    article_data, raw_html = parse_country_report(url, article_type or "publications", country or "Unknown")
                    
                    if article_data and article_data.get("success") and article_data.get("content"):
                        new_content = article_data["content"]
                        
                        # Only update if we got significantly more content
                        current_content_len = len(current_content_str.strip())
                        new_content_len = len(new_content.strip())
                        if new_content_len > (current_content_len + 500):
                            logger.info(f"Article {article_id}: New content is significantly longer ({new_content_len} vs {current_content_len} chars), updating...")
                            
                            # Update the database
                            update_article_content(conn, article_id, new_content, raw_html)
                            
                            # Call NLP embedding service
                            embedding_success = call_embedding_service(article_id)
                            
                            updated_articles.append({
                                "article_id": article_id,
                                "url": url,
                                "country": country,
                                "old_content_length": current_content_len,
                                "new_content_length": new_content_len,
                                "content_source": article_data.get("content_source", "unknown"),
                                "embedded": embedding_success
                            })
                            
                            logger.info(f"✓ Updated article {article_id} with {new_content_len} characters of content")
                        else:
                            logger.info(f"Article {article_id}: New content not significantly longer, skipping update")
                    else:
                        logger.warning(f"✗ Failed to extract content from {url} for article {article_id}")
                        
                except Exception as e:
                    logger.error(f"Failed to re-scrape article {article_id} ({url}): {e}")
                    continue
                    
    finally:
        conn.close()
        cleanup_selenium()
        
    logger.info(f"Re-scraping completed. Updated {len(updated_articles)} articles.")
    return updated_articles
