"""
Base tracker class for SecIntel AI tracker system.
Defines the interface all tracker plugins must implement.
"""

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

class BaseTracker(ABC):
    """
    Base class for all tracker plugins.

    Each tracker must implement scrape(), analyze(), and report() methods.
    """

    def __init__(self, name, config, db_manager):
        """
        Initialize the tracker.

        Args:
            name (str): Tracker name (e.g., 'defender', 'microsoft_products')
            config (dict): Tracker-specific configuration
            db_manager: Shared database manager instance
        """
        self.name = name
        self.config = config
        self.db = db_manager
        self.logger = logging.getLogger(f"secintel.{name}")

        # Register this tracker in the database
        display_name = config.get('display_name', name.title())
        self.db.register_tracker(name, display_name)

    @abstractmethod
    def scrape(self):
        """
        Scrape new articles/updates from configured sources.

        Returns:
            int: Number of new articles scraped
        """
        pass

    @abstractmethod
    def analyze(self):
        """
        Analyze articles and generate AI summaries.

        Returns:
            int: Number of articles analyzed
        """
        pass

    @abstractmethod
    def report(self, tier=None):
        """
        Generate reports for this tracker.

        Args:
            tier (int, optional): Report tier (1, 2, or 3)

        Returns:
            str: Path to generated report
        """
        pass

    def test_connection(self):
        """
        Test AI connection (if applicable).

        Returns:
            bool: True if connection successful
        """
        return True
