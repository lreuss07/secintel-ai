"""
Threat Intelligence tracker plugin for SecIntel AI.
Tracks general cybersecurity news and threat actor campaigns.
"""

from core.base_tracker import BaseTracker
from core.ioc_extractor import IOCExtractor
from core.lm_studio_connection import LMStudioConnectionManager
from .scraper import ThreatIntelScraper
from .summarizer import ArticleSummarizer, ExecutiveSummarizer
from .reporting import ReportGenerator
import logging

logger = logging.getLogger(__name__)

class ThreatIntelTracker(BaseTracker):
    """Tracker for general threat intelligence news"""

    def __init__(self, config, db_manager):
        super().__init__('threat_intel', config, db_manager)

        # Load sources from tracker-specific config
        import os
        import yaml
        tracker_config_path = os.path.join(os.path.dirname(__file__), 'config.yaml')
        with open(tracker_config_path, 'r') as f:
            tracker_config = yaml.safe_load(f)
            self.config['sources'] = tracker_config.get('sources', [])

        # Initialize threat intel components
        self.scraper = None
        self.summarizer = None

        # Initialize LM Studio connection manager and get AI config
        ai_config = self.config.get('ai', {})

        # Initialize reporter with AI config for model attribution
        self.reporter = ReportGenerator(ai_config=ai_config)
        # Extract lmstudio-specific config for connection manager
        lmstudio_config = ai_config.get('lmstudio', {})
        self.connection_manager = LMStudioConnectionManager(lmstudio_config)

    def scrape(self):
        """Scrape threat intelligence articles"""
        self.logger.info("=" * 70)
        self.logger.info("Starting threat intelligence scraping operation")
        self.logger.info("=" * 70)

        time_window = self.config.get('time_window_days')
        if time_window:
            self.logger.info(f"Using time window filter: {time_window} days")

        self.scraper = ThreatIntelScraper(
            self.config['sources'],
            time_window_days=time_window
        )
        scraped_results = self.scraper.scrape_all_sources()

        total_articles = 0
        for source_name, articles in scraped_results.items():
            self.logger.info(f"Scraped {len(articles)} articles from {source_name}")
            total_articles += len(articles)

            for article in articles:
                # Store article in database
                article_id = self.db.store_article(article, tracker_name='threat_intel')

                # Store tags if present
                if article.get('tags') and article_id:
                    for tag in article['tags']:
                        self.db.store_tag(article_id, tag)

        self.logger.info(f"Scraping operation completed - Total articles: {total_articles}")
        return total_articles

    def analyze(self):
        """Analyze threat intel articles with AI"""
        self.logger.info("=" * 70)
        self.logger.info("Starting threat intelligence analysis operation")
        self.logger.info("=" * 70)

        articles = self.db.get_articles_without_summary(tracker_name='threat_intel')
        self.logger.info(f"Found {len(articles)} articles to analyze")

        if not articles:
            self.logger.info("No articles require analysis")
            return 0

        # Check AI provider - only require LM Studio connection if using lmstudio
        tracker_ai_config = self.config.get('ai', {})
        ai_provider = tracker_ai_config.get('provider', 'lmstudio')

        if ai_provider == 'lmstudio':
            # Ensure LM Studio connection is established
            if not self.connection_manager.ensure_connection(allow_prompt=True):
                self.logger.error("Cannot proceed with analysis without LM Studio connection")
                return 0
        else:
            self.logger.info(f"Using {ai_provider} provider - skipping LM Studio connection check")

        # Initialize summarizer and IOC extractor with verified connection config
        self.summarizer = ArticleSummarizer(ai_config=tracker_ai_config)
        ioc_extractor = IOCExtractor()

        for idx, article in enumerate(articles, 1):
            article_id = article['id']
            self.logger.info(f"Analyzing article {idx}/{len(articles)}: {article['title']}")

            try:
                # Generate summary with pre-classification
                # The summarizer now returns (summary, content_type)
                summary, content_type = self.summarizer.summarize(
                    title=article['title'],
                    content=article['content']
                )

                # Store summary with content type classification
                self.db.update_article_summary(article_id, summary, content_type=content_type)
                self.logger.info(f"✓ Summary generated for article ID: {article_id} (classified as '{content_type}')")

                # Extract IOCs from article content (only for threat advisories)
                # For other content types, IOC extraction is still done but may return fewer results
                iocs = ioc_extractor.extract_from_text(article['content'])
                if iocs:
                    ioc_count = sum(len(v) for v in iocs.values())
                    self.db.store_iocs(article_id, iocs)
                    self.logger.info(f"  Extracted and stored {ioc_count} IOCs ({', '.join(f'{len(v)} {k}' for k, v in iocs.items())})")

            except Exception as e:
                self.logger.error(f"✗ Failed to analyze article ID {article_id}: {str(e)}")
                continue

        self.logger.info(f"Analysis operation completed - Processed {len(articles)} articles")
        return len(articles)

    def report(self, tier=None):
        """Generate threat intelligence reports"""
        self.logger.info("=" * 70)
        self.logger.info("Starting threat intelligence report generation")
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
            tracker_name='threat_intel'
        )

        self.logger.info(f"Found {len(recent_articles)} threat intel articles from last {time_window} days")

        if not recent_articles:
            self.logger.warning("No recent threat intel articles with summaries available for reporting")
            return None

        # Enhance articles with tags
        for article in recent_articles:
            tags = self.db.get_tags_for_article(article['id'])
            article['tags'] = [tag['tag'] for tag in tags] if tags else []

        # Check AI provider - only require LM Studio connection if using lmstudio
        tracker_ai_config = self.config.get('ai', {})
        ai_provider = tracker_ai_config.get('provider', 'lmstudio')

        if ai_provider == 'lmstudio':
            # Ensure LM Studio connection is established
            if not self.connection_manager.ensure_connection(allow_prompt=True):
                self.logger.error("Cannot proceed with report generation without LM Studio connection")
                return None
        else:
            self.logger.info(f"Using {ai_provider} provider - skipping LM Studio connection check")

        # Initialize executive summarizer for generating high-level summaries
        executive_summarizer = ExecutiveSummarizer(ai_config=tracker_ai_config)

        # Generate report using tier-specific methods
        output_dir = self.config.get('report_dir', 'reports/threat_intel')

        try:
            if tier == 0:
                report_path = self.reporter.generate_tier0_daily(
                    articles=recent_articles,
                    output_dir=output_dir,
                    summarizer=executive_summarizer
                )
            elif tier == 1:
                report_path = self.reporter.generate_tier1_digest(
                    articles=recent_articles,
                    output_dir=output_dir,
                    summarizer=executive_summarizer
                )
            elif tier == 2:
                report_path = self.reporter.generate_tier2_biweekly(
                    articles=recent_articles,
                    output_dir=output_dir,
                    summarizer=executive_summarizer
                )
            elif tier == 3:
                report_path = self.reporter.generate_tier3_archive(
                    articles=recent_articles,
                    output_dir=output_dir,
                    summarizer=executive_summarizer
                )
            else:
                # Default to tier 3 for standard reports
                report_path = self.reporter.generate_tier3_archive(
                    articles=recent_articles,
                    output_dir=output_dir,
                    summarizer=executive_summarizer
                )

            if report_path:
                self.logger.info(f"✓ Report generated: {report_path}")
            else:
                self.logger.warning("✗ Failed to generate report")

            return report_path

        except Exception as e:
            self.logger.error(f"Error generating report: {str(e)}", exc_info=True)
            return None

    def test_connection(self):
        """Test LM Studio connection"""
        return self.connection_manager.ensure_connection(allow_prompt=True)
