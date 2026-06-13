"""
LLM News summarizer module.
Handles AI-powered summarization of LLM news and updates using AI backends (LM Studio or Claude).
"""

import logging
import re
from datetime import datetime
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from core.ai_client import AIClient
from core.report_helpers import SummaryCleanupMixin, content_too_short, insufficient_content_placeholder
from core.prompt_library import render

logger = logging.getLogger(__name__)


class LLMNewsSummarizer(SummaryCleanupMixin):
    """Generates summaries for LLM news and update articles"""

    def __init__(self, ai_config=None, base_url=None, api_key=None, model=None):
        """
        Initialize the LLM news summarizer.

        Args:
            ai_config (dict, optional): AI configuration dict (new format)
            base_url (str, optional): LM Studio API endpoint (legacy format)
            api_key (str, optional): API key (legacy format)
            model (str, optional): Model name (legacy format)
        """
        # Support both new and legacy initialization
        if ai_config:
            self.ai_client = AIClient(ai_config)
        else:
            # Legacy format - create LM Studio client
            logger.warning("Using legacy summarizer initialization. Consider passing ai_config instead.")
            from core.ai_client import AIClientFactory
            self.ai_client = AIClientFactory.create_lmstudio(
                base_url=base_url or "http://localhost:1234/v1",
                api_key=api_key or "lm-studio",
                model=model or "local-model"
            )

    def summarize(self, title, content, content_type=None, provider=None, product=None):
        """
        Generate a summary for an LLM news article.

        Args:
            title (str): Article title
            content (str): Article content
            content_type (list, optional): Classification of content type
            provider (str, optional): LLM provider name (e.g., Anthropic, OpenAI)
            product (str, optional): Product name (e.g., Claude, ChatGPT)

        Returns:
            tuple: (summary, content_type) - Generated summary and detected content type
        """
        try:
            # Skip too-thin content (empty RSS stub / paywall) - don't burn an LLM call
            if content_too_short(content):
                logger.warning(f"Content too short ({len(content) if content else 0} chars) for '{title}' - skipping AI summarization")
                return insufficient_content_placeholder(content), "general_update"

            # Build context
            type_context = ""
            if content_type and isinstance(content_type, list):
                type_context = f"\nContent Classification: {', '.join(content_type)}\n"

            provider_context = ""
            if provider:
                provider_context = f"\nProvider: {provider}\n"
            if product:
                provider_context += f"Product: {product}\n"

            prompt = render('llm_news.article.user',
                            title=title,
                            content=content[:8000],
                            provider_context=provider_context,
                            type_context=type_context)

            # Call the AI API
            summary = self.ai_client.chat_completion(
                messages=[
                    {
                        "role": "system",
                        "content": render('llm_news.article.system')
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                max_tokens=2000
            )

            # Remove any trailing questions the AI might have added
            summary = self._remove_trailing_questions(summary)

            # Detect content type if not provided
            detected_type = content_type[0] if content_type else self._detect_content_type(title, content)

            logger.info(f"Generated LLM news summary for: {title}")

            return summary, detected_type

        except Exception as e:
            logger.error(f"Error generating LLM news summary: {str(e)}")
            # Return None so the caller leaves the article unsummarized for retry
            return None, "general_update"

    def _detect_content_type(self, title, content):
        """Detect the content type based on title and content keywords"""
        text = f"{title} {content}".lower()

        if any(kw in text for kw in ['new model', 'release', 'launch', 'announcing', 'introducing']):
            return 'model_release'
        elif any(kw in text for kw in ['api', 'endpoint', 'deprecation', 'sdk']):
            return 'api_update'
        elif any(kw in text for kw in ['pricing', 'cost', 'tier', 'plan']):
            return 'pricing_change'
        elif any(kw in text for kw in ['security', 'vulnerability', 'safety']):
            return 'security_notice'
        elif any(kw in text for kw in ['paper', 'research', 'benchmark']):
            return 'research'
        elif any(kw in text for kw in ['feature', 'capability', 'enhancement']):
            return 'feature_announcement'
        else:
            return 'general_update'


class LLMNewsExecutiveSummarizer(SummaryCleanupMixin):
    """Generates executive summaries from multiple LLM news articles"""

    def __init__(self, ai_config=None, base_url=None, api_key=None, model=None):
        """
        Initialize the executive summarizer for LLM news.

        Args:
            ai_config (dict, optional): AI configuration dict (new format)
            base_url (str, optional): LM Studio API endpoint (legacy format)
            api_key (str, optional): API key (legacy format)
            model (str, optional): Model name (legacy format)
        """
        # Support both new and legacy initialization
        if ai_config:
            self.ai_client = AIClient(ai_config)
        else:
            # Legacy format - create LM Studio client
            logger.warning("Using legacy summarizer initialization. Consider passing ai_config instead.")
            from core.ai_client import AIClientFactory
            self.ai_client = AIClientFactory.create_lmstudio(
                base_url=base_url or "http://localhost:1234/v1",
                api_key=api_key or "lm-studio",
                model=model or "local-model"
            )

    def create_summary(self, articles, max_articles=30, time_period="last 30 days", provider_focus=None):
        """
        Create an executive summary from multiple LLM news articles.

        Args:
            articles (list): List of article dictionaries with summaries
            max_articles (int): Maximum number of articles to include
            time_period (str): Time period description
            provider_focus (str): Optional provider name to focus the summary on

        Returns:
            dict: Executive summary with structured information
        """
        try:
            # Get current month and year for the report title
            current_date = datetime.now()
            current_month_year = current_date.strftime("%B %Y")

            # Create week-specific date format for tier 1 reports
            is_tier1_report = time_period == "last 7 days"
            day = current_date.day
            day_suffix = self._get_day_suffix(day)
            week_date_formatted = f"the week of {current_date.strftime('%B')} {day}{day_suffix}, {current_date.year}"

            # Limit number of articles to prevent token overflow
            articles_to_process = articles[:max_articles]

            # Prepare article summaries for analysis
            articles_text = ""
            providers_seen = set()
            provider_counts = {}  # Count articles per provider for accuracy
            for idx, article in enumerate(articles_to_process, 1):
                provider = article.get('provider', 'Unknown')
                providers_seen.add(provider)
                provider_counts[provider] = provider_counts.get(provider, 0) + 1
                articles_text += f"\n--- Article {idx} ---\n"
                articles_text += f"Provider: {provider}\n"
                articles_text += f"Product: {article.get('product', 'Unknown')}\n"
                articles_text += f"Source: {article.get('source', 'Unknown')}\n"
                articles_text += f"Title: {article.get('title', 'Unknown')}\n"
                articles_text += f"Date: {article.get('published_date', 'Unknown')}\n"
                articles_text += f"Content Type: {article.get('content_type', 'General')}\n"
                articles_text += f"Summary:\n{article.get('summary', 'No summary available')}\n"

            # Build provider counts string for the prompt
            provider_counts_str = ", ".join([f"{p}: {c}" for p, c in sorted(provider_counts.items())])

            # Determine date format for prompt
            if is_tier1_report:
                date_format = week_date_formatted
                title_format = f"LLM News & Updates Summary – For {week_date_formatted}"
                overview_instruction = "High-level summary of noteworthy LLM developments for this week"
            else:
                date_format = current_month_year
                title_format = f"LLM News & Updates Summary – {current_month_year}"
                overview_instruction = "High-level summary of noteworthy LLM developments"

            # Build provider list for the prompt
            provider_list = ", ".join(sorted(providers_seen))

            prompt = render('llm_news.exec.user',
                            time_period=time_period,
                            current_date_str=current_date.strftime('%B %d, %Y'),
                            title_format=title_format,
                            date_format=date_format,
                            provider_list=provider_list,
                            provider_counts_str=provider_counts_str,
                            articles_text=articles_text,
                            overview_instruction=overview_instruction)

            # Call AI API
            executive_summary = self.ai_client.chat_completion(
                messages=[
                    {
                        "role": "system",
                        "content": render('llm_news.exec.system')
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                max_tokens=4000
            )

            # Remove any trailing questions the AI might have added
            executive_summary = self._remove_trailing_questions(executive_summary)

            # Structure the response
            summary_data = {
                'summary': executive_summary,
                'article_count': len(articles_to_process),
                'time_period': time_period,
                'sources': list(set(article.get('source', 'Unknown') for article in articles_to_process)),
                'providers': list(providers_seen),
                'content_types': self._count_content_types(articles_to_process)
            }

            logger.info(f"Generated executive summary for {len(articles_to_process)} LLM news articles")

            return summary_data

        except Exception as e:
            logger.error(f"Error generating executive summary: {str(e)}")
            return {
                'summary': f"Error generating executive summary: {str(e)}",
                'article_count': 0,
                'time_period': time_period,
                'sources': [],
                'providers': [],
                'content_types': {}
            }

    def _count_content_types(self, articles):
        """Count the distribution of content types."""
        type_counts = {}
        for article in articles:
            content_type = article.get('content_type', 'general_update')
            if isinstance(content_type, list):
                for ct in content_type:
                    type_counts[ct] = type_counts.get(ct, 0) + 1
            else:
                type_counts[content_type] = type_counts.get(content_type, 0) + 1
        return type_counts

    def create_provider_summary(self, provider_name, articles, time_period="last 7 days"):
        """
        Create a brief summary for a specific provider's updates.

        Args:
            provider_name (str): Name of the provider (e.g., "Anthropic", "OpenAI")
            articles (list): List of article dictionaries for this provider
            time_period (str): Time period description

        Returns:
            str: Brief provider summary (2-4 sentences)
        """
        if not articles:
            return ""

        try:
            # Prepare article info for analysis
            articles_text = ""
            for idx, article in enumerate(articles[:10], 1):  # Limit to 10 articles
                articles_text += f"\n{idx}. {article.get('title', 'Unknown')}\n"
                summary = article.get('summary', '')
                if summary:
                    # Take first 500 chars of summary
                    articles_text += f"   Summary: {summary[:500]}...\n" if len(summary) > 500 else f"   Summary: {summary}\n"

            prompt = render('llm_news.provider_mini.user',
                            provider_name=provider_name,
                            time_period=time_period,
                            article_count=len(articles),
                            articles_text=articles_text)

            # Call AI API
            summary = self.ai_client.chat_completion(
                messages=[
                    {
                        "role": "system",
                        "content": render('llm_news.provider_mini.system')
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                max_tokens=300
            )

            # Clean up the response
            summary = self._remove_trailing_questions(summary)

            logger.info(f"Generated provider summary for {provider_name} ({len(articles)} articles)")
            return summary.strip()

        except Exception as e:
            logger.error(f"Error generating provider summary for {provider_name}: {str(e)}")
            return ""
