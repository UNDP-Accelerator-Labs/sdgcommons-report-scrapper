"""Database operations for articles"""

import logging
from datetime import datetime, date

logger = logging.getLogger(__name__)


def article_exists(conn, url):
    """
    Check if article already exists in database.
    
    Args:
        conn: Database connection
        url: Article URL to check
        
    Returns:
        bool: True if article exists, False otherwise
    """
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM articles WHERE url = %s", (url,))
        return cur.fetchone() is not None


def get_existing_article(conn, url):
    """
    Return existing article id and article_type for a url, or None.
    
    Args:
        conn: Database connection
        url: Article URL to search for
        
    Returns:
        dict or None: Article info with 'id' and 'article_type' keys
    """
    with conn.cursor() as cur:
        cur.execute("SELECT id, article_type FROM articles WHERE url = %s", (url,))
        row = cur.fetchone()
        if row:
            return {"id": row[0], "article_type": row[1]}
        return None


def insert_article_to_db(conn, article_data, raw_html):
    """
    Insert article into database including country name.
    Creates records in articles, article_content, and raw_html tables.
    
    Args:
        conn: Database connection
        article_data: Dictionary containing article information
        raw_html: Raw HTML content of the article
        
    Returns:
        int: Article ID of the newly created record
    """
    try:
        with conn.cursor() as cur:
            conn.rollback()
            
            current_date = date.today()
            current_timestamp = datetime.now()
            
            # Check if country column exists, add if not
            try:
                cur.execute("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'articles' AND column_name = 'country'
                """)
                if not cur.fetchone():
                    cur.execute("ALTER TABLE articles ADD COLUMN country VARCHAR(100)")
                    logger.info("Added country column to articles table")
            except Exception as e:
                logger.warning(f"Error checking/adding country column: {e}")
            
            # Insert into articles table
            cur.execute("""
                INSERT INTO articles (
                    url, language, title, posted_date, posted_date_str, 
                    article_type, created_at, updated_at, deleted, has_lab,
                    lat, lng, privilege, rights, tags, country,
                    parsed_date, relevance, iso3
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                article_data["url"],
                article_data.get("language", "en"),
                article_data["title"],
                current_date,
                current_date.strftime('%Y-%m-%d'),
                article_data.get("report_type", "publication"),
                current_timestamp,
                current_timestamp,
                False,
                False,
                article_data.get("lat"),
                article_data.get("lng"),
                1,
                1,
                [article_data.get("report_type", ""), article_data.get("country", "")],
                article_data.get("country", "Unknown"),
                current_timestamp,
                2,
                article_data.get("iso3")
            ))
            
            article_id = cur.fetchone()[0]
            
            # Insert content
            cur.execute("""
                INSERT INTO article_content (article_id, content, created_at, updated_at)
                VALUES (%s, %s, %s, %s)
            """, (
                article_id,
                article_data.get("content", ""),
                current_timestamp,
                current_timestamp
            ))
            
            # Insert raw HTML
            cur.execute("""
                INSERT INTO raw_html (article_id, raw_html, created_at, updated_at)
                VALUES (%s, %s, %s, %s)
            """, (
                article_id,
                raw_html if raw_html is not None else article_data.get("content", ""),
                current_timestamp,
                current_timestamp
            ))
            
            conn.commit()
            logger.info(f"Successfully inserted article ID {article_id}: {article_data['title'][:50]}...")
            return article_id
            
    except Exception as e:
        logger.error(f"Failed to insert article into database: {e}")
        conn.rollback()
        raise


def update_article_content(conn, article_id, new_content, raw_html=None):
    """
    Update article content and raw_html for an existing article.
    
    Args:
        conn: Database connection
        article_id: ID of the article to update
        new_content: New content to set
        raw_html: Optional raw HTML to update
        
    Returns:
        bool: True if update successful
    """
    try:
        with conn.cursor() as cur:
            current_timestamp = datetime.now()
            
            # Update article_content
            cur.execute("""
                UPDATE article_content 
                SET content = %s, updated_at = %s 
                WHERE article_id = %s
            """, (new_content, current_timestamp, article_id))

            # Update html_content if exists
            cur.execute("""
                UPDATE article_html_content 
                SET html_content = %s, updated_at = %s 
                WHERE article_id = %s
            """, (new_content, current_timestamp, article_id))
            
            # Update raw_html 
            cur.execute("""
                UPDATE raw_html 
                SET raw_html = %s, updated_at = %s 
                WHERE article_id = %s
            """, (raw_html or new_content, current_timestamp, article_id))
            
            # Update the articles table's updated_at timestamp
            cur.execute("""
                UPDATE articles 
                SET updated_at = %s 
                WHERE id = %s
            """, (current_timestamp, article_id))
            
            conn.commit()
            logger.info(f"Successfully updated content for article ID {article_id}")
            return True
            
    except Exception as e:
        logger.error(f"Failed to update article content for ID {article_id}: {e}")
        conn.rollback()
        raise
