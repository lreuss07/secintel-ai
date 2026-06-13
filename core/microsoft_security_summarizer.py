"""
Defender-focused summarizer module.
Handles AI-powered summarization of Microsoft Defender updates using AI backends (LM Studio or Claude).
"""

import logging
import json
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

class MicrosoftSecurityProductSummarizer(SummaryCleanupMixin):
    """Generates summaries for Microsoft Security Product update articles"""

    def __init__(self, ai_config=None, base_url=None, api_key=None, model=None):
        """
        Initialize the Microsoft Security Product summarizer.

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

    def summarize(self, title, content, update_type=None):
        """
        Generate a summary for a Microsoft Security Product update article.

        Args:
            title (str): Article title
            content (str): Article content
            update_type (list, optional): Classification of update type

        Returns:
            str: Generated summary focused on security product changes
        """
        try:
            # Skip too-thin content (empty RSS stub / paywall) - don't burn an LLM call
            if content_too_short(content):
                logger.warning(f"Content too short ({len(content) if content else 0} chars) for '{title}' - skipping AI summarization")
                return insufficient_content_placeholder(content)

            # Build update type context
            update_context = ""
            if update_type and isinstance(update_type, list):
                update_context = f"\nUpdate Classification: {', '.join(update_type)}\n"

            prompt = render('microsoft_products.article.user',
                            title=title, content=content, update_context=update_context)

            # Call the AI API
            summary = self.ai_client.chat_completion(
                messages=[
                    {
                        "role": "system",
                        "content": render('microsoft_products.article.system')
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                max_tokens=2500
            )

            # Remove any trailing questions the AI might have added
            summary = self._remove_trailing_questions(summary)

            logger.info(f"Generated security product summary for: {title}")

            return summary

        except Exception as e:
            logger.error(f"Error generating security product summary: {str(e)}")
            # Return None (not an error string) so the caller leaves the article
            # unsummarized for retry rather than persisting the error as a summary.
            return None


class MicrosoftSecurityExecutiveSummarizer(SummaryCleanupMixin):
    """Generates executive summaries from multiple Microsoft Security Product update articles"""

    def __init__(self, ai_config=None, base_url=None, api_key=None, model=None):
        """
        Initialize the executive summarizer for Microsoft Security Product updates.

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

    def create_summary(self, articles, max_articles=30, time_period="last 30 days", product_focus=None):
        """
        Create an executive summary from multiple Microsoft Security Product update articles.

        Args:
            articles (list): List of article dictionaries with summaries
            max_articles (int): Maximum number of articles to include
            time_period (str): Time period description
            product_focus (str): Optional product name to focus the summary on

        Returns:
            dict: Executive summary with structured information
        """
        try:
            # Get current month and year for the report title
            current_date = datetime.now()
            current_month_year = current_date.strftime("%B %Y")

            # Create week-specific date format for tier 1 reports (7-day window)
            is_tier1_report = time_period == "last 7 days"
            day = current_date.day
            day_suffix = self._get_day_suffix(day)
            week_date_formatted = f"the week of {current_date.strftime('%B')} {day}{day_suffix}, {current_date.year}"

            # Limit number of articles to prevent token overflow
            articles_to_process = articles[:max_articles]

            # Prepare article summaries for analysis
            articles_text = ""
            for idx, article in enumerate(articles_to_process, 1):
                articles_text += f"\n--- Article {idx} ---\n"
                articles_text += f"Source: {article.get('source', 'Unknown')}\n"
                articles_text += f"Title: {article.get('title', 'Unknown')}\n"
                articles_text += f"Date: {article.get('published_date', 'Unknown')}\n"
                articles_text += f"Update Type: {', '.join(article.get('update_type', ['General']))}\n"
                articles_text += f"Summary:\n{article.get('summary', 'No summary available')}\n"

            # Customize prompt based on whether this is product-specific
            if product_focus:
                prompt = render('microsoft_products.exec_product.user',
                                product_focus=product_focus, time_period=time_period,
                                articles_text=articles_text)
            else:
                # Determine which date format to use in the prompt
                if is_tier1_report:
                    date_format = week_date_formatted
                    title_format = f"Microsoft Security Product Update Summary – For {week_date_formatted}"
                    date_instruction = f"The current date is {current_date.strftime('%B %d, %Y')}. You MUST use \"For {week_date_formatted}\" in your title."
                    overview_instruction = "High-level summary of noteworthy security product updates for this week"
                else:
                    date_format = current_month_year
                    title_format = f"Microsoft Security Product Update Summary – {current_month_year}"
                    date_instruction = f"The current date is {current_month_year}. You MUST use \"{current_month_year}\" in your title."
                    overview_instruction = "High-level summary of noteworthy security product updates"

                prompt = render('microsoft_products.exec_overview.user',
                                time_period=time_period, date_instruction=date_instruction,
                                title_format=title_format, date_format=date_format,
                                articles_text=articles_text,
                                overview_instruction=overview_instruction)

            # Call AI API
            executive_summary = self.ai_client.chat_completion(
                messages=[
                    {
                        "role": "system",
                        "content": render('microsoft_products.exec.system')
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
                'update_types': self._count_update_types(articles_to_process)
            }

            logger.info(f"Generated executive summary for {len(articles_to_process)} security product updates")

            return summary_data

        except Exception as e:
            logger.error(f"Error generating executive summary: {str(e)}")
            return {
                'summary': f"Error generating executive summary: {str(e)}",
                'article_count': 0,
                'time_period': time_period,
                'sources': [],
                'update_types': {}
            }
    
    def _count_update_types(self, articles):
        """
        Count the distribution of update types.
        
        Args:
            articles (list): List of articles
            
        Returns:
            dict: Count of each update type
        """
        type_counts = {}
        for article in articles:
            update_types = article.get('update_type', ['General'])
            for update_type in update_types:
                type_counts[update_type] = type_counts.get(update_type, 0) + 1
        return type_counts
