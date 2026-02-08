"""
Microsoft Security Product reporting module.
Handles generation of daily security product update reports optimized for cybersecurity engineers.
"""

import os
import logging
import re
from datetime import datetime
import markdown
from markdown.extensions.tables import TableExtension
from markdown.extensions.nl2br import Nl2BrExtension
from jinja2 import Environment, FileSystemLoader, select_autoescape
from collections import defaultdict

logger = logging.getLogger(__name__)

class MicrosoftSecurityReportGenerator:
    """Generates Microsoft Security Product update reports for product updates and features"""

    LAST_REPORT_FILE = '.last_report_time'

    def __init__(self, template_dir=None, ai_config=None):
        """
        Initialize the Microsoft Security Product report generator.

        Args:
            template_dir (str, optional): Directory containing report templates
            ai_config (dict, optional): AI configuration for model attribution
        """
        # If template_dir not provided, use module directory's templates subfolder
        if template_dir is None:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            template_dir = os.path.join(current_dir, 'templates')

        # Ensure template directory exists
        os.makedirs(template_dir, exist_ok=True)

        # Initialize Jinja2 environment
        self.env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=select_autoescape(['html', 'xml'])
        )

        # Store AI config for model attribution in reports
        self.ai_config = ai_config

    def _get_ai_model_attribution(self):
        """
        Generate AI model attribution string for reports.

        Returns:
            dict: Dictionary with model name, provider type, and formatted display string
        """
        if not self.ai_config:
            return {
                'model_name': 'Unknown',
                'provider_type': 'Unknown',
                'display': 'AI Model: Unknown'
            }

        provider = self.ai_config.get('provider', 'unknown').lower()

        if provider == 'lmstudio':
            lm_config = self.ai_config.get('lmstudio', {})
            model_name = lm_config.get('model', 'local-model')
            return {
                'model_name': model_name,
                'provider_type': 'Local',
                'display': f'AI Model: {model_name} (Local - LM Studio)'
            }
        elif provider == 'claude':
            claude_config = self.ai_config.get('claude', {})
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

    def _remove_trailing_questions(self, text):
        """
        Remove trailing questions that the AI might have added at the end of summaries.

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

    def _prepare_articles(self, articles):
        """
        Prepare articles for reporting (no filtering, all updates included).

        Args:
            articles (list): List of article dictionaries

        Returns:
            list: All articles (unfiltered)
        """
        # Previously filtered vulnerability-related articles, but now we include all updates
        # since these are product updates, not security threats
        logger.info(f"Processing {len(articles)} security product updates for report")

        # Add source type, preview, and availability status to each article
        for article in articles:
            # Clean any trailing questions from AI-generated summaries
            if 'summary' in article and article['summary']:
                article['summary'] = self._remove_trailing_questions(article['summary'])

            article['source_type'] = self._get_source_type(article.get('source', ''))
            article['preview'] = self._extract_preview(article.get('summary', ''))
            article['availability'] = self._detect_availability(article)

        return articles

    def _detect_availability(self, article):
        """
        Detect the availability status of a feature/update from article content.

        Args:
            article (dict): Article dictionary

        Returns:
            dict: Availability info with 'status', 'label', and 'color'
        """
        title = article.get('title', '').lower()
        summary = article.get('summary', '').lower()
        content = article.get('content', '').lower()
        combined = f"{title} {summary} {content}"

        # Check for deprecated/retiring features
        # First check for negative phrases (mentions that nothing is deprecated)
        negative_deprecation_phrases = [
            'no deprecated', 'not deprecated', 'none deprecated',
            'no breaking changes', 'none identified',
            'no end of support', 'not retiring', 'not sunset'
        ]

        # Check for positive deprecation indicators
        positive_deprecation_phrases = [
            'will be deprecated', 'is deprecated', 'are deprecated',
            'being deprecated', 'has been deprecated', 'have been deprecated',
            'deprecating this', 'deprecating the', 'feature deprecated',
            'is retiring', 'will retire', 'being retired',
            'end of support on', 'end of support for', 'support ends',
            'will sunset', 'is sunset', 'being sunset',
            'no longer supported as of', 'no longer available as of'
        ]

        # Exclude "What's New" articles from deprecation detection (they're about new features, not deprecations)
        whats_new_indicators = ["what's new", "whats new", "what is new", "new in"]
        is_whats_new_article = any(indicator in title for indicator in whats_new_indicators)

        # Only flag as deprecated if positive phrases exist AND negative phrases don't dominate
        # AND it's not a "What's New" article
        has_negative = any(phrase in combined for phrase in negative_deprecation_phrases)
        has_positive = any(phrase in combined for phrase in positive_deprecation_phrases)

        if has_positive and not has_negative and not is_whats_new_article:
            return {
                'status': 'deprecated',
                'label': 'Deprecated',
                'color': '#d13438'  # Red
            }

        # Check for preview features
        preview_keywords = ['preview', 'beta', 'public preview', 'private preview', 'coming soon', 'in development']
        ga_keywords = ['generally available', 'now available', 'ga release', 'general availability', 'rolling out', 'launched']

        has_preview = any(keyword in combined for keyword in preview_keywords)
        has_ga = any(keyword in combined for keyword in ga_keywords)

        # If both mentioned, check which is more prominent (GA takes precedence if explicit)
        if has_ga and 'generally available' in combined:
            return {
                'status': 'ga',
                'label': 'GA',
                'color': '#107c10'  # Green
            }
        elif has_preview and not has_ga:
            return {
                'status': 'preview',
                'label': 'Preview',
                'color': '#ffb900'  # Yellow/Orange
            }
        elif has_ga:
            return {
                'status': 'ga',
                'label': 'GA',
                'color': '#107c10'  # Green
            }

        # Default - no specific status detected
        return None

    def _detect_licensing(self, article):
        """
        Detect licensing requirements from article content.

        Args:
            article (dict): Article dictionary

        Returns:
            str: License tier or None
        """
        title = article.get('title', '').lower()
        summary = article.get('summary', '').lower()
        content = article.get('content', '').lower()
        combined = f"{title} {summary} {content}"

        # Check for specific license mentions
        if any(keyword in combined for keyword in ['microsoft 365 e5', 'm365 e5', 'e5 license', 'e5 required']):
            return 'E5'
        elif any(keyword in combined for keyword in ['microsoft 365 e3', 'm365 e3', 'e3 license']):
            return 'E3'
        elif any(keyword in combined for keyword in ['security copilot', 'copilot license']):
            return 'Copilot'
        elif any(keyword in combined for keyword in ['entra premium', 'entra id premium', 'p1 license', 'p2 license']):
            return 'Entra Premium'
        elif any(keyword in combined for keyword in ['intune license', 'endpoint manager license']):
            return 'Intune License'
        elif any(keyword in combined for keyword in ['add-on', 'additional license', 'separate license']):
            return 'Add-on'
        elif any(keyword in combined for keyword in ['included', 'no additional', 'all customers', 'all users']):
            return 'Included'

        return None

    def _calculate_priority(self, article):
        """
        Calculate priority score for an article based on security impact and urgency.

        Priority Levels:
        - CRITICAL: Security patches, breaking changes, imminent deprecated features
        - HIGH: GA releases of security features, compliance updates, deprecations with timeline
        - MEDIUM: Preview security features, enhancements, general updates
        - LOW: Blog posts, general announcements, minor updates

        Args:
            article (dict): Article dictionary

        Returns:
            dict: Priority information with level, score, and reasoning
        """
        title = article.get('title', '').lower()
        summary = article.get('summary', '').lower()
        content = article.get('content', '').lower()
        combined = f"{title} {summary} {content}"

        priority_score = 0
        reasons = []

        # CRITICAL indicators (highest priority)
        critical_keywords = [
            'security patch', 'security update', 'vulnerability', 'cve-', 'exploit',
            'critical security', 'zero-day', 'security advisory',
            'immediate action', 'action required', 'urgent',
            'breaking change', 'breaking changes',
            'deprecated.*january|february|march', 'end of support.*202[5-6]',
            'retirement.*202[5-6]', 'migration required'
        ]

        for keyword in critical_keywords:
            if re.search(keyword, combined):
                priority_score += 100
                reasons.append(f"Critical: {keyword.replace('.*', ' ')}")
                break  # One critical indicator is enough

        # HIGH priority indicators
        high_keywords = [
            'generally available.*security', 'ga.*security feature',
            'compliance', 'regulatory', 'audit',
            'will be deprecated', 'being deprecated', 'deprecation',
            'new security', 'security capability',
            'authentication', 'authorization', 'access control',
            'encryption', 'threat protection', 'malware',
            'conditional access', 'zero trust',
            'data loss prevention', 'dlp', 'information protection'
        ]

        for keyword in high_keywords:
            if re.search(keyword, combined):
                priority_score += 50
                reasons.append(f"High: {keyword.replace('.*', ' ')}")
                break

        # MEDIUM priority indicators
        medium_keywords = [
            'preview.*security', 'public preview', 'private preview',
            'enhancement', 'improvement', 'update',
            'new feature', 'capability',
            'integration', 'configuration'
        ]

        for keyword in medium_keywords:
            if re.search(keyword, combined):
                priority_score += 25
                reasons.append(f"Medium: {keyword.replace('.*', ' ')}")
                break

        # Additional scoring factors

        # Check availability status
        status = self._detect_availability(article)
        if status:
            if status['status'] == 'deprecated':
                priority_score += 75
                reasons.append("Deprecated feature")
            elif status['status'] == 'ga':
                priority_score += 30
                reasons.append("Generally Available")
            elif status['status'] == 'preview':
                priority_score += 15
                reasons.append("Preview feature")

        # Security-related products get priority boost
        security_products = [
            'defender', 'sentinel', 'entra', 'purview',
            'security copilot', 'intune', 'endpoint'
        ]
        if any(product in combined for product in security_products):
            priority_score += 10
            reasons.append("Security product")

        # Determine priority level
        if priority_score >= 100:
            level = 'CRITICAL'
            color = '#d13438'  # Red
        elif priority_score >= 50:
            level = 'HIGH'
            color = '#ff8c00'  # Dark Orange
        elif priority_score >= 25:
            level = 'MEDIUM'
            color = '#ffb900'  # Yellow
        else:
            level = 'LOW'
            color = '#5c5c5c'  # Gray

        return {
            'level': level,
            'score': priority_score,
            'color': color,
            'reasons': reasons[:2]  # Keep top 2 reasons
        }

    def _build_licensing_summary(self, articles):
        """
        Build a summary of licensing requirements across all articles.

        Args:
            articles (list): List of article dictionaries

        Returns:
            dict: Licensing summary with counts and article titles
        """
        licensing = {
            'E5': [],
            'E3': [],
            'Entra Premium': [],
            'Intune License': [],
            'Copilot': [],
            'Add-on': [],
            'Included': []
        }

        for article in articles:
            license_tier = self._detect_licensing(article)
            if license_tier and license_tier in licensing:
                licensing[license_tier].append(article.get('title', 'Unknown'))

        # Remove empty tiers
        return {k: v for k, v in licensing.items() if v}

    def _generate_product_summary(self, product_name, articles):
        """
        Generate a concise executive summary for a specific product's updates.

        Args:
            product_name (str): Name of the product
            articles (list): List of articles for this product

        Returns:
            dict: Product summary with key metrics and narrative
        """
        if not articles:
            return None

        # Calculate metrics
        total_updates = len(articles)

        # Priority breakdown
        priority_counts = {'CRITICAL': 0, 'HIGH': 0, 'MEDIUM': 0, 'LOW': 0}
        for article in articles:
            if 'priority' in article:
                priority_counts[article['priority']['level']] += 1

        # Availability breakdown
        ga_count = sum(1 for a in articles if a.get('availability') and a.get('availability').get('status') == 'ga')
        preview_count = sum(1 for a in articles if a.get('availability') and a.get('availability').get('status') == 'preview')
        deprecated_count = sum(1 for a in articles if a.get('availability') and a.get('availability').get('status') == 'deprecated')

        # Extract key themes from titles
        all_titles = ' '.join([a.get('title', '') for a in articles]).lower()

        themes = []
        if 'security' in all_titles or 'threat' in all_titles or 'protection' in all_titles:
            themes.append('security enhancements')
        if 'authentication' in all_titles or 'sign-in' in all_titles or 'mfa' in all_titles:
            themes.append('authentication improvements')
        if 'compliance' in all_titles or 'governance' in all_titles:
            themes.append('compliance updates')
        if 'ai' in all_titles or 'copilot' in all_titles or 'intelligence' in all_titles:
            themes.append('AI capabilities')
        if 'integration' in all_titles:
            themes.append('integrations')
        if 'preview' in all_titles:
            themes.append('preview features')
        if 'generally available' in all_titles or 'now available' in all_titles:
            themes.append('GA releases')

        # Build narrative summary
        narrative_parts = []
        narrative_parts.append(f"{total_updates} update{'s' if total_updates != 1 else ''}")

        if priority_counts['CRITICAL'] > 0:
            narrative_parts.append(f"{priority_counts['CRITICAL']} critical")
        if priority_counts['HIGH'] > 0:
            narrative_parts.append(f"{priority_counts['HIGH']} high priority")

        if themes:
            narrative_parts.append(f"focusing on {', '.join(themes[:3])}")

        if ga_count > 0:
            narrative_parts.append(f"{ga_count} GA release{'s' if ga_count != 1 else ''}")
        if deprecated_count > 0:
            narrative_parts.append(f"⚠️ {deprecated_count} deprecation{'s' if deprecated_count != 1 else ''}")

        narrative = ' | '.join(narrative_parts)

        return {
            'product_name': product_name,
            'total_updates': total_updates,
            'priority_counts': priority_counts,
            'ga_count': ga_count,
            'preview_count': preview_count,
            'deprecated_count': deprecated_count,
            'themes': themes,
            'narrative': narrative,
            'top_articles': articles[:3]  # Top 3 most important
        }

    def _extract_preview(self, summary, max_sentences=2, max_chars=200):
        """
        Extract a short preview from the article summary.

        Args:
            summary (str): Full article summary
            max_sentences (int): Maximum number of sentences
            max_chars (int): Maximum character length

        Returns:
            str: Short preview text
        """
        if not summary:
            return ''

        # Remove markdown formatting for cleaner preview
        clean_text = summary

        # Remove markdown tables (lines with pipes)
        clean_text = re.sub(r'^\|.*\|$', '', clean_text, flags=re.MULTILINE)
        # Remove table separator lines
        clean_text = re.sub(r'^[\s]*[-|:]+[\s]*$', '', clean_text, flags=re.MULTILINE)
        # Remove headers
        clean_text = re.sub(r'^#+\s+.*$', '', clean_text, flags=re.MULTILINE)
        # Remove bold/italic markers
        clean_text = re.sub(r'\*+([^*]+)\*+', r'\1', clean_text)
        # Remove bullet points
        clean_text = re.sub(r'^[\s]*[-*•]\s+', '', clean_text, flags=re.MULTILINE)
        # Remove numbered lists
        clean_text = re.sub(r'^[\s]*\d+\.\s+', '', clean_text, flags=re.MULTILINE)
        # Remove horizontal rules
        clean_text = re.sub(r'^---+$', '', clean_text, flags=re.MULTILINE)
        # Remove code blocks
        clean_text = re.sub(r'```[\s\S]*?```', '', clean_text)
        # Remove inline code
        clean_text = re.sub(r'`[^`]+`', '', clean_text)
        # Remove extra whitespace
        clean_text = ' '.join(clean_text.split())

        if not clean_text:
            return ''

        # Split into sentences
        sentences = re.split(r'(?<=[.!?])\s+', clean_text)

        # Take first N sentences
        preview_sentences = sentences[:max_sentences]
        preview = ' '.join(preview_sentences)

        # Truncate if too long
        if len(preview) > max_chars:
            preview = preview[:max_chars].rsplit(' ', 1)[0] + '...'

        return preview.strip()

    def _get_source_type(self, source_name):
        """
        Classify the source into a type for display purposes.

        Args:
            source_name (str): Name of the source

        Returns:
            dict: Source type info with 'type', 'label', and 'color'
        """
        source_lower = source_name.lower()

        # Official Microsoft Learn documentation (What's New pages)
        if "what's new" in source_lower or "whats new" in source_lower or "release notes" in source_lower:
            return {
                'type': 'documentation',
                'label': 'Official Docs',
                'color': '#0078d4'  # Microsoft blue
            }

        # Microsoft Security Blog
        if 'microsoft security blog' in source_lower or 'security blog' in source_lower:
            return {
                'type': 'blog',
                'label': 'MS Security Blog',
                'color': '#107c10'  # Green
            }

        # Tech Community blogs (official announcements)
        if 'tech community' in source_lower:
            return {
                'type': 'announcement',
                'label': 'Tech Community',
                'color': '#5c2d91'  # Purple
            }

        # 3rd party sources
        if any(third_party in source_lower for third_party in ['jeffrey appel', 'appel']):
            return {
                'type': 'third_party',
                'label': '3rd Party',
                'color': '#ff8c00'  # Orange
            }

        # Default
        return {
            'type': 'other',
            'label': 'Other',
            'color': '#666666'  # Gray
        }

    def _categorize_by_product(self, articles):
        """
        Categorize articles by Microsoft Defender Product using source field mapping.

        Args:
            articles (list): List of article dictionaries

        Returns:
            dict: Articles organized by product (ordered dict with primary products first)
        """
        # Define primary Defender products in the order they should appear
        primary_products = [
            'Defender XDR',
            'Defender for Endpoint',
            'Defender for Office 365',
            'Defender for Identity',
            'Defender for Cloud Apps',
            'Defender Vulnerability Management',
            'Defender Threat Intelligence',
            'Microsoft Sentinel',
            'Microsoft Security Copilot',
            '3rd Party Defender Information',
            'Other Defender Related Security Updates'
        ]

        # Initialize all primary products with empty lists
        products = {product: [] for product in primary_products}

        # Map source names to product categories (most accurate method)
        # These match the exact source names from config_defender.yaml
        source_mapping = {
            # Defender XDR (Microsoft 365 Defender)
            'Defender XDR What\'s New': 'Defender XDR',
            "Defender XDR What's New": 'Defender XDR',
            'Tech Community - Defender XDR Blog': 'Defender XDR',
            'Tech Community - Microsoft 365 Defender Blog': 'Defender XDR',

            # Defender for Endpoint
            'Defender for Endpoint What\'s New': 'Defender for Endpoint',
            "Defender for Endpoint What's New": 'Defender for Endpoint',
            'Tech Community - Defender for Endpoint Blog': 'Defender for Endpoint',

            # Defender for Office 365
            'Defender for Office 365 What\'s New': 'Defender for Office 365',
            "Defender for Office 365 What's New": 'Defender for Office 365',
            'Tech Community - Defender for Office 365 Blog': 'Defender for Office 365',

            # Defender for Identity
            'Defender for Identity What\'s New': 'Defender for Identity',
            "Defender for Identity What's New": 'Defender for Identity',

            # Defender for Cloud Apps
            'Defender for Cloud Apps Release Notes': 'Defender for Cloud Apps',
            'Tech Community - Defender for Cloud Apps Blog': 'Defender for Cloud Apps',
            'Tech Community - Microsoft Defender for Cloud Blog': 'Defender for Cloud Apps',

            # Defender Vulnerability Management
            'Defender Vulnerability Management What\'s New': 'Defender Vulnerability Management',
            "Defender Vulnerability Management What's New": 'Defender Vulnerability Management',
            'Tech Community - Defender Vulnerability Management Blog': 'Defender Vulnerability Management',

            # Defender Threat Intelligence
            'Tech Community - Defender Threat Intelligence Blog': 'Defender Threat Intelligence',

            # Microsoft Sentinel
            'Microsoft Sentinel What\'s New': 'Microsoft Sentinel',
            "Microsoft Sentinel What's New": 'Microsoft Sentinel',
            'Tech Community - Microsoft Sentinel Blog': 'Microsoft Sentinel',

            # Security Copilot
            'Tech Community - Security Copilot Blog': 'Microsoft Security Copilot',

            # 3rd Party Sources
            'Jeffrey Appel Blog': '3rd Party Defender Information',
        }

        for article in articles:
            source = article.get('source', '')
            title = article.get('title', '')

            # Try to categorize by source first (most accurate)
            categorized = False

            # Check if source matches any known source mapping
            if source in source_mapping:
                product = source_mapping[source]
                products[product].append(article)
                categorized = True
                logger.debug(f"Mapped '{source}' -> '{product}': {title[:50]}...")
            # Check if source contains "Microsoft Security Blog" or "Tech Community"
            elif 'Microsoft Security Blog' in source or 'security blog' in source.lower() or 'Tech Community' in source:
                # For Tech Community articles, try to categorize by content keywords
                if 'Tech Community' in source:
                    # Try to categorize by title/content keywords
                    title_lower = title.lower()
                    content_lower = article.get('content', '').lower()
                    combined = f"{title_lower} {content_lower}"

                    if 'defender xdr' in combined or 'm365 defender' in combined or 'microsoft 365 defender' in combined:
                        products['Defender XDR'].append(article)
                        categorized = True
                        logger.debug(f"Mapped Tech Community (XDR) -> 'Defender XDR': {title[:50]}...")
                    elif 'defender for endpoint' in combined or 'mde' in combined:
                        products['Defender for Endpoint'].append(article)
                        categorized = True
                        logger.debug(f"Mapped Tech Community (Endpoint) -> 'Defender for Endpoint': {title[:50]}...")
                    elif 'defender for office' in combined or 'mdo' in combined:
                        products['Defender for Office 365'].append(article)
                        categorized = True
                        logger.debug(f"Mapped Tech Community (Office) -> 'Defender for Office 365': {title[:50]}...")
                    elif 'defender for identity' in combined or 'mdi' in combined:
                        products['Defender for Identity'].append(article)
                        categorized = True
                        logger.debug(f"Mapped Tech Community (Identity) -> 'Defender for Identity': {title[:50]}...")
                    elif 'defender for cloud apps' in combined or 'mcas' in combined or 'cloud app security' in combined:
                        products['Defender for Cloud Apps'].append(article)
                        categorized = True
                        logger.debug(f"Mapped Tech Community (Cloud Apps) -> 'Defender for Cloud Apps': {title[:50]}...")
                    elif 'vulnerability management' in combined or 'tvm' in combined or 'threat and vulnerability' in combined:
                        products['Defender Vulnerability Management'].append(article)
                        categorized = True
                        logger.debug(f"Mapped Tech Community (Vuln Mgmt) -> 'Defender Vulnerability Management': {title[:50]}...")
                    elif 'threat intelligence' in combined and 'defender' in combined:
                        products['Defender Threat Intelligence'].append(article)
                        categorized = True
                        logger.debug(f"Mapped Tech Community (Threat Intel) -> 'Defender Threat Intelligence': {title[:50]}...")
                    elif 'sentinel' in combined:
                        products['Microsoft Sentinel'].append(article)
                        categorized = True
                        logger.debug(f"Mapped Tech Community (Sentinel) -> 'Microsoft Sentinel': {title[:50]}...")
                    elif 'copilot' in combined and 'security' in combined:
                        products['Microsoft Security Copilot'].append(article)
                        categorized = True
                        logger.debug(f"Mapped Tech Community (Copilot) -> 'Microsoft Security Copilot': {title[:50]}...")

                # If Tech Community article wasn't categorized or it's from Security Blog, put in Other
                if not categorized:
                    products['Other Defender Related Security Updates'].append(article)
                    categorized = True
                    logger.debug(f"Mapped '{source}' -> 'Other Defender Related Security Updates': {title[:50]}...")
            # Check if source contains "Microsoft Security Blog"
            elif 'Microsoft Security Blog' in source or 'security blog' in source.lower():
                products['Other Defender Related Security Updates'].append(article)
                categorized = True
                logger.debug(f"Mapped Security Blog -> 'Other Defender Related Security Updates': {title[:50]}...")
            else:
                # Fallback: try to match source name with product keywords
                source_lower = source.lower()

                if 'xdr' in source_lower or 'm365 defender' in source_lower or 'microsoft 365 defender' in source_lower:
                    products['Defender XDR'].append(article)
                    categorized = True
                elif 'endpoint' in source_lower:
                    products['Defender for Endpoint'].append(article)
                    categorized = True
                elif 'office 365' in source_lower or 'office365' in source_lower:
                    products['Defender for Office 365'].append(article)
                    categorized = True
                elif 'identity' in source_lower:
                    products['Defender for Identity'].append(article)
                    categorized = True
                elif 'cloud apps' in source_lower or 'cloud app security' in source_lower:
                    products['Defender for Cloud Apps'].append(article)
                    categorized = True
                elif 'vulnerability' in source_lower:
                    products['Defender Vulnerability Management'].append(article)
                    categorized = True
                elif 'threat intelligence' in source_lower:
                    products['Defender Threat Intelligence'].append(article)
                    categorized = True
                elif 'sentinel' in source_lower:
                    products['Microsoft Sentinel'].append(article)
                    categorized = True
                elif 'copilot' in source_lower:
                    products['Microsoft Security Copilot'].append(article)
                    categorized = True
                elif 'appel' in source_lower or '3rd party' in source_lower:
                    products['3rd Party Defender Information'].append(article)
                    categorized = True

            # If still not categorized, put in "Other" category
            if not categorized:
                products['Other Defender Related Security Updates'].append(article)
                logger.debug(f"Uncategorized source '{source}' -> 'Other Defender Related Security Updates': {title[:50]}...")

        # Log categorization summary
        logger.info("Article categorization summary:")
        for product_name in primary_products:
            count = len(products[product_name])
            if count > 0:
                logger.info(f"  {product_name}: {count} article(s)")

        # Always include all primary products (even if they have 0 updates)
        final_products = {}

        # Add all primary products (even if empty)
        for product in primary_products:
            final_products[product] = self._sort_articles_by_date(products[product])

        return final_products

    def _sort_articles_by_date(self, articles):
        """
        Sort articles by published_date in descending order (newest first).

        Args:
            articles (list): List of article dictionaries

        Returns:
            list: Sorted articles
        """
        def get_sort_date(article):
            """Extract a sortable date from the article."""
            date_str = article.get('published_date', '')
            if not date_str:
                # No date, sort to the end
                return '0000-00-00'

            try:
                # Handle ISO format with time
                if 'T' in date_str or '+' in date_str:
                    from datetime import datetime
                    dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    return dt.strftime('%Y-%m-%d')
                # Already in YYYY-MM-DD format
                elif len(date_str) >= 10 and date_str[4] == '-':
                    return date_str[:10]
                else:
                    return date_str
            except:
                return '0000-00-00'

        return sorted(articles, key=get_sort_date, reverse=True)

    def _calculate_stats(self, articles):
        """
        Calculate statistics from articles - counts unique articles per category.
        Uses direct content analysis with specific keywords for accuracy.

        Args:
            articles (list): List of article dictionaries

        Returns:
            dict: Statistics dictionary with unique article counts
        """
        # Use sets to track unique articles per category
        stats_sets = {
            'new_features': set(),
            'bug_fixes': set(),
            'performance_improvements': set(),
            'integrations': set(),
            'platform_updates': set()
        }

        # Define specific keyword patterns for each stat category
        stat_keywords = {
            'new_features': ['new feature', 'introducing', 'now available', 'new capability', 'announcing', 'launched', 'rolling out', 'general availability', 'now supports'],
            'bug_fixes': ['bug fix', 'fixed issue', 'resolved issue', 'fixes a bug', 'addresses issue', 'issue resolved', 'problem fixed'],
            'performance_improvements': ['performance improvement', 'performance enhancement', 'faster performance', 'improved performance', 'speed improvement', 'latency reduction', 'optimization'],
            'integrations': ['new integration', 'integrates with', 'integration with', 'now works with', 'connector for', 'connect to', 'interoperability'],
            'platform_updates': ['platform update', 'version update', 'agent update', 'client update', 'sensor update', 'engine update']
        }

        for idx, article in enumerate(articles):
            # Combine title and content for keyword matching
            title = article.get('title', '').lower()
            content = article.get('content', '').lower()
            summary = article.get('summary', '').lower()
            combined_text = f"{title} {content} {summary}"

            # Check each category for keyword matches
            for category, keywords in stat_keywords.items():
                if any(keyword in combined_text for keyword in keywords):
                    stats_sets[category].add(idx)

        # Convert sets to counts
        stats = {key: len(value) for key, value in stats_sets.items()}

        return stats


    def _clean_action_item(self, text):
        """
        Clean and format an action item text.

        Args:
            text (str): Raw action item text

        Returns:
            str: Cleaned action item
        """
        if not text:
            return ""

        # Remove markdown table syntax
        if '|' in text:
            # If it's mostly table syntax, skip it
            if text.count('|') > 3:
                return ""

        # Clean markdown formatting
        text = self._clean_markdown(text)

        # Remove common prefixes that leak through
        text = re.sub(r'^\s*(?:Action\s+Items?|Timeline|Priority|When|Where|Who)[:\s]+', '', text, flags=re.IGNORECASE)

        # Remove incomplete sentences at the start
        text = re.sub(r'^\s*(?:that|which|for|to|the|a|an)\s+', '', text, flags=re.IGNORECASE)

        # Clean up whitespace
        text = re.sub(r'\s+', ' ', text).strip()

        # Capitalize first letter
        if text:
            text = text[0].upper() + text[1:]

        # Ensure it ends with punctuation
        if text and text[-1] not in '.!?':
            text += '.'

        return text

    def _truncate_action_item(self, text, max_length):
        """
        Truncate action item text intelligently at sentence or word boundaries.

        Args:
            text (str): Action item text
            max_length (int): Maximum character length

        Returns:
            str: Truncated text with proper ending
        """
        if not text or len(text) <= max_length:
            return text

        # Try to find a sentence boundary within the limit
        truncated = text[:max_length]

        # Look for sentence endings (.!?) working backwards
        for i in range(len(truncated) - 1, max(0, len(truncated) - 50), -1):
            if truncated[i] in '.!?':
                return truncated[:i + 1]

        # No sentence boundary found - truncate at last complete word
        # Find the last space
        last_space = truncated.rfind(' ')
        if last_space > max_length * 0.6:  # At least 60% of max length
            truncated = truncated[:last_space]

        # Don't end with punctuation that suggests continuation
        while truncated and truncated[-1] in '(,-–:;':
            truncated = truncated[:-1].rstrip()

        return truncated.rstrip() + '...'

    def _is_valid_action_item(self, text):
        """
        Validate if text is a meaningful action item.

        Args:
            text (str): Action item text

        Returns:
            bool: True if valid action item
        """
        if not text or len(text) < 20:
            return False

        # Skip if it's mostly table syntax or formatting
        if text.count('|') > 2 or text.count('-') > 5:
            return False

        # Skip if it contains table separators
        if re.match(r'^[\s\-|:]+$', text):
            return False

        # Skip generic review statements
        if re.match(r'^Review\s+critical\s+update:', text):
            return False

        # Skip informational statements (not actions)
        informational_patterns = [
            r'^Can\s+Use\s+It\??',  # "Can Use It?" statements
            r'^Availability\s*[-–:]',  # Availability info
            r'^No\s+Breaking\s+Changes',  # Informational
            r'^Limitations?:',  # Limitations info
            r'^Future\s+Updates?:',  # Future info
            r'^Most\s+features\s+are',  # Informational
            r'^\w+\s+is\s+(GA|preview|available)',  # Status statements
        ]

        for pattern in informational_patterns:
            if re.match(pattern, text, re.IGNORECASE):
                return False

        # Must have at least a few words
        if len(text.split()) < 4:
            return False

        # Should have some actionable content
        actionable_keywords = [
            'enable', 'disable', 'configure', 'deploy', 'upgrade', 'migrate',
            'verify', 'check', 'ensure', 'review', 'update', 'install',
            'test', 'validate', 'monitor', 'plan', 'audit', 'assess',
            'should', 'must', 'need', 'required', 'recommend'
        ]

        text_lower = text.lower()
        has_action = any(keyword in text_lower for keyword in actionable_keywords)

        return has_action

    def _calculate_days_ago(self, date_str):
        """
        Calculate days ago from a date string.

        Args:
            date_str (str): Date string in format YYYY-MM-DD or other parseable format

        Returns:
            int: Number of days ago (None if unparseable)
        """
        if not date_str:
            return None

        try:
            # Try parsing as YYYY-MM-DD
            if isinstance(date_str, str):
                if 'T' in date_str or '+' in date_str:
                    # ISO format with time
                    pub_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                else:
                    # Simple date format
                    pub_date = datetime.strptime(date_str[:10], '%Y-%m-%d')
            else:
                return None

            # Calculate days ago
            today = datetime.now()
            if pub_date.tzinfo:
                # Make today timezone-aware if pub_date has timezone
                from datetime import timezone
                today = datetime.now(timezone.utc)

            delta = today - pub_date
            return delta.days

        except (ValueError, AttributeError):
            return None

    def _get_last_report_time(self, output_dir):
        """
        Get the timestamp of the last report generation.

        Args:
            output_dir (str): Report output directory

        Returns:
            datetime: Last report time (None if no previous report)
        """
        try:
            last_report_file = os.path.join(output_dir, self.LAST_REPORT_FILE)
            if os.path.exists(last_report_file):
                with open(last_report_file, 'r') as f:
                    timestamp_str = f.read().strip()
                    return datetime.fromisoformat(timestamp_str)
        except Exception as e:
            logger.debug(f"Could not read last report time: {e}")
        return None

    def _save_report_time(self, output_dir):
        """
        Save the current timestamp as the last report generation time.

        Args:
            output_dir (str): Report output directory
        """
        try:
            last_report_file = os.path.join(output_dir, self.LAST_REPORT_FILE)
            with open(last_report_file, 'w') as f:
                f.write(datetime.now().isoformat())
            logger.debug(f"Saved report generation time to {last_report_file}")
        except Exception as e:
            logger.warning(f"Could not save report time: {e}")

    def _identify_new_articles(self, articles, last_report_time):
        """
        Identify articles that are new since the last report.

        Args:
            articles (list): List of article dictionaries
            last_report_time (datetime): Timestamp of last report (None if first run)

        Returns:
            tuple: (new_articles, existing_articles, new_count, existing_count)
        """
        if last_report_time is None:
            # First report - all articles are "new"
            return articles, [], len(articles), 0

        new_articles = []
        existing_articles = []

        for article in articles:
            scraped_date_str = article.get('scraped_date', '')
            if scraped_date_str:
                try:
                    # Parse scraped_date (format: YYYY-MM-DD HH:MM:SS or similar)
                    if isinstance(scraped_date_str, str):
                        # Try ISO format first
                        if 'T' in scraped_date_str or '+' in scraped_date_str:
                            scraped_date = datetime.fromisoformat(scraped_date_str.replace('Z', '+00:00'))
                        else:
                            # Try common formats
                            for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d']:
                                try:
                                    scraped_date = datetime.strptime(scraped_date_str, fmt)
                                    break
                                except ValueError:
                                    continue
                            else:
                                # Couldn't parse, treat as existing
                                existing_articles.append(article)
                                continue
                    else:
                        existing_articles.append(article)
                        continue

                    # Make timezone-naive for comparison if needed
                    if scraped_date.tzinfo and not last_report_time.tzinfo:
                        scraped_date = scraped_date.replace(tzinfo=None)
                    elif not scraped_date.tzinfo and last_report_time.tzinfo:
                        last_report_time = last_report_time.replace(tzinfo=None)

                    # Compare dates
                    if scraped_date > last_report_time:
                        article['is_new_since_last_report'] = True
                        new_articles.append(article)
                    else:
                        article['is_new_since_last_report'] = False
                        existing_articles.append(article)

                except Exception as e:
                    logger.debug(f"Could not parse scraped_date '{scraped_date_str}': {e}")
                    existing_articles.append(article)
            else:
                # No scraped date, treat as existing
                existing_articles.append(article)

        return new_articles, existing_articles, len(new_articles), len(existing_articles)

    def _format_date_with_age(self, date_str, days_ago=None):
        """
        Format a date string with age indicator.

        Args:
            date_str (str): Date string
            days_ago (int): Days ago (calculated if None)

        Returns:
            dict: Dictionary with formatted_date, days_ago, age_category
        """
        if not date_str:
            return {
                'formatted_date': 'Date unknown',
                'days_ago': None,
                'age_category': 'unknown'
            }

        # Calculate days ago if not provided
        if days_ago is None:
            days_ago = self._calculate_days_ago(date_str)

        # Format the date nicely
        try:
            if 'T' in date_str or '+' in date_str:
                pub_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            else:
                pub_date = datetime.strptime(date_str[:10], '%Y-%m-%d')
            formatted_date = pub_date.strftime('%b %d, %Y')
        except:
            formatted_date = date_str[:10] if len(date_str) >= 10 else date_str

        # Determine age category
        if days_ago is None:
            age_category = 'unknown'
            age_text = 'Date unknown'
        elif days_ago == 0:
            age_category = 'today'
            age_text = 'Today'
        elif days_ago == 1:
            age_category = 'new'
            age_text = 'Yesterday'
        elif days_ago <= 7:
            age_category = 'new'
            age_text = f'{days_ago} days ago'
        elif days_ago <= 30:
            age_category = 'recent'
            age_text = f'{days_ago} days ago'
        else:
            age_category = 'older'
            age_text = f'{days_ago} days ago'

        return {
            'formatted_date': formatted_date,
            'days_ago': days_ago,
            'age_category': age_category,
            'age_text': age_text
        }

    def _clean_markdown(self, text):
        """
        Clean markdown syntax and HTML from text.

        Args:
            text (str): Text with potential markdown and/or HTML

        Returns:
            str: Cleaned plain text
        """
        if not text:
            return ""

        # First, aggressively remove all HTML tags and attributes
        # Remove <a> tags completely (including href attributes that might leak)
        text = re.sub(r'<a\s+[^>]*?href=["\']([^"\']*)["\'][^>]*?>(.*?)</a>', r'\2', text, flags=re.IGNORECASE | re.DOTALL)
        # Remove any remaining HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        # Decode common HTML entities
        text = text.replace('&nbsp;', ' ')
        text = text.replace('&amp;', '&')
        text = text.replace('&lt;', '<')
        text = text.replace('&gt;', '>')
        text = text.replace('&quot;', '"')
        text = text.replace('&#39;', "'")

        # Remove markdown bold/italic
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
        text = re.sub(r'\*(.+?)\*', r'\1', text)
        text = re.sub(r'__(.+?)__', r'\1', text)
        text = re.sub(r'_(.+?)_', r'\1', text)

        # Remove markdown links but keep the text
        text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)

        # Remove markdown code blocks
        text = re.sub(r'`(.+?)`', r'\1', text)

        # Remove markdown list prefixes (-, *, •, numbered lists)
        text = re.sub(r'^[\s]*[-*•]\s+', '', text, flags=re.MULTILINE)
        text = re.sub(r'^[\s]*\d+\.\s+', '', text, flags=re.MULTILINE)

        # Remove common markdown section prefixes from action items/breaking changes
        text = re.sub(r'^[\s]*[-–]\s*(Breaking Changes?|Future Planning|Deprecation Path|Action Items?|Timeline|Priority)[:\s]+', '', text, flags=re.IGNORECASE)

        # Clean up extra whitespace
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()

        return text

    def generate_tier1_digest(self, executive_summary, articles, output_dir, summarizer=None):
        """
        Generate Tier 1 Digest Report - Quick daily/weekly scan (5-10 min read).

        - Last 7 days only
        - CRITICAL and HIGH priority articles only
        - Executive summary + headlines + action items
        - Minimal format for quick scanning

        Args:
            executive_summary (dict): Executive summary data
            articles (list): List of article dictionaries
            output_dir (str): Directory to save the report
            summarizer: AI summarizer instance for generating product summaries

        Returns:
            str: Path to the generated report
        """
        logger.info("Generating Tier 1 Digest Report (7 days, Critical/High only)")

        # Add priority scoring to all articles
        for article in articles:
            article['priority'] = self._calculate_priority(article)

        # Filter for Critical and High priority only
        filtered_articles = [a for a in articles if a['priority']['level'] in ['CRITICAL', 'HIGH']]

        logger.info(f"Filtered {len(filtered_articles)} Critical/High priority articles from {len(articles)} total")

        # Sort by priority score (highest first)
        filtered_articles.sort(key=lambda x: x['priority']['score'], reverse=True)

        # Generate report using filtered articles
        return self._generate_report_with_tier(
            executive_summary=executive_summary,
            articles=filtered_articles,
            output_dir=output_dir,
            time_period="last 7 days",
            tier=1,
            tier_name="Tier 1: Critical & High Priority Digest",
            summarizer=summarizer
        )

    def generate_tier2_biweekly(self, executive_summary, articles, output_dir, summarizer=None):
        """
        Generate Tier 2 Bi-Weekly Report - Regular review (30 min read).

        - Last 14 days
        - CRITICAL, HIGH and MEDIUM priority articles
        - Summaries without full content
        - Organized by product

        Args:
            executive_summary (dict): Executive summary data
            articles (list): List of article dictionaries
            output_dir (str): Directory to save the report
            summarizer: AI summarizer instance for generating product summaries

        Returns:
            str: Path to the generated report
        """
        logger.info("Generating Tier 2 Bi-Weekly Report (14 days, Critical/High/Medium priority)")

        # Add priority scoring to all articles
        for article in articles:
            article['priority'] = self._calculate_priority(article)

        # Filter for Critical, High and Medium priority
        filtered_articles = [a for a in articles if a['priority']['level'] in ['CRITICAL', 'HIGH', 'MEDIUM']]

        logger.info(f"Filtered {len(filtered_articles)} Critical/High/Medium priority articles from {len(articles)} total")

        # Sort by priority score (highest first)
        filtered_articles.sort(key=lambda x: x['priority']['score'], reverse=True)

        # Generate report using filtered articles
        return self._generate_report_with_tier(
            executive_summary=executive_summary,
            articles=filtered_articles,
            output_dir=output_dir,
            time_period="last 14 days",
            tier=2,
            tier_name="Tier 2: Critical, High & Medium Priority Updates",
            summarizer=summarizer
        )

    def generate_tier3_archive(self, executive_summary, articles, output_dir, summarizer=None):
        """
        Generate Tier 3 Monthly Archive - Full reference report.

        - Last 30 days
        - ALL priorities
        - Full detailed content
        - Complete archive for deep dives

        Args:
            executive_summary (dict): Executive summary data
            articles (list): List of article dictionaries
            output_dir (str): Directory to save the report
            summarizer: AI summarizer instance for generating product summaries

        Returns:
            str: Path to the generated report
        """
        logger.info("Generating Tier 3 Monthly Archive (30 days, all priorities)")

        # Add priority scoring to all articles
        for article in articles:
            article['priority'] = self._calculate_priority(article)

        # Sort by priority score (highest first)
        articles.sort(key=lambda x: x['priority']['score'], reverse=True)

        logger.info(f"Including all {len(articles)} articles in archive")

        # Generate report using all articles
        return self._generate_report_with_tier(
            executive_summary=executive_summary,
            articles=articles,
            output_dir=output_dir,
            time_period="last 30 days",
            tier=3,
            tier_name="Tier 3: Complete Monthly Archive",
            summarizer=summarizer
        )

    def _generate_report_with_tier(self, executive_summary, articles, output_dir, time_period, tier, tier_name, summarizer=None):
        """
        Generate a report with tier-specific formatting.

        Args:
            executive_summary (dict): Executive summary data
            articles (list): List of article dictionaries (already filtered)
            output_dir (str): Directory to save the report
            time_period (str): Time period description
            tier (int): Tier number (1, 2, or 3)
            tier_name (str): Display name for the tier
            summarizer: AI summarizer instance for generating product summaries

        Returns:
            str: Path to the generated report
        """
        try:
            # Ensure output directory exists
            os.makedirs(output_dir, exist_ok=True)

            # Prepare articles for report
            articles = self._prepare_articles(articles)

            # Get last report time and identify new articles
            last_report_time = self._get_last_report_time(output_dir)
            new_articles, existing_articles, new_count, existing_count = self._identify_new_articles(articles, last_report_time)

            # Calculate statistics
            stats = self._calculate_stats(articles)

            # Add priority breakdown to stats
            priority_counts = {'CRITICAL': 0, 'HIGH': 0, 'MEDIUM': 0, 'LOW': 0}
            for article in articles:
                if 'priority' in article:
                    priority_counts[article['priority']['level']] += 1
            stats['priority_breakdown'] = priority_counts

            # Organize articles by product
            products = self._categorize_by_product(articles)

            # For Tier 1 and 2, limit articles per product
            if tier in [1, 2]:
                max_per_product = 5 if tier == 1 else 10
                for product_name in products:
                    products[product_name] = products[product_name][:max_per_product]

            # Generate AI executive summaries for each product
            product_summaries = {}
            if summarizer:
                logger.info("Generating AI executive summaries for each product...")
                for product_name, product_articles in products.items():
                    if len(product_articles) > 0:
                        try:
                            logger.info(f"  Generating summary for {product_name} ({len(product_articles)} articles)...")
                            # Use the AI summarizer to create an executive summary for this product
                            product_exec_summary = summarizer.create_summary(
                                product_articles,
                                time_period=time_period,
                                product_focus=product_name
                            )
                            # Convert markdown to HTML
                            summary_text = product_exec_summary.get('summary', '')
                            if summary_text:
                                product_summaries[product_name] = markdown.markdown(
                                    summary_text,
                                    extensions=['tables', 'nl2br', 'fenced_code']
                                )
                            else:
                                product_summaries[product_name] = None
                        except Exception as e:
                            logger.error(f"Failed to generate summary for {product_name}: {str(e)}")
                            product_summaries[product_name] = None

                logger.info(f"Generated AI summaries for {len(product_summaries)} product categories")
            else:
                logger.warning("No summarizer provided - skipping product-level executive summaries")

            # Add date information to all articles
            for article in articles:
                date_info = self._format_date_with_age(article.get('published_date', ''))
                article['date_info'] = date_info

            # Convert markdown to HTML in article summaries
            for article in articles:
                if 'summary' in article and article['summary']:
                    article['summary'] = markdown.markdown(
                        article['summary'],
                        extensions=['tables', 'nl2br', 'fenced_code']
                    )

            # Process executive summary
            exec_summary_text = ""
            if isinstance(executive_summary, dict):
                exec_summary_text = markdown.markdown(
                    executive_summary.get('summary', ''),
                    extensions=['tables', 'nl2br', 'fenced_code']
                )
            elif isinstance(executive_summary, str):
                exec_summary_text = markdown.markdown(
                    executive_summary,
                    extensions=['tables', 'nl2br', 'fenced_code']
                )

            # Get AI model attribution for display in report
            ai_model_info = self._get_ai_model_attribution()

            # Prepare template data
            template_data = {
                'title': f"Microsoft Defender Update Report - {tier_name}",
                'date': datetime.now().strftime('%B %d, %Y at %I:%M %p'),
                'time_period': time_period,
                'tier': tier,
                'tier_name': tier_name,
                'total_updates': len(articles),
                'stats': stats,
                'executive_summary': exec_summary_text,
                'products': products,
                'product_summaries': product_summaries,  # Product-level executive summaries
                'new_count': new_count,
                'existing_count': existing_count,
                'new_articles': new_articles,
                'last_report_time': last_report_time.strftime('%Y-%m-%d %H:%M') if last_report_time else None,
                'ai_model_info': ai_model_info  # AI model attribution
            }

            # Generate HTML report
            try:
                template = self.env.get_template('security_product_report_tiered.html')
                html_content = template.render(**template_data)

                # Save HTML report with tier indicator
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                report_filename = f"security_product_tier{tier}_report_{timestamp}.html"
                report_path = os.path.join(output_dir, report_filename)

                with open(report_path, 'w', encoding='utf-8') as f:
                    f.write(html_content)

                logger.info(f"Tier {tier} HTML report generated: {report_path}")
                return report_path

            except Exception as template_error:
                logger.warning(f"Template rendering failed, using fallback: {str(template_error)}")
                # If template doesn't exist, use the standard template
                return self.generate_security_product_report(executive_summary, articles, output_dir, time_period)

        except Exception as e:
            logger.error(f"Error generating tier {tier} report: {str(e)}", exc_info=True)
            return None

    def generate_security_product_report(self, executive_summary, articles, output_dir, time_period="last 30 days"):
        """
        Generate a Microsoft Security Product daily report.

        Args:
            executive_summary (dict): Executive summary data
            articles (list): List of article dictionaries
            output_dir (str): Directory to save the report
            time_period (str): Time period description

        Returns:
            str: Path to the generated report
        """
        try:
            # Ensure output directory exists
            os.makedirs(output_dir, exist_ok=True)

            # Prepare articles for report
            articles = self._prepare_articles(articles)

            # Get last report time and identify new articles
            last_report_time = self._get_last_report_time(output_dir)
            new_articles, existing_articles, new_count, existing_count = self._identify_new_articles(articles, last_report_time)

            if last_report_time:
                logger.info(f"Found {new_count} new articles since last report ({last_report_time.strftime('%Y-%m-%d %H:%M')})")
            else:
                logger.info(f"First report generation - all {len(articles)} articles are new")

            # Calculate statistics
            stats = self._calculate_stats(articles)

            # Organize articles by product
            products = self._categorize_by_product(articles)

            # Add date information to all articles
            for article in articles:
                date_info = self._format_date_with_age(article.get('published_date', ''))
                article['date_info'] = date_info

            # Convert markdown to HTML in article summaries (do this AFTER extraction and date processing)
            for article in articles:
                if 'summary' in article and article['summary']:
                    article['summary'] = markdown.markdown(
                        article['summary'],
                        extensions=['tables', 'nl2br', 'fenced_code']
                    )

            # Process executive summary
            exec_summary_text = ""
            if isinstance(executive_summary, dict):
                exec_summary_text = markdown.markdown(
                    executive_summary.get('summary', ''),
                    extensions=['tables', 'nl2br', 'fenced_code']
                )
            elif isinstance(executive_summary, str):
                exec_summary_text = markdown.markdown(
                    executive_summary,
                    extensions=['tables', 'nl2br', 'fenced_code']
                )

            # Get AI model attribution for display in report
            ai_model_info = self._get_ai_model_attribution()

            # Prepare template data
            template_data = {
                'title': f"Microsoft Defender Update Report - {datetime.now().strftime('%B %d, %Y')}",
                'date': datetime.now().strftime('%B %d, %Y at %I:%M %p'),
                'time_period': time_period,
                'total_updates': len(articles),
                'stats': stats,
                'executive_summary': exec_summary_text,
                'products': products,
                'new_articles': new_articles,
                'new_count': new_count,
                'existing_count': existing_count,
                'last_report_time': last_report_time.strftime('%B %d, %Y at %I:%M %p') if last_report_time else None,
                'ai_model_info': ai_model_info  # AI model attribution
            }

            # Render the template
            template = self.env.get_template('security_product_report.html')
            html_content = template.render(**template_data)

            # Generate timestamp for filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

            # Save the HTML report
            output_path = os.path.join(output_dir, f'security_product_report_{timestamp}.html')
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(html_content)

            logger.info(f"Generated Microsoft Security Product report: {output_path}")
            logger.info(f"  - Total updates: {len(articles)}")
            logger.info(f"  - New since last report: {new_count}")
            logger.info(f"  - Products covered: {len(products)}")

            # Save report generation time for next run
            self._save_report_time(output_dir)

            return output_path

        except Exception as e:
            logger.error(f"Error generating security product report: {str(e)}", exc_info=True)
            return None

    def generate_markdown_report(self, executive_summary, articles, output_dir, time_period="last 30 days"):
        """
        Generate a Markdown report for Microsoft Security Product updates.

        Args:
            executive_summary (dict): Executive summary data
            articles (list): List of article dictionaries
            output_dir (str): Directory to save the report
            time_period (str): Time period description

        Returns:
            str: Path to the generated report
        """
        try:
            # Ensure output directory exists
            os.makedirs(output_dir, exist_ok=True)

            # Prepare articles for report
            articles = self._prepare_articles(articles)

            # Get last report time and identify new articles
            last_report_time = self._get_last_report_time(output_dir)
            new_articles, existing_articles, new_count, existing_count = self._identify_new_articles(articles, last_report_time)

            if last_report_time:
                logger.info(f"Found {new_count} new articles since last report ({last_report_time.strftime('%Y-%m-%d %H:%M')})")
            else:
                logger.info(f"First report generation - all {len(articles)} articles are new")

            # Add date information to all articles
            for article in articles:
                date_info = self._format_date_with_age(article.get('published_date', ''))
                article['date_info'] = date_info

            # Organize articles by product
            products = self._categorize_by_product(articles)

            # Calculate statistics
            stats = self._calculate_stats(articles)

            # Build Markdown content
            md_content = f"# Microsoft Defender Update Report\n\n"
            md_content += f"**Generated:** {datetime.now().strftime('%B %d, %Y at %I:%M %p')}\n\n"
            md_content += f"**Period:** {time_period}\n\n"

            # Statistics
            md_content += "## Quick Stats\n\n"
            md_content += f"- **Total Updates:** {len(articles)}\n"
            md_content += f"- **New Features:** {stats['new_features']}\n"
            md_content += f"- **Bug Fixes:** {stats['bug_fixes']}\n"
            md_content += f"- **Performance Improvements:** {stats['performance_improvements']}\n"
            md_content += f"- **Integrations:** {stats['integrations']}\n"
            md_content += f"- **Platform Updates:** {stats['platform_updates']}\n\n"

            # What's New Section
            if new_count > 0:
                md_content += "## 🆕 What's New Since Last Report\n\n"
                md_content += f"**{new_count}** new update{'s' if new_count != 1 else ''} added since "
                md_content += f"{last_report_time.strftime('%B %d, %Y at %I:%M %p')}\n\n"
                if existing_count > 0:
                    md_content += f"*({existing_count} existing update{'s' if existing_count != 1 else ''} also included)*\n\n"

                for article in new_articles[:10]:
                    md_content += f"### 🔸 [{article['title']}]({article['url']}) **[NEW]**\n\n"
                    if article.get('date_info'):
                        date_info = article['date_info']
                        if date_info.get('age_text') and date_info['age_text'] != 'Date unknown':
                            md_content += f"**Date:** {date_info['formatted_date']} ({date_info['age_text']}) | "
                        else:
                            md_content += f"**Date:** {date_info.get('formatted_date', 'Unknown')} | "
                    md_content += f"**Source:** {article.get('source', 'Unknown')}\n\n"
                    if article.get('update_type'):
                        md_content += f"**Type:** {', '.join(article['update_type'])}\n\n"
                    md_content += "---\n\n"

                if new_count > 10:
                    md_content += f"*Showing first 10 of {new_count} new updates. See full details below.*\n\n"

            elif last_report_time:
                md_content += "## 📊 No New Updates\n\n"
                md_content += f"No new updates have been added since your last report on {last_report_time.strftime('%B %d, %Y at %I:%M %p')}.\n\n"
                md_content += f"*All {len(articles)} updates shown were already in the previous report.*\n\n"

            # Executive Summary
            md_content += "## Executive Summary\n\n"
            if isinstance(executive_summary, dict):
                md_content += executive_summary.get('summary', 'No executive summary available.') + "\n\n"
            elif isinstance(executive_summary, str):
                md_content += executive_summary + "\n\n"
            else:
                md_content += "No executive summary available.\n\n"

            # Updates by Product
            md_content += "## Updates by Product\n\n"

            for product_name, product_updates in products.items():
                md_content += f"### {product_name} ({len(product_updates)} update{'s' if len(product_updates) != 1 else ''})\n\n"

                for update in product_updates:
                    md_content += f"#### [{update['title']}]({update['url']})\n\n"

                    # Format date with age indicator
                    date_str = "Unknown"
                    if update.get('date_info'):
                        date_info = update['date_info']
                        if date_info.get('age_text') and date_info['age_text'] != 'Date unknown':
                            date_str = f"{date_info['formatted_date']} ({date_info['age_text']})"
                        else:
                            date_str = date_info.get('formatted_date', 'Unknown')
                    elif update.get('published_date'):
                        date_str = update['published_date']

                    md_content += f"**Date:** {date_str} | **Source:** {update.get('source', 'Unknown')}\n\n"

                    # Update types
                    if update.get('update_type'):
                        md_content += f"**Type:** {', '.join(update['update_type'])}\n\n"

                    # Summary
                    md_content += update.get('summary', 'No summary available.') + "\n\n"
                    md_content += "---\n\n"

            # Footer
            md_content += "\n---\n\n"
            md_content += "*This report was automatically generated by SecIntel AI - Security Intelligence Tracker.*\n\n"
            md_content += "**Confidential - For Internal Use Only**\n"

            # Generate timestamp for filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

            # Save the Markdown report
            output_path = os.path.join(output_dir, f'security_product_report_{timestamp}.md')
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(md_content)

            logger.info(f"Generated Microsoft Security Product Markdown report: {output_path}")
            logger.info(f"  - Total updates: {len(articles)}")
            logger.info(f"  - New since last report: {new_count}")

            # Save report generation time for next run (only if HTML report didn't already save it)
            # This ensures consistency if both reports are generated
            self._save_report_time(output_dir)

            return output_path

        except Exception as e:
            logger.error(f"Error generating Markdown report: {str(e)}", exc_info=True)
            return None
