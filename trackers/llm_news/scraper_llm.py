"""
LLM News Scraper for SecIntel AI.
Handles RSS feeds and web scraping for Large Language Model news and updates.
"""

import logging
import requests
import feedparser
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from dateutil import parser as date_parser
from urllib.parse import urljoin, urlparse
import re
import time
import random

logger = logging.getLogger(__name__)


class LLMNewsScraper:
    """Multi-source scraper for LLM news and updates"""

    def __init__(self, sources_config, time_window_days=None, max_articles_per_source=None):
        self.sources = sources_config
        self.time_window_days = time_window_days or 30
        self.max_articles_per_source = max_articles_per_source
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
        ]
        self.session = requests.Session()

    def _get_headers(self):
        """Get randomized headers for requests"""
        return {
            'User-Agent': random.choice(self.user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive',
        }

    def _normalize_url(self, url):
        """Normalize URL: ensure https, remove duplicate extensions and slashes"""
        if not url:
            return url

        # Fix duplicate extensions like .html.html
        url = re.sub(r'(\.html)+', '.html', url)
        url = re.sub(r'(\.htm)+', '.htm', url)

        # Fix double slashes in path (but not in protocol)
        # Split on :// to preserve protocol
        if '://' in url:
            protocol, rest = url.split('://', 1)
            # Replace multiple slashes with single slash in the path
            rest = re.sub(r'/+', '/', rest)
            url = protocol + '://' + rest

        # Upgrade http to https for known secure sites
        if url.startswith('http://'):
            parsed = urlparse(url)
            # Most modern sites support https
            secure_domains = [
                'workspaceupdates.googleblog.com',
                'blog.google',
                'openai.com',
                'status.openai.com',
                'anthropic.com',
                'github.com',
                'github.blog',
                'ai.google.dev',
                'mistral.ai',
                'lmstudio.ai',
                'learn.microsoft.com',
                'docs.anthropic.com',
            ]
            if any(domain in parsed.netloc for domain in secure_domains):
                url = 'https://' + url[7:]

        return url

    def _is_valid_title(self, title):
        """Check if a title is valid (not garbage/navigation element)"""
        if not title:
            return False

        # Too short
        if len(title) < 10:
            return False

        # Known garbage patterns
        garbage_patterns = [
            r'^login',
            r'^signup',
            r'^sign up',
            r'^sign in',
            r'^download',
            r'^menu',
            r'^nav',
            r'^home$',
            r'^blog$',
            r'^news$',
            r'^about',
            r'^contact',
            r'^subscribe',
            r'^newsletter',
            r'login or signup',
            r'downloadlogin',
            r'^skip to',
            r'^go to',
            # Generic page elements
            r'^in this article',
            r'^getting started',
            r'^overview$',
            r'^documentation',
            r'^table of contents',
            r'^contents$',
            r'^main$',
            r'^introduction$',
            # Date-only titles (e.g., "December 19, 2025")
            r'^(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},?\s+\d{4}$',
            # Version-only titles
            r'^v?\d+\.\d+(\.\d+)?$',
        ]

        title_lower = title.lower().strip()
        for pattern in garbage_patterns:
            if re.match(pattern, title_lower):
                return False

        # Check for titles that are just emojis or special chars
        # Remove emojis and check if anything meaningful remains
        text_only = re.sub(r'[^\w\s]', '', title)
        if len(text_only.strip()) < 5:
            return False

        return True

    def _extract_date_from_title(self, title):
        """Try to extract a date from the title text."""
        if not title:
            return None

        # Match patterns like "December 19, 2025" or "January 9, 2026"
        date_pattern = r'(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},?\s+\d{4}'
        match = re.search(date_pattern, title.lower())
        if match:
            try:
                return date_parser.parse(match.group(), fuzzy=True)
            except:
                pass
        return None

    def _extract_date_from_content(self, content):
        """Try to extract a date from article content."""
        if not content:
            return None

        # Look for common date patterns in content
        patterns = [
            # "Published: January 9, 2026" or "Date: January 9, 2026"
            r'(?:published|date|posted|updated)[\s:]+(\w+\s+\d{1,2},?\s+\d{4})',
            # ISO format: 2026-01-09
            r'(\d{4}-\d{2}-\d{2})',
            # "January 9, 2026" at start of content
            r'^((?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},?\s+\d{4})',
        ]

        for pattern in patterns:
            match = re.search(pattern, content.lower()[:500])  # Check first 500 chars
            if match:
                try:
                    return date_parser.parse(match.group(1), fuzzy=True)
                except:
                    pass
        return None

    def _is_valid_article_url(self, url, base_url=None):
        """Check if a URL is a valid article URL (not just a homepage)."""
        if not url:
            return False

        parsed = urlparse(url)
        path = parsed.path.rstrip('/')

        # Reject URLs that are just homepages or root paths
        if not path or path == '/' or path in ['', '/blog', '/news', '/changelog']:
            return False

        # Reject URLs that are just domain roots (e.g., https://www.claude.ai)
        if len(path.split('/')) < 2:
            # Allow if path has a file extension
            if not re.search(r'\.\w{2,5}$', path):
                return False

        # Known generic homepage patterns to reject
        generic_patterns = [
            r'^https?://(?:www\.)?claude\.ai/?$',
            r'^https?://(?:www\.)?openai\.com/?$',
            r'^https?://(?:www\.)?anthropic\.com/?$',
            r'^https?://(?:www\.)?gemini\.google\.com/?$',
            r'^https?://ai\.google\.dev/?$',
        ]

        for pattern in generic_patterns:
            if re.match(pattern, url):
                return False

        return True

    def _is_within_time_window(self, date_obj):
        """Check if a date is within the configured time window"""
        if not date_obj:
            return True  # Include if no date available

        if isinstance(date_obj, str):
            try:
                date_obj = date_parser.parse(date_obj, fuzzy=True)
            except:
                return True

        # Make datetime timezone-naive for comparison
        if hasattr(date_obj, 'tzinfo') and date_obj.tzinfo:
            date_obj = date_obj.replace(tzinfo=None)

        cutoff_date = datetime.now() - timedelta(days=self.time_window_days)
        return date_obj >= cutoff_date

    def scrape_all_sources(self):
        """Scrape all configured sources"""
        results = {}

        for source in self.sources:
            source_name = source.get('name', 'Unknown')
            source_type = source.get('type', 'web')

            logger.info(f"Scraping source: {source_name} (type: {source_type})")

            try:
                if source_type == 'rss':
                    articles = self.scrape_rss_feed(source)
                elif source_type == 'web':
                    articles = self.scrape_web_page(source)
                elif source_type == 'headless':
                    articles = self.scrape_headless(source)
                else:
                    logger.warning(f"Unknown source type: {source_type}")
                    articles = []

                if self.max_articles_per_source and len(articles) > self.max_articles_per_source:
                    logger.info(f"TESTING MODE: Limiting {source_name} to {self.max_articles_per_source} articles (of {len(articles)})")
                    articles = articles[:self.max_articles_per_source]

                results[source_name] = articles
                logger.info(f"Scraped {len(articles)} articles from {source_name}")

                # Be polite - add delay between sources
                time.sleep(1)

            except Exception as e:
                logger.error(f"Error scraping {source_name}: {str(e)}")
                results[source_name] = []

        return results

    # =========================================================================
    # RSS Feed Scraping
    # =========================================================================

    def scrape_rss_feed(self, source):
        """Scrape RSS feed source"""
        feed_url = source.get('feed_url') or source.get('url')
        provider = source.get('provider', 'Unknown')
        product = source.get('product', 'Unknown')
        filter_keywords = source.get('filter_keywords', [])

        logger.info(f"Fetching RSS feed: {feed_url}")

        try:
            feed = feedparser.parse(feed_url)
        except Exception as e:
            logger.error(f"Failed to parse RSS feed {feed_url}: {str(e)}")
            return []

        articles = []

        for entry in feed.entries:
            title = entry.get('title', '')
            link = entry.get('link', '')
            published = entry.get('published', entry.get('updated', ''))
            description = entry.get('description', entry.get('summary', ''))
            content = entry.get('content', [{}])[0].get('value', '') if entry.get('content') else ''

            # Use content if available, otherwise description
            full_content = content or description

            # Parse date
            pub_date = None
            if published:
                try:
                    pub_date = date_parser.parse(published, fuzzy=True)
                except:
                    pass

            # Check time window
            if not self._is_within_time_window(pub_date):
                continue

            # Filter by keywords if configured
            if filter_keywords:
                text_to_search = f"{title} {full_content}".lower()
                if not any(kw.lower() in text_to_search for kw in filter_keywords):
                    continue

            # Classify content type
            content_types = self.classify_content_type(title, full_content)

            # Normalize URL
            normalized_link = self._normalize_url(link)

            article = {
                'source': source.get('name'),
                'provider': provider,
                'product': product,
                'title': title,
                'url': normalized_link,
                'published_date': pub_date.isoformat() if pub_date else None,
                'content': full_content[:10000],  # Limit content length
                'content_type': content_types,
                'scraped_date': datetime.now().isoformat()
            }
            articles.append(article)

        return articles

    # =========================================================================
    # Web Page Scraping
    # =========================================================================

    def scrape_web_page(self, source):
        """Scrape web page source"""
        url = source.get('url')

        # Use specialized scraper for Anthropic news
        if 'anthropic.com/news' in url:
            return self._scrape_anthropic_news(source)

        # Use specialized scraper for Claude Release Notes
        if 'release-notes' in url and ('platform.claude.com' in url or 'docs.anthropic.com' in url):
            return self._scrape_claude_release_notes(source)

        # Use specialized scraper for Gemini Release Notes
        if 'gemini.google' in url and 'release-notes' in url:
            return self._scrape_gemini_release_notes(source)

        # Use specialized scraper for Gemini CLI Changelog
        if 'geminicli.com' in url and 'changelog' in url:
            return self._scrape_gemini_cli_changelog(source)

        provider = source.get('provider', 'Unknown')
        product = source.get('product', 'Unknown')
        selectors = source.get('selectors', {})
        filter_keywords = source.get('filter_keywords', [])

        logger.info(f"Fetching web page: {url}")

        try:
            response = self.session.get(url, headers=self._get_headers(), timeout=30)
            response.raise_for_status()
        except Exception as e:
            logger.error(f"Failed to fetch {url}: {str(e)}")
            return []

        soup = BeautifulSoup(response.text, 'html.parser')
        articles = []

        # Try to find article containers
        container_selector = selectors.get('article_container', 'article, .post, .news-item, section')
        containers = soup.select(container_selector)

        if not containers:
            # Fallback to generic patterns
            containers = soup.find_all('article') or soup.find_all('div', class_=re.compile(r'post|news|update|release|entry'))

        for container in containers:
            # Extract title
            title_selector = selectors.get('title', 'h2, h3, h4, .title')
            title_elem = container.select_one(title_selector)
            title = title_elem.get_text(strip=True) if title_elem else ''

            # Validate title (exclude garbage/navigation elements)
            if not self._is_valid_title(title):
                continue

            # Extract link
            link_selector = selectors.get('link', 'a')
            link_elem = container.select_one(link_selector)
            link = link_elem.get('href', '') if link_elem else ''

            # Make link absolute if relative
            if link and not link.startswith('http'):
                link = urljoin(url, link)

            # Normalize URL
            link = self._normalize_url(link)

            # Extract date
            date_selector = selectors.get('date', 'time, .date, [datetime]')
            date_elem = container.select_one(date_selector)
            date_str = ''
            if date_elem:
                date_str = date_elem.get('datetime', '') or date_elem.get_text(strip=True)

            # Parse date
            pub_date = None
            if date_str:
                try:
                    pub_date = date_parser.parse(date_str, fuzzy=True)
                except:
                    pass

            # Check time window
            if not self._is_within_time_window(pub_date):
                continue

            # Extract content
            content_selector = selectors.get('content', 'p, .description, .excerpt, .summary')
            content_parts = []
            for elem in container.select(content_selector):
                text = elem.get_text(strip=True)
                if text:
                    content_parts.append(text)
            content = ' '.join(content_parts)

            if not content:
                content = container.get_text(strip=True)[:2000]

            # Filter by keywords if configured
            if filter_keywords:
                text_to_search = f"{title} {content}".lower()
                if not any(kw.lower() in text_to_search for kw in filter_keywords):
                    continue

            # Skip very short content
            if len(content) < 20:
                continue

            # Classify content type
            content_types = self.classify_content_type(title, content)

            article = {
                'source': source.get('name'),
                'provider': provider,
                'product': product,
                'title': title,
                'url': link or url,
                'published_date': pub_date.isoformat() if pub_date else None,
                'content': content[:10000],
                'content_type': content_types,
                'scraped_date': datetime.now().isoformat()
            }
            articles.append(article)

        return articles

    # =========================================================================
    # Specialized Scrapers
    # =========================================================================

    def _scrape_anthropic_news(self, source):
        """
        Specialized scraper for Anthropic news using sitemap + individual article pages.
        The news listing page only shows ~13 articles, but sitemap has all ~170.
        """
        provider = source.get('provider', 'Anthropic')
        product = source.get('product', 'Claude')
        filter_keywords = source.get('filter_keywords', [])

        logger.info("Fetching Anthropic news via sitemap")

        # Step 1: Get article URLs from sitemap
        sitemap_url = "https://www.anthropic.com/sitemap.xml"
        try:
            response = self.session.get(sitemap_url, headers=self._get_headers(), timeout=30)
            response.raise_for_status()
        except Exception as e:
            logger.error(f"Failed to fetch sitemap: {str(e)}")
            return []

        soup = BeautifulSoup(response.text, 'xml')
        articles = []

        # Find all news URLs with their lastmod dates
        news_entries = []
        for url_elem in soup.find_all('url'):
            loc = url_elem.find('loc')
            lastmod = url_elem.find('lastmod')

            if loc and '/news/' in loc.text:
                article_url = loc.text
                mod_date = None
                if lastmod:
                    try:
                        mod_date = date_parser.parse(lastmod.text)
                    except:
                        pass

                # Filter by time window using lastmod
                if self._is_within_time_window(mod_date):
                    news_entries.append({'url': article_url, 'lastmod': mod_date})

        logger.info(f"Found {len(news_entries)} recent news articles in sitemap")

        # Step 2: Fetch each article page to get title, date, category
        for entry in news_entries:
            article_url = entry['url']

            try:
                response = self.session.get(article_url, headers=self._get_headers(), timeout=30)
                response.raise_for_status()
                article_soup = BeautifulSoup(response.text, 'html.parser')

                # Extract title from h1
                title_elem = article_soup.find('h1')
                title = title_elem.get_text(strip=True) if title_elem else ''

                if not title:
                    # Try meta title
                    meta_title = article_soup.find('meta', property='og:title')
                    if meta_title:
                        title = meta_title.get('content', '')

                if not self._is_valid_title(title):
                    continue

                # Extract date - try time element first, then look for date patterns
                pub_date = None
                time_elem = article_soup.find('time')
                if time_elem:
                    date_str = time_elem.get('datetime', '') or time_elem.get_text(strip=True)
                    try:
                        pub_date = date_parser.parse(date_str, fuzzy=True)
                    except:
                        pass

                # Fallback to lastmod from sitemap
                if not pub_date:
                    pub_date = entry['lastmod']

                # Extract category from meta or page content
                category = ''
                # Look for category in breadcrumbs or tags
                for span in article_soup.find_all('span'):
                    span_text = span.get_text(strip=True)
                    if span_text in ['Announcements', 'Product', 'Policy', 'Research',
                                    'Case Study', 'Economic Research', 'Societal Impacts']:
                        category = span_text
                        break

                # Extract first paragraph as content
                content_parts = [title]
                if category:
                    content_parts.append(f"Category: {category}")

                for p in article_soup.find_all('p')[:3]:
                    p_text = p.get_text(strip=True)
                    if p_text and len(p_text) > 50:
                        content_parts.append(p_text)
                        break

                content = ' '.join(content_parts)

                # Filter by keywords if configured
                if filter_keywords:
                    text_to_search = f"{title} {content}".lower()
                    if not any(kw.lower() in text_to_search for kw in filter_keywords):
                        continue

                # Classify content type
                content_types = self.classify_content_type(title, content)

                article = {
                    'source': source.get('name', 'Anthropic News'),
                    'provider': provider,
                    'product': product,
                    'title': title,
                    'url': article_url,
                    'published_date': pub_date.isoformat() if pub_date else None,
                    'content': content[:10000],
                    'content_type': content_types,
                    'scraped_date': datetime.now().isoformat()
                }
                articles.append(article)
                logger.debug(f"Scraped: {title}")

                # Be polite - small delay between requests
                time.sleep(0.5)

            except Exception as e:
                logger.warning(f"Failed to fetch {article_url}: {str(e)}")
                continue

        logger.info(f"Scraped {len(articles)} articles from Anthropic news")
        return articles

    def _scrape_claude_release_notes(self, source):
        """
        Specialized scraper for Claude Release Notes page.
        The page is JavaScript-rendered, but contains JSON data with all content.
        Extracts dates and content from the embedded JSON/RSC data.
        """
        url = source.get('url', 'https://platform.claude.com/docs/en/release-notes/overview')
        provider = source.get('provider', 'Anthropic')
        product = source.get('product', 'Claude API')
        filter_keywords = source.get('filter_keywords', [])

        logger.info(f"Fetching Claude Release Notes: {url}")

        try:
            # Follow redirects
            response = self.session.get(url, headers=self._get_headers(), timeout=30, allow_redirects=True)
            response.raise_for_status()
        except Exception as e:
            logger.error(f"Failed to fetch {url}: {str(e)}")
            return []

        html = response.text
        articles = []

        # Date pattern to find in the JSON data
        date_pattern = r'"((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})'

        # Find all unique dates in the page
        date_matches = re.findall(date_pattern, html, re.IGNORECASE)
        unique_dates = []
        for date in date_matches:
            if date not in unique_dates:
                unique_dates.append(date)

        logger.info(f"Found {len(unique_dates)} date entries in release notes")

        # For each date, try to extract associated content from the JSON
        for date_text in unique_dates:
            # Parse the date
            pub_date = None
            try:
                # Remove ordinal suffixes (st, nd, rd, th)
                clean_date = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', date_text)
                pub_date = date_parser.parse(clean_date, fuzzy=True)
            except:
                continue

            # Check time window
            if not self._is_within_time_window(pub_date):
                continue

            # Try to extract content following this date in the JSON
            # Look for text content after the date string
            escaped_date = re.escape(date_text)
            content_pattern = rf'"{escaped_date}"[^"]*"([^"]+)"'

            content_matches = re.findall(content_pattern, html[:50000])  # Limit search
            content_parts = []

            # Also search for content in a broader pattern
            # The JSON often has structure like: "date", followed by content arrays
            broader_pattern = rf'{escaped_date}[^\]]*?\["([^"]+)"'
            broader_matches = re.findall(broader_pattern, html[:100000])

            for match in (content_matches + broader_matches)[:10]:
                # Clean up escaped characters
                text = match.replace('\\n', ' ').replace('\\t', ' ').replace('\\"', '"')
                # Skip if it's just another date or very short
                if len(text) > 30 and not re.match(date_pattern, f'"{text}'):
                    content_parts.append(text)

            # If we couldn't extract content, create a generic entry
            if not content_parts:
                content = f"Claude API release notes for {date_text}. See full details at the documentation site."
            else:
                content = ' '.join(content_parts[:5])  # Limit to first 5 content pieces

            # Create title
            title = f"Claude API Updates - {date_text}"

            # Try to make a better title from content
            if content_parts:
                first_item = content_parts[0]
                if len(first_item) > 30:
                    if '. ' in first_item[:120]:
                        title = first_item[:first_item.index('. ', 0, 120) + 1]
                    else:
                        title = first_item[:100] + '...' if len(first_item) > 100 else first_item

            # Filter by keywords if configured
            if filter_keywords:
                text_to_search = f"{title} {content}".lower()
                if not any(kw.lower() in text_to_search for kw in filter_keywords):
                    continue

            # Classify content type
            content_types = self.classify_content_type(title, content)

            article = {
                'source': source.get('name', 'Claude Release Notes'),
                'provider': provider,
                'product': product,
                'title': title,
                'url': url,
                'published_date': pub_date.isoformat() if pub_date else None,
                'content': content[:10000],
                'content_type': content_types,
                'scraped_date': datetime.now().isoformat()
            }
            articles.append(article)

        logger.info(f"Scraped {len(articles)} release notes from Claude docs")
        return articles

    def _scrape_gemini_release_notes(self, source):
        """
        Specialized scraper for Gemini Release Notes page.
        Structure: h2 date headings (YYYY.MM.DD) followed by h3 feature titles and content.
        """
        url = source.get('url', 'https://gemini.google/release-notes/')
        provider = source.get('provider', 'Google')
        product = source.get('product', 'Gemini')
        filter_keywords = source.get('filter_keywords', [])

        logger.info(f"Fetching Gemini Release Notes: {url}")

        try:
            response = self.session.get(url, headers=self._get_headers(), timeout=30)
            response.raise_for_status()
        except Exception as e:
            logger.error(f"Failed to fetch {url}: {str(e)}")
            return []

        soup = BeautifulSoup(response.text, 'html.parser')
        articles = []

        # Find date headings (format: YYYY.MM.DD)
        date_pattern = re.compile(r'(\d{4})\.(\d{2})\.(\d{2})')

        for heading in soup.find_all(['h2', 'h3']):
            heading_text = heading.get_text(strip=True)
            date_match = date_pattern.match(heading_text)

            if not date_match:
                continue

            # Parse the date
            try:
                year, month, day = date_match.groups()
                pub_date = datetime(int(year), int(month), int(day))
            except:
                continue

            # Check time window
            if not self._is_within_time_window(pub_date):
                continue

            # Get content - find all siblings until next date heading
            content_parts = []
            titles = []
            current = heading.find_next_sibling()

            while current:
                current_text = current.get_text(strip=True)

                # Stop if we hit another date heading
                if current.name in ['h2'] and date_pattern.match(current_text):
                    break

                # Collect feature titles (h3)
                if current.name == 'h3':
                    titles.append(current_text)

                # Collect content
                if current.name in ['p', 'ul', 'ol', 'li', 'div']:
                    if current_text:
                        content_parts.append(current_text)

                current = current.find_next_sibling()

            content = ' '.join(content_parts)
            if not content or len(content) < 20:
                continue

            # Create title from first feature or date
            if titles:
                title = titles[0]
            else:
                title = f"Gemini Updates - {heading_text}"

            # Filter by keywords if configured
            if filter_keywords:
                text_to_search = f"{title} {content}".lower()
                if not any(kw.lower() in text_to_search for kw in filter_keywords):
                    continue

            # Classify content type
            content_types = self.classify_content_type(title, content)

            article = {
                'source': source.get('name', 'Gemini Release Notes'),
                'provider': provider,
                'product': product,
                'title': title,
                'url': f"{url}#{heading_text}",
                'published_date': pub_date.isoformat() if pub_date else None,
                'content': content[:10000],
                'content_type': content_types,
                'scraped_date': datetime.now().isoformat()
            }
            articles.append(article)

        logger.info(f"Scraped {len(articles)} release notes from Gemini")
        return articles

    def _scrape_gemini_cli_changelog(self, source):
        """
        Specialized scraper for Gemini CLI Changelog.
        Structure: h2 headings in wrapper divs like "Announcements: v0.25.0 - 2026-01-20"
        Content is in ul/p elements that are siblings of the heading wrapper div.
        """
        url = source.get('url', 'https://geminicli.com/docs/changelogs/')
        provider = source.get('provider', 'Google')
        product = source.get('product', 'Gemini CLI')
        filter_keywords = source.get('filter_keywords', [])

        logger.info(f"Fetching Gemini CLI Changelog: {url}")

        try:
            response = self.session.get(url, headers=self._get_headers(), timeout=30)
            response.raise_for_status()
        except Exception as e:
            logger.error(f"Failed to fetch {url}: {str(e)}")
            return []

        soup = BeautifulSoup(response.text, 'html.parser')
        articles = []

        # Find version headings (format: "Announcements: v0.25.0 - 2026-01-20")
        version_pattern = re.compile(r'v(\d+\.\d+\.\d+)\s*[-–]\s*(\d{4}-\d{2}-\d{2})')

        # Find heading wrapper divs that contain version info
        for heading_wrapper in soup.find_all('div', class_='sl-heading-wrapper'):
            h2 = heading_wrapper.find(['h2', 'h3'])
            if not h2:
                continue

            heading_text = h2.get_text(strip=True)
            version_match = version_pattern.search(heading_text)

            if not version_match:
                continue

            version, date_str = version_match.groups()

            # Parse the date
            try:
                pub_date = date_parser.parse(date_str)
            except:
                continue

            # Check time window
            if not self._is_within_time_window(pub_date):
                continue

            # Get content - find sibling elements of the wrapper until next heading wrapper
            content_parts = []
            current = heading_wrapper.find_next_sibling()

            while current:
                # Stop if we hit another heading wrapper
                if current.name == 'div' and 'sl-heading-wrapper' in current.get('class', []):
                    break

                # Collect content from ul, ol, p elements
                if current.name in ['ul', 'ol', 'p']:
                    current_text = current.get_text(strip=True)
                    if current_text and len(current_text) > 10:
                        content_parts.append(current_text)

                current = current.find_next_sibling()

            content = ' '.join(content_parts)
            if not content or len(content) < 20:
                continue

            # Create title from heading
            title = f"Gemini CLI v{version}"

            # Try to extract a better title from the heading if it has one
            # e.g., "Announcements: v0.25.0 - 2026-01-20" -> extract "Announcements"
            title_match = re.match(r'^([^:]+):', heading_text)
            if title_match:
                title = f"Gemini CLI v{version}: {title_match.group(1)}"

            # Filter by keywords if configured
            if filter_keywords:
                text_to_search = f"{title} {content}".lower()
                if not any(kw.lower() in text_to_search for kw in filter_keywords):
                    continue

            # Classify content type
            content_types = self.classify_content_type(title, content)

            article = {
                'source': source.get('name', 'Gemini CLI Changelog'),
                'provider': provider,
                'product': product,
                'title': title,
                'url': f"{url}#v{version}",
                'published_date': pub_date.isoformat() if pub_date else None,
                'content': content[:10000],
                'content_type': content_types,
                'scraped_date': datetime.now().isoformat()
            }
            articles.append(article)

        logger.info(f"Scraped {len(articles)} changelog entries from Gemini CLI")
        return articles

    # =========================================================================
    # Content Classification
    # =========================================================================

    def classify_content_type(self, title, content):
        """Classify the type of LLM update based on title and content.
        Returns max 2 most relevant tags to avoid over-classification.
        """
        text = f"{title} {content}".lower()
        content_types = []
        scores = {}  # Track confidence scores

        # Detect if this is a feature/product update context (not a model release)
        # These indicate the article is about using AI in a product, not releasing a new model
        feature_context_indicators = [
            'workspace', 'google meet', 'gmail', 'classroom', 'google drive',
            'take notes', 'speech translation', 'emoji reaction', 'audio lesson',
            'weekly recap', 'admin console', 'migrate files', 'dropbox',
            'writing tools', 'copilot in', 'powered by'
        ]
        is_feature_context = any(kw in text for kw in feature_context_indicators)

        # Model Release - require actual model names/versions, not just generic keywords
        # Must have both an indicator word AND a model identifier
        # BUT exclude if it's clearly a feature context (e.g., "Gemini in Meet")
        model_indicators = ['new model', 'model release', 'launching', 'introducing',
                           'announcing', "we're releasing", 'now available']
        model_identifiers = ['gpt-4', 'gpt-5', 'claude-3', 'claude-4', 'claude opus', 'claude sonnet', 'claude haiku',
                            'gemini 2', 'gemini 3', 'gemini-2', 'gemini-3', 'gemini flash', 'gemini pro',
                            'llama 3', 'llama 4', 'llama-3', 'llama-4',
                            'mistral-', 'mixtral', 'codestral', 'devstral',
                            'o1-', 'o3-', 'o4-',
                            'transformers 5', 'v5.0', 'v4.0', 'rc1', 'rc2',
                            'ocr 3', 'ocr-3']

        # Stricter model identifiers that always indicate a model release
        strict_model_identifiers = ['gpt-5', 'claude-4', 'llama 4', 'llama-4', 'gemini 3 flash',
                                   'transformers 5', 'v5.0', 'rc1', 'rc2', 'ocr 3', 'ocr-3',
                                   'codestral', 'devstral', 'mixtral']

        has_indicator = any(kw in text for kw in model_indicators)
        has_identifier = any(kw in text for kw in model_identifiers)
        has_strict_identifier = any(kw in text for kw in strict_model_identifiers)

        # Only classify as model_release if:
        # 1. Has a strict identifier (always a model release), OR
        # 2. Has indicator + identifier AND NOT in a feature context
        if has_strict_identifier:
            scores['model_release'] = 3  # High priority
        elif has_indicator and has_identifier and not is_feature_context:
            scores['model_release'] = 2  # Medium priority

        # API Update - more specific keywords
        api_keywords = ['api update', 'api change', 'new endpoint', 'deprecation',
                       'breaking change', 'rate limit', 'sdk update', 'library update',
                       'api version', 'rest api', 'streaming api', '/v1/', 'endpoint']
        if any(kw in text for kw in api_keywords):
            scores['api_update'] = 2

        # Feature Announcement - more specific keywords
        feature_keywords = ['new feature', 'new capability', 'we\'re adding',
                          'now supports', 'beta release', 'function calling',
                          'tool use', 'multimodal', 'code interpreter',
                          'file upload', 'image generation', 'agent loop']
        if any(kw in text for kw in feature_keywords):
            scores['feature_announcement'] = 2

        # Research - more specific keywords
        research_keywords = ['research paper', 'benchmark', 'evaluation', 'technical report',
                           'arxiv', 'findings', 'study shows', 'paper:', 'research:']
        if any(kw in text for kw in research_keywords):
            scores['research'] = 2

        # Pricing Change - more specific keywords
        pricing_keywords = ['pricing update', 'price change', 'new pricing', 'cost reduction',
                          'free tier', 'rate change', 'token price', 'billing']
        if any(kw in text for kw in pricing_keywords):
            scores['pricing_change'] = 2

        # Security Notice - more specific keywords (high priority)
        security_keywords = ['security update', 'vulnerability', 'cve-', 'security patch',
                           'safety update', 'content policy', 'security advisory', 'security fix']
        if any(kw in text for kw in security_keywords):
            scores['security_notice'] = 3  # High priority

        # Sort by score and take top 2
        if scores:
            sorted_types = sorted(scores.items(), key=lambda x: x[1], reverse=True)
            content_types = [t[0] for t in sorted_types[:2]]

        # Default if no classification
        if not content_types:
            content_types.append('general_update')

        return content_types

    # =========================================================================
    # Headless Browser Scraping (for sites that block regular requests)
    # =========================================================================

    def scrape_headless(self, source):
        """Scrape JavaScript-rendered pages using Playwright with stealth settings"""
        url = source.get('url')
        provider = source.get('provider', 'Unknown')
        product = source.get('product', 'Unknown')
        wait_for = source.get('wait_for', 'body')
        selectors = source.get('selectors', {})

        logger.info(f"Fetching with headless browser: {url}")

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.warning("Playwright not installed. Run: pip install playwright && playwright install chromium")
            return self._scrape_headless_fallback(source, url)

        articles = []

        try:
            with sync_playwright() as p:
                # Launch with stealth-like settings
                browser = None
                try:
                    browser = p.chromium.launch(
                        headless=True,
                        args=[
                            '--disable-blink-features=AutomationControlled',
                            '--disable-dev-shm-usage',
                            '--no-sandbox',
                        ]
                    )
                except Exception:
                    try:
                        browser = p.firefox.launch(headless=True)
                    except Exception as e:
                        logger.error(f"Failed to launch any browser: {e}")
                        return self._scrape_headless_fallback(source, url)

                # Create context with realistic settings
                context = browser.new_context(
                    user_agent=random.choice(self.user_agents),
                    viewport={'width': 1920, 'height': 1080},
                    locale='en-US',
                    timezone_id='America/New_York',
                )

                # Add stealth scripts to avoid detection
                context.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                    Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                    Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
                    window.chrome = {runtime: {}};
                """)

                page = context.new_page()

                try:
                    # Navigate with longer timeout
                    page.goto(url, timeout=60000, wait_until='domcontentloaded')

                    # Wait for dynamic content
                    try:
                        page.wait_for_selector(wait_for, timeout=15000, state='attached')
                    except Exception:
                        logger.warning(f"Wait for selector '{wait_for}' timed out, continuing anyway")

                    # Extra wait for JS rendering
                    time.sleep(3)

                    # Get page content
                    html = page.content()
                    soup = BeautifulSoup(html, 'html.parser')

                    # Route to specific parser based on provider
                    if 'perplexity' in provider.lower():
                        articles = self._parse_perplexity_changelog(soup, source, url)
                    elif 'cursor' in provider.lower():
                        articles = self._parse_cursor_blog(soup, source, url)
                    else:
                        # Use generic web scraper
                        articles = self._scrape_generic_headless(soup, source, url, selectors)

                    logger.info(f"Found {len(articles)} articles from {url}")

                except Exception as e:
                    logger.error(f"Page navigation failed for {url}: {e}")

                browser.close()

        except Exception as e:
            logger.error(f"Headless scraping failed for {url}: {str(e)}")
            articles = self._scrape_headless_fallback(source, url)

        return articles

    def _scrape_headless_fallback(self, source, url):
        """Fallback to requests when Playwright is not available"""
        logger.info(f"Using requests fallback for {url}")
        try:
            response = self.session.get(url, headers=self._get_headers(), timeout=30)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                return self._scrape_generic_headless(soup, source, url, source.get('selectors', {}))
            else:
                logger.warning(f"Fallback request failed with status {response.status_code}")
                return []
        except Exception as e:
            logger.error(f"Fallback request failed: {e}")
            return []

    def _scrape_generic_headless(self, soup, source, url, selectors):
        """Generic scraper for headless-fetched pages"""
        provider = source.get('provider', 'Unknown')
        product = source.get('product', 'Unknown')
        articles = []

        # Use provided selectors or defaults
        container_sel = selectors.get('article_container', 'article, section, [class*="post"], [class*="entry"]')
        title_sel = selectors.get('title', 'h2, h3, h4')
        link_sel = selectors.get('link', 'a')
        date_sel = selectors.get('date', 'time, [datetime], [class*="date"]')
        content_sel = selectors.get('content', 'p')

        containers = soup.select(container_sel)
        logger.info(f"Found {len(containers)} potential article containers")

        for container in containers[:50]:  # Limit to avoid noise
            try:
                # Extract title
                title_elem = container.select_one(title_sel)
                title = title_elem.get_text(strip=True) if title_elem else None

                if not title or not self._is_valid_title(title):
                    continue

                # Extract link
                link_elem = container.select_one(link_sel)
                article_url = None
                if link_elem and link_elem.get('href'):
                    article_url = urljoin(url, link_elem['href'])
                elif container.name == 'a' and container.get('href'):
                    article_url = urljoin(url, container['href'])

                # Extract date
                date_elem = container.select_one(date_sel)
                pub_date = None
                if date_elem:
                    date_str = date_elem.get('datetime') or date_elem.get_text(strip=True)
                    try:
                        pub_date = date_parser.parse(date_str, fuzzy=True)
                    except:
                        pass

                # Extract content
                content_elem = container.select_one(content_sel)
                content = content_elem.get_text(strip=True) if content_elem else ''

                articles.append({
                    'title': title,
                    'url': article_url or url,
                    'author': provider,
                    'published_date': pub_date,
                    'content': content[:2000] if content else '',
                    'source': source.get('name', 'Unknown'),
                    'provider': provider,
                    'product': product,
                })

            except Exception as e:
                logger.debug(f"Error parsing container: {e}")
                continue

        return articles

    def _parse_perplexity_changelog(self, soup, source, url):
        """Parse Perplexity changelog page (Framer-based structure)"""
        provider = source.get('provider', 'Perplexity')
        product = source.get('product', 'Perplexity')
        articles = []
        seen_titles = set()

        # Pattern 1: Find h4 tags with "What We Shipped" titles (Framer structure)
        # These contain titles like "What We Shipped - January 16th, 2026"
        shipped_headings = soup.find_all('h4', string=re.compile(r'What We Shipped', re.IGNORECASE))

        for heading in shipped_headings:
            try:
                title = heading.get_text(strip=True)

                if title in seen_titles:
                    continue
                seen_titles.add(title)

                # Extract date from title like "What We Shipped - January 16th, 2026"
                pub_date = None
                date_match = re.search(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}', title, re.IGNORECASE)
                if date_match:
                    try:
                        pub_date = date_parser.parse(date_match.group(), fuzzy=True)
                    except:
                        pass

                # Get content from parent container
                # Walk up to find the container div, then get all text
                container = heading.parent
                for _ in range(3):  # Walk up a few levels
                    if container and container.parent:
                        container = container.parent

                content = ''
                if container:
                    # Get text but exclude the title we already have
                    content_text = container.get_text(' ', strip=True)
                    # Remove the title from content
                    content = content_text.replace(title, '').strip()
                    # Clean up "See changes" links
                    content = re.sub(r'\s*See changes\s*', ' ', content).strip()

                    # If no date from title, try to extract from content date code (e.g., "12.12.25")
                    if not pub_date:
                        date_code_match = re.search(r'(\d{2})\.(\d{2})\.(\d{2})', content)
                        if date_code_match:
                            month, day, year = date_code_match.groups()
                            try:
                                # Assume 20xx for year
                                full_year = 2000 + int(year)
                                pub_date = datetime(full_year, int(month), int(day))
                            except:
                                pass

                if title and len(title) > 10:
                    articles.append({
                        'title': title,
                        'url': url,
                        'author': provider,
                        'published_date': pub_date,
                        'content': content[:2000] if content else '',
                        'source': source.get('name', 'Perplexity Changelog'),
                        'provider': provider,
                        'product': product,
                    })
            except Exception as e:
                logger.debug(f"Error parsing Framer changelog entry: {e}")
                continue

        # Pattern 2: Fallback - look for any text matching "What We Shipped"
        if not articles:
            shipped_texts = soup.find_all(string=re.compile(r'What We Shipped'))
            for text_node in shipped_texts:
                try:
                    title = text_node.strip()
                    if not title or title in seen_titles:
                        continue
                    seen_titles.add(title)

                    # Extract date
                    pub_date = None
                    date_match = re.search(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}', title, re.IGNORECASE)
                    if date_match:
                        try:
                            pub_date = date_parser.parse(date_match.group(), fuzzy=True)
                        except:
                            pass

                    # Get parent for content
                    parent = text_node.parent
                    if parent:
                        grandparent = parent.parent.parent if parent.parent else parent
                        content = grandparent.get_text(' ', strip=True) if grandparent else ''
                        content = content.replace(title, '').strip()[:2000]
                    else:
                        content = ''

                    if len(title) > 10:
                        articles.append({
                            'title': title,
                            'url': url,
                            'author': provider,
                            'published_date': pub_date,
                            'content': content,
                            'source': source.get('name', 'Perplexity Changelog'),
                            'provider': provider,
                            'product': product,
                        })
                except Exception as e:
                    logger.debug(f"Error parsing text node: {e}")
                    continue

        logger.info(f"Parsed {len(articles)} Perplexity changelog entries")
        return articles

    def _parse_cursor_blog(self, soup, source, url):
        """Parse Cursor blog page"""
        provider = source.get('provider', 'Cursor')
        product = source.get('product', 'Cursor')
        articles = []
        seen_urls = set()

        # Find all links to blog posts (not categories or pagination)
        blog_links = soup.select('a[href^="/blog/"]')

        for link in blog_links:
            try:
                href = link.get('href', '')

                # Skip category pages, pagination, and the main blog link
                if not href or href == '/blog' or '/topic/' in href or '/page/' in href:
                    continue
                if href in seen_urls:
                    continue
                seen_urls.add(href)

                # Get all text from the link
                full_text = link.get_text(' ', strip=True)

                # Extract title - first sentence or up to first period
                title_match = re.match(r'^([^\.]+(?:\.(?!\s*[a-z]))?)', full_text)
                if title_match:
                    title = title_match.group(1).strip()
                else:
                    title = full_text[:100]

                # Clean up title if it's too long (contains excerpt)
                if len(title) > 80:
                    # Try to find a natural break
                    words = title.split()
                    if len(words) > 10:
                        title = ' '.join(words[:10]) + '...'

                # Look for date in the text
                date_match = re.search(
                    r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4}',
                    full_text
                )
                pub_date = None
                if date_match:
                    try:
                        pub_date = date_parser.parse(date_match.group(), fuzzy=True)
                    except:
                        pass

                # Get excerpt (remaining text after title)
                excerpt = full_text.replace(title, '').strip()
                if date_match:
                    excerpt = excerpt.replace(date_match.group(), '').strip()
                # Clean up category labels
                excerpt = re.sub(r'^(product|research|company|customers|news)\s*·?\s*', '', excerpt, flags=re.IGNORECASE)

                article_url = f'https://cursor.com{href}'

                articles.append({
                    'title': title,
                    'url': article_url,
                    'author': provider,
                    'published_date': pub_date,
                    'content': excerpt[:2000] if excerpt else '',
                    'source': source.get('name', 'Cursor Blog'),
                    'provider': provider,
                    'product': product,
                })

            except Exception as e:
                logger.debug(f"Error parsing Cursor blog entry: {e}")
                continue

        logger.info(f"Parsed {len(articles)} Cursor blog entries")
        return articles
