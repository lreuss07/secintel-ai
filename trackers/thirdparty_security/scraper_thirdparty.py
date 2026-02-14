"""
Third-party Security Tools Scraper for SecIntel AI.
Handles multiple source types: RSS feeds, JSON APIs, web scraping, and headless browser.
"""

import logging
import requests
import feedparser
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from dateutil import parser as date_parser
import re
import time
import random

logger = logging.getLogger(__name__)


class ThirdPartySecurityScraper:
    """Multi-source scraper for third-party security tool updates"""

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
                elif source_type == 'api':
                    articles = self.scrape_api(source)
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
        url = source.get('url')
        vendor = source.get('vendor', 'Unknown')
        products = source.get('products', [])
        product = source.get('product')
        filter_pattern = source.get('filter_pattern')
        filter_by_title = source.get('filter_by_title', False)

        logger.info(f"Fetching RSS feed: {url}")

        try:
            feed = feedparser.parse(url)
        except Exception as e:
            logger.error(f"Failed to parse RSS feed {url}: {str(e)}")
            return []

        articles = []

        for entry in feed.entries:
            title = entry.get('title', '')
            link = entry.get('link', '')
            published = entry.get('published', entry.get('updated', ''))
            description = entry.get('description', entry.get('summary', ''))

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

            # Filter by product name if configured (for multi-product feeds)
            if filter_by_title and products:
                matched_product = None
                for prod in products:
                    if prod.lower() in title.lower():
                        matched_product = prod
                        break
                if not matched_product:
                    continue
                article_product = matched_product
            elif filter_pattern:
                if filter_pattern.lower() not in title.lower() and filter_pattern.lower() not in description.lower():
                    continue
                article_product = product
            else:
                article_product = product

            # Classify update type
            update_types = self.classify_update_type(title, description, vendor)

            article = {
                'source': source.get('name'),
                'vendor': vendor,
                'product': article_product,
                'title': title,
                'url': link,
                'published_date': pub_date.isoformat() if pub_date else None,
                'content': description,
                'update_type': update_types,
                'scraped_date': datetime.now().isoformat()
            }
            articles.append(article)

        return articles

    # =========================================================================
    # JSON API Scraping
    # =========================================================================

    def scrape_api(self, source):
        """Scrape JSON API source"""
        url = source.get('url')
        vendor = source.get('vendor', 'Unknown')
        product = source.get('product', 'Unknown')
        params = source.get('params', {})
        # Base URL for making relative links absolute
        base_url = source.get('base_url', '')

        logger.info(f"Fetching API: {url}")

        # Build query parameters
        query_params = {}
        for key, value in params.items():
            if isinstance(value, list):
                # Handle multiple values for same parameter (labelkey)
                for v in value:
                    if key not in query_params:
                        query_params[key] = []
                    if isinstance(query_params[key], list):
                        query_params[key].append(v)
                    else:
                        query_params[key] = [query_params[key], v]
            else:
                query_params[key] = value

        # Build URL with parameters (handle multiple values)
        url_with_params = url + "?"
        param_parts = []
        for key, value in query_params.items():
            if isinstance(value, list):
                for v in value:
                    param_parts.append(f"{key}={v}")
            else:
                param_parts.append(f"{key}={value}")
        url_with_params += "&".join(param_parts)

        # Use JSON Accept header for API requests
        headers = self._get_headers()
        headers['Accept'] = 'application/json, text/html'

        try:
            response = self.session.get(url_with_params, headers=headers, timeout=30)
            response.raise_for_status()
        except Exception as e:
            logger.error(f"Failed to fetch API {url}: {str(e)}")
            return []

        articles = []

        # Try JSON parsing first (for JSON APIs)
        try:
            import json
            data = json.loads(response.text)

            # Handle API response with SearchResults key
            results_list = None
            if isinstance(data, dict):
                if 'SearchResults' in data:
                    results_list = data.get('SearchResults', [])
                elif 'results' in data:
                    results_list = data.get('results', [])

            if results_list:
                for item in results_list:
                    title = item.get('title', '')
                    link = item.get('link', item.get('url', ''))

                    # Handle API date fields
                    pub_date_str = item.get('createdOn', item.get('addedOn', item.get('lastRevised', '')))
                    description = item.get('snippet', item.get('description', ''))

                    # Make link absolute if relative
                    if link and not link.startswith('http') and base_url:
                        link = f"{base_url}{link}"

                    # Parse date
                    pub_date = None
                    if pub_date_str:
                        try:
                            pub_date = date_parser.parse(pub_date_str, fuzzy=True)
                        except:
                            pass

                    if not self._is_within_time_window(pub_date):
                        continue

                    update_types = self.classify_update_type(title, description, vendor)

                    article = {
                        'source': source.get('name'),
                        'vendor': vendor,
                        'product': product,
                        'title': title,
                        'url': link,
                        'published_date': pub_date.isoformat() if pub_date else None,
                        'content': description[:5000] if description else '',
                        'update_type': update_types,
                        'scraped_date': datetime.now().isoformat()
                    }
                    articles.append(article)

                # If we got JSON results, return them
                if articles:
                    return articles

        except json.JSONDecodeError:
            pass  # Fall through to HTML parsing

        # Fall back to HTML parsing
        soup = BeautifulSoup(response.text, 'html.parser')

        # Look for search result items
        result_items = soup.find_all('div', class_='search-result') or soup.find_all('article') or soup.find_all('li', class_='result')

        if not result_items:
            # Try to extract from JSON if response is JSON
            try:
                import json
                data = json.loads(response.text)

                # Handle API response with SearchResults key
                results_list = None
                if isinstance(data, dict):
                    if 'SearchResults' in data:
                        results_list = data.get('SearchResults', [])
                    elif 'results' in data:
                        results_list = data.get('results', [])

                if results_list:
                    for item in results_list:
                        title = item.get('title', '')
                        link = item.get('link', item.get('url', ''))

                        # Handle API date fields (createdOn, addedOn)
                        pub_date_str = item.get('createdOn', item.get('addedOn', item.get('lastRevised', item.get('published', ''))))
                        description = item.get('snippet', item.get('description', item.get('summary', '')))

                        # Extract additional info from metadata if available
                        metadata = item.get('metadata', {})
                        if not description and metadata:
                            description = metadata.get('description', '')

                        # Make link absolute if relative
                        if link and not link.startswith('http') and base_url:
                            link = f"{base_url}{link}"

                        # Parse date (ISO format like "2025-12-15T10:30:00Z")
                        pub_date = None
                        if pub_date_str:
                            try:
                                pub_date = date_parser.parse(pub_date_str, fuzzy=True)
                            except:
                                pass

                        if not self._is_within_time_window(pub_date):
                            continue

                        update_types = self.classify_update_type(title, description, vendor)

                        article = {
                            'source': source.get('name'),
                            'vendor': vendor,
                            'product': product,
                            'title': title,
                            'url': link,
                            'published_date': pub_date.isoformat() if pub_date else None,
                            'content': description[:5000] if description else '',
                            'update_type': update_types,
                            'scraped_date': datetime.now().isoformat()
                        }
                        articles.append(article)
            except json.JSONDecodeError:
                pass

        # Parse HTML results
        for item in result_items:
            title_elem = item.find(['h2', 'h3', 'h4', 'a'])
            title = title_elem.get_text(strip=True) if title_elem else ''

            link_elem = item.find('a', href=True)
            link = link_elem['href'] if link_elem else ''
            if link and not link.startswith('http') and base_url:
                link = f"{base_url}{link}"

            date_elem = item.find(['time', 'span'], class_=['date', 'published'])
            pub_date_str = date_elem.get_text(strip=True) if date_elem else ''

            description_elem = item.find(['p', 'div'], class_=['description', 'summary', 'excerpt'])
            description = description_elem.get_text(strip=True) if description_elem else ''

            # Parse date
            pub_date = None
            if pub_date_str:
                try:
                    pub_date = date_parser.parse(pub_date_str, fuzzy=True)
                except:
                    pass

            if not self._is_within_time_window(pub_date):
                continue

            if title:
                update_types = self.classify_update_type(title, description, vendor)

                article = {
                    'source': source.get('name'),
                    'vendor': vendor,
                    'product': product,
                    'title': title,
                    'url': link,
                    'published_date': pub_date.isoformat() if pub_date else None,
                    'content': description,
                    'update_type': update_types,
                    'scraped_date': datetime.now().isoformat()
                }
                articles.append(article)

        return articles

    # =========================================================================
    # Static Web Page Scraping
    # =========================================================================

    def scrape_web_page(self, source):
        """Scrape static web page source"""
        url = source.get('url')
        vendor = source.get('vendor', 'Unknown')
        product = source.get('product', 'Unknown')
        selectors = source.get('selectors', {})
        source_name = source.get('name', 'Unknown')

        logger.info(f"Fetching web page: {url}")

        try:
            response = self.session.get(url, headers=self._get_headers(), timeout=30)
            response.raise_for_status()
        except Exception as e:
            logger.error(f"Failed to fetch {url}: {str(e)}")
            return []

        soup = BeautifulSoup(response.text, 'html.parser')

        # Route to specific scraper based on parser config
        parser_type = source.get('parser', 'generic')
        if parser_type == 'release_page':
            return self._scrape_release_page(soup, source)
        elif parser_type == 'version_list':
            return self._scrape_version_list(soup, source)
        else:
            return self._scrape_generic_web(soup, source)

    def _scrape_release_page(self, soup, source):
        """Scrape release pages with date-attributed release sections"""
        vendor = source.get('vendor', 'Unknown')
        product = source.get('product', 'Unknown')
        articles = []

        releases = soup.find_all('div', class_='release') or soup.find_all(attrs={'data-release-date': True})

        for release in releases:
            # Get date from data attribute
            date_str = release.get('data-release-date', '')
            pub_date = None
            if date_str:
                try:
                    pub_date = date_parser.parse(date_str)
                except:
                    pass

            if not self._is_within_time_window(pub_date):
                continue

            # Get title
            title_elem = release.find(['h2', 'h3', 'h4'])
            title = title_elem.get_text(strip=True) if title_elem else f"{product} Release {date_str}"

            # Get content
            content_parts = []
            for p in release.find_all(['p', 'li']):
                text = p.get_text(strip=True)
                if text:
                    content_parts.append(text)
            content = ' '.join(content_parts)

            # Get URL (if linked)
            link = source.get('url')
            if date_str:
                link = f"{link}#{date_str}"

            update_types = self.classify_update_type(title, content, vendor)

            article = {
                'source': source.get('name'),
                'vendor': vendor,
                'product': product,
                'title': title,
                'url': link,
                'published_date': pub_date.isoformat() if pub_date else None,
                'content': content[:5000],  # Limit content length
                'update_type': update_types,
                'scraped_date': datetime.now().isoformat()
            }
            articles.append(article)

        return articles

    def _scrape_version_list(self, soup, source):
        """Scrape release notes pages with version group lists"""
        vendor = source.get('vendor', 'Unknown')
        product = source.get('product', 'Unknown')
        base_url = source.get('base_url', '')
        articles = []

        # Find all list items containing version groups
        # Structure: <li> containing <div class="heading"> and <ul class="group">
        version_items = soup.find_all('li')

        for item in version_items:
            # Get version heading from this item
            heading = item.find('div', class_='heading')
            if not heading:
                continue

            version = heading.get_text(strip=True)

            # Find the group list within this item
            group = item.find('ul', class_='group')
            if not group:
                continue

            # Find all list items with release note links
            release_items = group.find_all('li')
            for release_item in release_items:
                link = release_item.find('a', href=True)
                if not link:
                    continue

                title = link.get_text(strip=True)
                href = link['href']

                if not href.startswith('http') and base_url:
                    href = f"{base_url}{href}"

                # Extract date from the span with class "content"
                date_span = release_item.find('span', class_='content')
                pub_date = None
                if date_span:
                    date_text = date_span.get_text(strip=True)
                    # Date format is like "15/Dec/2025" or "19/Dec/2025"
                    try:
                        pub_date = date_parser.parse(date_text, fuzzy=True)
                    except:
                        pass

                # If no date in span, try to find it in the text
                if not pub_date:
                    date_match = re.search(r'(\d{1,2}/\w{3}/\d{4})', release_item.get_text())
                    if date_match:
                        try:
                            pub_date = date_parser.parse(date_match.group(1), fuzzy=True)
                        except:
                            pass

                if not self._is_within_time_window(pub_date):
                    continue

                # Only include actual release notes
                if 'release' in title.lower() and 'notes' in title.lower():
                    update_types = self.classify_update_type(title, '', vendor)

                    article = {
                        'source': source.get('name'),
                        'vendor': vendor,
                        'product': product,
                        'title': title,
                        'url': href,
                        'published_date': pub_date.isoformat() if pub_date else None,
                        'content': f"Release Notes for {version}",
                        'update_type': update_types,
                        'scraped_date': datetime.now().isoformat()
                    }
                    articles.append(article)

        return articles

    def _scrape_generic_web(self, soup, source):
        """Generic web page scraper fallback"""
        vendor = source.get('vendor', 'Unknown')
        product = source.get('product', 'Unknown')
        selectors = source.get('selectors', {})
        articles = []

        # Navigation/junk URL patterns to skip
        skip_url_patterns = [
            r'^/Account/', r'^/Login', r'^/Logout', r'^/Register',
            r'^/Search', r'^/Help', r'^/Contact', r'^/About',
            r'^#', r'^javascript:', r'^mailto:'
        ]

        # Navigation/junk title patterns to skip
        skip_title_patterns = [
            r'^(Login|Logout|Sign In|Sign Out|Register|Search|Help|Contact|About)$',
            r'^(Home|Menu|Navigation|Skip to|Back to)$'
        ]

        # Try common patterns
        items = soup.find_all('article') or soup.find_all('div', class_=re.compile(r'release|update|changelog|entry'))

        for item in items:
            title_elem = item.find(['h1', 'h2', 'h3', 'h4', 'a'])
            title = title_elem.get_text(strip=True) if title_elem else ''

            link_elem = item.find('a', href=True)
            link = link_elem['href'] if link_elem else source.get('url')

            # Skip navigation/junk URLs
            if link and any(re.match(pattern, link, re.IGNORECASE) for pattern in skip_url_patterns):
                continue

            # Skip navigation/junk titles
            if title and any(re.match(pattern, title, re.IGNORECASE) for pattern in skip_title_patterns):
                continue

            # Skip very short titles (likely navigation elements)
            if len(title) < 5:
                continue

            date_elem = item.find(['time', 'span', 'div'], class_=re.compile(r'date|time|published'))
            date_str = date_elem.get_text(strip=True) if date_elem else ''

            content_elem = item.find(['p', 'div'], class_=re.compile(r'content|body|description|summary'))
            content = content_elem.get_text(strip=True) if content_elem else item.get_text(strip=True)[:1000]

            # Skip entries with very short content (likely not real articles)
            if len(content) < 20:
                continue

            pub_date = None
            if date_str:
                try:
                    pub_date = date_parser.parse(date_str, fuzzy=True)
                except:
                    pass

            if not self._is_within_time_window(pub_date):
                continue

            if title:
                update_types = self.classify_update_type(title, content, vendor)

                article = {
                    'source': source.get('name'),
                    'vendor': vendor,
                    'product': product,
                    'title': title,
                    'url': link,
                    'published_date': pub_date.isoformat() if pub_date else None,
                    'content': content[:5000],
                    'update_type': update_types,
                    'scraped_date': datetime.now().isoformat()
                }
                articles.append(article)

        return articles

    # =========================================================================
    # Headless Browser Scraping (JavaScript-rendered pages)
    # =========================================================================

    def scrape_headless(self, source):
        """Scrape JavaScript-rendered pages using Playwright"""
        url = source.get('url')
        url_template = source.get('url_template')
        vendor = source.get('vendor', 'Unknown')
        product = source.get('product', 'Unknown')
        wait_for = source.get('wait_for', 'body')
        dynamic_year = source.get('dynamic_year', False)
        fallback_to_previous_year = source.get('fallback_to_previous_year', False)

        # Handle dynamic year in URL
        years_to_try = []
        if url_template and dynamic_year:
            current_year = datetime.now().year
            years_to_try.append(current_year)
            if fallback_to_previous_year:
                years_to_try.append(current_year - 1)
            url = url_template.format(year=current_year)

        logger.info(f"Fetching with headless browser: {url}")

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.warning("Playwright not installed. Falling back to requests.")
            # Try with requests as fallback
            return self._scrape_headless_fallback(source, url)

        articles = []

        try:
            with sync_playwright() as p:
                # Try Chromium first (more reliable), fallback to Firefox
                browser = None
                try:
                    browser = p.chromium.launch(headless=True)
                except Exception:
                    try:
                        browser = p.firefox.launch(headless=True)
                    except Exception as e:
                        logger.error(f"Failed to launch any browser: {e}")
                        return self._scrape_headless_fallback(source, url)

                context = browser.new_context(
                    user_agent=random.choice(self.user_agents),
                    viewport={'width': 1920, 'height': 1080}
                )
                page = context.new_page()

                # Try each year URL if using dynamic years
                urls_to_try = [url]
                if url_template and years_to_try:
                    urls_to_try = [url_template.format(year=year) for year in years_to_try]

                for try_url in urls_to_try:
                    logger.info(f"Trying URL: {try_url}")

                    # Navigate with longer timeout (90s) for slow pages
                    try:
                        page.goto(try_url, timeout=90000, wait_until='domcontentloaded')
                    except Exception as e:
                        logger.warning(f"Navigation timed out for {try_url}: {e}")
                        continue

                    # Try to wait for selector, but don't fail if it times out
                    try:
                        page.wait_for_selector(wait_for, timeout=15000, state='attached')
                    except Exception as e:
                        logger.warning(f"Wait for selector timed out for {try_url}, trying next URL")
                        continue

                    # Give JS time to render
                    time.sleep(3)

                    # Get page content
                    html = page.content()
                    soup = BeautifulSoup(html, 'html.parser')

                    # Route to specific parser based on config
                    parser_type = source.get('parser', 'generic')
                    parser_map = {
                        'release_notes_dated': self._parse_release_notes_dated,
                        'changelog_table': self._parse_changelog_table,
                        'monthly_sections': self._parse_monthly_sections,
                        'generic': self._scrape_generic_web,
                    }
                    parser = parser_map.get(parser_type, self._scrape_generic_web)
                    articles = parser(soup, source, try_url)

                    # If we got articles, stop trying other URLs
                    if articles:
                        logger.info(f"Found {len(articles)} articles from {try_url}")
                        break
                    else:
                        logger.warning(f"No articles found from {try_url}, trying next URL if available")

                browser.close()

        except Exception as e:
            logger.error(f"Headless scraping failed for {url}: {str(e)}")
            # Try fallback
            articles = self._scrape_headless_fallback(source, url)

        return articles

    def _scrape_headless_fallback(self, source, url):
        """Fallback when Playwright is not available"""
        logger.info(f"Using requests fallback for {url}")
        vendor = source.get('vendor', 'Unknown')
        product = source.get('product', 'Unknown')

        try:
            response = self.session.get(url, headers=self._get_headers(), timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            # Try generic scraping
            return self._scrape_generic_web(soup, source)
        except Exception as e:
            logger.error(f"Fallback scraping failed: {str(e)}")
            return []

    def _parse_release_notes_dated(self, soup, source, url):
        """Parse release notes with dated sections (date headers followed by feature entries)"""
        vendor = source.get('vendor', 'Unknown')
        product = source.get('product', 'Unknown')
        articles = []

        # Look for date section containers (div with date header)
        # Format: <div class="mb-2 r-notes-title"><b>DATE</b></div>
        date_divs = soup.find_all('div', class_='r-notes-title')

        for date_div in date_divs:
            # Extract date from <b> tag inside the div
            date_b = date_div.find('b')
            if not date_b:
                continue

            date_text = date_b.get_text(strip=True)

            # Parse date
            pub_date = None
            try:
                pub_date = date_parser.parse(date_text, fuzzy=True)
            except:
                continue

            if not self._is_within_time_window(pub_date):
                continue

            # Find the parent container that holds all releases for this date
            parent = date_div.find_parent('div', class_='parent-release-notes')
            if not parent:
                continue

            # Find all individual release items within this date section
            # Each release has <h3 class="mt-1 release-notes-title">
            release_headings = parent.find_all('h3', class_='release-notes-title')

            for heading in release_headings:
                title_b = heading.find('b')
                if not title_b:
                    continue

                feature_title = title_b.get_text(strip=True)

                # Find the content div following this heading
                # It's typically <div class="article-page release-notes mt-2">
                content_div = heading.find_next_sibling('div', class_='release-notes')

                content_parts = []
                if content_div:
                    # Extract all text from paragraphs, lists, etc.
                    for elem in content_div.find_all(['p', 'li', 'div']):
                        text = elem.get_text(strip=True)
                        if text and len(text) > 10:  # Skip very short texts
                            content_parts.append(text)

                content = ' '.join(content_parts)

                if not content:
                    continue

                update_types = self.classify_update_type(feature_title, content, vendor)

                article = {
                    'source': source.get('name'),
                    'vendor': vendor,
                    'product': product,
                    'title': f"{feature_title} ({date_text})",
                    'url': url,
                    'published_date': pub_date.isoformat() if pub_date else None,
                    'content': content[:5000],
                    'update_type': update_types,
                    'scraped_date': datetime.now().isoformat()
                }
                articles.append(article)

        return articles

    def _parse_changelog_table(self, soup, source, url):
        """Parse changelog pages with table format (Release Date | Description columns)"""
        vendor = source.get('vendor', 'Unknown')
        product = source.get('product', 'Unknown')
        articles = []

        # Find article body
        article_body = soup.find('div', class_='article-content') or soup.find('article')

        if not article_body:
            logger.warning("Could not find article body in changelog page")
            return articles

        # Look for tables with "Release Date" and "Description" columns
        # Format: <table> with <tr> rows containing <td> cells
        tables = article_body.find_all('table')

        for table in tables:
            rows = table.find_all('tr')

            # Skip header row (first row usually has "Release Date | Description")
            for row in rows[1:]:  # Skip first row
                cells = row.find_all(['td', 'th'])

                if len(cells) < 2:
                    continue

                # First cell is the release date (e.g., "December 2025")
                date_cell = cells[0]
                date_text = date_cell.get_text(strip=True)

                # Second cell is the description
                description_cell = cells[1]
                description_text = description_cell.get_text(strip=True)

                # Parse date from first cell
                pub_date = None
                try:
                    # Parse "Month YYYY" format to first day of month
                    parsed_date = date_parser.parse(date_text, fuzzy=True, default=datetime(2000, 1, 1))

                    # For month-only dates (e.g., "December 2025"), use last day of month
                    # This ensures entries from that month are included in the time window
                    import calendar
                    last_day = calendar.monthrange(parsed_date.year, parsed_date.month)[1]
                    pub_date = datetime(parsed_date.year, parsed_date.month, last_day)
                except:
                    continue

                if not self._is_within_time_window(pub_date):
                    continue

                # Extract individual updates from the description
                # Two formats exist:
                # 1. "December 22, 2025 - " (with year)
                # 2. "December 18 - " (without year, infer from row header)

                # First try pattern with year
                update_pattern_with_year = re.compile(r'(\w+ \d{1,2}, \d{4})\s*-\s*(.+?)(?=\w+ \d{1,2},? \d{0,4}\s*-|$)', re.DOTALL)
                # Pattern without year (e.g., "December 18 -")
                update_pattern_no_year = re.compile(r'(\w+ \d{1,2})\s*-\s*(.+?)(?=\w+ \d{1,2},? \d{0,4}\s*-|$)', re.DOTALL)

                matches_with_year = update_pattern_with_year.findall(description_text)
                matches_no_year = update_pattern_no_year.findall(description_text)

                # Combine both types of matches
                all_updates = []

                # Add matches with explicit year
                for date_str, content in matches_with_year:
                    try:
                        parsed = date_parser.parse(date_str.strip(), fuzzy=True)
                        all_updates.append((parsed, content.strip(), date_str.strip()))
                    except:
                        pass

                # Add matches without year - infer year from pub_date
                for date_str, content in matches_no_year:
                    # Skip if this is already captured by the year pattern
                    # Check by comparing against the display strings (3rd element)
                    if any(date_str.strip() in display_str for _, _, display_str in all_updates):
                        continue
                    try:
                        # Parse with the year from pub_date (the row header like "December 2025")
                        date_with_year = f"{date_str.strip()}, {pub_date.year}"
                        parsed = date_parser.parse(date_with_year, fuzzy=True)
                        all_updates.append((parsed, content.strip(), date_str.strip()))
                    except:
                        pass

                if all_updates:
                    # Multiple updates in this cell
                    for specific_date, update_content, date_str_display in all_updates:
                        if not self._is_within_time_window(specific_date):
                            continue

                        update_types = self.classify_update_type(update_content, update_content, vendor)

                        # Create unique URL by adding date anchor
                        date_anchor = specific_date.strftime('%Y-%m-%d') if specific_date else date_str_display.replace(' ', '-').replace(',', '')
                        unique_url = f"{url}#{date_anchor}"

                        article = {
                            'source': source.get('name'),
                            'vendor': vendor,
                            'product': product,
                            'title': f"{product} Update - {date_str_display}",
                            'url': unique_url,
                            'published_date': specific_date.isoformat() if specific_date else None,
                            'content': update_content[:5000],
                            'update_type': update_types,
                            'scraped_date': datetime.now().isoformat()
                        }
                        articles.append(article)
                else:
                    # Single update in this cell
                    if len(description_text) > 20:  # Skip very short entries
                        update_types = self.classify_update_type(description_text, description_text, vendor)

                        # Create unique URL by adding date anchor
                        date_anchor = pub_date.strftime('%Y-%m-%d') if pub_date else date_text.replace(' ', '-').replace(',', '')
                        unique_url = f"{url}#{date_anchor}"

                        article = {
                            'source': source.get('name'),
                            'vendor': vendor,
                            'product': product,
                            'title': f"{product} Update - {date_text}",
                            'url': unique_url,
                            'published_date': pub_date.isoformat() if pub_date else None,
                            'content': description_text[:5000],
                            'update_type': update_types,
                            'scraped_date': datetime.now().isoformat()
                        }
                        articles.append(article)

        return articles

    def _parse_monthly_sections(self, soup, source, url):
        """Parse release notes organized by monthly sections (h2 month headers with content below)"""
        vendor = source.get('vendor', 'Unknown')
        product = source.get('product', 'Unknown')
        articles = []

        # Find the main content block - there may be multiple, find one with h2 tags
        content_blocks = soup.find_all('div', class_='content_block_text')
        content_block = None
        for block in content_blocks:
            if block.find('h2'):
                content_block = block
                break

        if not content_block:
            content_block = soup.find('article') or soup

        # Find all month headings (h2 tags with month/year format)
        month_headings = content_block.find_all('h2')

        for heading in month_headings:
            month_text = heading.get_text(strip=True)

            # Parse month/year from heading (e.g., "November 2025", "October 2025")
            pub_date = None
            try:
                # Parse to first day of month
                parsed_date = date_parser.parse(month_text, fuzzy=True, default=datetime(2000, 1, 1))

                # For month-based release notes, use the last day of the month for time window check
                # This ensures we include the entire month if any part of it is within the window
                import calendar
                last_day = calendar.monthrange(parsed_date.year, parsed_date.month)[1]
                pub_date = datetime(parsed_date.year, parsed_date.month, last_day)
            except:
                # Skip if can't parse date
                continue

            if not self._is_within_time_window(pub_date):
                continue

            # Collect content until next h2
            content_parts = []
            sibling = heading.find_next_sibling()
            while sibling and sibling.name != 'h2':
                if sibling.name in ['p', 'ul', 'ol', 'h3', 'h4', 'div']:
                    text = sibling.get_text(strip=True)
                    if text:
                        content_parts.append(text)
                sibling = sibling.find_next_sibling()

            content = ' '.join(content_parts)

            # Skip if no content found
            if not content:
                continue

            update_types = self.classify_update_type(month_text, content, vendor)

            article = {
                'source': source.get('name'),
                'vendor': vendor,
                'product': product,
                'title': f"{product} Release Notes - {month_text}",
                'url': url,
                'published_date': pub_date.isoformat() if pub_date else None,
                'content': content[:5000],
                'update_type': update_types,
                'scraped_date': datetime.now().isoformat()
            }
            articles.append(article)

        return articles

    # =========================================================================
    # Update Type Classification
    # =========================================================================

    def classify_update_type(self, title, content, vendor=None):
        """Classify the type of update based on title and content"""
        text = f"{title} {content}".lower()
        update_types = []

        # Feature Update
        feature_keywords = ['new feature', 'enhancement', 'added', 'introducing', 'now available',
                           'capability', 'support for', 'new in', 'what\'s new', 'release']
        if any(kw in text for kw in feature_keywords):
            update_types.append('Feature Update')

        # Bug Fix
        bugfix_keywords = ['bug fix', 'fixed', 'resolved', 'corrected', 'issue', 'defect', 'patch']
        if any(kw in text for kw in bugfix_keywords):
            update_types.append('Bug Fix')

        # Security Patch
        security_keywords = ['security', 'vulnerability', 'cve', 'exploit', 'critical', 'advisory',
                            'security patch', 'security update']
        if any(kw in text for kw in security_keywords):
            update_types.append('Security Patch')

        # Performance Improvement
        perf_keywords = ['performance', 'optimization', 'improved', 'faster', 'efficiency', 'speed']
        if any(kw in text for kw in perf_keywords):
            update_types.append('Performance Improvement')

        # Deprecation
        deprecation_keywords = ['deprecated', 'end of life', 'eol', 'retiring', 'removed', 'sunset',
                               'discontinued', 'no longer supported']
        if any(kw in text for kw in deprecation_keywords):
            update_types.append('Deprecation')

        # Known Issue
        known_issue_keywords = ['known issue', 'limitation', 'workaround', 'known bug']
        if any(kw in text for kw in known_issue_keywords):
            update_types.append('Known Issue')

        # Default if no classification
        if not update_types:
            update_types.append('General Update')

        return update_types
