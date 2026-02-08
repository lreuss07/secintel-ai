"""
Source Validator for SecIntel AI

Validates source configurations and optionally tests connectivity.
"""

import logging
import os
from typing import Dict, List, Optional, Tuple
from pathlib import Path

import yaml
import requests
import feedparser

logger = logging.getLogger(__name__)

# Schema definitions for each source type
# Format: {'field_name': {'required': bool, 'type': expected_type, 'hint': str}}

COMMON_FIELDS = {
    'name': {'required': True, 'type': str, 'hint': 'Display name for this source'},
    'type': {'required': True, 'type': str, 'hint': 'Source type: rss, web, api, or headless'},
    'url': {'required': False, 'type': str, 'hint': 'Main URL of the source'},
    'vendor': {'required': False, 'type': str, 'hint': 'Vendor name (for third-party tracking)'},
    'provider': {'required': False, 'type': str, 'hint': 'Provider name (alternative to vendor)'},
    'product': {'required': False, 'type': str, 'hint': 'Product name'},
    'products': {'required': False, 'type': list, 'hint': 'List of product names to filter'},
    'keywords': {'required': False, 'type': list, 'hint': 'Keywords to filter content'},
}

RSS_FIELDS = {
    'feed_url': {'required': True, 'type': str, 'hint': 'URL to the RSS/Atom feed'},
    'filter_pattern': {'required': False, 'type': str, 'hint': 'Regex pattern to filter entries'},
    'filter_by_title': {'required': False, 'type': bool, 'hint': 'Filter RSS entries by title'},
    'filter_keywords': {'required': False, 'type': list, 'hint': 'Keywords to filter feed entries'},
}

WEB_FIELDS = {
    'content_selector': {'required': False, 'type': str, 'hint': 'CSS selector for main content'},
    'article_selector': {'required': False, 'type': str, 'hint': 'CSS selector for article links'},
    'single_page': {'required': False, 'type': bool, 'hint': 'Whether to scrape a single page only'},
    'selectors': {'required': False, 'type': dict, 'hint': 'Dict of CSS selectors for different elements'},
}

API_FIELDS = {
    'params': {'required': False, 'type': dict, 'hint': 'Query parameters for API requests'},
    'headers': {'required': False, 'type': dict, 'hint': 'HTTP headers for API requests'},
}

HEADLESS_FIELDS = {
    'url_template': {'required': False, 'type': str, 'hint': 'URL template with {year} placeholder'},
    'wait_for': {'required': False, 'type': str, 'hint': 'CSS selector to wait for before scraping'},
    'dynamic_year': {'required': False, 'type': bool, 'hint': 'Automatically substitute current year'},
    'fallback_to_previous_year': {'required': False, 'type': bool, 'hint': 'Try previous year if current fails'},
}

# All valid fields by source type
VALID_FIELDS = {
    'rss': {**COMMON_FIELDS, **RSS_FIELDS},
    'web': {**COMMON_FIELDS, **WEB_FIELDS},
    'api': {**COMMON_FIELDS, **API_FIELDS},
    'headless': {**COMMON_FIELDS, **HEADLESS_FIELDS},
}

VALID_SOURCE_TYPES = ['rss', 'web', 'api', 'headless']


class ValidationError:
    """Represents a single validation error."""

    def __init__(self, source_name: str, field: str, message: str, hint: Optional[str] = None):
        self.source_name = source_name
        self.field = field
        self.message = message
        self.hint = hint

    def __str__(self):
        result = f"  - {self.message}"
        if self.hint:
            result += f"\n    Hint: {self.hint}"
        return result


class ConnectionResult:
    """Represents a connectivity test result."""

    def __init__(self, source_name: str, source_type: str, success: bool,
                 message: str, item_count: Optional[int] = None):
        self.source_name = source_name
        self.source_type = source_type
        self.success = success
        self.message = message
        self.item_count = item_count

    def __str__(self):
        status = "OK" if self.success else "FAIL"
        result = f"    {'[OK]' if self.success else '[FAIL]'} {self.source_name} ({self.source_type}) - {self.message}"
        if self.item_count is not None and self.success:
            result += f", {self.item_count} items"
        return result


class SourceValidator:
    """Validates source configurations for SecIntel AI trackers."""

    def __init__(self, trackers_dir: str = None):
        if trackers_dir is None:
            trackers_dir = Path(__file__).parent.parent / 'trackers'
        self.trackers_dir = Path(trackers_dir)

    def get_tracker_names(self) -> List[str]:
        """Get list of available tracker names."""
        trackers = []
        for item in self.trackers_dir.iterdir():
            if item.is_dir() and not item.name.startswith('_'):
                config_path = item / 'config.yaml'
                if config_path.exists():
                    trackers.append(item.name)
        return sorted(trackers)

    def load_tracker_sources(self, tracker_name: str) -> Tuple[List[dict], Optional[str]]:
        """Load sources from a tracker's config file.

        Returns:
            Tuple of (sources list, error message or None)
        """
        config_path = self.trackers_dir / tracker_name / 'config.yaml'

        if not config_path.exists():
            return [], f"Config file not found: {config_path}"

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            sources = config.get('sources', [])
            if not isinstance(sources, list):
                return [], "sources must be a list"

            return sources, None

        except yaml.YAMLError as e:
            return [], f"YAML parse error: {e}"
        except Exception as e:
            return [], f"Error loading config: {e}"

    def validate_source(self, source: dict, source_index: int) -> List[ValidationError]:
        """Validate a single source configuration.

        Returns:
            List of ValidationError objects (empty if valid)
        """
        errors = []
        source_name = source.get('name', f'source #{source_index + 1}')

        # Check for required 'name' field
        if 'name' not in source:
            errors.append(ValidationError(
                source_name, 'name',
                "Missing required field: name",
                "Every source needs a unique display name"
            ))

        # Check for required 'type' field
        if 'type' not in source:
            errors.append(ValidationError(
                source_name, 'type',
                "Missing required field: type",
                f"Valid types: {', '.join(VALID_SOURCE_TYPES)}"
            ))
            return errors  # Can't continue without type

        source_type = source.get('type')
        if source_type not in VALID_SOURCE_TYPES:
            errors.append(ValidationError(
                source_name, 'type',
                f"Invalid source type: '{source_type}'",
                f"Valid types: {', '.join(VALID_SOURCE_TYPES)}"
            ))
            return errors  # Can't continue with invalid type

        # Get valid fields for this source type
        valid_fields = VALID_FIELDS[source_type]

        # Check type-specific required fields
        if source_type == 'rss':
            url = source.get('url', '')
            feed_url = source.get('feed_url', '')

            # If no feed_url, check if url looks like a feed URL
            url_is_feed = url.endswith(('.xml', '.rss', '.atom', '/feed/', '/feed', '/rss'))

            if not feed_url and not url_is_feed:
                errors.append(ValidationError(
                    source_name, 'feed_url',
                    "Missing required field: feed_url (required for type: rss)",
                    "RSS sources need 'feed_url', or 'url' can be the feed if it ends with .xml/.rss/.atom"
                ))
            if not url and not feed_url:
                errors.append(ValidationError(
                    source_name, 'url',
                    "Missing required field: url",
                    "At least one of 'url' or 'feed_url' is required"
                ))

        elif source_type == 'web':
            if 'url' not in source:
                errors.append(ValidationError(
                    source_name, 'url',
                    "Missing required field: url",
                    "The URL of the page to scrape"
                ))

        elif source_type == 'api':
            if 'url' not in source:
                errors.append(ValidationError(
                    source_name, 'url',
                    "Missing required field: url",
                    "The API endpoint URL"
                ))

        elif source_type == 'headless':
            if 'url' not in source and 'url_template' not in source:
                errors.append(ValidationError(
                    source_name, 'url/url_template',
                    "Missing required field: url or url_template",
                    "Headless sources need either 'url' or 'url_template' (with {year} placeholder)"
                ))

        # Check for unknown fields (possible typos)
        for field in source.keys():
            if field not in valid_fields:
                # Check if it might be a typo of a known field
                similar = self._find_similar_field(field, valid_fields.keys())
                hint = f"Did you mean '{similar}'?" if similar else None
                errors.append(ValidationError(
                    source_name, field,
                    f"Unknown field: '{field}'",
                    hint
                ))

        # Validate field types
        for field, value in source.items():
            if field in valid_fields:
                expected_type = valid_fields[field]['type']
                if not isinstance(value, expected_type):
                    errors.append(ValidationError(
                        source_name, field,
                        f"Field '{field}' should be {expected_type.__name__}, got {type(value).__name__}",
                        valid_fields[field].get('hint')
                    ))

        return errors

    def _find_similar_field(self, field: str, valid_fields: List[str]) -> Optional[str]:
        """Find a similar valid field name (for typo detection)."""
        field_lower = field.lower()
        for valid in valid_fields:
            # Simple similarity check
            if field_lower in valid.lower() or valid.lower() in field_lower:
                return valid
            # Check for common typos (e.g., feed_url vs feedurl)
            if field_lower.replace('_', '') == valid.lower().replace('_', ''):
                return valid
        return None

    def validate_tracker(self, tracker_name: str) -> Tuple[int, List[ValidationError]]:
        """Validate all sources in a tracker.

        Returns:
            Tuple of (source count, list of errors)
        """
        sources, load_error = self.load_tracker_sources(tracker_name)

        if load_error:
            return 0, [ValidationError(tracker_name, 'config', load_error)]

        all_errors = []
        for i, source in enumerate(sources):
            errors = self.validate_source(source, i)
            all_errors.extend(errors)

        return len(sources), all_errors

    def validate_all(self, tracker_filter: Optional[str] = None) -> Dict[str, Tuple[int, List[ValidationError]]]:
        """Validate all trackers (or a specific one).

        Returns:
            Dict mapping tracker name to (source count, errors list)
        """
        results = {}

        trackers = [tracker_filter] if tracker_filter else self.get_tracker_names()

        for tracker_name in trackers:
            count, errors = self.validate_tracker(tracker_name)
            results[tracker_name] = (count, errors)

        return results

    def test_connection(self, source: dict, timeout: int = 10) -> ConnectionResult:
        """Test connectivity to a single source.

        Returns:
            ConnectionResult object
        """
        source_name = source.get('name', 'Unknown')
        source_type = source.get('type', 'unknown')

        try:
            if source_type == 'rss':
                return self._test_rss(source, timeout)
            elif source_type == 'web':
                return self._test_web(source, timeout)
            elif source_type == 'api':
                return self._test_api(source, timeout)
            elif source_type == 'headless':
                return ConnectionResult(
                    source_name, source_type, True,
                    "Skipped (requires Playwright browser)"
                )
            else:
                return ConnectionResult(
                    source_name, source_type, False,
                    f"Unknown source type: {source_type}"
                )
        except Exception as e:
            return ConnectionResult(
                source_name, source_type, False,
                f"Error: {str(e)}"
            )

    def _test_rss(self, source: dict, timeout: int) -> ConnectionResult:
        """Test an RSS feed source."""
        source_name = source.get('name', 'Unknown')
        feed_url = source.get('feed_url', '')
        url = source.get('url', '')

        # Use url as feed_url if feed_url not specified and url looks like a feed
        if not feed_url:
            if url and url.endswith(('.xml', '.rss', '.atom', '/feed/', '/feed', '/rss')):
                feed_url = url
            else:
                return ConnectionResult(source_name, 'rss', False, "No feed_url specified")

        try:
            # Fetch the feed
            response = requests.get(feed_url, timeout=timeout, headers={
                'User-Agent': 'SecIntel AI Source Validator/1.0'
            })
            response.raise_for_status()

            # Parse as RSS/Atom
            feed = feedparser.parse(response.content)

            if feed.bozo and feed.bozo_exception:
                # Feed has parse errors but may still work
                return ConnectionResult(
                    source_name, 'rss', True,
                    f"200 OK (parse warning: {type(feed.bozo_exception).__name__})",
                    len(feed.entries)
                )

            return ConnectionResult(
                source_name, 'rss', True,
                "200 OK",
                len(feed.entries)
            )

        except requests.exceptions.HTTPError as e:
            return ConnectionResult(source_name, 'rss', False, f"HTTP {e.response.status_code}")
        except requests.exceptions.Timeout:
            return ConnectionResult(source_name, 'rss', False, f"Timeout after {timeout}s")
        except requests.exceptions.RequestException as e:
            return ConnectionResult(source_name, 'rss', False, f"Connection error: {type(e).__name__}")

    def _test_web(self, source: dict, timeout: int) -> ConnectionResult:
        """Test a web scraping source."""
        source_name = source.get('name', 'Unknown')
        url = source.get('url', '')

        if not url:
            return ConnectionResult(source_name, 'web', False, "No url specified")

        try:
            response = requests.head(url, timeout=timeout, allow_redirects=True, headers={
                'User-Agent': 'SecIntel AI Source Validator/1.0'
            })
            response.raise_for_status()

            return ConnectionResult(source_name, 'web', True, f"{response.status_code} OK")

        except requests.exceptions.HTTPError as e:
            return ConnectionResult(source_name, 'web', False, f"HTTP {e.response.status_code}")
        except requests.exceptions.Timeout:
            return ConnectionResult(source_name, 'web', False, f"Timeout after {timeout}s")
        except requests.exceptions.RequestException as e:
            return ConnectionResult(source_name, 'web', False, f"Connection error: {type(e).__name__}")

    def _test_api(self, source: dict, timeout: int) -> ConnectionResult:
        """Test an API source."""
        source_name = source.get('name', 'Unknown')
        url = source.get('url', '')
        params = source.get('params', {})

        if not url:
            return ConnectionResult(source_name, 'api', False, "No url specified")

        try:
            response = requests.get(url, params=params, timeout=timeout, headers={
                'User-Agent': 'SecIntel AI Source Validator/1.0',
                'Accept': 'application/json'
            })
            response.raise_for_status()

            # Try to parse as JSON
            try:
                data = response.json()
                if isinstance(data, list):
                    item_count = len(data)
                elif isinstance(data, dict):
                    # Try common patterns for item counts
                    item_count = data.get('total', data.get('count', len(data.get('results', data.get('items', [])))))
                else:
                    item_count = None

                return ConnectionResult(source_name, 'api', True, "200 OK", item_count)

            except ValueError:
                return ConnectionResult(source_name, 'api', True, "200 OK (not JSON)")

        except requests.exceptions.HTTPError as e:
            return ConnectionResult(source_name, 'api', False, f"HTTP {e.response.status_code}")
        except requests.exceptions.Timeout:
            return ConnectionResult(source_name, 'api', False, f"Timeout after {timeout}s")
        except requests.exceptions.RequestException as e:
            return ConnectionResult(source_name, 'api', False, f"Connection error: {type(e).__name__}")

    def test_tracker_connections(self, tracker_name: str, timeout: int = 10) -> List[ConnectionResult]:
        """Test connections for all sources in a tracker."""
        sources, load_error = self.load_tracker_sources(tracker_name)

        if load_error:
            return [ConnectionResult(tracker_name, 'config', False, load_error)]

        results = []
        for source in sources:
            result = self.test_connection(source, timeout)
            results.append(result)

        return results


def print_validation_results(results: Dict[str, Tuple[int, List[ValidationError]]]) -> int:
    """Print validation results in a formatted way.

    Returns:
        Total error count
    """
    total_errors = 0

    print("\nValidating sources...\n")

    for tracker_name, (source_count, errors) in results.items():
        print(f"[{tracker_name}] {source_count} sources")

        if errors:
            print("  Schema errors:")
            for error in errors:
                print(f"    {error.source_name}:")
                print(f"      {error}")
            total_errors += len(errors)
        else:
            print("  Schema valid")

        print()

    if total_errors > 0:
        print(f"Summary: {total_errors} error(s) found")
    else:
        print("Summary: All sources valid")

    return total_errors


def print_connection_results(tracker_name: str, results: List[ConnectionResult]) -> int:
    """Print connection test results.

    Returns:
        Number of failures
    """
    failures = sum(1 for r in results if not r.success)

    print(f"\n  Testing connections for {tracker_name}...")
    for result in results:
        print(f"  {result}")

    return failures
