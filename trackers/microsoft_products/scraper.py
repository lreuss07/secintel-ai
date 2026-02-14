"""
Enhanced scraper module for Microsoft Defender Update Tracking.
Extends the base scraper with Defender-specific filtering.
"""

import logging
import time
import random
import requests
import feedparser
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import urllib.parse
import re
import json
from dateutil import parser as date_parser

logger = logging.getLogger(__name__)

class MicrosoftSecurityProductScraper:
    """Scrapes Microsoft Security Product updates from various sources with intelligent filtering"""

    # Microsoft security product keywords for filtering
    SECURITY_PRODUCT_KEYWORDS = [
        # Identity & Access
        'entra', 'entra id', 'azure ad', 'azure active directory', 'identity protection',
        'conditional access', 'privileged identity management', 'pim',

        # Endpoint Management
        'intune', 'endpoint manager', 'mem', 'autopilot', 'windows autopilot',
        'mobile device management', 'mdm', 'mobile application management', 'mam',

        # Data Governance & Compliance
        'purview', 'compliance', 'data loss prevention', 'dlp', 'information protection',
        'sensitivity labels', 'retention', 'ediscovery', 'insider risk',

        # Microsoft 365 Security
        'microsoft 365', 'm365', 'office 365', 'o365', 'exchange online protection',
        'sharepoint security', 'safe attachments', 'safe links',

        # Microsoft Teams
        'microsoft teams', 'teams', 'teams admin', 'teams security', 'teams compliance',
        'teams policies', 'teams meeting',

        # SharePoint
        'sharepoint', 'sharepoint online', 'sharepoint server', 'sharepoint security',
        'document library', 'site collection', 'sharepoint admin',

        # Exchange
        'exchange online', 'exchange server', 'exchange admin', 'exchange security',
        'mailbox', 'email security', 'exchange protection', 'transport rules',

        # Windows Security
        'windows security', 'windows 11', 'windows hello', 'bitlocker', 'secure boot',
        'credential guard', 'device guard', 'application control',

        # AI-Powered Security
        'security copilot', 'copilot for security', 'microsoft copilot',

        # General security terms
        'security update', 'security patch', 'vulnerability', 'authentication',
        'authorization', 'zero trust', 'threat protection'
    ]
    
    def __init__(self, sources_config, time_window_days=None, max_articles_per_source=None):
        """
        Initialize the scraper with source configurations.

        Args:
            sources_config (list): List of source configurations
            time_window_days (int, optional): Only scrape articles from the last N days
            max_articles_per_source (int, optional): Max articles to scrape per source (testing mode)
        """
        self.sources = sources_config
        self.time_window_days = time_window_days
        self.max_articles_per_source = max_articles_per_source
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Safari/605.1.15',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:90.0) Gecko/20100101 Firefox/90.0'
        ]
    
    def get_random_user_agent(self):
        """Get a random user agent to avoid being blocked."""
        return random.choice(self.user_agents)

    def is_security_product_related(self, text, keywords=None):
        """
        Check if text is related to Microsoft Security Products.

        Args:
            text (str): Text to check
            keywords (list, optional): Custom keywords to check against

        Returns:
            bool: True if text contains security product keywords
        """
        if not text:
            return False

        text_lower = text.lower()
        keywords_to_check = keywords or self.SECURITY_PRODUCT_KEYWORDS

        return any(keyword.lower() in text_lower for keyword in keywords_to_check)
    
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
        Scrape all configured sources, filtering for Microsoft security product content.

        Returns:
            dict: Dictionary of articles by source
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
            elif source['type'] == 'blog_index':
                articles = self.scrape_blog_index(source)
            else:
                logger.warning(f"Unsupported source type: {source['type']}")
                continue

            # Filter articles for security product relevance if keywords are specified
            if 'keywords' in source and source['keywords']:
                original_count = len(articles)
                articles = [
                    article for article in articles
                    if self.is_security_product_related(
                        f"{article.get('title', '')} {article.get('content', '')}",
                        source['keywords']
                    )
                ]
                logger.info(f"Filtered {original_count} articles to {len(articles)} security product articles")

            if self.max_articles_per_source and len(articles) > self.max_articles_per_source:
                logger.info(f"TESTING MODE: Limiting {source_name} to {self.max_articles_per_source} articles (of {len(articles)})")
                articles = articles[:self.max_articles_per_source]

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
            
            for entry in feed.entries:
                # Extract and normalize published date
                published_date = ''
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    try:
                        # Convert time struct to datetime and format as YYYY-MM-DD
                        import time
                        published_date = datetime(*entry.published_parsed[:6]).strftime('%Y-%m-%d')
                    except Exception as e:
                        logger.debug(f"Error parsing published_parsed: {e}")

                if not published_date and entry.get('published'):
                    # Try to parse the raw date string
                    try:
                        parsed = date_parser.parse(entry.get('published'))
                        published_date = parsed.strftime('%Y-%m-%d')
                    except Exception as e:
                        logger.debug(f"Error parsing published date '{entry.get('published')}': {e}")
                        published_date = entry.get('published', '')

                # Extract basic info from feed
                article = {
                    'source': source_config['name'],
                    'title': entry.title,
                    'url': entry.link,
                    'author': entry.get('author', ''),
                    'published_date': published_date,
                    'tags': [tag.term for tag in entry.get('tags', [])] if hasattr(entry, 'tags') else []
                }
                
                # Get full content
                if 'content' in entry:
                    article['content'] = entry.content[0].value
                elif hasattr(entry, 'summary'):
                    article['content'] = entry.summary

                    # Fetch full article if content seems truncated (unless disabled)
                    fetch_full = source_config.get('fetch_full_content', True)
                    if fetch_full and len(article['content']) < 1000:
                        full_content = self.fetch_article_content(article['url'], source_config)
                        if full_content:
                            article['content'] = full_content
                else:
                    # Only fetch if fetch_full_content is not disabled
                    if source_config.get('fetch_full_content', True):
                        article['content'] = self.fetch_article_content(article['url'], source_config)
                    else:
                        article['content'] = ""
                
                # Extract update type if present
                article['update_type'] = self.classify_update_type(article['title'], article['content'], article['source'])
                
                articles.append(article)
            
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

            # Check if this is a single-page documentation format
            if source_config.get('single_page', False):
                return self._scrape_single_page(source_config, soup, url)

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
                
                # Fetch full article content and metadata
                article_data = self.fetch_article_content(href, source_config)

                # Skip if no content was retrieved or outside time window
                if not article_data:
                    continue

                # Basic article info
                article = {
                    'source': source_config['name'],
                    'title': link.text.strip() if link.text else 'Unknown Title',
                    'url': href,
                    'content': article_data['content'],
                    'published_date': article_data['date'],
                    'author': '',
                    'tags': []
                }

                # Classify update type
                article['update_type'] = self.classify_update_type(article['title'], article['content'], article['source'])

                articles.append(article)
            
        except Exception as e:
            logger.error(f"Error scraping web page {source_config['url']}: {str(e)}")

        return articles

    def _scrape_single_page(self, source_config, soup, url):
        """
        Scrape a single-page documentation format (e.g., Microsoft Learn What's New pages).
        For pages with month/year sections, extracts each section separately and filters by time window.

        Args:
            source_config (dict): Source configuration
            soup (BeautifulSoup): Parsed HTML
            url (str): Page URL

        Returns:
            list: List of article dictionaries
        """
        articles = []

        try:
            # Extract page title
            title_tag = soup.find('h1') or soup.find('title')
            page_title = title_tag.get_text().strip() if title_tag else source_config['name']

            # Check if this is a Microsoft Learn "What's New" page with month/year sections
            if 'learn.microsoft.com' in url and 'whats-new' in url.lower():
                articles = self._scrape_monthly_sections(source_config, soup, url, page_title)
                if articles:
                    return articles

            # Fallback to treating entire page as one article
            content = None
            pub_date = ''

            # For Tech Community articles, try JSON-LD extraction first
            if 'techcommunity.microsoft.com' in url:
                content = self._extract_from_json_ld(soup, url)
                pub_date = self.extract_date_from_page(soup, url)

            # If JSON-LD extraction failed or not applicable, use regular method
            if not content:
                # Extract content based on content selector
                content_selector = source_config.get('content_selector', 'main, article, [role="main"]')

                # Try each selector until we find content
                content_element = None
                for selector in content_selector.split(','):
                    content_element = soup.select_one(selector.strip())
                    if content_element:
                        break

                if not content_element:
                    logger.warning(f"Content element not found for single-page source: {url}")
                    return articles

                # Remove navigation, TOC, and other non-content elements
                for element in content_element.select('nav, .toc, script, style, iframe, .feedback, .metadata'):
                    element.decompose()

                content = content_element.get_text(separator='\n').strip()

            # Only create article if we have substantial content
            if len(content) > 100:
                article = {
                    'source': source_config['name'],
                    'title': page_title,
                    'url': url,
                    'content': content,
                    'author': '',
                    'published_date': pub_date,
                    'tags': []
                }

                # Classify update type
                article['update_type'] = self.classify_update_type(article['title'], article['content'], article['source'])

                articles.append(article)
                logger.info(f"Scraped single-page article: {page_title} ({len(content)} characters)")
            else:
                logger.warning(f"Insufficient content found for {url} ({len(content)} characters)")

        except Exception as e:
            logger.error(f"Error scraping single-page source {url}: {str(e)}")

        return articles

    def _scrape_monthly_sections(self, source_config, soup, url, page_title):
        """
        Scrape monthly sections from Microsoft Learn "What's New" pages.
        Extracts content from H2 headers formatted as "Month Year" and filters by time window.

        Args:
            source_config (dict): Source configuration
            soup (BeautifulSoup): Parsed HTML
            url (str): Page URL
            page_title (str): Page title

        Returns:
            list: List of article dictionaries, one per month section
        """
        articles = []

        try:
            # Get the main content element
            content_selector = source_config.get('content_selector', 'main, article, [role="main"]')
            content_element = None
            for selector in content_selector.split(','):
                content_element = soup.select_one(selector.strip())
                if content_element:
                    break

            if not content_element:
                logger.warning(f"Content element not found for {url}")
                return articles

            # Find all H2 headers that represent months
            h2_headers = content_element.find_all('h2')

            if not h2_headers:
                logger.info(f"No H2 headers found on {url}, falling back to full page scraping")
                return articles

            logger.info(f"Found {len(h2_headers)} H2 sections on {url}")

            # Process each H2 section
            for h2 in h2_headers:
                try:
                    section_title = h2.get_text().strip()

                    # Try to parse month and year from the header
                    month_year_date = self._parse_month_year(section_title)

                    if not month_year_date:
                        logger.debug(f"Could not parse month/year from H2: '{section_title}'")
                        continue

                    # Check if this month is within the time window
                    if not self._is_month_in_window(month_year_date):
                        logger.debug(f"Section '{section_title}' is outside time window, skipping")
                        continue

                    # Extract all content until the next H2
                    section_content = self._extract_section_content(h2)

                    if not section_content or len(section_content) < 100:
                        logger.debug(f"Insufficient content in section '{section_title}' ({len(section_content) if section_content else 0} chars)")
                        continue

                    # Create article for this month section
                    # Add a URL fragment to make each section unique
                    section_url = f"{url}#{section_title.lower().replace(' ', '-')}"

                    article = {
                        'source': source_config['name'],
                        'title': f"{page_title} - {section_title}",
                        'url': section_url,
                        'content': section_content,
                        'author': '',
                        'published_date': month_year_date.strftime('%Y-%m-%d'),
                        'tags': []
                    }

                    # Classify update type
                    article['update_type'] = self.classify_update_type(
                        article['title'],
                        article['content'],
                        article['source']
                    )

                    articles.append(article)
                    logger.info(f"Scraped section: {section_title} ({len(section_content)} characters)")

                except Exception as e:
                    logger.error(f"Error processing H2 section: {str(e)}")
                    continue

            if articles:
                logger.info(f"Successfully scraped {len(articles)} monthly sections from {url}")
            else:
                logger.warning(f"No monthly sections within time window found on {url}")

        except Exception as e:
            logger.error(f"Error scraping monthly sections from {url}: {str(e)}")

        return articles

    def _parse_month_year(self, text):
        """
        Parse month and year from text like "November 2025" or "Week of November 18, 2024".

        Args:
            text (str): Text to parse

        Returns:
            datetime: Parsed date (set to first day of month) or None if parsing fails
        """
        try:
            # Common patterns: "November 2025", "Week of November 18, 2024"
            # Try to find month name and year
            import calendar

            text_lower = text.lower().strip()

            # Extract year (4 digits)
            year_match = re.search(r'\b(20\d{2})\b', text)
            if not year_match:
                return None
            year = int(year_match.group(1))

            # Extract month name
            month_num = None
            for month_idx, month_name in enumerate(calendar.month_name):
                if month_name and month_name.lower() in text_lower:
                    month_num = month_idx
                    break

            # Also check abbreviated month names
            if month_num is None:
                for month_idx, month_abbr in enumerate(calendar.month_abbr):
                    if month_abbr and month_abbr.lower() in text_lower:
                        month_num = month_idx
                        break

            if month_num is None or month_num == 0:
                return None

            # Return datetime set to first day of the month
            return datetime(year, month_num, 1)

        except Exception as e:
            logger.debug(f"Error parsing month/year from '{text}': {e}")
            return None

    def _is_month_in_window(self, month_date):
        """
        Check if a month is within the configured time window.

        Args:
            month_date (datetime): Date representing the month (usually first day)

        Returns:
            bool: True if within window or no window configured
        """
        if not self.time_window_days:
            return True

        try:
            cutoff_date = datetime.now() - timedelta(days=self.time_window_days)
            # Consider the entire month - use the last day of the month for comparison
            import calendar
            last_day = calendar.monthrange(month_date.year, month_date.month)[1]
            month_end = datetime(month_date.year, month_date.month, last_day)

            return month_end >= cutoff_date
        except Exception as e:
            logger.debug(f"Error checking month window: {e}")
            return True  # Include if we can't determine

    def _extract_section_content(self, h2_element):
        """
        Extract all content after an H2 element until the next H2.

        Args:
            h2_element: BeautifulSoup H2 element

        Returns:
            str: Section content
        """
        content_parts = []

        # Get all siblings after this H2 until the next H2
        for sibling in h2_element.find_next_siblings():
            # Stop at the next H2
            if sibling.name == 'h2':
                break

            # Skip script, style, nav elements
            if sibling.name in ['script', 'style', 'nav', 'iframe']:
                continue

            # Get text content
            text = sibling.get_text(separator='\n').strip()
            if text:
                content_parts.append(text)

        return '\n\n'.join(content_parts)

    def scrape_blog_index(self, source_config):
        """
        Scrape a blog index page (e.g., Tech Community) that uses Next.js with Apollo state.
        Extracts article links and dates from __NEXT_DATA__, filters by time window,
        then scrapes each article individually.

        Args:
            source_config (dict): Source configuration

        Returns:
            list: List of article dictionaries
        """
        articles = []

        try:
            url = source_config['url']
            headers = {'User-Agent': self.get_random_user_agent()}
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')

            # Find the __NEXT_DATA__ script tag
            next_data_script = soup.find('script', {'id': '__NEXT_DATA__'})
            if not next_data_script:
                logger.warning(f"No __NEXT_DATA__ found on {url}")
                return articles

            # Parse the JSON data
            next_data = json.loads(next_data_script.string)
            apollo_state = next_data.get('props', {}).get('pageProps', {}).get('apolloState', {})

            if not apollo_state:
                logger.warning(f"No Apollo state found in __NEXT_DATA__ on {url}")
                return articles

            # Extract blog messages from Apollo state
            blog_messages = []
            for key, obj in apollo_state.items():
                if key.startswith('BlogTopicMessage:message:'):
                    if isinstance(obj, dict) and obj.get('__typename') == 'BlogTopicMessage':
                        blog_messages.append({
                            'id': obj.get('uid', ''),
                            'subject': obj.get('subject', ''),
                            'postTime': obj.get('postTime', ''),
                        })

            logger.info(f"Found {len(blog_messages)} articles on blog index page")

            # Filter by time window if specified
            if self.time_window_days:
                from datetime import datetime, timedelta, timezone
                cutoff_date = datetime.now(timezone.utc) - timedelta(days=self.time_window_days)

                filtered_messages = []
                for msg in blog_messages:
                    try:
                        post_date = datetime.fromisoformat(msg['postTime'])
                        if post_date >= cutoff_date:
                            filtered_messages.append(msg)
                    except Exception as e:
                        logger.debug(f"Could not parse date '{msg['postTime']}': {e}")
                        # Include articles with unparseable dates
                        filtered_messages.append(msg)

                blog_messages = filtered_messages
                logger.info(f"Filtered to {len(blog_messages)} articles within last {self.time_window_days} days")

            # Scrape each article
            for msg in blog_messages:
                try:
                    # Construct article URL (slug format: title-with-dashes/id)
                    title_slug = msg['subject'].lower()
                    # Remove special characters and replace spaces with hyphens
                    title_slug = re.sub(r'[^\w\s-]', '', title_slug)
                    title_slug = re.sub(r'[-\s]+', '-', title_slug).strip('-')

                    article_url = f"https://techcommunity.microsoft.com/blog/microsoftthreatprotectionblog/{title_slug}/{msg['id']}"

                    logger.info(f"Fetching article: {msg['subject']}")

                    # Fetch and parse the article page
                    article_response = requests.get(article_url, headers=headers, timeout=30)
                    article_response.raise_for_status()
                    article_soup = BeautifulSoup(article_response.content, 'html.parser')

                    # Extract content using JSON-LD (Tech Community articles use this)
                    content = self._extract_from_json_ld(article_soup, article_url)

                    if content and len(content) > 100:
                        # Parse the date
                        try:
                            post_date = datetime.fromisoformat(msg['postTime'])
                            published_date = post_date.strftime('%Y-%m-%d')
                        except:
                            published_date = msg['postTime']

                        article = {
                            'source': source_config['name'],
                            'title': msg['subject'],
                            'url': article_url,
                            'content': content,
                            'published_date': published_date,
                            'author': '',
                            'tags': []
                        }

                        # Classify update type
                        article['update_type'] = self.classify_update_type(
                            article['title'],
                            article['content'],
                            article['source']
                        )

                        articles.append(article)
                        logger.info(f"Scraped blog article: {msg['subject']} ({len(content)} characters)")
                    else:
                        logger.warning(f"Insufficient content for {article_url}")

                    # Be nice to the server
                    time.sleep(random.uniform(1, 2))

                except Exception as e:
                    logger.error(f"Error scraping blog article {msg.get('subject', 'unknown')}: {str(e)}")
                    continue

        except Exception as e:
            logger.error(f"Error scraping blog index {source_config.get('url', 'unknown')}: {str(e)}")

        return articles

    def extract_date_from_page(self, soup, url):
        """
        Extract publication date from an article page.

        Args:
            soup (BeautifulSoup): Parsed HTML
            url (str): Article URL for logging

        Returns:
            str: ISO formatted date string or empty string
        """
        date_selectors = [
            'time[datetime]',
            'meta[property="article:published_time"]',
            'meta[name="publishdate"]',
            'span.publish-date',
            'div.publish-date',
            '.lia-message-dates',
            'time',
        ]

        for selector in date_selectors:
            element = soup.select_one(selector)
            if element:
                # Try datetime attribute first
                date_str = element.get('datetime') or element.get('content')
                if not date_str:
                    date_str = element.get_text().strip()

                if date_str:
                    try:
                        # Parse the date
                        parsed_date = date_parser.parse(date_str)
                        return parsed_date.strftime('%Y-%m-%d')
                    except Exception as e:
                        logger.debug(f"Failed to parse date '{date_str}' from {url}: {e}")
                        continue

        logger.debug(f"Could not extract date from {url}")
        return ""

    def is_within_time_window(self, date_str):
        """
        Check if a date is within the configured time window.

        Args:
            date_str (str): Date string in YYYY-MM-DD format

        Returns:
            bool: True if within window or no window configured
        """
        if not self.time_window_days or not date_str:
            return True

        try:
            article_date = datetime.strptime(date_str, '%Y-%m-%d')
            cutoff_date = datetime.now() - timedelta(days=self.time_window_days)
            return article_date >= cutoff_date
        except Exception as e:
            logger.debug(f"Error checking date window: {e}")
            return True  # Include if we can't determine

    def fetch_article_content(self, url, source_config):
        """
        Fetch the full content and metadata of an article.

        Args:
            url (str): Article URL
            source_config (dict): Source configuration

        Returns:
            dict: Dictionary with 'content' and 'date' keys, or None if failed
        """
        try:
            response = self.make_request(url)

            if not response:
                return None

            soup = BeautifulSoup(response.text, 'html.parser')

            # Extract date
            pub_date = self.extract_date_from_page(soup, url)

            # Check if within time window
            if not self.is_within_time_window(pub_date):
                logger.info(f"Skipping article outside time window: {url} ({pub_date})")
                return None

            content = None

            # For Tech Community articles, try to extract from JSON-LD first
            if 'techcommunity.microsoft.com' in url:
                content = self._extract_from_json_ld(soup, url)

            # If JSON-LD extraction failed or not applicable, use regular method
            if not content:
                # Extract content based on source-specific content selector
                content_selector = source_config.get('content_selector', 'article')

                # Try each selector until we find content
                content_element = None
                for selector in content_selector.split(','):
                    content_element = soup.select_one(selector.strip())
                    if content_element:
                        break

                if content_element:
                    # Remove script, style, and iframe elements
                    for element in content_element.select('script, style, iframe'):
                        element.decompose()
                    content = content_element.get_text(separator='\n').strip()

            if not content or len(content) < 50:
                logger.warning(f"Insufficient content found for {url} ({len(content) if content else 0} characters)")
                return None

            return {
                'content': content,
                'date': pub_date
            }

        except Exception as e:
            logger.error(f"Error fetching article content from {url}: {str(e)}")
            return None

    def _extract_from_json_ld(self, soup, url):
        """
        Extract article content from JSON-LD structured data (used by Tech Community).

        Args:
            soup (BeautifulSoup): Parsed HTML
            url (str): Article URL for logging

        Returns:
            str: Article content or None
        """
        try:
            # Find JSON-LD script tags
            json_ld_scripts = soup.find_all('script', {'type': 'application/ld+json'})

            logger.debug(f"Found {len(json_ld_scripts)} JSON-LD scripts in {url}")

            for i, script in enumerate(json_ld_scripts):
                try:
                    # Get script content - handle both .string and .get_text()
                    script_content = script.string or script.get_text()

                    if not script_content:
                        logger.debug(f"Script {i+1} has no content")
                        continue

                    data = json.loads(script_content)

                    # Look for BlogPosting type
                    if isinstance(data, dict) and data.get('@type') == 'BlogPosting':
                        description = data.get('description', '')
                        if description and len(description) > 100:
                            logger.info(f"Extracted {len(description)} chars from JSON-LD BlogPosting for {url}")
                            return description
                        else:
                            logger.debug(f"BlogPosting found but description too short: {len(description) if description else 0} chars")

                except json.JSONDecodeError as e:
                    logger.debug(f"Failed to parse JSON in script {i+1}: {e}")
                    continue
                except Exception as e:
                    logger.debug(f"Error processing script {i+1}: {e}")
                    continue

            logger.debug(f"No suitable JSON-LD content found for {url}")
            return None

        except Exception as e:
            logger.error(f"Error extracting JSON-LD from {url}: {e}")
            return None
    
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
        
        return True
    
    def classify_update_type(self, title, content, source=''):
        """
        Classify the type of security product update based on content.

        Args:
            title (str): Article title
            content (str): Article content
            source (str): Source name (optional)

        Returns:
            list: List of update type tags
        """
        update_types = []
        combined_text = f"{title} {content}".lower()
        title_lower = title.lower()

        # Check if this is an aggregated news source (blog index, monthly news, roundups, etc.)
        is_aggregated = any(keyword in source.lower() for keyword in ['blog', 'monthly news', 'roundup', 'weekly']) or \
                       any(keyword in title.lower() for keyword in ['monthly news', 'weekly'])

        # Define classification patterns - use specific phrases to reduce false positives
        classifications = {
            'Feature Update': ['new feature', 'introducing', 'now available', 'new capability', 'announcing', 'launched', 'rolling out'],
            'Bug Fix': ['bug fix', 'fixed issue', 'resolved issue', 'fixes a bug', 'addresses issue'],
            'Security Patch': ['security update', 'security vulnerability', 'cve-', 'security patch', 'security fix'],
            'Performance Improvement': ['performance improvement', 'performance enhancement', 'faster performance', 'improved performance', 'optimization improvement', 'speed improvement'],
            'Configuration Update': ['new setting', 'configuration option', 'policy update', 'new policy', 'setting change'],
            'Known Issue': ['known issue', 'known limitation', 'investigating issue', 'aware of issue'],
            'Platform Update': ['platform update', 'version update', 'build update', 'agent update', 'client update'],
            'Integration': ['new integration', 'integrates with', 'integration with', 'now works with', 'connector for'],
            'Deprecation': ['deprecat', 'end of support', 'retiring', 'sunset', 'no longer supported'],
            'Preview': ['public preview', 'private preview', 'preview feature', 'in preview', 'beta release']
        }

        for update_type, keywords in classifications.items():
            # For aggregated news sources, require security keywords in title
            # to avoid false positives from mentions in general content
            if update_type == 'Security Patch' and is_aggregated:
                if any(keyword in title_lower for keyword in keywords):
                    update_types.append(update_type)
            else:
                if any(keyword in combined_text for keyword in keywords):
                    update_types.append(update_type)

        return update_types if update_types else ['General Update']
