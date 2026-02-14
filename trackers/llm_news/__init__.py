"""
LLM News tracker plugin for SecIntel AI.
Tracks news and updates from major Large Language Model providers.
"""

from core.base_tracker import BaseTracker
from core.lm_studio_connection import LMStudioConnectionManager
from .scraper_llm import LLMNewsScraper
from .summarizer_llm import LLMNewsSummarizer, LLMNewsExecutiveSummarizer
from .reporting_llm import LLMNewsReportGenerator
import logging

logger = logging.getLogger(__name__)


class LLMNewsTracker(BaseTracker):
    """Tracker for LLM news and updates"""

    def __init__(self, config, db_manager):
        super().__init__('llm_news', config, db_manager)

        # Load sources from tracker-specific config
        import os
        import yaml
        tracker_config_path = os.path.join(os.path.dirname(__file__), 'config.yaml')
        with open(tracker_config_path, 'r') as f:
            tracker_config = yaml.safe_load(f)
            self.config['sources'] = tracker_config.get('sources', [])

        # Initialize components
        self.scraper = None
        self.summarizer = None
        self.executive_summarizer = None
        self.reporter = LLMNewsReportGenerator()

        # Initialize LM Studio connection manager
        ai_config = self.config.get('ai', {})
        # Extract lmstudio-specific config for connection manager
        lmstudio_config = ai_config.get('lmstudio', {})
        self.connection_manager = LMStudioConnectionManager(lmstudio_config)

    def _get_model_name(self):
        """Get the configured AI model name for report attribution."""
        ai_config = self.config.get('ai', {})
        provider = ai_config.get('provider', 'lmstudio')

        if provider == 'lmstudio':
            lm_config = ai_config.get('lmstudio', {})
            return lm_config.get('model', 'local-model')
        elif provider == 'claude':
            claude_config = ai_config.get('claude', {})
            return claude_config.get('model', 'claude-sonnet')
        else:
            return provider

    def scrape(self):
        """Scrape LLM news from all configured sources"""
        self.logger.info("=" * 70)
        self.logger.info("Starting LLM news scraping operation")
        self.logger.info("=" * 70)

        time_window = self.config.get('time_window_days')
        sources = self.config['sources']
        if self.max_sources:
            self.logger.info(f"TESTING MODE: Limiting to {self.max_sources} sources (of {len(sources)})")
            sources = sources[:self.max_sources]
        self.scraper = LLMNewsScraper(
            sources,
            time_window_days=time_window,
            max_articles_per_source=self.max_articles_per_source
        )

        scraped_results = self.scraper.scrape_all_sources()

        total_articles = 0
        for source_name, articles in scraped_results.items():
            self.logger.info(f"Scraped {len(articles)} articles from {source_name}")
            total_articles += len(articles)

            for article in articles:
                # Store article in database
                article_id = self.db.store_article(article, tracker_name='llm_news')

                # Store content type tags if present
                if article.get('content_type') and article_id:
                    content_types = article['content_type']
                    if isinstance(content_types, list):
                        for ct in content_types:
                            self.db.store_tag(article_id, ct)
                    else:
                        self.db.store_tag(article_id, content_types)

                # Store provider tag
                if article.get('provider') and article_id:
                    self.db.store_tag(article_id, f"provider:{article['provider']}")

                # Store product tag
                if article.get('product') and article_id:
                    self.db.store_tag(article_id, f"product:{article['product']}")

        self.logger.info(f"Scraping operation completed - Total articles: {total_articles}")
        return total_articles

    def analyze(self):
        """Analyze LLM news articles with AI"""
        self.logger.info("=" * 70)
        self.logger.info("Starting LLM news analysis operation")
        self.logger.info("=" * 70)

        articles = self.db.get_articles_without_summary(tracker_name='llm_news')
        if self.max_summaries and len(articles) > self.max_summaries:
            self.logger.info(f"TESTING MODE: Limiting analysis to {self.max_summaries} articles (of {len(articles)})")
            articles = articles[:self.max_summaries]
        self.logger.info(f"Found {len(articles)} articles to analyze")

        if not articles:
            self.logger.info("No articles require analysis")
            return 0

        # Ensure LM Studio connection is established
        if not self.connection_manager.ensure_connection(allow_prompt=True):
            self.logger.error("Cannot proceed with analysis without LM Studio connection")
            return 0

        # Initialize summarizer with verified connection config
        ai_config = self.connection_manager.get_config()
        self.summarizer = LLMNewsSummarizer(ai_config=ai_config)

        for idx, article in enumerate(articles, 1):
            article_id = article['id']
            self.logger.info(f"Analyzing article {idx}/{len(articles)}: {article['title']}")

            try:
                # Get content type from tags
                tags = self.db.get_tags_for_article(article_id)
                content_types = [tag['tag'] for tag in tags if not tag['tag'].startswith('provider:') and not tag['tag'].startswith('product:')] if tags else None

                # Get provider from tags
                provider = None
                product = None
                if tags:
                    for tag in tags:
                        if tag['tag'].startswith('provider:'):
                            provider = tag['tag'].replace('provider:', '')
                        elif tag['tag'].startswith('product:'):
                            product = tag['tag'].replace('product:', '')

                # Generate summary
                summary, content_type = self.summarizer.summarize(
                    title=article['title'],
                    content=article['content'],
                    content_type=content_types,
                    provider=provider,
                    product=product
                )

                # Store summary with content type
                self.db.update_article_summary(article_id, summary, content_type=content_type)
                self.logger.info(f"Summary generated for article ID: {article_id} (type: {content_type})")

            except Exception as e:
                self.logger.error(f"Failed to analyze article ID {article_id}: {str(e)}")
                continue

        self.logger.info(f"Analysis operation completed - Processed {len(articles)} articles")
        return len(articles)

    def report(self, tier=None):
        """Generate LLM news reports"""
        self.logger.info("=" * 70)
        self.logger.info("Starting LLM news report generation")
        self.logger.info("=" * 70)

        # Determine time window based on tier
        if tier == 0:
            time_window = 1
            tier_name = "Tier 0: Daily Digest (24 hours)"
        elif tier == 1:
            time_window = 7
            tier_name = "Tier 1: Weekly Digest (7 days)"
        elif tier == 2:
            time_window = 14
            tier_name = "Tier 2: Bi-Weekly Review (14 days)"
        elif tier == 3:
            time_window = 30
            tier_name = "Tier 3: Monthly Archive (30 days)"
        else:
            time_window = self.config.get('time_window_days', 30)
            tier_name = f"Standard Report ({time_window} days)"

        self.logger.info(f"Generating {tier_name}")

        # Get recent articles
        recent_articles = self.db.get_recent_articles_with_summary(
            days=time_window,
            tracker_name='llm_news'
        )

        self.logger.info(f"Found {len(recent_articles)} LLM news articles from last {time_window} days")

        if not recent_articles:
            self.logger.warning("No recent LLM news articles with summaries available for reporting")
            return None

        # Filter out articles with generic/unhelpful titles and invalid URLs
        import re
        from urllib.parse import urlparse

        def is_generic_title(title):
            """Check if a title is generic and should be filtered out."""
            if not title:
                return True
            title_lower = title.lower().strip()
            generic_patterns = [
                r'^in this article',
                r'^getting started',
                r'^overview$',
                r'^documentation',
                r'^table of contents',
                # Date-only titles (e.g., "December 19, 2025")
                r'^(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},?\s+\d{4}$',
            ]
            for pattern in generic_patterns:
                if re.match(pattern, title_lower):
                    return True
            return False

        def is_valid_article_url(url):
            """Check if URL is a valid article URL (not just a homepage)."""
            if not url:
                return False
            parsed = urlparse(url)
            path = parsed.path.rstrip('/')
            # Reject homepage URLs
            if not path or path == '/':
                return False
            # Known generic homepage patterns
            generic_patterns = [
                r'^https?://(?:www\.)?claude\.ai/?$',
                r'^https?://(?:www\.)?openai\.com/?$',
                r'^https?://(?:www\.)?anthropic\.com/?$',
            ]
            for pattern in generic_patterns:
                if re.match(pattern, url):
                    return False
            return True

        # Filter out generic titles
        filtered_articles = [a for a in recent_articles if not is_generic_title(a.get('title', ''))]
        if len(filtered_articles) < len(recent_articles):
            self.logger.info(f"Filtered out {len(recent_articles) - len(filtered_articles)} articles with generic titles")
        recent_articles = filtered_articles

        # Filter out articles with invalid URLs
        valid_url_articles = [a for a in recent_articles if is_valid_article_url(a.get('url', ''))]
        if len(valid_url_articles) < len(recent_articles):
            self.logger.info(f"Filtered out {len(recent_articles) - len(valid_url_articles)} articles with invalid URLs")
        recent_articles = valid_url_articles

        # Deduplicate articles by title+source and URL similarity (keep first occurrence)
        seen_titles = set()
        seen_urls = set()
        deduplicated_articles = []

        def normalize_url_for_dedup(url):
            """Normalize URL for deduplication - remove fragments and some query params."""
            if not url:
                return ''
            # Remove fragment
            url = url.split('#')[0]
            # Remove trailing slashes
            url = url.rstrip('/')
            # Remove common tracking params
            url = re.sub(r'[?&](utm_\w+|ref|source)=[^&]*', '', url)
            return url.lower()

        def get_url_base(url):
            """Get the base URL path for similarity checking."""
            if not url:
                return ''
            # Get everything before query string and fragment
            base = url.split('?')[0].split('#')[0]
            return base.lower().rstrip('/')

        for article in recent_articles:
            title_key = (article.get('title', '').lower().strip(), article.get('source', ''))
            url = article.get('url', '')
            normalized_url = normalize_url_for_dedup(url)
            url_base = get_url_base(url)

            # Check for duplicate by title+source
            if title_key in seen_titles:
                self.logger.debug(f"Skipping duplicate article (title match): {article.get('title', '')[:50]}")
                continue

            # Check for duplicate by normalized URL
            if normalized_url and normalized_url in seen_urls:
                self.logger.debug(f"Skipping duplicate article (URL match): {article.get('title', '')[:50]}")
                continue

            # Check for duplicate by URL base (catches same article with different fragments/params)
            if url_base and url_base in seen_urls:
                self.logger.debug(f"Skipping duplicate article (URL base match): {article.get('title', '')[:50]}")
                continue

            seen_titles.add(title_key)
            if normalized_url:
                seen_urls.add(normalized_url)
            if url_base:
                seen_urls.add(url_base)
            deduplicated_articles.append(article)

        if len(deduplicated_articles) < len(recent_articles):
            self.logger.info(f"Removed {len(recent_articles) - len(deduplicated_articles)} duplicate articles")
        recent_articles = deduplicated_articles

        # Enhance articles with tag information
        for article in recent_articles:
            tags = self.db.get_tags_for_article(article['id'])
            if tags:
                article['content_type'] = [tag['tag'] for tag in tags if not tag['tag'].startswith('provider:') and not tag['tag'].startswith('product:')]
                # Fall back to tags for provider/product if not in article
                if not article.get('provider'):
                    for tag in tags:
                        if tag['tag'].startswith('provider:'):
                            article['provider'] = tag['tag'].replace('provider:', '')
                            break
                if not article.get('product'):
                    for tag in tags:
                        if tag['tag'].startswith('product:'):
                            article['product'] = tag['tag'].replace('product:', '')
                            break
            if not article.get('content_type'):
                article['content_type'] = ['general_update']
            # Default provider/product if still missing
            if not article.get('provider'):
                article['provider'] = 'Unknown'
            if not article.get('product'):
                article['product'] = 'Unknown'

        # Ensure LM Studio connection is established
        if not self.connection_manager.ensure_connection(allow_prompt=True):
            self.logger.error("Cannot proceed with report generation without LM Studio connection")
            return None

        # Initialize executive summarizer with verified connection config
        ai_config = self.connection_manager.get_config()
        self.executive_summarizer = LLMNewsExecutiveSummarizer(ai_config=ai_config)

        # Generate executive summary
        self.logger.info("Generating executive summary...")
        executive_summary = self.executive_summarizer.create_summary(
            recent_articles,
            time_period=f"last {time_window} days"
        )

        # Group articles by provider for provider summaries
        self.logger.info("Generating provider summaries...")
        provider_articles = {}
        for article in recent_articles:
            provider = article.get('provider', 'Other')
            source = article.get('source', '').lower()
            title = article.get('title', '').lower()

            # Determine provider (same logic as reporting)
            matched_provider = 'Other'
            known_providers = ['Anthropic', 'OpenAI', 'Google', 'Meta', 'LM Studio',
                             'Mistral AI', 'Microsoft', 'Perplexity', 'Hugging Face',
                             'Ollama', 'LangChain']

            for kp in known_providers:
                if kp.lower() in provider.lower():
                    matched_provider = kp
                    break

            # Check source/title for Ollama/LangChain
            if matched_provider == 'Other':
                if 'ollama' in source or 'ollama' in title:
                    matched_provider = 'Ollama'
                elif 'langchain' in source or 'langchain' in title:
                    matched_provider = 'LangChain'

            if matched_provider not in provider_articles:
                provider_articles[matched_provider] = []
            provider_articles[matched_provider].append(article)

        # Generate AI summary for each provider
        provider_summaries = {}
        time_period_str = f"last {time_window} days"
        for provider_name, articles in provider_articles.items():
            if articles:
                self.logger.info(f"Generating summary for {provider_name} ({len(articles)} articles)...")
                summary = self.executive_summarizer.create_provider_summary(
                    provider_name, articles, time_period=time_period_str
                )
                if summary:
                    provider_summaries[provider_name] = summary

        self.logger.info(f"Generated {len(provider_summaries)} provider summaries")

        # Generate report based on tier
        output_dir = self.config.get('report_dir', 'reports/llm_news')

        # Get model name for report attribution
        model_name = self._get_model_name()

        if tier == 0:
            report_path = self.reporter._generate_report_with_tier(
                executive_summary=executive_summary,
                articles=recent_articles,
                output_dir=output_dir,
                time_period="last 24 hours",
                tier=0,
                tier_name="Tier 0 Daily Digest",
                summarizer=self.executive_summarizer,
                provider_summaries=provider_summaries,
                model_name=model_name
            )
        elif tier == 1:
            report_path = self.reporter.generate_tier1_digest(
                executive_summary=executive_summary,
                articles=recent_articles,
                output_dir=output_dir,
                summarizer=self.executive_summarizer,
                provider_summaries=provider_summaries,
                model_name=model_name
            )
        elif tier == 2:
            report_path = self.reporter.generate_tier2_biweekly(
                executive_summary=executive_summary,
                articles=recent_articles,
                output_dir=output_dir,
                summarizer=self.executive_summarizer,
                provider_summaries=provider_summaries,
                model_name=model_name
            )
        elif tier == 3:
            report_path = self.reporter.generate_tier3_archive(
                executive_summary=executive_summary,
                articles=recent_articles,
                output_dir=output_dir,
                summarizer=self.executive_summarizer,
                provider_summaries=provider_summaries,
                model_name=model_name
            )
        else:
            report_path = self.reporter.generate_llm_news_report(
                executive_summary=executive_summary,
                articles=recent_articles,
                output_dir=output_dir,
                time_period=f"last {time_window} days",
                provider_summaries=provider_summaries,
                model_name=model_name
            )

        if report_path:
            self.logger.info(f"Report generated: {report_path}")
        else:
            self.logger.warning("Failed to generate report")

        return report_path

    def test_connection(self):
        """Test LM Studio connection"""
        return self.connection_manager.ensure_connection(allow_prompt=True)
