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

logger = logging.getLogger(__name__)


class LLMNewsSummarizer:
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
            # Build context
            type_context = ""
            if content_type and isinstance(content_type, list):
                type_context = f"\nContent Classification: {', '.join(content_type)}\n"

            provider_context = ""
            if provider:
                provider_context = f"\nProvider: {provider}\n"
            if product:
                provider_context += f"Product: {product}\n"

            prompt = f"""You are an AI/LLM industry analyst helping cybersecurity professionals stay current with AI tool developments. Analyze the following LLM news article and provide a concise, informative summary.

Title: {title}
{provider_context}
Content:
{content[:8000]}
{type_context}

Please provide a structured summary that includes:

1. **What's New**: Clearly identify what was announced, released, or changed
   - Model name, version, or capability affected
   - Key features or improvements

2. **Technical Details**: Important technical information
   - Model specifications (if announced)
   - API changes or new endpoints
   - Performance benchmarks or improvements
   - Pricing changes

3. **Cybersecurity Relevance**: How this affects security professionals
   - New capabilities useful for security work
   - Code analysis or vulnerability detection improvements
   - Potential risks or considerations
   - Integration possibilities with security tools

4. **Action Items**: What users should know or do
   - Availability and access (general, beta, enterprise-only)
   - Migration requirements if applicable
   - Recommended actions

Keep the summary technical and focused on practical implications for cybersecurity professionals using LLMs. Aim for 200-300 words.

CRITICAL ACCURACY RULES:
- ONLY use information explicitly stated in the article content above
- Do NOT invent or guess model version numbers (like GPT-5.1, GPT-4.1)
- Do NOT fabricate statistics, percentages, or pricing unless explicitly stated
- If a detail is not mentioned, say "not specified" or omit it entirely
- Do NOT reference deprecated or outdated API endpoints unless mentioned in the article

IMPORTANT: Provide ONLY the summary content. Do NOT ask follow-up questions, do NOT offer to refine the summary, and do NOT ask if the user wants more details. End your response after completing the summary.
"""

            # Call the AI API
            summary = self.ai_client.chat_completion(
                messages=[
                    {
                        "role": "system",
                        "content": "You are an AI industry analyst specializing in LLM developments. Provide clear, informative summaries that help cybersecurity professionals understand and leverage new AI capabilities. Never ask follow-up questions."
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
            return f"Error generating summary: {str(e)}", "general_update"

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


class LLMNewsExecutiveSummarizer:
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

    def _get_day_suffix(self, day):
        """Get the ordinal suffix for a day number (st, nd, rd, th)."""
        if 10 <= day % 100 <= 20:
            suffix = 'th'
        else:
            suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th')
        return suffix

    def _remove_trailing_questions(self, text):
        """Remove trailing questions that the AI might add at the end of summaries."""
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

            prompt = f"""You are an AI industry analyst helping cybersecurity professionals stay current with LLM developments. Analyze the following LLM news from the {time_period} and create a comprehensive executive summary.

CRITICAL INSTRUCTION - FOLLOW EXACTLY:
The current date is {current_date.strftime('%B %d, %Y')}.
Your title MUST be EXACTLY: "{title_format}"
The report is for {date_format}.

Providers covered: {provider_list}
ARTICLE COUNTS BY PROVIDER: {provider_counts_str}

{articles_text}

Create a structured executive summary that includes:

1. **Executive Overview** (2-3 sentences)
   - {overview_instruction}
   - Key themes across LLM providers

2. **Major Announcements**
   - New model releases
   - Significant capability updates
   - Breaking changes or deprecations

3. **Provider Updates** (organized by provider)
   IMPORTANT: Use the ARTICLE COUNTS BY PROVIDER above to determine which providers have updates.
   If a provider has 0 articles in the counts, say "No updates reported."
   If a provider has 1+ articles, you MUST include their updates from the articles above.

   - **Anthropic Claude**: Recent updates
   - **OpenAI**: Recent updates
   - **Google Gemini**: Recent updates
   - **Meta Llama**: Recent updates
   - **LM Studio**: Recent updates
   - **Mistral AI**: Recent updates
   - **Microsoft Copilot**: Recent updates
   - **Perplexity**: Recent updates
   - **Hugging Face**: Recent updates
   - **Others**: Any other providers (LangChain, Ollama, etc.)

4. **Cybersecurity Relevance**
   - New capabilities useful for security work
   - Code analysis or threat detection improvements
   - Security considerations or risks
   - Integration opportunities

5. **API & Developer Updates**
   - New API endpoints or features
   - SDK updates
   - Rate limit or pricing changes
   - Deprecations to be aware of

6. **Worth Exploring**
   - Features worth trying for security work
   - New capabilities to evaluate
   - Recommended actions

7. **Key Metrics**
   - Number of provider updates
   - Types of announcements (releases, features, etc.)

Format the summary in clear sections with bullet points. Be specific about model names, versions, and dates. This summary should help cybersecurity professionals quickly understand what's new in the LLM landscape and how it might affect their work.

CRITICAL ACCURACY RULES:
- ONLY use information explicitly stated in the article summaries above
- Do NOT invent or guess model version numbers (like GPT-5.1, GPT-4.1, GPT-5.2)
- Do NOT fabricate statistics, percentages, or pricing unless explicitly stated in the articles
- PROVIDER UPDATES ACCURACY: Check the ARTICLE COUNTS BY PROVIDER line above. If a provider shows count > 0, you MUST find and include their updates. If count is 0, say "No updates reported."
- Do NOT reference deprecated or outdated API endpoints unless mentioned in the articles
- If details are not specified in the source material, omit them rather than guessing

IMPORTANT: Provide ONLY the executive summary content. Do NOT ask follow-up questions, do NOT offer to refine the summary, and do NOT ask if the user wants more details. End your response after completing the summary.
"""

            # Call AI API
            executive_summary = self.ai_client.chat_completion(
                messages=[
                    {
                        "role": "system",
                        "content": "You are an AI industry analyst specializing in LLM developments. Create comprehensive, informative summaries that help cybersecurity professionals stay current with AI capabilities and integrate them into their security work. Never ask follow-up questions."
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

            prompt = f"""You are an AI industry analyst. Create a brief 2-4 sentence summary of {provider_name}'s updates from the {time_period}.

Provider: {provider_name}
Number of updates: {len(articles)}

Articles:
{articles_text}

Write a concise summary highlighting:
- Key releases or announcements
- Most important changes for users
- Any security-relevant updates

Keep it to 2-4 sentences maximum. Be specific about model names and features. Focus on what matters most to cybersecurity professionals.

CRITICAL: Only use information from the articles above. Do NOT invent version numbers, statistics, or details not mentioned. If something is unclear, omit it.

IMPORTANT: Provide ONLY the summary. No introductions, no questions, no offers to elaborate."""

            # Call AI API
            summary = self.ai_client.chat_completion(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a concise AI industry analyst. Provide brief, informative summaries without any follow-up questions or offers to elaborate."
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
