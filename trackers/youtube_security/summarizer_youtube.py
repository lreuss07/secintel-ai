"""
YouTube Security summarizer module.
Handles AI-powered summarization of security YouTube video transcripts.
"""

import logging
import re
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from core.ai_client import AIClient
from core.report_helpers import SummaryCleanupMixin, content_too_short, insufficient_content_placeholder
from core.prompt_library import render

logger = logging.getLogger(__name__)


class YouTubeSecuritySummarizer(SummaryCleanupMixin):
    """Generates summaries for security YouTube video transcripts."""

    def __init__(self, ai_config=None, ai_max_chars=None):
        if ai_config:
            self.ai_client = AIClient(ai_config)
        else:
            logger.warning("Using legacy summarizer initialization.")
            from core.ai_client import AIClientFactory
            self.ai_client = AIClientFactory.create_lmstudio()

        self.ai_max_chars = ai_max_chars or 12000

    def summarize(self, title, content, content_type=None, provider=None, product=None):
        """
        Generate a summary for a YouTube security video transcript.

        Args:
            title (str): Video title
            content (str): Transcript text
            content_type (list, optional): Pre-classified content types
            provider (str, optional): Channel provider (e.g., "YouTube")
            product (str, optional): Channel name (e.g., "John Hammond")

        Returns:
            tuple: (summary, content_type)
        """
        try:
            # Skip too-thin transcripts (failed/empty transcription) - don't burn an LLM call
            if content_too_short(content):
                logger.warning(f"Transcript too short ({len(content) if content else 0} chars) for '{title}' - skipping AI summarization")
                return insufficient_content_placeholder(content), "general_security"

            type_context = ""
            if content_type and isinstance(content_type, list):
                type_context = f"\nContent Classification: {', '.join(content_type)}\n"

            channel_context = ""
            if product:
                channel_context = f"\nChannel: {product}\n"

            # Truncate transcript for AI context window
            transcript_text = content[:self.ai_max_chars]

            prompt = render('youtube.article.user',
                            title=title,
                            channel_context=channel_context,
                            transcript_text=transcript_text,
                            type_context=type_context)

            summary = self.ai_client.chat_completion(
                messages=[
                    {
                        "role": "system",
                        "content": render('youtube.article.system')
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                max_tokens=2000
            )

            summary = self._remove_trailing_questions(summary)

            detected_type = content_type[0] if content_type else self._detect_content_type(title, content)

            logger.info(f"Generated summary for video: {title}")

            return summary, detected_type

        except Exception as e:
            logger.error(f"Error generating video summary: {e}")
            # Return None so the caller leaves the article unsummarized for retry
            return None, "general_security"

    def _detect_content_type(self, title, content):
        """Detect content type based on title and content keywords."""
        text = f"{title} {content[:2000]}".lower()

        if any(kw in text for kw in ['cve', 'vulnerability', 'exploit', 'zero-day', 'zero day', 'ransomware', 'malware', 'breach']):
            return 'threat_advisory'
        elif any(kw in text for kw in ['ctf', 'capture the flag', 'hack the box', 'htb', 'tryhackme', 'walkthrough', 'writeup']):
            return 'ctf_walkthrough'
        elif any(kw in text for kw in ['tutorial', 'how to', 'guide', 'learn', 'getting started', 'beginner']):
            return 'tutorial'
        elif any(kw in text for kw in ['tool', 'review', 'demo', 'demonstration', 'comparison']):
            return 'tool_review'
        elif any(kw in text for kw in ['news', 'update', 'announcement', 'released', 'patch', 'advisory']):
            return 'security_news'
        else:
            return 'general_security'


class YouTubeSecurityExecutiveSummarizer(SummaryCleanupMixin):
    """Generates executive summaries from multiple YouTube security videos."""

    def __init__(self, ai_config=None):
        if ai_config:
            self.ai_client = AIClient(ai_config)
        else:
            logger.warning("Using legacy summarizer initialization.")
            from core.ai_client import AIClientFactory
            self.ai_client = AIClientFactory.create_lmstudio()

    def create_summary(self, articles, max_articles=30, time_period="last 30 days"):
        """
        Create an executive summary from multiple YouTube security video articles.

        Args:
            articles (list): List of article dicts with summaries
            max_articles (int): Max articles to include
            time_period (str): Time period description

        Returns:
            dict: Executive summary with structured information
        """
        try:
            current_date = datetime.now()
            current_month_year = current_date.strftime("%B %Y")

            is_tier1 = time_period == "last 7 days"
            day = current_date.day
            day_suffix = self._get_day_suffix(day)
            week_date = f"the week of {current_date.strftime('%B')} {day}{day_suffix}, {current_date.year}"

            articles_to_process = articles[:max_articles]

            # Build article text grouped by channel
            articles_text = ""
            channels_seen = set()
            channel_counts = {}
            for idx, article in enumerate(articles_to_process, 1):
                channel = article.get('product', article.get('source', 'Unknown'))
                channels_seen.add(channel)
                channel_counts[channel] = channel_counts.get(channel, 0) + 1
                articles_text += f"\n--- Video {idx} ---\n"
                articles_text += f"Channel: {channel}\n"
                articles_text += f"Title: {article.get('title', 'Unknown')}\n"
                articles_text += f"Date: {article.get('published_date', 'Unknown')}\n"
                articles_text += f"Content Type: {article.get('content_type', 'General')}\n"
                articles_text += f"Summary:\n{article.get('summary', 'No summary available')}\n"

            channel_counts_str = ", ".join([f"{c}: {n}" for c, n in sorted(channel_counts.items())])

            if is_tier1:
                date_format = week_date
                title_format = f"Security YouTube Summary - For {week_date}"
            else:
                date_format = current_month_year
                title_format = f"Security YouTube Summary - {current_month_year}"

            channel_list = ", ".join(sorted(channels_seen))

            prompt = render('youtube.exec.user',
                            time_period=time_period,
                            formatted_date=current_date.strftime('%B %d, %Y'),
                            title_format=title_format,
                            channel_list=channel_list,
                            channel_counts_str=channel_counts_str,
                            articles_text=articles_text)

            executive_summary = self.ai_client.chat_completion(
                messages=[
                    {
                        "role": "system",
                        "content": render('youtube.exec.system')
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                max_tokens=4000
            )

            executive_summary = self._remove_trailing_questions(executive_summary)

            summary_data = {
                'summary': executive_summary,
                'article_count': len(articles_to_process),
                'time_period': time_period,
                'sources': list(set(a.get('source', 'Unknown') for a in articles_to_process)),
                'channels': list(channels_seen),
                'content_types': self._count_content_types(articles_to_process)
            }

            logger.info(f"Generated executive summary for {len(articles_to_process)} videos")
            return summary_data

        except Exception as e:
            logger.error(f"Error generating executive summary: {e}")
            return {
                'summary': f"Error generating executive summary: {e}",
                'article_count': 0,
                'time_period': time_period,
                'sources': [],
                'channels': [],
                'content_types': {}
            }

    def _count_content_types(self, articles):
        """Count the distribution of content types."""
        type_counts = {}
        for article in articles:
            content_type = article.get('content_type', 'general_security')
            if isinstance(content_type, list):
                for ct in content_type:
                    type_counts[ct] = type_counts.get(ct, 0) + 1
            else:
                type_counts[content_type] = type_counts.get(content_type, 0) + 1
        return type_counts

    def create_channel_summary(self, channel_name, articles, time_period="last 7 days"):
        """
        Create a brief summary for a specific channel's videos.

        Args:
            channel_name (str): Channel name
            articles (list): Articles from this channel
            time_period (str): Time period description

        Returns:
            str: Brief channel summary (2-4 sentences)
        """
        if not articles:
            return ""

        try:
            articles_text = ""
            for idx, article in enumerate(articles[:10], 1):
                articles_text += f"\n{idx}. {article.get('title', 'Unknown')}\n"
                summary = article.get('summary', '')
                if summary:
                    articles_text += f"   Summary: {summary[:500]}...\n" if len(summary) > 500 else f"   Summary: {summary}\n"

            prompt = render('youtube.channel_mini.user',
                            channel_name=channel_name,
                            time_period=time_period,
                            video_count=len(articles),
                            articles_text=articles_text)

            summary = self.ai_client.chat_completion(
                messages=[
                    {
                        "role": "system",
                        "content": render('youtube.channel_mini.system')
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                max_tokens=300
            )

            summary = self._remove_trailing_questions(summary)
            logger.info(f"Generated channel summary for {channel_name} ({len(articles)} videos)")
            return summary.strip()

        except Exception as e:
            logger.error(f"Error generating channel summary for {channel_name}: {e}")
            return ""
