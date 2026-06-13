"""
YouTube Security tracker plugin for SecIntel AI.
Tracks security YouTube channels via transcripts.
"""

from core.base_tracker import BaseTracker
from core.lm_studio_connection import LMStudioConnectionManager
from core.ai_client import AIClient
from .scraper_youtube import YouTubeSecurityScraper
from .summarizer_youtube import YouTubeSecuritySummarizer, YouTubeSecurityExecutiveSummarizer
from .reporting_youtube import YouTubeSecurityReportGenerator
import logging

logger = logging.getLogger(__name__)


class YouTubeSecurityTracker(BaseTracker):
    """Tracker for security YouTube channels"""

    def __init__(self, config, db_manager):
        super().__init__('youtube_security', config, db_manager)

        # Load sources from tracker-specific config
        import os
        import yaml
        tracker_config_path = os.path.join(os.path.dirname(__file__), 'config.yaml')
        with open(tracker_config_path, 'r') as f:
            tracker_config = yaml.safe_load(f)
            self.config['sources'] = tracker_config.get('sources', [])
            self.config['transcript'] = tracker_config.get('transcript', {})
            self.config['youtube_api_key'] = tracker_config.get('youtube_api_key')

        # Initialize components
        self.scraper = None
        self.summarizer = None
        self.executive_summarizer = None
        self.reporter = YouTubeSecurityReportGenerator()

        # Initialize LM Studio connection manager
        ai_config = self.config.get('ai', {})
        lmstudio_config = ai_config.get('lmstudio', {})
        self.connection_manager = LMStudioConnectionManager(lmstudio_config)

    def _get_model_name(self):
        """Get the AI model name for report attribution."""
        from core.report_helpers import resolve_lmstudio_model
        ai_config = self.config.get('ai', {})
        provider = ai_config.get('provider', 'lmstudio')

        if provider == 'lmstudio':
            # Resolve the actually-loaded model, not the config placeholder
            return resolve_lmstudio_model(ai_config.get('lmstudio', {}))
        elif provider == 'claude':
            claude_config = ai_config.get('claude', {})
            return claude_config.get('model', 'claude-sonnet')
        else:
            return provider

    def scrape(self):
        """Scrape YouTube channels for new videos with transcripts."""
        self.logger.info("=" * 70)
        self.logger.info("Starting YouTube security scraping operation")
        self.logger.info("=" * 70)

        time_window = self.config.get('time_window_days')
        sources = self.config['sources']
        transcript_config = self.config.get('transcript', {})

        if self.max_sources:
            self.logger.info(f"TESTING MODE: Limiting to {self.max_sources} sources (of {len(sources)})")
            sources = sources[:self.max_sources]

        self.scraper = YouTubeSecurityScraper(
            sources,
            time_window_days=time_window,
            max_articles_per_source=self.max_articles_per_source,
            transcript_config=transcript_config,
            api_key=self.config.get('youtube_api_key'),
        )

        scraped_results = self.scraper.scrape_all_sources()

        total_articles = 0
        for source_name, articles in scraped_results.items():
            self.logger.info(f"Scraped {len(articles)} videos from {source_name}")
            total_articles += len(articles)

            for article in articles:
                # Store article in database
                article_id = self.db.store_article(article, tracker_name='youtube_security')

                # Store provider tag
                if article.get('provider') and article_id:
                    self.db.store_tag(article_id, f"provider:{article['provider']}")

                # Store product/channel tag
                if article.get('product') and article_id:
                    self.db.store_tag(article_id, f"product:{article['product']}")

        self.logger.info(f"Scraping operation completed - Total videos: {total_articles}")
        return total_articles

    def analyze(self):
        """Analyze YouTube video transcripts with AI."""
        self.logger.info("=" * 70)
        self.logger.info("Starting YouTube security analysis operation")
        self.logger.info("=" * 70)

        articles = self.db.get_articles_without_summary(tracker_name='youtube_security')
        if self.max_summaries and len(articles) > self.max_summaries:
            self.logger.info(f"TESTING MODE: Limiting analysis to {self.max_summaries} articles (of {len(articles)})")
            articles = articles[:self.max_summaries]
        self.logger.info(f"Found {len(articles)} videos to analyze")

        if not articles:
            self.logger.info("No videos require analysis")
            return 0

        # Check AI provider - only require LM Studio connection if using lmstudio
        ai_config = self.config.get('ai', {})
        ai_provider = ai_config.get('provider', 'lmstudio')

        if ai_provider == 'lmstudio':
            if not self.connection_manager.ensure_connection(allow_prompt=True):
                self.logger.error("Cannot proceed with analysis without LM Studio connection")
                return 0
        else:
            self.logger.info(f"Using {ai_provider} provider - skipping LM Studio connection check")

        # Initialize summarizer with full AI config (preserves provider selection)
        transcript_config = self.config.get('transcript', {})
        ai_max_chars = transcript_config.get('ai_max_chars', 12000)
        self.summarizer = YouTubeSecuritySummarizer(ai_config=ai_config, ai_max_chars=ai_max_chars)

        # IOC extractor
        from core.ioc_extractor import IOCExtractor
        ioc_extractor = IOCExtractor()

        for idx, article in enumerate(articles, 1):
            article_id = article['id']
            self.logger.info(f"Analyzing video {idx}/{len(articles)}: {article['title']}")

            try:
                # Get tags for context
                tags = self.db.get_tags_for_article(article_id)
                content_types = [tag['tag'] for tag in tags if not tag['tag'].startswith('provider:') and not tag['tag'].startswith('product:')] if tags else None

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

                # Skip on failure - summarize() returns None so the video stays
                # unsummarized and is retried on the next run.
                if not summary:
                    self.logger.warning(f"No summary produced for video ID {article_id} - left unsummarized for retry")
                    continue

                # Store summary with content type
                self.db.update_article_summary(article_id, summary, content_type=content_type)
                self.logger.info(f"Summary generated for video ID: {article_id} (type: {content_type})")

                # Store content type as tag
                if content_type:
                    self.db.store_tag(article_id, content_type)

                # Extract IOCs from transcript and summary
                combined_text = f"{article.get('content', '')} {summary}"
                iocs = ioc_extractor.extract_from_text(combined_text)
                if iocs:
                    self.db.store_iocs(article_id, iocs)

            except Exception as e:
                self.logger.error(f"Failed to analyze video ID {article_id}: {e}")
                continue

        self.logger.info(f"Analysis operation completed - Processed {len(articles)} videos")
        return len(articles)

    def report(self, tier=None):
        """Generate YouTube security reports."""
        self.logger.info("=" * 70)
        self.logger.info("Starting YouTube security report generation")
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
            tracker_name='youtube_security',
            limit=self.max_summaries
        )

        self.logger.info(f"Found {len(recent_articles)} YouTube videos from last {time_window} days")

        if not recent_articles:
            self.logger.warning("No recent YouTube videos with summaries available for reporting")
            return None

        # Enhance articles with tag information
        for article in recent_articles:
            tags = self.db.get_tags_for_article(article['id'])
            if tags:
                article['content_type'] = [tag['tag'] for tag in tags if not tag['tag'].startswith('provider:') and not tag['tag'].startswith('product:')]
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
                article['content_type'] = ['general_security']
            if not article.get('provider'):
                article['provider'] = 'YouTube'
            if not article.get('product'):
                article['product'] = 'Unknown'

        # Check AI provider - only require LM Studio connection if using lmstudio
        ai_config = self.config.get('ai', {})
        ai_provider = ai_config.get('provider', 'lmstudio')

        if ai_provider == 'lmstudio':
            if not self.connection_manager.ensure_connection(allow_prompt=True):
                self.logger.error("Cannot proceed with report generation without LM Studio connection")
                return None
        else:
            self.logger.info(f"Using {ai_provider} provider - skipping LM Studio connection check")

        # Initialize executive summarizer with full AI config (preserves provider selection)
        self.executive_summarizer = YouTubeSecurityExecutiveSummarizer(ai_config=ai_config)

        # Generate executive summary
        self.logger.info("Generating executive summary...")
        executive_summary = self.executive_summarizer.create_summary(
            recent_articles,
            time_period=f"last {time_window} days"
        )

        # Group articles by channel for channel summaries
        self.logger.info("Generating channel summaries...")
        channel_articles = {}
        for article in recent_articles:
            channel = article.get('product', article.get('source', 'Unknown'))
            if channel not in channel_articles:
                channel_articles[channel] = []
            channel_articles[channel].append(article)

        # Generate AI summary for each channel
        channel_summaries = {}
        time_period_str = f"last {time_window} days"
        for channel_name, articles in channel_articles.items():
            if articles:
                self.logger.info(f"Generating summary for {channel_name} ({len(articles)} videos)...")
                summary = self.executive_summarizer.create_channel_summary(
                    channel_name, articles, time_period=time_period_str
                )
                if summary:
                    channel_summaries[channel_name] = summary

        self.logger.info(f"Generated {len(channel_summaries)} channel summaries")

        # Generate report
        output_dir = self.config.get('report_dir', 'reports/youtube_security')
        model_name = self._get_model_name()

        if tier == 0:
            report_path = self.reporter._generate_report_with_tier(
                executive_summary=executive_summary,
                articles=recent_articles,
                output_dir=output_dir,
                time_period="last 24 hours",
                tier=0,
                tier_name="Tier 0 Daily Digest",
                channel_summaries=channel_summaries,
                model_name=model_name
            )
        elif tier == 1:
            report_path = self.reporter.generate_tier1_digest(
                executive_summary=executive_summary,
                articles=recent_articles,
                output_dir=output_dir,
                channel_summaries=channel_summaries,
                model_name=model_name
            )
        elif tier == 2:
            report_path = self.reporter.generate_tier2_biweekly(
                executive_summary=executive_summary,
                articles=recent_articles,
                output_dir=output_dir,
                channel_summaries=channel_summaries,
                model_name=model_name
            )
        elif tier == 3:
            report_path = self.reporter.generate_tier3_archive(
                executive_summary=executive_summary,
                articles=recent_articles,
                output_dir=output_dir,
                channel_summaries=channel_summaries,
                model_name=model_name
            )
        else:
            report_path = self.reporter.generate_report(
                executive_summary=executive_summary,
                articles=recent_articles,
                output_dir=output_dir,
                time_period=f"last {time_window} days",
                channel_summaries=channel_summaries,
                model_name=model_name
            )

        if report_path:
            self.logger.info(f"Report generated: {report_path}")
        else:
            self.logger.warning("Failed to generate report")

        return report_path

    def test_connection(self):
        """Test AI provider connection (LM Studio or Claude)"""
        ai_config = self.config.get('ai', {})
        ai_provider = ai_config.get('provider', 'lmstudio')

        if ai_provider == 'lmstudio':
            return self.connection_manager.ensure_connection(allow_prompt=True)
        else:
            return AIClient(ai_config).test_connection()
