"""
Scraper module for the CTI Aggregator.
Handles scraping of threat intelligence from various sources.
"""

import logging
import time
import random
import requests
import feedparser
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import urllib.parse

logger = logging.getLogger(__name__)

class ThreatIntelScraper:
    """Scrapes threat intelligence from various sources"""
    
    def __init__(self, sources_config, time_window_days=None):
        """
        Initialize the scraper with source configurations.

        Args:
            sources_config (list): List of source configurations
            time_window_days (int, optional): Global time window override - only scrape articles from last N days
        """
        self.sources = sources_config
        self.time_window_days = time_window_days
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Safari/605.1.15',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:90.0) Gecko/20100101 Firefox/90.0'
        ]
    
    def get_random_user_agent(self):
        """
        Get a random user agent to avoid being blocked.
        
        Returns:
            str: Random user agent string
        """
        return random.choice(self.user_agents)
    
    def make_request(self, url, headers=None):
        """
        Make a request to a URL with proper error handling.
        
        Args:
            url (str): URL to request
            headers (dict, optional): HTTP headers
            
        Returns:
            requests.Response or None: Response object if successful, None otherwise
        """
        if not headers:
            headers = {'User-Agent': self.get_random_user_agent()}
            
        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            logger.error(f"Request error for {url}: {str(e)}")
            return None
    
    def scrape_all_sources(self):
        """
        Scrape all configured sources.
        
        Returns:
            dict: Dictionary of articles by source
                {
                    'source_name': [article1, article2, ...],
                    ...
                }
        """
        results = {}
        
        for source in self.sources:
            source_name = source['name']
            logger.info(f"Scraping source: {source_name}")
            
            # Determine scraping method based on source type
            if source['type'] == 'rss':
                articles = self.scrape_rss_feed(source)
            elif source['type'] == 'web':
                articles = self.scrape_web_page(source)
            else:
                logger.warning(f"Unsupported source type: {source['type']}")
                continue
            
            results[source_name] = articles
            
            # Be nice to the servers
            time.sleep(random.uniform(1, 3))
        
        return results
    
    def scrape_rss_feed(self, source_config):
        """
        Scrape articles from an RSS feed.

        Args:
            source_config (dict): Source configuration

        Returns:
            list: List of article dictionaries
        """
        articles = []

        try:
            feed_url = source_config['feed_url']
            feed = feedparser.parse(feed_url)

            if not feed.entries:
                logger.warning(f"No entries found in feed: {feed_url}")
                return articles

            logger.info(f"Found {len(feed.entries)} entries in feed: {feed_url}")

            # Limit articles per source (default 50, configurable per source)
            max_articles = source_config.get('max_articles', 50)

            # Date filtering - use global time_window_days if set, otherwise use per-source config
            if self.time_window_days is not None:
                max_age_days = self.time_window_days
            else:
                max_age_days = source_config.get('max_age_days', 30)
            cutoff_date = datetime.now() - timedelta(days=max_age_days)
            logger.info(f"Filtering articles to last {max_age_days} days (cutoff: {cutoff_date.strftime('%Y-%m-%d')})")

            articles_processed = 0
            articles_skipped_old = 0

            for entry in feed.entries:
                # Check if we've hit the article limit
                if articles_processed >= max_articles:
                    logger.info(f"Reached max_articles limit ({max_articles}) for {source_config['name']}")
                    break
                # Check article age if published_date is available
                published_date = None
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    try:
                        published_date = datetime(*entry.published_parsed[:6])
                        if published_date < cutoff_date:
                            articles_skipped_old += 1
                            continue
                    except (TypeError, ValueError):
                        pass  # If date parsing fails, include the article

                # Extract basic info from feed
                article = {
                    'source': source_config['name'],
                    'title': entry.title,
                    'url': entry.link,
                    'author': entry.get('author', ''),
                    'published_date': entry.get('published', ''),
                    'tags': [tag.term for tag in entry.get('tags', [])] if hasattr(entry, 'tags') else []
                }

                # Get full content
                if 'content' in entry:
                    # Some feeds include full content
                    article['content'] = entry.content[0].value
                elif hasattr(entry, 'summary'):
                    # Some feeds include summaries that might contain partial content
                    article['content'] = entry.summary

                    # Only fetch full article if summary is very short (< 500 chars)
                    # Most RSS feeds provide adequate summaries for AI analysis
                    if len(article['content']) < 500:
                        full_content = self.fetch_article_content(article['url'], source_config)
                        if full_content and len(full_content) > len(article['content']):
                            article['content'] = full_content
                else:
                    # No summary available, try to fetch the full article
                    article['content'] = self.fetch_article_content(article['url'], source_config)

                    # If fetch failed but we have a title, create minimal content
                    if not article['content']:
                        article['content'] = f"Article: {article['title']}"

                articles.append(article)
                articles_processed += 1

            # Log filtering summary
            if articles_skipped_old > 0:
                logger.info(f"Skipped {articles_skipped_old} articles older than {max_age_days} days from {source_config['name']}")

            logger.info(f"Scraped {len(articles)} articles from {source_config['name']}")

        except Exception as e:
            logger.error(f"Error scraping RSS feed {source_config['feed_url']}: {str(e)}")

        return articles
    
    def scrape_web_page(self, source_config):
        """
        Scrape articles from a web page.
        
        Args:
            source_config (dict): Source configuration
            
        Returns:
            list: List of article dictionaries
        """
        articles = []
        
        try:
            url = source_config['url']
            response = self.make_request(url)
            
            if not response:
                return articles
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract article links based on source-specific selectors
            article_selector = source_config.get('article_selector', 'a')
            article_links = soup.select(article_selector)
            
            for link in article_links:
                href = link.get('href')
                
                if not href:
                    continue
                
                # Make absolute URL if relative
                if not href.startswith(('http://', 'https://')):
                    href = urllib.parse.urljoin(url, href)
                
                # Skip non-article links
                if not self.is_article_url(href, source_config):
                    continue
                
                # Basic article info
                article = {
                    'source': source_config['name'],
                    'title': link.text.strip() if link.text else 'Unknown Title',
                    'url': href,
                    'tags': []
                }
                
                # Fetch full article content
                article['content'] = self.fetch_article_content(href, source_config)
                
                # Skip if no content was retrieved
                if not article['content']:
                    continue
                
                articles.append(article)
            
        except Exception as e:
            logger.error(f"Error scraping web page {source_config['url']}: {str(e)}")
        
        return articles
    
    def fetch_article_content(self, url, source_config):
        """
        Fetch the full content of an article.

        Args:
            url (str): Article URL
            source_config (dict): Source configuration

        Returns:
            str: Article content or empty string if failed
        """
        try:
            response = self.make_request(url)

            if not response:
                return ""

            soup = BeautifulSoup(response.text, 'html.parser')

            # Try source-specific content selector first, then common fallbacks
            selectors = [
                source_config.get('content_selector'),
                'article',
                'div.article-content',
                'div.post-content',
                'div.entry-content',
                'div.content',
                'main article',
                'main',
                'div[class*="article"]',
                'div[class*="post"]',
                'div[class*="content"]'
            ]

            content_element = None
            for selector in selectors:
                if selector:
                    content_element = soup.select_one(selector)
                    if content_element:
                        break

            if not content_element:
                logger.debug(f"Content element not found for {url}, using RSS summary")
                return ""

            # Remove script, style, iframe, and navigation elements
            for element in content_element.select('script, style, iframe, nav, header, footer, aside, .advertisement, .ad'):
                element.decompose()

            return content_element.get_text(separator='\n').strip()

        except Exception as e:
            logger.debug(f"Error fetching article content from {url}: {str(e)}")
            return ""
    
    def is_article_url(self, url, source_config):
        """
        Check if a URL is likely to be an article.
        
        Args:
            url (str): URL to check
            source_config (dict): Source configuration
            
        Returns:
            bool: True if URL is likely an article, False otherwise
        """
        # Check if URL matches any include patterns
        if 'url_include_patterns' in source_config:
            return any(pattern in url for pattern in source_config['url_include_patterns'])
        
        # Check if URL matches any exclude patterns
        if 'url_exclude_patterns' in source_config:
            return not any(pattern in url for pattern in source_config['url_exclude_patterns'])
        
        # Default to assuming it's an article
        return True
