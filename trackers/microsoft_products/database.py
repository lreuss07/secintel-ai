"""
Database module for SecIntel AI.
Handles SQLite database operations for storing and retrieving threat intelligence.
"""

import os
import sqlite3
import json
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Manages SQLite database operations for the CTI Aggregator"""
    
    def __init__(self, db_path):
        """
        Initialize the database manager.
        
        Args:
            db_path (str): Path to the SQLite database file
        """
        self.db_path = db_path
        # Ensure the directory exists
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        
    def get_connection(self):
        """
        Get a connection to the SQLite database.
        
        Returns:
            sqlite3.Connection: Database connection
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Return rows as dictionaries
        return conn
    
    def initialize_database(self):
        """
        Initialize the database schema if it doesn't exist.
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Create articles table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE,
                author TEXT,
                published_date TEXT,
                content TEXT NOT NULL,
                summary TEXT,
                scraped_date TEXT NOT NULL,
                analyzed_date TEXT
            )
            ''')
            
            # Create IOCs table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS iocs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_id INTEGER NOT NULL,
                type TEXT NOT NULL,
                value TEXT NOT NULL,
                context TEXT,
                FOREIGN KEY (article_id) REFERENCES articles (id),
                UNIQUE (article_id, type, value)
            )
            ''')
            
            # Create index on IOC values for faster lookups
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_ioc_value ON iocs (value)')
            
            # Create tags table for additional metadata
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_id INTEGER NOT NULL,
                tag TEXT NOT NULL,
                FOREIGN KEY (article_id) REFERENCES articles (id),
                UNIQUE (article_id, tag)
            )
            ''')
            
            conn.commit()
            logger.info("Database schema initialized successfully")
            return True
            
        except sqlite3.Error as e:
            logger.error(f"SQLite error during database initialization: {str(e)}")
            return False
        
        finally:
            if conn:
                conn.close()
    
    def store_article(self, article):
        """
        Store an article in the database.
        
        Args:
            article (dict): Article data containing:
                - source: Source name
                - title: Article title
                - url: Article URL
                - author: Author name (optional)
                - published_date: Publication date (optional)
                - content: Article content
                - tags: List of tags (optional)
        
        Returns:
            int: Article ID if successful, None otherwise
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Check if article already exists (by URL)
            cursor.execute('SELECT id FROM articles WHERE url = ?', (article['url'],))
            existing = cursor.fetchone()
            
            if existing:
                logger.info(f"Article already exists in database: {article['url']}")
                return existing['id']
            
            # Prepare article data
            current_time = datetime.now().isoformat()
            
            article_data = {
                'source': article['source'],
                'title': article['title'],
                'url': article['url'],
                'author': article.get('author', ''),
                'published_date': article.get('published_date', ''),
                'content': article['content'],
                'summary': None,  # Will be filled by AI summarizer
                'scraped_date': current_time,
                'analyzed_date': None
            }
            
            # Insert article
            cursor.execute('''
            INSERT INTO articles (source, title, url, author, published_date, content, 
                                summary, scraped_date, analyzed_date)
            VALUES (:source, :title, :url, :author, :published_date, :content, 
                    :summary, :scraped_date, :analyzed_date)
            ''', article_data)
            
            article_id = cursor.lastrowid
            
            # Store tags if provided
            if 'tags' in article and article['tags']:
                for tag in article['tags']:
                    cursor.execute('''
                    INSERT OR IGNORE INTO tags (article_id, tag)
                    VALUES (?, ?)
                    ''', (article_id, tag))
            
            # Add source-specific tags
            if article['source'] == 'Volexity Blog':
                # Common tags for Volexity articles
                default_tags = ['volexity', 'threat-research']
                for tag in default_tags:
                    cursor.execute('''
                    INSERT OR IGNORE INTO tags (article_id, tag)
                    VALUES (?, ?)
                    ''', (article_id, tag))
                
                # Try to extract threat actor names from title
                title_lower = article['title'].lower()
                actor_keywords = [
                    'apt', 'group', 'threat actor', 'campaign', 'operation',
                    'hackers', 'north korea', 'china', 'russia', 'iran', 'lazarus',
                    'conti', 'fin7', 'cozy bear', 'fancy bear', 'kimsuky', 'mustang panda'
                ]
                
                if any(keyword in title_lower for keyword in actor_keywords):
                    cursor.execute('''
                    INSERT OR IGNORE INTO tags (article_id, tag)
                    VALUES (?, ?)
                    ''', (article_id, 'apt-attribution'))
            
            conn.commit()
            logger.info(f"Stored article: {article['title']} (ID: {article_id})")
            return article_id
            
        except sqlite3.Error as e:
            logger.error(f"SQLite error storing article: {str(e)}")
            if conn:
                conn.rollback()
            return None
            
        finally:
            if conn:
                conn.close()
    
    def store_iocs(self, article_id, iocs):
        """
        Store IOCs associated with an article.
        
        Args:
            article_id (int): Article ID
            iocs (dict): Dictionary of IOCs by type
                {
                    'ip': [{'value': '1.2.3.4', 'context': 'C2 server'}],
                    'domain': [...],
                    'hash': [...]
                }
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            for ioc_type, ioc_list in iocs.items():
                for ioc in ioc_list:
                    cursor.execute('''
                    INSERT OR IGNORE INTO iocs (article_id, type, value, context)
                    VALUES (?, ?, ?, ?)
                    ''', (article_id, ioc_type, ioc['value'], ioc.get('context', '')))
            
            conn.commit()
            logger.info(f"Stored IOCs for article ID {article_id}")
            return True
            
        except sqlite3.Error as e:
            logger.error(f"SQLite error storing IOCs: {str(e)}")
            if conn:
                conn.rollback()
            return False
            
        finally:
            if conn:
                conn.close()
    
    def update_article_summary(self, article_id, summary):
        """
        Update an article with its AI-generated summary.
        
        Args:
            article_id (int): Article ID
            summary (str): AI-generated summary
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            current_time = datetime.now().isoformat()
            
            cursor.execute('''
            UPDATE articles
            SET summary = ?, analyzed_date = ?
            WHERE id = ?
            ''', (summary, current_time, article_id))
            
            conn.commit()
            logger.info(f"Updated summary for article ID {article_id}")
            return True
            
        except sqlite3.Error as e:
            logger.error(f"SQLite error updating article summary: {str(e)}")
            if conn:
                conn.rollback()
            return False
            
        finally:
            if conn:
                conn.close()
    
    def get_articles_without_summary(self):
        """
        Get articles that don't have an AI summary yet.
        
        Returns:
            list: List of article dictionaries
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
            SELECT id, source, title, url, author, published_date, content
            FROM articles
            WHERE summary IS NULL
            ORDER BY scraped_date ASC
            ''')
            
            articles = [dict(row) for row in cursor.fetchall()]
            logger.info(f"Retrieved {len(articles)} articles without summaries")
            return articles
            
        except sqlite3.Error as e:
            logger.error(f"SQLite error retrieving unsummarized articles: {str(e)}")
            return []
            
        finally:
            if conn:
                conn.close()
    
    def get_iocs_for_article(self, article_id):
        """
        Get all IOCs associated with an article.
        
        Args:
            article_id (int): Article ID
        
        Returns:
            dict: Dictionary of IOCs by type
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
            SELECT type, value, context
            FROM iocs
            WHERE article_id = ?
            ''', (article_id,))
            
            iocs = {}
            for row in cursor.fetchall():
                ioc_type = row['type']
                if ioc_type not in iocs:
                    iocs[ioc_type] = []
                    
                iocs[ioc_type].append({
                    'value': row['value'],
                    'context': row['context']
                })
                
            return iocs
            
        except sqlite3.Error as e:
            logger.error(f"SQLite error retrieving IOCs: {str(e)}")
            return {}
            
        finally:
            if conn:
                conn.close()
    
    def get_recent_articles_with_summary(self, days=30):
        """
        Get recent articles that have been summarized.

        Args:
            days (int): Number of days to look back (based on published_date)

        Returns:
            list: List of article dictionaries with summaries
        """
        try:
            from dateutil import parser as date_parser

            conn = self.get_connection()
            cursor = conn.cursor()

            cutoff_datetime = datetime.now() - timedelta(days=days)

            # Retrieve all articles with summaries (we'll filter by date in Python)
            cursor.execute('''
            SELECT id, source, title, url, author, published_date, content, summary, scraped_date, analyzed_date
            FROM articles
            WHERE summary IS NOT NULL
            ORDER BY published_date DESC
            ''')

            articles = []
            for row in cursor.fetchall():
                article = dict(row)

                # Filter out "What's New" whole-page articles without section anchors
                # These are landing pages that should have been parsed into monthly sections
                url = article.get('url', '')
                source = article.get('source', '').lower()
                if ('whats-new' in url.lower() or 'what-s-new' in url.lower()) and '#' not in url:
                    # This is a whole-page "What's New" article without a section anchor
                    # Skip it as it should have been parsed into monthly sections
                    logger.debug(f"Skipping whole-page What's New article {article['id']}: {url}")
                    continue

                # Parse published_date to determine if article is within time window
                try:
                    # Skip articles without a published_date (empty or None)
                    if not article['published_date'] or article['published_date'].strip() == '':
                        logger.debug(f"Article {article['id']} ('{article['title'][:50]}...') has no published_date - excluding from time-based filter")
                        continue

                    # Try to parse published_date (handles both ISO and RFC 2822 formats)
                    published_dt = date_parser.parse(article['published_date'])

                    # Convert to naive datetime for comparison (remove timezone info)
                    if published_dt.tzinfo is not None:
                        # Convert to UTC naive datetime
                        published_dt_naive = published_dt.replace(tzinfo=None) - published_dt.utcoffset()
                    else:
                        published_dt_naive = published_dt

                    # Check if article was published within the time window
                    if published_dt_naive >= cutoff_datetime:
                        # Add IOCs to each article
                        article['iocs'] = self.get_iocs_for_article(article['id'])
                        articles.append(article)
                    else:
                        logger.debug(f"Article {article['id']} published {published_dt_naive.strftime('%Y-%m-%d')} is outside {days}-day window (cutoff: {cutoff_datetime.strftime('%Y-%m-%d')})")
                except (ValueError, TypeError) as e:
                    # If published_date can't be parsed, skip the article (don't include it)
                    logger.warning(f"Could not parse published_date '{article['published_date']}' for article {article['id']} ('{article['title'][:50]}...') - excluding from report")
                    continue

            logger.info(f"Retrieved {len(articles)} recent articles with summaries (published within last {days} days)")
            return articles

        except sqlite3.Error as e:
            logger.error(f"SQLite error retrieving recent articles: {str(e)}")
            return []

        finally:
            if conn:
                conn.close()
    
    def search_by_ioc(self, ioc_value):
        """
        Search for articles containing a specific IOC.
        
        Args:
            ioc_value (str): IOC value to search for
        
        Returns:
            list: List of article dictionaries containing the IOC
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
            SELECT a.id, a.source, a.title, a.url, a.author, a.published_date, 
                   a.summary, a.scraped_date, i.type, i.value, i.context
            FROM articles a
            JOIN iocs i ON a.id = i.article_id
            WHERE i.value LIKE ?
            ORDER BY a.scraped_date DESC
            ''', (f'%{ioc_value}%',))
            
            results = {}
            for row in cursor.fetchall():
                article_id = row['id']
                
                if article_id not in results:
                    results[article_id] = {
                        'id': article_id,
                        'source': row['source'],
                        'title': row['title'],
                        'url': row['url'],
                        'author': row['author'],
                        'published_date': row['published_date'],
                        'summary': row['summary'],
                        'scraped_date': row['scraped_date'],
                        'iocs': {}
                    }
                
                # Add IOC to the article
                ioc_type = row['type']
                if ioc_type not in results[article_id]['iocs']:
                    results[article_id]['iocs'][ioc_type] = []
                    
                results[article_id]['iocs'][ioc_type].append({
                    'value': row['value'],
                    'context': row['context']
                })
            
            return list(results.values())
            
        except sqlite3.Error as e:
            logger.error(f"SQLite error searching for IOC: {str(e)}")
            return []
            
        finally:
            if conn:
                conn.close()
