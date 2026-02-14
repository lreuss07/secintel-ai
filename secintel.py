#!/usr/bin/env python3
"""
SecIntel AI - Security Intelligence Tracker

AI-powered security intelligence aggregation and reporting platform.
"""

import argparse
import logging
import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from core.config import load_config
from core.database import DatabaseManager
from core.source_validator import (
    SourceValidator, print_validation_results, print_connection_results
)
from trackers.defender import DefenderTracker
from trackers.microsoft_products import MicrosoftProductsTracker
from trackers.threat_intel import ThreatIntelTracker
from trackers.thirdparty_security import ThirdPartySecurityTracker
from trackers.llm_news import LLMNewsTracker

# Set up logging
Path("logs").mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/secintel.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        prog='secintel',
        description='SecIntel AI - Security Intelligence Tracker'
    )

    parser.add_argument('--config', '-c',
                        default='config.yaml',
                        help='Path to configuration file')

    parser.add_argument('--tracker', '-t',
                        choices=['defender', 'microsoft_products', 'threat_intel', 'thirdparty_security', 'llm_news', 'all'],
                        default='all',
                        help='Which tracker to run')

    parser.add_argument('--scrape', action='store_true',
                        help='Scrape new updates from sources')

    parser.add_argument('--analyze', action='store_true',
                        help='Analyze and summarize scraped updates')

    parser.add_argument('--report', action='store_true',
                        help='Generate reports')

    parser.add_argument('--tier', type=int, choices=[0, 1, 2, 3],
                        help='Report tier: 0=Daily (1d), 1=Weekly (7d), 2=Bi-Weekly (14d), 3=Monthly (30d)')

    parser.add_argument('--full-run', action='store_true',
                        help='Run complete workflow (scrape, analyze, report)')

    parser.add_argument('--test-connection', action='store_true',
                        help='Test connection to LM Studio server')

    parser.add_argument('--list', action='store_true',
                        help='List available trackers')

    parser.add_argument('--validate-sources', action='store_true',
                        help='Validate source configurations')

    parser.add_argument('--test-connections', action='store_true',
                        help='Test connectivity to sources (use with --validate-sources)')

    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Enable verbose logging')

    # Testing mode arguments
    parser.add_argument('--testing', action='store_true',
                        help='Enable testing mode with resource limits (default: 2 sources, 3 articles/source, 3 summaries)')

    parser.add_argument('--max-sources', type=int, default=None,
                        help='Max sources to scrape per tracker (default: 2 in testing mode)')

    parser.add_argument('--max-articles', type=int, default=None,
                        help='Max articles to scrape per source (default: 3 in testing mode)')

    parser.add_argument('--max-summaries', type=int, default=None,
                        help='Max articles to AI-summarize per tracker (default: 3 in testing mode)')

    return parser.parse_args()

def get_trackers(config, db_manager, tracker_name):
    """
    Get tracker instances based on tracker name.

    Args:
        config (dict): Configuration dictionary
        db_manager: Database manager instance
        tracker_name (str): 'defender', 'microsoft_products', or 'all'

    Returns:
        list: List of tracker instances
    """
    trackers = []

    if tracker_name in ['defender', 'all']:
        if config['trackers']['defender'].get('enabled', True):
            defender_config = config['trackers']['defender'].copy()
            defender_config['ai'] = config['ai']  # Add global AI config
            if 'testing' in config:
                defender_config['testing'] = config['testing']
            trackers.append(DefenderTracker(defender_config, db_manager))

    if tracker_name in ['microsoft_products', 'all']:
        if config['trackers']['microsoft_products'].get('enabled', True):
            ms_config = config['trackers']['microsoft_products'].copy()
            ms_config['ai'] = config['ai']  # Add global AI config
            if 'testing' in config:
                ms_config['testing'] = config['testing']
            trackers.append(MicrosoftProductsTracker(ms_config, db_manager))

    if tracker_name in ['threat_intel', 'all']:
        if config['trackers']['threat_intel'].get('enabled', True):
            ti_config = config['trackers']['threat_intel'].copy()
            ti_config['ai'] = config['ai']  # Add global AI config
            if 'testing' in config:
                ti_config['testing'] = config['testing']
            trackers.append(ThreatIntelTracker(ti_config, db_manager))

    if tracker_name in ['thirdparty_security', 'all']:
        if config['trackers']['thirdparty_security'].get('enabled', True):
            tp_config = config['trackers']['thirdparty_security'].copy()
            tp_config['ai'] = config['ai']  # Add global AI config
            if 'testing' in config:
                tp_config['testing'] = config['testing']
            trackers.append(ThirdPartySecurityTracker(tp_config, db_manager))

    if tracker_name in ['llm_news', 'all']:
        if config['trackers']['llm_news'].get('enabled', True):
            llm_config = config['trackers']['llm_news'].copy()
            llm_config['ai'] = config['ai']  # Add global AI config
            if 'testing' in config:
                llm_config['testing'] = config['testing']
            trackers.append(LLMNewsTracker(llm_config, db_manager))

    return trackers

def list_trackers(config):
    """List all available trackers"""
    print("\n" + "=" * 70)
    print("Available Trackers")
    print("=" * 70)

    for name, tracker_config in config['trackers'].items():
        enabled = tracker_config.get('enabled', True)
        status = "✓ enabled" if enabled else "✗ disabled"
        display_name = tracker_config.get('display_name', name.title())
        print(f"  {name:25} [{status:12}] - {display_name}")

    print()

def main():
    """Main entry point"""
    args = parse_arguments()

    try:
        # Set log level
        if args.verbose:
            logging.getLogger().setLevel(logging.DEBUG)

        # Load configuration
        config = load_config(args.config)
        logger.info(f"Configuration loaded from {args.config}")

        # Apply testing mode limits
        if args.testing:
            config['testing'] = {
                'max_sources': args.max_sources if args.max_sources is not None else 2,
                'max_articles_per_source': args.max_articles if args.max_articles is not None else 3,
                'max_summaries': args.max_summaries if args.max_summaries is not None else 3,
            }
            logger.info(f"TESTING MODE enabled - limits: {config['testing']}")
        elif any([args.max_sources, args.max_articles, args.max_summaries]):
            config['testing'] = {}
            if args.max_sources is not None:
                config['testing']['max_sources'] = args.max_sources
            if args.max_articles is not None:
                config['testing']['max_articles_per_source'] = args.max_articles
            if args.max_summaries is not None:
                config['testing']['max_summaries'] = args.max_summaries
            logger.info(f"Resource limits applied: {config['testing']}")

        # List trackers if requested
        if args.list:
            list_trackers(config)
            return

        # Validate sources if requested
        if args.validate_sources:
            validator = SourceValidator()

            # Determine which tracker(s) to validate
            tracker_filter = None if args.tracker == 'all' else args.tracker

            # Run schema validation
            results = validator.validate_all(tracker_filter)
            total_errors = print_validation_results(results)

            # Run connectivity tests if requested
            if args.test_connections:
                print("\n" + "=" * 70)
                print("Testing Connections")
                print("=" * 70)

                total_failures = 0
                trackers_to_test = [tracker_filter] if tracker_filter else validator.get_tracker_names()

                for tracker_name in trackers_to_test:
                    connection_results = validator.test_tracker_connections(tracker_name)
                    failures = print_connection_results(tracker_name, connection_results)
                    total_failures += failures

                print()
                if total_failures > 0:
                    print(f"Connection Summary: {total_failures} source(s) failed")
                else:
                    print("Connection Summary: All sources reachable")

            # Exit with error code if validation failed
            if total_errors > 0:
                sys.exit(1)
            return

        # Initialize shared database
        db_manager = DatabaseManager(config['database']['path'])
        db_manager.initialize_database()
        logger.info("Database initialized successfully")

        # Get tracker instances
        trackers = get_trackers(config, db_manager, args.tracker)

        if not trackers:
            logger.error(f"No enabled trackers found for: {args.tracker}")
            sys.exit(1)

        logger.info(f"Loaded {len(trackers)} tracker(s)")

        # Test connection if requested
        if args.test_connection:
            logger.info("\n" + "=" * 70)
            logger.info("Testing LM Studio Connection")
            logger.info("=" * 70)

            all_success = True
            for tracker in trackers:
                logger.info(f"\nTesting {tracker.name}...")
                if not tracker.test_connection():
                    all_success = False

            if all_success:
                logger.info("\n✓ All trackers can connect to LM Studio successfully!")
            else:
                logger.error("\n✗ Some trackers failed to connect to LM Studio")
                sys.exit(1)
            return

        # Determine operations
        run_scrape = args.scrape or args.full_run
        run_analyze = args.analyze or args.full_run
        run_report = args.report or args.full_run

        # If no operation specified, show help
        if not (run_scrape or run_analyze or run_report):
            print("\nSecIntel AI - Security Intelligence Tracker")
            print("=" * 70)
            print("\nUsage:")
            print("  --tracker {defender,microsoft_products,all}")
            print("                        Which tracker to run (default: all)")
            print("  --scrape              Scrape new updates from sources")
            print("  --analyze             Analyze and summarize scraped updates")
            print("  --report              Generate reports")
            print("  --tier {0,1,2,3}      Report tier (0=Daily, 1=Weekly, 2=Bi-Weekly, 3=Monthly)")
            print("  --full-run            Run complete workflow (scrape, analyze, report)")
            print("  --test-connection     Test connection to LM Studio")
            print("  --validate-sources    Validate source configurations")
            print("  --test-connections    Test connectivity to sources (with --validate-sources)")
            print("  --list                List available trackers")
            print("  --config FILE         Specify configuration file")
            print("  --testing             Enable testing mode (limited sources/articles/summaries)")
            print("  --max-sources N       Max sources per tracker (default: 2 in testing mode)")
            print("  --max-articles N      Max articles per source (default: 3 in testing mode)")
            print("  --max-summaries N     Max AI summaries per tracker (default: 3 in testing mode)")
            print("\nExamples:")
            print("  python secintel.py --list")
            print("  python secintel.py --test-connection")
            print("  python secintel.py --validate-sources")
            print("  python secintel.py --validate-sources --test-connections")
            print("  python secintel.py --validate-sources --tracker threat_intel")
            print("  python secintel.py --tracker threat_intel --tier 0 --full-run")
            print("  python secintel.py --tracker defender --full-run")
            print("  python secintel.py --tracker all --report --tier 1")
            print("  python secintel.py --scrape --analyze")
            print("  python secintel.py --testing --full-run")
            print("  python secintel.py --testing --tracker defender --max-sources 1 --full-run")
            print()
            return

        # Map tier to time_window_days for scraping
        tier_to_days = {
            0: 1,    # Daily
            1: 7,    # Weekly
            2: 14,   # Bi-weekly
            3: 30,   # Monthly
        }

        # Execute operations for each tracker
        for tracker in trackers:
            logger.info(f"\n{'=' * 70}")
            logger.info(f"Running tracker: {tracker.name}")
            logger.info(f"{'=' * 70}\n")

            # Set time_window_days based on tier if specified
            if args.tier is not None:
                tracker.config['time_window_days'] = tier_to_days.get(args.tier, 30)
                logger.info(f"Set time window to {tracker.config['time_window_days']} days based on tier {args.tier}")

            try:
                if run_scrape:
                    tracker.scrape()

                if run_analyze:
                    tracker.analyze()

                if run_report:
                    tracker.report(tier=args.tier)

            except Exception as e:
                logger.error(f"Error in {tracker.name} tracker: {str(e)}", exc_info=True)
                continue

        logger.info("\n" + "=" * 70)
        logger.info("SecIntel AI workflow completed successfully")
        logger.info("=" * 70)

    except FileNotFoundError as e:
        logger.error(f"Configuration error: {str(e)}")
        logger.error("Run with --config to specify a valid configuration file")
        sys.exit(1)

    except Exception as e:
        logger.error(f"Error in SecIntel AI: {str(e)}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
