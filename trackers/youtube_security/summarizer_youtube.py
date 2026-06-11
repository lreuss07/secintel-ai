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

logger = logging.getLogger(__name__)


class YouTubeSecuritySummarizer:
    """Generates summaries for security YouTube video transcripts."""

    def __init__(self, ai_config=None, ai_max_chars=None):
        if ai_config:
            self.ai_client = AIClient(ai_config)
        else:
            logger.warning("Using legacy summarizer initialization.")
            from core.ai_client import AIClientFactory
            self.ai_client = AIClientFactory.create_lmstudio()

        self.ai_max_chars = ai_max_chars or 12000

    def _remove_trailing_questions(self, text):
        """Remove trailing questions the AI might add."""
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
            type_context = ""
            if content_type and isinstance(content_type, list):
                type_context = f"\nContent Classification: {', '.join(content_type)}\n"

            channel_context = ""
            if product:
                channel_context = f"\nChannel: {product}\n"

            # Truncate transcript for AI context window
            transcript_text = content[:self.ai_max_chars]

            prompt = f"""You are a cybersecurity analyst summarizing a security YouTube video. The content below is an auto-generated transcript, so expect informal language, filler words, and tangents. Focus on extracting the substantive security content.

Title: {title}
{channel_context}
Transcript:
{transcript_text}
{type_context}

Provide a structured summary that includes:

1. **Overview**: What is this video about? (1-2 sentences)

2. **Key Security Topics**: Main security topics covered
   - Specific vulnerabilities, threats, or techniques discussed
   - Tools or technologies mentioned
   - Attack vectors or defense strategies

3. **Technical Details**: Important technical information
   - CVEs, exploit techniques, or attack methodologies
   - Commands, tools, or configurations shown
   - Network/system details relevant to security

4. **Actionable Takeaways**: What should security professionals do?
   - Patches to apply or configurations to change
   - Tools to evaluate or deploy
   - Threats to monitor or investigate

Keep the summary technical and focused on practical security value. Aim for 200-300 words. Ignore sponsor segments, personal anecdotes, and off-topic tangents.

CRITICAL ACCURACY RULES:
- ONLY use information explicitly stated in the transcript
- Do NOT invent CVE numbers, tool names, or technical details
- If a detail is unclear from the transcript, say "not specified" or omit it
- Do NOT add information from your own knowledge that wasn't in the transcript

IMPORTANT: Provide ONLY the summary. Do NOT ask follow-up questions or offer to elaborate."""

            summary = self.ai_client.chat_completion(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a cybersecurity analyst summarizing security video transcripts. Provide clear, actionable summaries focused on security value. Never ask follow-up questions."
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
            return f"Error generating summary: {e}", "general_security"

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


class YouTubeSecurityExecutiveSummarizer:
    """Generates executive summaries from multiple YouTube security videos."""

    def __init__(self, ai_config=None):
        if ai_config:
            self.ai_client = AIClient(ai_config)
        else:
            logger.warning("Using legacy summarizer initialization.")
            from core.ai_client import AIClientFactory
            self.ai_client = AIClientFactory.create_lmstudio()

    def _get_day_suffix(self, day):
        """Get ordinal suffix for a day number."""
        if 10 <= day % 100 <= 20:
            suffix = 'th'
        else:
            suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th')
        return suffix

    def _remove_trailing_questions(self, text):
        """Remove trailing questions the AI might add."""
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

            prompt = f"""You are a cybersecurity analyst creating an executive summary of security YouTube content from the {time_period}.

CRITICAL INSTRUCTION:
The current date is {current_date.strftime('%B %d, %Y')}.
Your title MUST be: "{title_format}"

Channels covered: {channel_list}
VIDEO COUNTS BY CHANNEL: {channel_counts_str}

{articles_text}

Create a structured executive summary:

1. **Executive Overview** (2-3 sentences)
   - Key security themes covered across videos
   - Notable trends or recurring topics

2. **Channel Highlights** (organized by channel)
   For each channel with videos, summarize the key content:
   - What topics were covered
   - Most important takeaways

3. **Threat Landscape** (from video content)
   - Vulnerabilities discussed
   - Attack techniques demonstrated
   - Threat actors or campaigns mentioned

4. **Tools & Techniques**
   - Security tools featured or reviewed
   - Techniques demonstrated
   - Useful commands or configurations

5. **Actionable Intelligence**
   - Patches or updates to apply
   - Threats to investigate
   - Skills to develop
   - Resources to explore

6. **Content Distribution**
   - Number of videos by channel
   - Types of content (threat advisories, CTF walkthroughs, tutorials, etc.)

Format with clear sections and bullet points. Be specific about tools, CVEs, and techniques mentioned.

CRITICAL: Only use information from the video summaries above. Do NOT invent details.

IMPORTANT: Provide ONLY the summary. No follow-up questions."""

            executive_summary = self.ai_client.chat_completion(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a cybersecurity analyst creating executive summaries of security YouTube content. Provide comprehensive, actionable summaries. Never ask follow-up questions."
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

            prompt = f"""Create a brief 2-4 sentence summary of {channel_name}'s security videos from the {time_period}.

Channel: {channel_name}
Number of videos: {len(articles)}

Videos:
{articles_text}

Highlight:
- Key security topics covered
- Most important takeaways
- Any critical threats or vulnerabilities discussed

Keep to 2-4 sentences. Be specific about security topics.

CRITICAL: Only use information from the videos above. Do NOT invent details.

IMPORTANT: Provide ONLY the summary. No questions or offers to elaborate."""

            summary = self.ai_client.chat_completion(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a concise cybersecurity analyst. Provide brief, informative summaries without follow-up questions."
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
