"""
Third-party Security Tools tracker plugin for SecIntel AI.
Tracks updates from various security vendors.
"""

from core.base_tracker import BaseTracker
from core.lm_studio_connection import LMStudioConnectionManager
from .scraper_thirdparty import ThirdPartySecurityScraper
from .summarizer_thirdparty import ThirdPartySecuritySummarizer, ThirdPartySecurityExecutiveSummarizer
from .reporting_thirdparty import ThirdPartySecurityReportGenerator
import logging

logger = logging.getLogger(__name__)


class ThirdPartySecurityTracker(BaseTracker):
    """Tracker for third-party security product updates"""

    def __init__(self, config, db_manager):
        super().__init__('thirdparty_security', config, db_manager)

        # Load sources from tracker-specific config
        import os
        import yaml
        tracker_config_path = os.path.join(os.path.dirname(__file__), 'config.yaml')
        with open(tracker_config_path, 'r') as f:
            tracker_config = yaml.safe_load(f)
            self.config['sources'] = tracker_config.get('sources', [])
            # Store tracker-specific config for vendor_styles and vendors list
            self.tracker_config = tracker_config

        # Initialize components
        self.scraper = None
        self.summarizer = None
        self.executive_summarizer = None

        # Initialize LM Studio connection manager
        ai_config = self.config.get('ai', {})

        # Initialize reporter with AI config for model attribution and tracker config for vendor styles
        self.reporter = ThirdPartySecurityReportGenerator(ai_config=ai_config, tracker_config=self.tracker_config)
        # Extract lmstudio-specific config for connection manager
        lmstudio_config = ai_config.get('lmstudio', {})
        self.connection_manager = LMStudioConnectionManager(lmstudio_config)

    def scrape(self):
        """Scrape third-party security tool updates"""
        self.logger.info("=" * 70)
        self.logger.info("Starting 3rd Party Security Tools update scraping operation")
        self.logger.info("=" * 70)

        time_window = self.config.get('time_window_days')
        self.scraper = ThirdPartySecurityScraper(
            self.config['sources'],
            time_window_days=time_window
        )

        scraped_results = self.scraper.scrape_all_sources()

        total_articles = 0
        for source_name, articles in scraped_results.items():
            self.logger.info(f"Scraped {len(articles)} updates from {source_name}")
            total_articles += len(articles)

            for article in articles:
                # Store article in database
                article_id = self.db.store_article(article, tracker_name='thirdparty_security')

                # Store update type tags if present
                if article.get('update_type') and article_id:
                    for update_type in article['update_type']:
                        self.db.store_tag(article_id, update_type)

                # Store vendor tag
                if article.get('vendor') and article_id:
                    self.db.store_tag(article_id, f"vendor:{article['vendor']}")

                # Store product tag
                if article.get('product') and article_id:
                    self.db.store_tag(article_id, f"product:{article['product']}")

        self.logger.info(f"Scraping operation completed - Total updates: {total_articles}")
        return total_articles

    def analyze(self):
        """Analyze third-party security updates with AI"""
        self.logger.info("=" * 70)
        self.logger.info("Starting 3rd Party Security Tools update analysis operation")
        self.logger.info("=" * 70)

        articles = self.db.get_articles_without_summary(tracker_name='thirdparty_security')
        self.logger.info(f"Found {len(articles)} updates to analyze")

        if not articles:
            self.logger.info("No updates require analysis")
            return 0

        # Ensure LM Studio connection is established
        if not self.connection_manager.ensure_connection(allow_prompt=True):
            self.logger.error("Cannot proceed with analysis without LM Studio connection")
            return 0

        # Initialize summarizer with verified connection config
        ai_config = self.connection_manager.get_config()
        self.summarizer = ThirdPartySecuritySummarizer(ai_config=ai_config)

        for idx, article in enumerate(articles, 1):
            article_id = article['id']
            self.logger.info(f"Analyzing update {idx}/{len(articles)}: {article['title']}")

            try:
                # Get update type classification
                tags = self.db.get_tags_for_article(article_id)
                update_types = [tag['tag'] for tag in tags if not tag['tag'].startswith('vendor:') and not tag['tag'].startswith('product:')] if tags else None

                # Generate summary
                summary = self.summarizer.summarize(
                    title=article['title'],
                    content=article['content'],
                    update_type=update_types
                )

                # Store summary
                self.db.update_article_summary(article_id, summary)
                self.logger.info(f"Summary generated for update ID: {article_id}")

            except Exception as e:
                self.logger.error(f"Failed to analyze update ID {article_id}: {str(e)}")
                continue

        self.logger.info(f"Analysis operation completed - Processed {len(articles)} updates")
        return len(articles)

    def report(self, tier=None):
        """Generate third-party security reports"""
        self.logger.info("=" * 70)
        self.logger.info("Starting 3rd Party Security Tools report generation")
        self.logger.info("=" * 70)

        # Determine time window based on tier
        if tier == 0:
            time_window = 1
            tier_name = "Tier 0: Daily Digest (24 hours)"
        elif tier == 1:
            time_window = 7
            tier_name = "Tier 1: Weekly Digest (Critical & High Priority)"
        elif tier == 2:
            time_window = 14
            tier_name = "Tier 2: Bi-Weekly Review (High & Medium Priority)"
        elif tier == 3:
            time_window = 30
            tier_name = "Tier 3: Monthly Archive (All Priorities)"
        else:
            time_window = self.config.get('time_window_days', 30)
            tier_name = f"Standard Report ({time_window} days)"

        self.logger.info(f"Generating {tier_name}")

        # Get recent articles
        recent_articles = self.db.get_recent_articles_with_summary(
            days=time_window,
            tracker_name='thirdparty_security'
        )

        self.logger.info(f"Found {len(recent_articles)} updates from last {time_window} days")

        if not recent_articles:
            self.logger.warning("No recent updates with summaries available for reporting")
            return None

        # Enhance articles with tag information
        for article in recent_articles:
            tags = self.db.get_tags_for_article(article['id'])
            if tags:
                article['update_type'] = [tag['tag'] for tag in tags if not tag['tag'].startswith('vendor:') and not tag['tag'].startswith('product:')]
                # Extract vendor and product from tags
                for tag in tags:
                    if tag['tag'].startswith('vendor:'):
                        article['vendor'] = tag['tag'].replace('vendor:', '')
                    elif tag['tag'].startswith('product:'):
                        article['product'] = tag['tag'].replace('product:', '')
            if not article.get('update_type'):
                article['update_type'] = ['General Update']

        # Ensure LM Studio connection is established
        if not self.connection_manager.ensure_connection(allow_prompt=True):
            self.logger.error("Cannot proceed with report generation without LM Studio connection")
            return None

        # Initialize executive summarizer with verified connection config and tracker config
        ai_config = self.connection_manager.get_config()
        self.executive_summarizer = ThirdPartySecurityExecutiveSummarizer(ai_config=ai_config, tracker_config=self.tracker_config)

        # Generate executive summary
        self.logger.info("Generating executive summary...")
        executive_summary = self.executive_summarizer.create_summary(
            recent_articles,
            time_period=f"last {time_window} days"
        )

        # Generate report based on tier
        output_dir = self.config.get('report_dir', 'reports/thirdparty_security')

        if tier == 0:
            report_path = self.reporter._generate_report_with_tier(
                executive_summary=executive_summary,
                articles=recent_articles,
                output_dir=output_dir,
                time_period="last 24 hours",
                tier=0,
                tier_name="Tier 0 Daily Digest",
                summarizer=self.executive_summarizer
            )
        elif tier == 1:
            report_path = self.reporter.generate_tier1_digest(
                executive_summary=executive_summary,
                articles=recent_articles,
                output_dir=output_dir,
                summarizer=self.executive_summarizer
            )
        elif tier == 2:
            report_path = self.reporter.generate_tier2_biweekly(
                executive_summary=executive_summary,
                articles=recent_articles,
                output_dir=output_dir,
                summarizer=self.executive_summarizer
            )
        elif tier == 3:
            report_path = self.reporter.generate_tier3_archive(
                executive_summary=executive_summary,
                articles=recent_articles,
                output_dir=output_dir,
                summarizer=self.executive_summarizer
            )
        else:
            report_path = self.reporter.generate_security_product_report(
                executive_summary=executive_summary,
                articles=recent_articles,
                output_dir=output_dir,
                time_period=f"last {time_window} days",
                summarizer=self.executive_summarizer
            )

        if report_path:
            self.logger.info(f"Report generated: {report_path}")
        else:
            self.logger.warning("Failed to generate report")

        return report_path

    def test_connection(self):
        """Test LM Studio connection"""
        return self.connection_manager.ensure_connection(allow_prompt=True)
