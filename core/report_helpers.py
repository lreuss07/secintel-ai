"""
Shared helper mixins for tracker summarizers and report generators.

These methods were previously copy-pasted across every tracker's summarizer
and reporting modules (15 copies of _remove_trailing_questions, 5 of
_get_day_suffix, 4 of _get_ai_model_attribution) and had already started to
drift - e.g. only some copies had the None-guard in _remove_trailing_questions.
This module is the single canonical home; tracker classes inherit the mixins.

Usage:
    from core.report_helpers import SummaryCleanupMixin, AIModelAttributionMixin

    class MyReportGenerator(SummaryCleanupMixin, AIModelAttributionMixin):
        def __init__(self, ai_config=None):
            self.ai_config = ai_config   # used by _get_ai_model_attribution
"""

import logging
import re

import requests

logger = logging.getLogger(__name__)

# Cache of resolved LM Studio model names, keyed by base_url, for the lifetime
# of the process (the CLI is one-shot, so a --full-run generating several
# reports queries the endpoint at most once).
_lmstudio_model_cache = {}


def resolve_lmstudio_model(lm_config, timeout=2):
    """
    Resolve the model name actually loaded in LM Studio, for report attribution.

    The config's `model` is typically a placeholder ('local-model') that doesn't
    drive model selection - LM Studio serves whatever the user has loaded. This
    queries LM Studio's native REST API (`/api/v0/models`), which reports a
    `state` of 'loaded' for the active model, and returns that real name.

    Falls back to the configured model name on any failure (endpoint
    unreachable, older LM Studio without the native API, no base_url). Never
    raises - report generation must not depend on the AI server being up.
    """
    lm_config = lm_config or {}
    configured = lm_config.get('model', 'local-model')
    base_url = lm_config.get('base_url')
    if not base_url:
        return configured
    if base_url in _lmstudio_model_cache:
        return _lmstudio_model_cache[base_url]

    # base_url is the OpenAI-compatible root (…/v1); the native API is at …/api/v0
    root = base_url.rstrip('/')
    if root.endswith('/v1'):
        root = root[:-len('/v1')]

    resolved = configured
    try:
        resp = requests.get(f"{root}/api/v0/models", timeout=timeout)
        resp.raise_for_status()
        loaded = [m['id'] for m in resp.json().get('data', [])
                  if m.get('state') == 'loaded' and m.get('id')]
        if loaded:
            resolved = loaded[0]
        else:
            # Older LM Studio without state info: only trust /v1/models when it
            # lists exactly one model (otherwise we can't tell which is active).
            ids = [m['id'] for m in requests.get(f"{root}/v1/models", timeout=timeout).json().get('data', []) if m.get('id')]
            if len(ids) == 1:
                resolved = ids[0]
    except Exception as e:
        logger.debug(f"Could not resolve loaded LM Studio model from {base_url}: {e}")

    _lmstudio_model_cache[base_url] = resolved
    return resolved


def clear_model_cache():
    """Reset the resolved-model cache (used by tests)."""
    _lmstudio_model_cache.clear()


# Minimum scraped content length worth sending to the LLM. Below this a page is
# almost always an empty RSS stub, an ad, or a paywall - summarizing it wastes a
# call and can push some local models into a degenerate "nothing to summarize"
# loop. Matches the threshold the threat_intel summarizer already used.
MIN_SUMMARY_CONTENT_CHARS = 200


def content_too_short(content):
    """True when scraped content is too thin to be worth summarizing."""
    return not content or len(content.strip()) < MIN_SUMMARY_CONTENT_CHARS


def insufficient_content_placeholder(content):
    """
    Placeholder summary stored for too-thin content so the article is marked
    done (not re-attempted every run) without burning an LLM call. Mirrors the
    note the threat_intel summarizer produces for the same case.
    """
    n = len(content) if content else 0
    return (f"*Content unavailable or insufficient for analysis (only {n} characters "
            f"scraped). This may be due to a temporary scraping issue or paywall.*")


class SummaryCleanupMixin:
    """Text-cleanup helpers shared by summarizers and report generators."""

    def _remove_trailing_questions(self, text):
        """
        Remove trailing questions that the AI might add at the end of summaries.

        Args:
            text (str): Summary text

        Returns:
            str: Cleaned text without trailing questions
        """
        if not text:
            return text

        # Common question patterns to remove
        question_patterns = [
            r'\n\n?Do you want.*?\?.*?$',
            r'\n\n?Would you like.*?\?.*?$',
            r'\n\n?Should I.*?\?.*?$',
            r'\n\n?Can I.*?\?.*?$',
            r'\n\n?Is there anything.*?\?.*?$',
            r'\n\n?Let me know if.*?\?.*?$',
            r'\n\n?Feel free to.*?\?.*?$',
            r'\n\n?Please let me know.*?\?.*?$',
        ]

        cleaned = text
        for pattern in question_patterns:
            cleaned = re.sub(pattern, '', cleaned, flags=re.DOTALL | re.IGNORECASE)

        return cleaned.strip()

    def _get_day_suffix(self, day):
        """
        Get the ordinal suffix for a day number (st, nd, rd, th).

        Args:
            day (int): Day of the month (1-31)

        Returns:
            str: Ordinal suffix (st, nd, rd, th)
        """
        if 10 <= day % 100 <= 20:
            suffix = 'th'
        else:
            suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th')
        return suffix


class AIModelAttributionMixin:
    """AI model attribution for report headers. Reads self.ai_config."""

    def _get_ai_model_attribution(self):
        """
        Generate AI model attribution string for reports.

        Returns:
            dict: Dictionary with model name, provider type, and formatted display string
        """
        ai_config = getattr(self, 'ai_config', None)
        if not ai_config:
            return {
                'model_name': 'Unknown',
                'provider_type': 'Unknown',
                'display': 'AI Model: Unknown'
            }

        provider = ai_config.get('provider', 'unknown').lower()

        if provider == 'lmstudio':
            lm_config = ai_config.get('lmstudio', {})
            model_name = resolve_lmstudio_model(lm_config)
            return {
                'model_name': model_name,
                'provider_type': 'Local',
                'display': f'AI Model: {model_name} (Local - LM Studio)'
            }
        elif provider == 'claude':
            claude_config = ai_config.get('claude', {})
            model_name = claude_config.get('model', 'claude-sonnet-4-20250514')
            return {
                'model_name': model_name,
                'provider_type': 'Cloud',
                'display': f'AI Model: {model_name} (Cloud - Anthropic Claude API)'
            }
        else:
            return {
                'model_name': provider,
                'provider_type': 'Unknown',
                'display': f'AI Model: {provider} (Unknown Provider)'
            }
