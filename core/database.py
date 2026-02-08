"""
Database module for SecIntel AI tracker system.
Handles SQLite database operations with multi-tracker support.
"""

import os
import sqlite3
import json
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Manages SQLite database operations with tag support and multi-tracker functionality"""

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

            # Create trackers table for multi-tracker support
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS trackers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                display_name TEXT,
                enabled BOOLEAN DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            ''')

            # Create articles table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tracker_name TEXT,
                source TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                author TEXT,
                published_date TEXT,
                content TEXT NOT NULL,
                summary TEXT,
                content_type TEXT,
                scraped_date TEXT NOT NULL,
                analyzed_date TEXT,
                provider TEXT,
                product TEXT,
                UNIQUE(tracker_name, url)
            )
            ''')

            # Add provider and product columns if they don't exist (migration)
            try:
                cursor.execute('ALTER TABLE articles ADD COLUMN provider TEXT')
            except sqlite3.OperationalError:
                pass  # Column already exists
            try:
                cursor.execute('ALTER TABLE articles ADD COLUMN product TEXT')
            except sqlite3.OperationalError:
                pass  # Column already exists

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
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_articles_tracker ON articles (tracker_name)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_articles_scraped ON articles (scraped_date)')

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

            cursor.execute('CREATE INDEX IF NOT EXISTS idx_tags_article ON tags (article_id)')

            conn.commit()
            logger.info("Database schema initialized successfully")
            return True

        except sqlite3.Error as e:
            logger.error(f"SQLite error during database initialization: {str(e)}")
            return False

        finally:
            if conn:
                conn.close()

    def register_tracker(self, name, display_name):
        """
        Register a tracker in the database.

        Args:
            name (str): Internal tracker name
            display_name (str): Display name for reports

        Returns:
            bool: True if successful
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute('''
            INSERT OR IGNORE INTO trackers (name, display_name)
            VALUES (?, ?)
            ''', (name, display_name))

            conn.commit()
            return True

        except sqlite3.Error as e:
            logger.error(f"Error registering tracker: {e}")
            return False
        finally:
            if conn:
                conn.close()

    def store_article(self, article, tracker_name=None):
        """
        Store an article in the database.

        Args:
            article (dict): Article data with keys: source, title, url, content, etc.
            tracker_name (str): Name of the tracker (optional, for backwards compatibility)

        Returns:
            int or None: Article ID if successful, None if article already exists or error
        """
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            current_time = datetime.now().isoformat()

            # Ensure content is a string (convert dict/list to JSON if needed)
            content = article['content']
            if isinstance(content, (dict, list)):
                content = json.dumps(content)
            elif not isinstance(content, str):
                content = str(content)

            # Ensure published_date is a string
            published_date = article.get('published_date', '')
            if isinstance(published_date, (dict, list)):
                published_date = json.dumps(published_date)
            elif not isinstance(published_date, str):
                published_date = str(published_date)

            cursor.execute('''
            INSERT INTO articles (tracker_name, source, title, url, author, published_date, content, scraped_date, provider, product)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                tracker_name,
                article['source'],
                article['title'],
                article['url'],
                article.get('author', ''),
                published_date,
                content,
                current_time,
                article.get('provider', ''),
                article.get('product', '')
            ))

            article_id = cursor.lastrowid
            conn.commit()
            logger.info(f"Stored article: {article['title']} (ID: {article_id})")
            return article_id

        except sqlite3.IntegrityError:
            # Article already exists (duplicate URL)
            logger.info(f"Article already exists in database: {article['url']}")
            return None

        except sqlite3.Error as e:
            logger.error(f"SQLite error storing article: {str(e)}")
            if conn:
                conn.rollback()
            return None

        finally:
            if conn:
                conn.close()

    def store_tag(self, article_id, tag):
        """
        Store a tag associated with an article.

        Args:
            article_id (int): Article ID
            tag (str): Tag value (e.g., update type, product name)

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute('''
            INSERT OR IGNORE INTO tags (article_id, tag)
            VALUES (?, ?)
            ''', (article_id, tag))

            conn.commit()
            logger.debug(f"Stored tag '{tag}' for article ID {article_id}")
            return True

        except sqlite3.Error as e:
            logger.error(f"SQLite error storing tag: {str(e)}")
            if conn:
                conn.rollback()
            return False

        finally:
            if conn:
                conn.close()

    def get_tags_for_article(self, article_id):
        """
        Get all tags associated with an article.

        Args:
            article_id (int): Article ID

        Returns:
            list: List of tag dictionaries [{'id': 1, 'tag': 'Feature Update'}, ...]
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute('''
            SELECT id, tag
            FROM tags
            WHERE article_id = ?
            ORDER BY tag
            ''', (article_id,))

            tags = [dict(row) for row in cursor.fetchall()]
            return tags

        except sqlite3.Error as e:
            logger.error(f"SQLite error retrieving tags: {str(e)}")
            return []

        finally:
            if conn:
                conn.close()

    def store_iocs(self, article_id, iocs):
        """
        Store IOCs associated with an article.

        Args:
            article_id (int): Article ID
            iocs (dict): Dictionary of IOCs by type

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

    def get_iocs_for_article(self, article_id):
        """
        Get all IOCs associated with an article.

        Args:
            article_id (int): Article ID

        Returns:
            dict: Dictionary of IOCs grouped by type
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute('''
            SELECT type, value, context
            FROM iocs
            WHERE article_id = ?
            ORDER BY type, value
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

    def update_article_summary(self, article_id, summary, content_type=None):
        """
        Update an article with its AI-generated summary and content type.

        Args:
            article_id (int): Article ID
            summary (str): AI-generated summary
            content_type (str, optional): Content classification type

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            current_time = datetime.now().isoformat()

            if content_type:
                cursor.execute('''
                UPDATE articles
                SET summary = ?, content_type = ?, analyzed_date = ?
                WHERE id = ?
                ''', (summary, content_type, current_time, article_id))
            else:
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

    def get_articles_without_summary(self, tracker_name=None):
        """
        Get articles that don't have an AI summary yet.

        Args:
            tracker_name (str): Filter by tracker name (optional)

        Returns:
            list: List of article dictionaries
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            if tracker_name:
                cursor.execute('''
                SELECT id, source, title, url, author, published_date, content
                FROM articles
                WHERE summary IS NULL AND tracker_name = ?
                ORDER BY scraped_date ASC
                ''', (tracker_name,))
            else:
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
            logger.error(f"SQLite error retrieving articles without summary: {str(e)}")
            return []

        finally:
            if conn:
                conn.close()

    def get_recent_articles_with_summary(self, days=30, tracker_name=None):
        """
        Get recent articles that have been analyzed (have summaries).

        Args:
            days (int): Number of days to look back (based on published_date)
            tracker_name (str): Filter by tracker name (optional)

        Returns:
            list: List of article dictionaries with IOCs included
        """
        try:
            from dateutil import parser as date_parser

            conn = self.get_connection()
            cursor = conn.cursor()

            cutoff_datetime = datetime.now() - timedelta(days=days)

            # Retrieve all articles with summaries (we'll filter by date in Python)
            if tracker_name:
                cursor.execute('''
                SELECT id, source, title, url, author, published_date, content, summary, scraped_date, analyzed_date, provider, product
                FROM articles
                WHERE summary IS NOT NULL
                AND tracker_name = ?
                ORDER BY COALESCE(published_date, scraped_date) DESC
                ''', (tracker_name,))
            else:
                cursor.execute('''
                SELECT id, source, title, url, author, published_date, content, summary, scraped_date, analyzed_date, provider, product
                FROM articles
                WHERE summary IS NOT NULL
                ORDER BY COALESCE(published_date, scraped_date) DESC
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
                # Fall back to scraped_date if published_date is NULL
                try:
                    date_to_use = None
                    date_source = None

                    # Try published_date first
                    if article['published_date'] and article['published_date'].strip() != '':
                        try:
                            date_to_use = date_parser.parse(article['published_date'])
                            date_source = 'published'
                        except (ValueError, TypeError):
                            pass

                    # Fall back to scraped_date if published_date is not available
                    if date_to_use is None and article['scraped_date']:
                        try:
                            date_to_use = date_parser.parse(article['scraped_date'])
                            date_source = 'scraped'
                        except (ValueError, TypeError):
                            pass

                    # Skip if we couldn't parse any date
                    if date_to_use is None:
                        logger.debug(f"Article {article['id']} has no parseable date - excluding")
                        continue

                    # Convert to naive datetime for comparison (remove timezone info)
                    if date_to_use.tzinfo is not None:
                        # Convert to UTC naive datetime
                        date_naive = date_to_use.replace(tzinfo=None) - date_to_use.utcoffset()
                    else:
                        date_naive = date_to_use

                    # Check if article is within the time window
                    if date_naive >= cutoff_datetime:
                        # Add IOCs and tags to each article
                        article['iocs'] = self.get_iocs_for_article(article['id'])
                        article['tags'] = self.get_tags_for_article(article['id'])
                        articles.append(article)
                        if date_source == 'scraped':
                            logger.debug(f"Article {article['id']} using scraped_date (no published_date)")
                    else:
                        logger.debug(f"Article {article['id']} dated {date_naive.strftime('%Y-%m-%d')} is outside {days}-day window")
                except Exception as e:
                    logger.warning(f"Error processing article {article['id']}: {str(e)}")
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
