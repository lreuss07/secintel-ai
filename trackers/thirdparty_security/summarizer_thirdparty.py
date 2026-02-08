"""
Third-party Security Tools summarizer module.
Handles AI-powered summarization of security product updates using AI backends (LM Studio or Claude).
"""

import logging
import re
from datetime import datetime
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from core.ai_client import AIClient

logger = logging.getLogger(__name__)


class ThirdPartySecuritySummarizer:
    """Generates summaries for third-party security product update articles"""

    def __init__(self, ai_config=None, base_url=None, api_key=None, model=None):
        """
        Initialize the third-party security product summarizer.

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

    def _remove_trailing_questions(self, text):
        """
        Remove trailing questions that the AI might add at the end of summaries.

        Args:
            text (str): Summary text

        Returns:
            str: Cleaned text without trailing questions
        """
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

    def summarize(self, title, content, update_type=None, vendor=None, product=None):
        """
        Generate a summary for a third-party security product update article.

        Args:
            title (str): Article title
            content (str): Article content
            update_type (list, optional): Classification of update type
            vendor (str, optional): Vendor name
            product (str, optional): Product name

        Returns:
            str: Generated summary focused on security product changes
        """
        try:
            # Build update type context
            update_context = ""
            if update_type and isinstance(update_type, list):
                update_context = f"\nUpdate Classification: {', '.join(update_type)}\n"

            vendor_context = ""
            if vendor:
                vendor_context = f"\nVendor: {vendor}\n"
            if product:
                vendor_context += f"Product: {product}\n"

            prompt = f"""You are a cybersecurity specialist assistant. Analyze the following security product update or announcement and provide a clear, informative summary.

Title: {title}
{vendor_context}
Content:
{content}
{update_context}

Please provide a structured summary that includes:

1. **What Changed**: Clearly identify what specific aspect of the security product was updated, changed, or announced
   - Which product/component was affected
   - Specific features, capabilities, or configurations affected

2. **Key Details**: Extract the most important technical details
   - Version numbers, build numbers, or release dates if mentioned
   - New features or capabilities introduced
   - Bugs fixed or issues resolved
   - Performance improvements
   - Changes to existing functionality
   - Policy or configuration changes

3. **What This Means**: How this affects your security environment
   - Who can use this (all users, specific licensing tiers, specific platforms)
   - Availability (automatic rollout, opt-in, configuration required)
   - Any breaking changes or deprecated features
   - Benefits and improvements this provides
   - Impact on security posture

4. **How to Use It**: Optional steps to take advantage of this update
   - Configuration options to explore
   - Recommended settings to consider
   - Getting started guidance
   - Timeline or availability if specified

5. **Additional Notes**: Any important details, prerequisites, or related information
   - Known limitations or requirements
   - Links to documentation if mentioned
   - Related updates or dependencies
   - Compliance or regulatory considerations

Keep the summary technical, specific, and informative. Focus on helping security administrators understand what's new and how they might use it. Aim for 300-400 words.

IMPORTANT: Provide ONLY the summary content. Do NOT ask follow-up questions, do NOT offer to refine the summary, and do NOT ask if the user wants more details. End your response after completing the summary.
"""

            # Call the AI API
            summary = self.ai_client.chat_completion(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a cybersecurity specialist. Provide clear, informative summaries of security product updates that help administrators understand new features, improvements, and changes. Never ask follow-up questions."
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
            return f"Error generating summary: {str(e)}"


class ThirdPartySecurityExecutiveSummarizer:
    """Generates executive summaries from multiple third-party security product update articles"""

    def __init__(self, ai_config=None, base_url=None, api_key=None, model=None, tracker_config=None):
        """
        Initialize the executive summarizer for third-party security product updates.

        Args:
            ai_config (dict, optional): AI configuration dict (new format)
            base_url (str, optional): LM Studio API endpoint (legacy format)
            api_key (str, optional): API key (legacy format)
            model (str, optional): Model name (legacy format)
            tracker_config (dict, optional): Tracker configuration with vendors list
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

        # Store tracker config for vendor list
        self.tracker_config = tracker_config or {}

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

    def _remove_trailing_questions(self, text):
        """
        Remove trailing questions that the AI might add at the end of summaries.

        Args:
            text (str): Summary text

        Returns:
            str: Cleaned text without trailing questions
        """
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

    def create_summary(self, articles, max_articles=30, time_period="last 30 days", vendor_focus=None):
        """
        Create an executive summary from multiple third-party security product update articles.

        Args:
            articles (list): List of article dictionaries with summaries
            max_articles (int): Maximum number of articles to include
            time_period (str): Time period description
            vendor_focus (str): Optional vendor name to focus the summary on

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
            vendors_seen = set()
            for idx, article in enumerate(articles_to_process, 1):
                vendor = article.get('vendor', 'Unknown')
                vendors_seen.add(vendor)
                articles_text += f"\n--- Article {idx} ---\n"
                articles_text += f"Vendor: {vendor}\n"
                articles_text += f"Product: {article.get('product', 'Unknown')}\n"
                articles_text += f"Source: {article.get('source', 'Unknown')}\n"
                articles_text += f"Title: {article.get('title', 'Unknown')}\n"
                articles_text += f"Date: {article.get('published_date', 'Unknown')}\n"
                articles_text += f"Update Type: {', '.join(article.get('update_type', ['General']))}\n"
                articles_text += f"Summary:\n{article.get('summary', 'No summary available')}\n"

            # Customize prompt based on whether this is vendor-specific
            if vendor_focus:
                prompt = f"""You are a cybersecurity specialist. Analyze the following {vendor_focus} updates from the {time_period} and create a concise executive summary.

{articles_text}

Create a brief executive summary for {vendor_focus} that includes:

1. **Key Updates** (2-3 sentences)
   - Most important changes or new features
   - Notable improvements or capabilities

2. **What Changed** (use a markdown table if multiple products, otherwise use bullet points)
   - New features and capabilities
   - Improvements and enhancements
   - Bug fixes if significant

3. **Action Items** (if applicable)
   Format each product/role as a separate subheading (###) followed by its action items as bullet points:

   ### KSAT Administrators
   - Action item 1
   - Action item 2

   ### SecurityCoach Administrators
   - Action item 1

   Do NOT put the product/role names as list items. Use ### subheadings.

Keep the summary concise and focused on {vendor_focus}. Format in markdown with clear sections.

IMPORTANT: Provide ONLY the executive summary content. Do NOT ask follow-up questions and do NOT offer to provide more details. End your response after completing the summary."""
            else:
                # Determine which date format to use in the prompt
                if is_tier1_report:
                    date_format = week_date_formatted
                    title_format = f"3rd Party Security Product Update Summary – For {week_date_formatted}"
                    date_instruction = f"The current date is {current_date.strftime('%B %d, %Y')}. You MUST use \"For {week_date_formatted}\" in your title."
                    overview_instruction = "High-level summary of noteworthy security product updates for this week"
                else:
                    date_format = current_month_year
                    title_format = f"3rd Party Security Product Update Summary – {current_month_year}"
                    date_instruction = f"The current date is {current_month_year}. You MUST use \"{current_month_year}\" in your title."
                    overview_instruction = "High-level summary of noteworthy security product updates"

                # Build vendor list for the prompt
                vendor_list = ", ".join(sorted(vendors_seen))

                # Build vendor section from config (or use vendors seen in articles)
                config_vendors = self.tracker_config.get('vendors', [])
                if config_vendors:
                    vendor_section = '\n'.join([f"   - {v}" for v in config_vendors])
                else:
                    vendor_section = '\n'.join([f"   - {v}" for v in sorted(vendors_seen)])

                prompt = f"""You are a cybersecurity specialist. Analyze the following third-party security product updates from the {time_period} and create a comprehensive overview summary.

CRITICAL INSTRUCTION - FOLLOW EXACTLY:
{date_instruction}
Your title MUST be EXACTLY: "{title_format}"
DO NOT use any other date format. The report is for {date_format}.

Vendors covered: {vendor_list}

{articles_text}

Create a structured summary that includes:

1. **Executive Overview** (2-3 sentences)
   - {overview_instruction}
   - Overall theme or focus of recent updates across your security tool portfolio

2. **Featured Updates** (highlighted items)
   - Notable new capabilities announced
   - Significant improvements or enhancements
   - Breaking changes or deprecations that require awareness

3. **New Features & Capabilities**
   - Major new features introduced
   - Enhanced capabilities or improvements
   - Preview features announced

4. **Vendor-Specific Updates** (organized by vendor)
{vendor_section}
   - Other vendors

5. **Performance & Reliability Improvements**
   - Bug fixes and stability improvements
   - Performance enhancements
   - Known issues resolved

6. **Worth Exploring** (optional recommendations)
   - Updates worth reviewing for your environment
   - New features to consider enabling
   - Configuration options to explore

7. **Upcoming Changes & Deprecations**
   - Features being deprecated
   - Timeline for upcoming changes
   - Migration paths if applicable

8. **Key Metrics** (if discernible from articles)
   - Number of new features
   - Number of improvements and fixes
   - Affected vendors/products

Format the summary in clear sections with bullet points. Be specific about version numbers, dates, and availability. This summary should help security administrators quickly understand what's new across their third-party security tools and what updates might be useful for their deployment.

IMPORTANT: Provide ONLY the executive summary content. Do NOT ask follow-up questions, do NOT offer to refine the summary, and do NOT ask if the user wants more details. End your response after completing the summary.
"""

            # Call AI API
            executive_summary = self.ai_client.chat_completion(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a cybersecurity specialist. Create comprehensive, informative summaries of security product updates that help administrators stay current with new features and improvements across their security tool portfolio. Never ask follow-up questions."
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
                'vendors': list(vendors_seen),
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
                'vendors': [],
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

    def create_vendor_summaries(self, articles_by_vendor, time_period="last 30 days"):
        """
        Create executive summaries for each vendor.

        Args:
            articles_by_vendor (dict): Dictionary mapping vendor names to lists of articles
            time_period (str): Time period description

        Returns:
            dict: Dictionary mapping vendor names to HTML summary strings
        """
        vendor_summaries = {}

        for vendor_name, articles in articles_by_vendor.items():
            if not articles or vendor_name == 'Other':
                continue

            try:
                # Generate vendor-specific summary using the existing method
                summary_data = self.create_summary(
                    articles=articles,
                    max_articles=20,
                    time_period=time_period,
                    vendor_focus=vendor_name
                )

                if summary_data and summary_data.get('summary'):
                    # Convert markdown to HTML
                    import markdown
                    from markdown.extensions.tables import TableExtension
                    from markdown.extensions.nl2br import Nl2BrExtension

                    md = markdown.Markdown(extensions=[TableExtension(), Nl2BrExtension()])
                    vendor_summaries[vendor_name] = md.convert(summary_data['summary'])
                    logger.info(f"Generated vendor summary for {vendor_name} ({len(articles)} articles)")

            except Exception as e:
                logger.error(f"Error generating summary for {vendor_name}: {str(e)}")
                continue

        return vendor_summaries
