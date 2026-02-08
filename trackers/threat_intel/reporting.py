"""
Reporting module for the CTI Aggregator.
Handles generation of reports and executive summaries.
"""

import os
import logging
from datetime import datetime
import markdown
import json
from jinja2 import Environment, FileSystemLoader, select_autoescape
from .summarizer import clean_summary_artifacts, validate_cves_in_text

logger = logging.getLogger(__name__)

class ReportGenerator:
    """Generates reports from executive summaries and article data"""
    
    def __init__(self, template_dir=None, ai_config=None):
        """
        Initialize the report generator.

        Args:
            template_dir (str, optional): Directory containing report templates
            ai_config (dict, optional): AI configuration for model attribution
        """
        # If template_dir not provided, use module directory's templates subfolder
        if template_dir is None:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            template_dir = os.path.join(os.path.dirname(current_dir), 'templates')

        # Ensure template directory exists
        os.makedirs(template_dir, exist_ok=True)

        # Create default template if it doesn't exist
        default_template_path = os.path.join(template_dir, 'executive_summary.html')
        if not os.path.exists(default_template_path):
            self.create_default_template(default_template_path)

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

    @staticmethod
    def _clean_thinking_tags(text):
        """
        Remove AI thinking tags from text.

        Some AI models output their reasoning in <think> tags. This function
        removes those tags and their content to keep only the final output.

        Args:
            text (str): Text potentially containing <think> tags

        Returns:
            str: Text with thinking tags removed
        """
        import re
        if not text:
            return text

        # Remove <think>...</think> tags and everything between them
        cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL | re.IGNORECASE)

        # Clean up any extra whitespace left behind
        cleaned = re.sub(r'\n\s*\n\s*\n', '\n\n', cleaned)
        cleaned = cleaned.strip()

        return cleaned

    @staticmethod
    def _fix_markdown_formatting(text):
        """
        Fix common markdown formatting issues from AI-generated summaries.

        The AI sometimes generates complex nested markdown that doesn't render
        properly, such as numbered lists with bold headings and sub-bullets.
        This function normalizes the formatting for better HTML conversion.

        Args:
            text (str): Markdown text with potential formatting issues

        Returns:
            str: Corrected markdown text
        """
        import re
        if not text:
            return text

        # Pattern 1: Fix numbered list items that start with bold text followed by sub-bullets
        # Example: "1. **Header**  \n   - item"
        # The double-space at end of bold is causing markdown issues

        # Remove trailing double-spaces after bold/italic markers at end of lines
        text = re.sub(r'\*\*\s\s+\n', '**\n', text)  # **  \n -> **\n
        text = re.sub(r'\*\s\s+\n', '*\n', text)     # *  \n -> *\n

        # Replace en-dashes and em-dashes with regular hyphens
        text = text.replace('‑', '-').replace('–', '-').replace('—', '-')

        return text

    def _fix_claude_formatting(self, text):
        """
        Fix Claude API-specific markdown formatting issues.

        Claude (especially Haiku) sometimes outputs continuous text without
        proper line breaks between sections, causing entire summaries to merge
        into single HTML elements. This function adds proper spacing.

        Args:
            text (str): Markdown text from Claude API

        Returns:
            str: Corrected markdown text with proper spacing
        """
        import re
        if not text:
            return text

        # Only apply these fixes for Claude provider
        if not self.ai_config or self.ai_config.get('provider', '').lower() != 'claude':
            return text

        # Special case: If the text starts with a section heading without ## markers,
        # add markdown heading marker. Pattern: "Threat Landscape Overview  The text..."
        # Common in Haiku output where it starts right into content
        first_line_pattern = r'^([A-Z][A-Za-z\s]{5,40}?)\s{2,}([A-Z][a-z])'
        if re.match(first_line_pattern, text):
            text = re.sub(first_line_pattern, r'## \1\n\n\2', text, count=1)

        # Fix Claude's continuous text output by ensuring proper line breaks
        # Pattern: "## Heading  Text text"  should be "## Heading\n\nText text"
        # Add double newline after markdown headings that lack proper spacing
        text = re.sub(r'(#{1,6}\s+[^\n]+?)(\s{2,})([^#\n])', r'\1\n\n\3', text)

        # Ensure blank line before markdown headings (## format)
        # But SKIP if at start of text (to avoid adding extra text before ## at the beginning)
        # Pattern: "text  ## Heading" should be "text\n\n## Heading"
        # Use negative lookbehind to avoid matching at start of string
        text = re.sub(r'(?<!^)([^\n])\s*(#{1,6}\s)', r'\1\n\n\2', text, flags=re.MULTILINE)

        # Ensure blank line before numbered lists
        # Pattern: "text  1. Item" should be "text\n\n1. Item"
        text = re.sub(r'([^\n])\s+(\d+\.\s+\*\*)', r'\1\n\n\2', text)

        # Ensure blank line before bullet lists starting with -
        # Pattern: "text  - Item" should be "text\n\n- Item"
        text = re.sub(r'([^\n])\s+(-\s+\*\*)', r'\1\n\n\2', text)

        # Clean up excessive whitespace (but preserve intentional double newlines)
        text = re.sub(r'\n{4,}', '\n\n', text)  # Max 2 consecutive newlines

        return text

    def create_default_template(self, template_path):
        """
        Create a default HTML template for executive summaries.
        
        Args:
            template_path (str): Path to save the template
        """
        default_template = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }}</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }
        .header {
            text-align: center;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 1px solid #ddd;
        }
        .logo {
            max-width: 200px;
            margin-bottom: 20px;
        }
        h1 {
            color: #2c3e50;
            margin-bottom: 10px;
        }
        h2 {
            color: #3498db;
            margin-top: 30px;
            margin-bottom: 15px;
            padding-bottom: 5px;
            border-bottom: 1px solid #eee;
        }
        h3 {
            color: #2c3e50;
        }
        .date {
            color: #7f8c8d;
            font-style: italic;
        }
        .executive-summary {
            background-color: #f9f9f9;
            padding: 20px;
            border-left: 4px solid #3498db;
            margin-bottom: 30px;
        }
        .key-section {
            background-color: #f5f5f5;
            padding: 15px;
            margin-bottom: 20px;
            border-radius: 5px;
        }
        .recommendations {
            background-color: #e8f4fc;
            padding: 15px;
            margin-bottom: 20px;
            border-radius: 5px;
        }
        .actor {
            margin-bottom: 15px;
            padding-bottom: 15px;
            border-bottom: 1px dotted #ddd;
        }
        .ioc {
            font-family: monospace;
            background-color: #f0f0f0;
            padding: 2px 5px;
            border-radius: 3px;
        }
        .article {
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 1px solid #eee;
        }
        .article-source {
            color: #7f8c8d;
            font-size: 0.9em;
        }
        .article-summary {
            margin-top: 10px;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 20px;
        }
        table, th, td {
            border: 1px solid #ddd;
        }
        th, td {
            padding: 12px;
            text-align: left;
        }
        th {
            background-color: #f2f2f2;
        }
        tr:nth-child(even) {
            background-color: #f9f9f9;
        }
        .footer {
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #ddd;
            font-size: 0.9em;
            color: #7f8c8d;
            text-align: center;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>{{ title }}</h1>
        <p class="date">Generated on {{ date }}</p>
    </div>

    <div class="executive-summary">
        <h2>Executive Summary</h2>
        {{ executive_summary|safe }}
    </div>

    <div class="key-section">
        <h2>Key Threat Actors</h2>
        {% if key_actors %}
            {% for actor in key_actors %}
                <div class="actor">
                    <h3>{{ actor.name }}</h3>
                    <p>{{ actor.description }}</p>
                </div>
            {% endfor %}
        {% else %}
            <p>No key threat actors identified in this reporting period.</p>
        {% endif %}
    </div>

    <div class="key-section">
        <h2>Critical Indicators of Compromise</h2>
        {% if critical_iocs %}
            <table>
                <tr>
                    <th>Type</th>
                    <th>Value</th>
                    <th>Description</th>
                </tr>
                {% for ioc in critical_iocs %}
                    <tr>
                        <td>{{ ioc.type }}</td>
                        <td class="ioc">{{ ioc.value }}</td>
                        <td>{{ ioc.description }}</td>
                    </tr>
                {% endfor %}
            </table>
        {% else %}
            <p>No critical IOCs identified in this reporting period.</p>
        {% endif %}
    </div>

    <div class="recommendations">
        <h2>Strategic Recommendations</h2>
        {% if recommendations %}
            <ol>
                {% for rec in recommendations %}
                    <li>{{ rec }}</li>
                {% endfor %}
            </ol>
        {% else %}
            <p>No strategic recommendations for this reporting period.</p>
        {% endif %}
    </div>

    <h2>Recent Threat Intelligence</h2>
    {% if articles %}
        {% for article in articles %}
            <div class="article">
                <h3><a href="{{ article.url }}">{{ article.title }}</a></h3>
                <p class="article-source">Source: {{ article.source }} | {{ article.published_date }}</p>
                <div class="article-summary">
                    {{ article.summary|safe }}
                </div>
            </div>
        {% endfor %}
    {% else %}
        <p>No recent articles available.</p>
    {% endif %}

    <div class="footer">
        <p>This report was automatically generated by the Cyber Threat Intelligence Aggregator.</p>
        <p>Confidential - For internal use only</p>
    </div>
</body>
</html>
"""
        os.makedirs(os.path.dirname(template_path), exist_ok=True)
        with open(template_path, 'w') as f:
            f.write(default_template)
            
        logger.info(f"Created default template at {template_path}")
    
    def generate_report(self, executive_summary, articles, output_dir, format='html'):
        """
        Generate a report from an executive summary and articles.
        
        Args:
            executive_summary (dict): Executive summary data
            articles (list): List of article dictionaries
            output_dir (str): Directory to save the report
            format (str): Report format ('html', 'markdown', or 'json')
        
        Returns:
            str: Path to the generated report
        """
        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)
        
        # Generate timestamp for filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Create report based on format
        if format == 'html':
            return self.generate_html_report(executive_summary, articles, output_dir, timestamp)
        elif format == 'markdown':
            return self.generate_markdown_report(executive_summary, articles, output_dir, timestamp)
        elif format == 'json':
            return self.generate_json_report(executive_summary, articles, output_dir, timestamp)
        else:
            logger.warning(f"Unsupported format: {format}, defaulting to HTML")
            return self.generate_html_report(executive_summary, articles, output_dir, timestamp)
    
    def generate_html_report(self, executive_summary, articles, output_dir, timestamp):
        """
        Generate an HTML report.
        
        Args:
            executive_summary (dict): Executive summary data
            articles (list): List of article dictionaries
            output_dir (str): Directory to save the report
            timestamp (str): Timestamp for the filename
        
        Returns:
            str: Path to the generated report
        """
        try:
            # Convert markdown to HTML in article summaries
            for article in articles:
                if 'summary' in article and article['summary']:
                    # Clean thinking tags first
                    article['summary'] = self._clean_thinking_tags(article['summary'])
                    # Clean prompt artifacts that may have leaked into summaries
                    article['summary'] = clean_summary_artifacts(article['summary'])
                    # Validate CVEs and add warnings for suspicious ones
                    article['summary'], _ = validate_cves_in_text(article['summary'])
                    # Fix formatting issues before conversion
                    article['summary'] = self._fix_markdown_formatting(article['summary'])
                    # Then convert markdown to HTML with all necessary extensions
                    article['summary'] = markdown.markdown(
                        article['summary'],
                        extensions=['tables', 'fenced_code', 'nl2br', 'sane_lists', 'md_in_html']
                    )

            # Prepare template data
            exec_text = executive_summary.get('executive_summary', '')
            # Fix formatting issues before conversion
            exec_text = self._fix_markdown_formatting(exec_text)
            # Apply Claude-specific formatting fixes if using Claude provider
            exec_text = self._fix_claude_formatting(exec_text)

            template_data = {
                'title': f"SecIntel AI Intelligence Executive Summary - {datetime.now().strftime('%B %d, %Y')}",
                'date': datetime.now().strftime('%B %d, %Y %H:%M'),
                'executive_summary': markdown.markdown(
                    exec_text,
                    extensions=['tables', 'fenced_code', 'nl2br', 'sane_lists', 'md_in_html']
                ),
                'key_actors': executive_summary.get('key_actors', []),
                'critical_iocs': executive_summary.get('critical_iocs', []),
                'recommendations': executive_summary.get('recommendations', []),
                'articles': articles
            }
            
            # Debug log to see what's being passed to the template
            logger.debug(f"Template data - key_actors: {template_data['key_actors']}")
            logger.debug(f"Template data - critical_iocs: {template_data['critical_iocs']}")
            logger.debug(f"Template data - recommendations: {template_data['recommendations']}")
            
            # Add fallback data if sections are empty
            if not template_data['key_actors'] or len(template_data['key_actors']) == 0:
                template_data['key_actors'] = [
                    {
                        "name": "No Specific Threat Actors Identified",
                        "description": "The analyzed reports did not contain specific threat actor attributions."
                    }
                ]
                
            if not template_data['critical_iocs'] or len(template_data['critical_iocs']) == 0:
                template_data['critical_iocs'] = [
                    {
                        "type": "N/A",
                        "value": "N/A",
                        "description": "No critical IOCs were identified in the analyzed reports."
                    }
                ]
                
            if not template_data['recommendations'] or len(template_data['recommendations']) == 0:
                template_data['recommendations'] = [
                    "Maintain regular security patches and updates for all systems",
                    "Implement multi-factor authentication for critical services",
                    "Conduct regular security awareness training for employees",
                    "Review and update incident response plans",
                    "Maintain offline backups of critical data"
                ]
            
            # Render the template
            template = self.env.get_template('executive_summary.html')
            html_content = template.render(**template_data)
            
            # Save the HTML report
            output_path = os.path.join(output_dir, f'secintel_report_{timestamp}.html')
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            logger.info(f"Generated HTML report: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"Error generating HTML report: {str(e)}")
            return None
    
    def generate_markdown_report(self, executive_summary, articles, output_dir, timestamp):
        """
        Generate a Markdown report.
        
        Args:
            executive_summary (dict): Executive summary data
            articles (list): List of article dictionaries
            output_dir (str): Directory to save the report
            timestamp (str): Timestamp for the filename
        
        Returns:
            str: Path to the generated report
        """
        try:
            # Build Markdown content
            md_content = f"# SecIntel AI Intelligence Executive Summary\n\n"
            md_content += f"Generated: {datetime.now().strftime('%B %d, %Y %H:%M')}\n\n"
            
            # Executive Summary
            md_content += "## Executive Summary\n\n"
            md_content += executive_summary.get('executive_summary', 'No executive summary available.') + "\n\n"
            
            # Key Threat Actors
            md_content += "## Key Threat Actors\n\n"
            key_actors = executive_summary.get('key_actors', [])
            if key_actors:
                for actor in key_actors:
                    md_content += f"### {actor.get('name', 'Unknown Actor')}\n\n"
                    md_content += f"{actor.get('description', 'No description available.')}\n\n"
            else:
                md_content += "No key threat actors identified in this reporting period.\n\n"
            
            # Critical IOCs
            md_content += "## Critical Indicators of Compromise\n\n"
            critical_iocs = executive_summary.get('critical_iocs', [])
            if critical_iocs:
                md_content += "| Type | Value | Description |\n"
                md_content += "|------|-------|-------------|\n"
                for ioc in critical_iocs:
                    md_content += f"| {ioc.get('type', 'Unknown')} | `{ioc.get('value', 'N/A')}` | {ioc.get('description', 'No description')} |\n"
                md_content += "\n"
            else:
                md_content += "No critical IOCs identified in this reporting period.\n\n"
            
            # Strategic Recommendations
            md_content += "## Strategic Recommendations\n\n"
            recommendations = executive_summary.get('recommendations', [])
            if recommendations:
                for i, rec in enumerate(recommendations, 1):
                    md_content += f"{i}. {rec}\n"
                md_content += "\n"
            else:
                md_content += "No strategic recommendations for this reporting period.\n\n"
            
            # Recent Articles
            md_content += "## Recent Threat Intelligence\n\n"
            if articles:
                for article in articles:
                    md_content += f"### [{article['title']}]({article['url']})\n\n"
                    md_content += f"Source: {article.get('source', 'Unknown')} | {article.get('published_date', 'Unknown date')}\n\n"
                    md_content += article.get('summary', 'No summary available.') + "\n\n"
                    md_content += "---\n\n"
            else:
                md_content += "No recent articles available.\n\n"
            
            # Footer
            md_content += "---\n\n"
            md_content += "*This report was automatically generated by SecIntel AI - Security Intelligence Tracker.*\n\n"
            md_content += "**Confidential - For internal use only**\n"
            
            # Save the Markdown report
            output_path = os.path.join(output_dir, f'secintel_report_{timestamp}.md')
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(md_content)
            
            logger.info(f"Generated Markdown report: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"Error generating Markdown report: {str(e)}")
            return None
    
    def generate_json_report(self, executive_summary, articles, output_dir, timestamp):
        """
        Generate a JSON report.
        
        Args:
            executive_summary (dict): Executive summary data
            articles (list): List of article dictionaries
            output_dir (str): Directory to save the report
            timestamp (str): Timestamp for the filename
        
        Returns:
            str: Path to the generated report
        """
        try:
            # Prepare report data
            report_data = {
                'title': f"SecIntel AI Intelligence Executive Summary - {datetime.now().strftime('%B %d, %Y')}",
                'generated_date': datetime.now().isoformat(),
                'executive_summary': executive_summary,
                'articles': [{
                    'id': article.get('id'),
                    'title': article.get('title'),
                    'url': article.get('url'),
                    'source': article.get('source'),
                    'published_date': article.get('published_date'),
                    'summary': article.get('summary'),
                    'iocs': article.get('iocs', {})
                } for article in articles]
            }
            
            # Save the JSON report
            output_path = os.path.join(output_dir, f'secintel_report_{timestamp}.json')
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(report_data, f, indent=2)
            
            logger.info(f"Generated JSON report: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"Error generating JSON report: {str(e)}")
            return None
    def _calculate_priority(self, article):
        """
        Calculate priority score for threat intel articles.
        
        Priority Levels:
        - CRITICAL: Active exploits, zero-days, ransomware campaigns, APT activity
        - HIGH: Vulnerabilities with POC, malware campaigns, threat actor TTPs
        - MEDIUM: Security advisories, general threats, IOC reports
        - LOW: News articles, general security updates
        
        Args:
            article (dict): Article dictionary
            
        Returns:
            dict: Priority information with level, score, and reasoning
        """
        import re
        
        title = article.get('title', '').lower()
        summary = article.get('summary', '').lower()
        content = article.get('content', '').lower()
        combined = f"{title} {summary} {content}"
        
        priority_score = 0
        reasons = []
        
        # CRITICAL indicators
        critical_keywords = [
            'zero-day', 'zero day', '0-day', '0day',
            'actively exploited', 'in-the-wild', 'in the wild',
            'ransomware attack', 'data breach', 'apt attack',
            'supply chain attack', 'critical vulnerability cve',
            'nation-state', 'state-sponsored',
            'immediate threat', 'active campaign'
        ]
        
        for keyword in critical_keywords:
            if keyword in combined:
                priority_score += 100
                reasons.append(f"Critical: {keyword}")
                break
        
        # HIGH priority indicators  
        high_keywords = [
            'vulnerability', 'cve-202', 'exploit', 'proof of concept', 'poc available',
            'malware campaign', 'ransomware', 'apt', 'advanced persistent',
            'threat actor', 'hacker group', 'cybercriminal',
            'credential theft', 'data exfiltration',
            'backdoor', 'trojan', 'remote access'
        ]
        
        for keyword in high_keywords:
            if keyword in combined:
                priority_score += 50
                reasons.append(f"High: {keyword}")
                break
        
        # MEDIUM priority indicators
        medium_keywords = [
            'security advisory', 'security update', 'patch released',
            'phishing campaign', 'malicious', 'suspicious',
            'threat intelligence', 'indicators of compromise', 'ioc',
            'attack technique', 'ttps', 'mitre att&ck'
        ]
        
        for keyword in medium_keywords:
            if keyword in combined:
                priority_score += 25
                reasons.append(f"Medium: {keyword}")
                break
        
        # IOC boost - articles with IOCs are more actionable
        if article.get('iocs'):
            ioc_count = sum(len(v) for v in article['iocs'].values())
            if ioc_count > 10:
                priority_score += 30
                reasons.append(f"{ioc_count} IOCs identified")
            elif ioc_count > 0:
                priority_score += 15
                reasons.append(f"{ioc_count} IOCs")
        
        # Tag boost - certain tags indicate higher priority
        tags = [tag['tag'] if isinstance(tag, dict) else tag for tag in article.get('tags', [])]
        priority_tags = ['apt-attribution', 'volexity', 'threat-research', 'active-exploitation']
        for tag in tags:
            if tag in priority_tags:
                priority_score += 20
                reasons.append(f"Tag: {tag}")
                break
        
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
            'reasons': reasons[:2]
        }
    
    def generate_tier0_daily(self, articles, output_dir, summarizer=None):
        """
        Generate Tier 0 Daily Digest (24 hours, all priority levels).

        Args:
            articles (list): List of article dictionaries
            output_dir (str): Output directory
            summarizer: Optional ExecutiveSummarizer for generating executive summaries

        Returns:
            str: Path to generated report
        """
        logger.info("Generating Tier 0 Daily Digest (24 hours, all priorities)")

        # Calculate priority for all articles
        for article in articles:
            article['priority'] = self._calculate_priority(article)

        # Include all articles (no filtering by priority for daily digest)
        # Sort by priority score (highest first)
        articles.sort(key=lambda x: x['priority']['score'], reverse=True)

        if not articles:
            logger.warning("No articles found for Tier 0 daily report")
            return None

        # Generate overall executive summary if summarizer provided
        executive_summary = None
        if summarizer:
            try:
                logger.info("Generating overall executive summary...")
                executive_summary = summarizer.create_summary(articles, max_articles=15)
                logger.info("✓ Executive summary generated")
            except Exception as e:
                logger.error(f"Failed to generate executive summary: {e}")

        # Generate report
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_path = os.path.join(output_dir, f'threat_intel_tier0_report_{timestamp}.html')

        html_content = self._generate_tier_html(
            title="Threat Intelligence - Tier 0 Daily Digest",
            subtitle="Security News from the Last 24 Hours",
            articles=articles,
            tier=0,
            executive_summary=executive_summary,
            summarizer=summarizer
        )

        os.makedirs(output_dir, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        logger.info(f"Tier 0 HTML report generated: {output_path}")
        return output_path

    def generate_tier1_digest(self, articles, output_dir, summarizer=None):
        """
        Generate Tier 1 Weekly Digest (7 days, Critical/High only).

        Args:
            articles (list): List of article dictionaries
            output_dir (str): Output directory
            summarizer: Optional ExecutiveSummarizer for generating executive summaries

        Returns:
            str: Path to generated report
        """
        logger.info("Generating Tier 1 Digest Report (7 days, Critical/High only)")

        # Calculate priority for all articles
        for article in articles:
            article['priority'] = self._calculate_priority(article)

        # Filter to Critical/High only
        filtered = [a for a in articles if a['priority']['level'] in ['CRITICAL', 'HIGH']]
        logger.info(f"Filtered {len(filtered)} Critical/High priority articles from {len(articles)} total")

        if not filtered:
            logger.warning("No Critical/High priority articles for Tier 1 report")
            return None

        # Sort by priority score (highest first)
        filtered.sort(key=lambda x: x['priority']['score'], reverse=True)

        # Generate overall executive summary if summarizer provided
        executive_summary = None
        if summarizer:
            try:
                logger.info("Generating overall executive summary...")
                executive_summary = summarizer.create_summary(filtered, max_articles=20)
                logger.info("✓ Executive summary generated")
            except Exception as e:
                logger.error(f"Failed to generate executive summary: {e}")

        # Generate report
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_path = os.path.join(output_dir, f'threat_intel_tier1_report_{timestamp}.html')

        # Simple HTML report
        html_content = self._generate_tier_html(
            title="Threat Intelligence - Tier 1 Weekly Digest",
            subtitle="Critical & High Priority Threats (7 days)",
            articles=filtered,
            tier=1,
            executive_summary=executive_summary,
            summarizer=summarizer
        )
        
        os.makedirs(output_dir, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        logger.info(f"Tier 1 HTML report generated: {output_path}")
        return output_path
    
    def generate_tier2_biweekly(self, articles, output_dir, summarizer=None):
        """
        Generate Tier 2 Bi-Weekly Report (14 days, High/Medium priority).

        Args:
            articles (list): List of article dictionaries
            output_dir (str): Output directory
            summarizer: Optional ExecutiveSummarizer for generating executive summaries

        Returns:
            str: Path to generated report
        """
        logger.info("Generating Tier 2 Bi-Weekly Report (14 days, Critical/High/Medium priority)")

        # Calculate priority for all articles
        for article in articles:
            article['priority'] = self._calculate_priority(article)

        # Filter to Critical/High/Medium
        filtered = [a for a in articles if a['priority']['level'] in ['CRITICAL', 'HIGH', 'MEDIUM']]
        logger.info(f"Filtered {len(filtered)} Critical/High/Medium priority articles from {len(articles)} total")

        if not filtered:
            logger.warning("No priority articles for Tier 2 report")
            return None

        # Sort by priority score
        filtered.sort(key=lambda x: x['priority']['score'], reverse=True)

        # Generate overall executive summary if summarizer provided
        executive_summary = None
        if summarizer:
            try:
                logger.info("Generating overall executive summary...")
                executive_summary = summarizer.create_summary(filtered, max_articles=20)
                logger.info("✓ Executive summary generated")
            except Exception as e:
                logger.error(f"Failed to generate executive summary: {e}")

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_path = os.path.join(output_dir, f'threat_intel_tier2_report_{timestamp}.html')

        html_content = self._generate_tier_html(
            title="Threat Intelligence - Tier 2 Bi-Weekly Review",
            subtitle="Critical, High & Medium Priority Threats (14 days)",
            articles=filtered,
            tier=2,
            executive_summary=executive_summary,
            summarizer=summarizer
        )
        
        os.makedirs(output_dir, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        logger.info(f"Tier 2 HTML report generated: {output_path}")
        return output_path
    
    def generate_tier3_archive(self, articles, output_dir, summarizer=None):
        """
        Generate Tier 3 Monthly Archive (30 days, all priorities).

        Args:
            articles (list): List of article dictionaries
            output_dir (str): Output directory
            summarizer: Optional ExecutiveSummarizer for generating executive summaries

        Returns:
            str: Path to generated report
        """
        logger.info("Generating Tier 3 Monthly Archive (30 days, all priorities)")

        # Calculate priority for all articles
        for article in articles:
            article['priority'] = self._calculate_priority(article)

        # Include all articles, sort by priority
        articles.sort(key=lambda x: x['priority']['score'], reverse=True)

        # Generate overall executive summary if summarizer provided
        executive_summary = None
        if summarizer:
            try:
                logger.info("Generating overall executive summary...")
                executive_summary = summarizer.create_summary(articles, max_articles=20)
                logger.info("✓ Executive summary generated")
            except Exception as e:
                logger.error(f"Failed to generate executive summary: {e}")

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_path = os.path.join(output_dir, f'threat_intel_tier3_report_{timestamp}.html')

        html_content = self._generate_tier_html(
            title="Threat Intelligence - Tier 3 Monthly Archive",
            subtitle="All Threat Intelligence (30 days)",
            articles=articles,
            tier=3,
            executive_summary=executive_summary,
            summarizer=summarizer
        )
        
        os.makedirs(output_dir, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        logger.info(f"Tier 3 HTML report generated: {output_path}")
        return output_path
    
    def _categorize_by_source(self, articles):
        """
        Categorize articles by source for better organization.

        Args:
            articles (list): List of article dictionaries

        Returns:
            dict: Articles organized by source
        """
        from collections import OrderedDict

        # Define primary threat intel sources
        primary_sources = [
            'Krebs on Security',
            'The Hacker News',
            'Info Security Magazine',
            'DarkReading',
            'Microsoft Security Blog',
            'Cisco Talos Intelligence',
            'Palo Alto Unit 42',
            'Google Threat Analysis Group',
            'Mandiant',
            'CrowdStrike Blog',
            'SentinelLabs',
            'Sophos Blog',
            'ESET Research',
            'Trend Micro Research',
            'Recorded Future',
            'Proofpoint Threat Insight',
            'Bleeping Computer',
            'CISA Alerts',
            'SANS Internet Storm Center',
            'TrustedSec',
            'Rapid7',
            'Black Hills InfoSec',
            'Ars Technica Security',
            'Other Sources'
        ]

        # Initialize all sources with empty lists
        sources = OrderedDict({source: [] for source in primary_sources})

        for article in articles:
            source_name = article.get('source', 'Unknown')

            # Map to primary source category
            categorized = False
            for primary in primary_sources[:-1]:  # Exclude "Other Sources"
                if primary.lower() in source_name.lower():
                    sources[primary].append(article)
                    categorized = True
                    break

            if not categorized:
                sources['Other Sources'].append(article)

        # Remove empty source categories
        return OrderedDict({k: v for k, v in sources.items() if v})

    def _generate_tier_html(self, title, subtitle, articles, tier, executive_summary=None, summarizer=None):
        """Generate professional HTML report matching Defender/MS Products style"""
        import markdown
        import re
        from collections import OrderedDict

        # Get AI model attribution
        ai_model_info = self._get_ai_model_attribution()

        # Calculate statistics
        priority_counts = {'CRITICAL': 0, 'HIGH': 0, 'MEDIUM': 0, 'LOW': 0}
        ioc_count = 0

        for article in articles:
            priority_counts[article['priority']['level']] += 1
            if article.get('iocs'):
                ioc_count += sum(len(v) for v in article['iocs'].values())

        # Categorize by source
        sources = self._categorize_by_source(articles)

        # Generate per-source executive summaries if summarizer provided
        source_summaries = {}
        if summarizer:
            for source_name, source_articles in sources.items():
                try:
                    logger.info(f"Generating executive summary for {source_name}...")
                    source_summary = summarizer.create_summary(source_articles, max_articles=10)
                    source_summaries[source_name] = source_summary
                    logger.info(f"✓ Summary generated for {source_name}")
                except Exception as e:
                    logger.error(f"Failed to generate summary for {source_name}: {e}")

        # Generate the professional HTML report
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}

        body {{
            font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
            line-height: 1.6;
            color: #323130;
            background: #faf9f8;
        }}

        .container {{
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }}

        /* Header Styles */
        .header {{
            background: linear-gradient(135deg, #0078d4 0%, #106ebe 100%);
            color: white;
            padding: 40px 30px;
            border-radius: 8px;
            margin-bottom: 30px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        }}

        .header h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
            font-weight: 600;
        }}

        .header .subtitle {{
            font-size: 1.2em;
            opacity: 0.95;
            margin-bottom: 5px;
        }}

        .header .date {{
            opacity: 0.85;
            font-size: 0.95em;
        }}

        .header .ai-model {{
            margin-top: 15px;
            padding: 10px 20px;
            background: rgba(255, 255, 255, 0.15);
            border-radius: 6px;
            font-size: 0.9em;
            display: inline-block;
            border: 1px solid rgba(255, 255, 255, 0.3);
        }}

        .header .ai-model .badge {{
            background: rgba(255, 255, 255, 0.25);
            padding: 3px 10px;
            border-radius: 4px;
            margin-left: 8px;
            font-weight: 600;
            font-size: 0.95em;
        }}

        /* Statistics Grid */
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 40px;
        }}

        .stat-card {{
            background: white;
            padding: 25px;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            text-align: center;
            border-top: 4px solid #0078d4;
        }}

        .stat-value {{
            font-size: 2.5em;
            font-weight: 700;
            color: #0078d4;
            line-height: 1;
        }}

        .stat-label {{
            color: #605e5c;
            font-size: 0.95em;
            margin-top: 8px;
        }}

        .stat-card.critical {{ border-top-color: #d13438; }}
        .stat-card.critical .stat-value {{ color: #d13438; }}

        .stat-card.high {{ border-top-color: #ff8c00; }}
        .stat-card.high .stat-value {{ color: #ff8c00; }}

        /* Executive Summary - Enhanced Visual Hierarchy */
        .executive-summary {{
            background: linear-gradient(135deg, #f8fbff 0%, #f0f7ff 100%);
            padding: 40px;
            border-radius: 12px;
            border-left: 5px solid #0078d4;
            margin-bottom: 40px;
            box-shadow: 0 4px 16px rgba(0, 120, 212, 0.08);
        }}

        .executive-summary > h3:first-child {{
            color: #0078d4;
            margin-bottom: 30px;
            font-size: 1.8em;
            border-bottom: 2px solid #0078d4;
            padding-bottom: 12px;
        }}

        /* Section headings within executive summary (h2 converted to h4) */
        .executive-summary h2 {{
            color: #0078d4;
            font-size: 1.4em;
            margin-top: 32px;
            margin-bottom: 16px;
            padding-top: 24px;
            padding-bottom: 8px;
            border-top: 1px solid #d0e3f5;
            border-bottom: none;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 10px;
        }}

        .executive-summary h2:first-of-type {{
            margin-top: 0;
            padding-top: 0;
            border-top: none;
        }}

        /* Add visual icons before section headings */
        .executive-summary h2::before {{
            content: '';
            display: inline-block;
            width: 4px;
            height: 24px;
            background: #0078d4;
            border-radius: 2px;
            margin-right: 8px;
        }}

        .executive-summary h4,
        .executive-summary h5 {{
            color: #005a9e;
            margin-top: 24px;
            margin-bottom: 12px;
            font-size: 1.15em;
        }}

        /* Paragraphs in executive summary */
        .executive-summary > p,
        .executive-summary > div > p {{
            margin-bottom: 16px;
            line-height: 1.85;
            color: #323130;
            font-size: 1.02em;
        }}

        /* First paragraph after heading - slightly emphasized */
        .executive-summary h2 + p {{
            font-size: 1.05em;
            color: #201f1e;
        }}

        /* Numbered lists - for prioritized items */
        .executive-summary ol {{
            margin: 20px 0 24px 0;
            padding-left: 0;
            list-style: none;
            counter-reset: threat-counter;
        }}

        .executive-summary ol > li {{
            counter-increment: threat-counter;
            position: relative;
            padding: 16px 16px 16px 56px;
            margin-bottom: 12px;
            background: white;
            border-radius: 8px;
            border: 1px solid #e1e5e8;
            box-shadow: 0 2px 4px rgba(0,0,0,0.04);
            line-height: 1.7;
        }}

        .executive-summary ol > li::before {{
            content: counter(threat-counter);
            position: absolute;
            left: 16px;
            top: 50%;
            transform: translateY(-50%);
            width: 28px;
            height: 28px;
            background: #0078d4;
            color: white;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 600;
            font-size: 0.9em;
        }}

        /* Bullet lists - for risk categories and general items */
        .executive-summary ul {{
            margin: 20px 0 24px 0;
            padding-left: 0;
            list-style: none;
        }}

        .executive-summary ul > li {{
            position: relative;
            padding: 14px 16px 14px 40px;
            margin-bottom: 10px;
            background: white;
            border-radius: 8px;
            border-left: 4px solid #0078d4;
            box-shadow: 0 2px 4px rgba(0,0,0,0.04);
            line-height: 1.7;
        }}

        .executive-summary ul > li::before {{
            content: '';
            position: absolute;
            left: 16px;
            top: 22px;
            width: 8px;
            height: 8px;
            background: #0078d4;
            border-radius: 50%;
        }}

        /* Bold text styling within lists */
        .executive-summary li strong {{
            color: #0078d4;
            font-weight: 600;
        }}

        /* Risk category styling - special highlight for impact assessment */
        .executive-summary li strong:first-child {{
            display: inline-block;
            min-width: 140px;
        }}

        /* Source Summary - Matches Executive Summary Style */
        .source-summary {{
            background: linear-gradient(135deg, #fafbfc 0%, #f5f7f9 100%);
            padding: 28px;
            border-radius: 10px;
            border-left: 4px solid #0078d4;
            margin: 24px 0;
            box-shadow: 0 2px 8px rgba(0,0,0,0.04);
        }}

        .source-summary h4 {{
            color: #0078d4;
            margin-bottom: 20px;
            font-size: 1.25em;
            font-weight: 600;
            padding-bottom: 10px;
            border-bottom: 1px solid #e1e5e8;
        }}

        .source-summary h2 {{
            color: #0078d4;
            font-size: 1.2em;
            margin-top: 24px;
            margin-bottom: 12px;
            padding-top: 16px;
            border-top: 1px solid #e1e5e8;
            font-weight: 600;
        }}

        .source-summary h2:first-of-type {{
            margin-top: 0;
            padding-top: 0;
            border-top: none;
        }}

        .source-summary h5 {{
            color: #005a9e;
            margin-top: 18px;
            margin-bottom: 10px;
            font-size: 1.08em;
        }}

        .source-summary > p {{
            line-height: 1.75;
            margin-bottom: 14px;
            color: #323130;
        }}

        /* Numbered lists in source summaries */
        .source-summary ol {{
            margin: 16px 0 20px 0;
            padding-left: 0;
            list-style: none;
            counter-reset: source-counter;
        }}

        .source-summary ol > li {{
            counter-increment: source-counter;
            position: relative;
            padding: 12px 12px 12px 44px;
            margin-bottom: 8px;
            background: white;
            border-radius: 6px;
            border: 1px solid #e8eaec;
            line-height: 1.65;
        }}

        .source-summary ol > li::before {{
            content: counter(source-counter);
            position: absolute;
            left: 12px;
            top: 50%;
            transform: translateY(-50%);
            width: 22px;
            height: 22px;
            background: #0078d4;
            color: white;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 600;
            font-size: 0.8em;
        }}

        /* Bullet lists in source summaries */
        .source-summary ul {{
            margin: 16px 0 20px 0;
            padding-left: 0;
            list-style: none;
        }}

        .source-summary ul > li {{
            position: relative;
            padding: 10px 12px 10px 32px;
            margin-bottom: 6px;
            background: white;
            border-radius: 6px;
            border-left: 3px solid #0078d4;
            line-height: 1.65;
        }}

        .source-summary ul > li::before {{
            content: '';
            position: absolute;
            left: 12px;
            top: 18px;
            width: 6px;
            height: 6px;
            background: #0078d4;
            border-radius: 50%;
        }}

        .source-summary li strong {{
            color: #0078d4;
            font-weight: 600;
        }}

        .source-summary strong {{
            color: #323130;
            font-weight: 600;
        }}

        /* Source Navigation */
        .source-nav {{
            background: white;
            padding: 25px;
            border-radius: 8px;
            margin-bottom: 30px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        }}

        .source-nav h2 {{
            color: #0078d4;
            margin-bottom: 20px;
            font-size: 1.4em;
        }}

        .source-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
            gap: 12px;
        }}

        .source-link {{
            display: block;
            padding: 12px 16px;
            background: #f3f2f1;
            border-radius: 6px;
            text-decoration: none;
            color: #323130;
            transition: all 0.2s;
            border-left: 3px solid #0078d4;
        }}

        .source-link:hover {{
            background: #0078d4;
            color: white;
            transform: translateX(3px);
        }}

        .source-count {{
            float: right;
            background: #0078d4;
            color: white;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 0.85em;
            font-weight: 600;
        }}

        .source-link:hover .source-count {{
            background: white;
            color: #0078d4;
        }}

        /* Source Sections */
        .source-section {{
            background: white;
            padding: 30px;
            border-radius: 8px;
            margin-bottom: 30px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        }}

        .source-section h2 {{
            color: #0078d4;
            font-size: 1.8em;
            margin-bottom: 20px;
            padding-bottom: 15px;
            border-bottom: 2px solid #f3f2f1;
        }}

        /* Article Styles */
        .article {{
            border-left: 4px solid #d2d0ce;
            padding: 20px;
            margin: 15px 0;
            background: #faf9f8;
            border-radius: 4px;
            cursor: pointer;
            transition: all 0.3s;
        }}

        .article:hover {{
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            transform: translateX(2px);
        }}

        .article.CRITICAL {{ border-left-color: #d13438; }}
        .article.HIGH {{ border-left-color: #ff8c00; }}
        .article.MEDIUM {{ border-left-color: #ffb900; }}
        .article.LOW {{ border-left-color: #5c5c5c; }}

        .article-header {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 15px;
        }}

        .priority-badge {{
            display: inline-block;
            padding: 6px 14px;
            border-radius: 4px;
            font-weight: 600;
            font-size: 0.85em;
            color: white;
            white-space: nowrap;
        }}

        .priority-badge.CRITICAL {{ background: #d13438; }}
        .priority-badge.HIGH {{ background: #ff8c00; }}
        .priority-badge.MEDIUM {{ background: #ffb900; color: #323130; }}
        .priority-badge.LOW {{ background: #8a8886; }}

        .article-title {{
            font-size: 1.3em;
            color: #0078d4;
            margin: 10px 0;
            flex: 1;
        }}

        .article-title a {{
            color: inherit;
            text-decoration: none;
        }}

        .article-title a:hover {{
            text-decoration: underline;
        }}

        .article-meta {{
            color: #605e5c;
            font-size: 0.9em;
            margin: 8px 0;
        }}

        .article-content {{
            margin-top: 15px;
            display: none;
            animation: slideDown 0.3s ease;
        }}

        .article.expanded .article-content {{
            display: block;
        }}

        .article-preview {{
            color: #605e5c;
            margin: 10px 0;
            font-size: 0.95em;
        }}

        .article-content h4 {{
            color: #0078d4;
            font-size: 1.1em;
            margin-top: 15px;
            margin-bottom: 10px;
        }}

        .article-content h5 {{
            color: #005a9e;
            font-size: 1em;
            margin-top: 12px;
            margin-bottom: 8px;
        }}

        .article-content table {{
            width: 100%;
            border-collapse: collapse;
            margin: 15px 0;
            font-size: 0.9em;
            background: white;
        }}

        .article-content table th,
        .article-content table td {{
            border: 1px solid #d2d0ce;
            padding: 10px 12px;
            text-align: left;
        }}

        .article-content table th {{
            background: #f3f2f1;
            font-weight: 600;
            color: #323130;
        }}

        .article-content table tr:nth-child(even) {{
            background: #faf9f8;
        }}

        .article-content p {{
            margin-bottom: 12px;
            line-height: 1.7;
        }}

        .article-content ul,
        .article-content ol {{
            margin: 10px 0 10px 25px;
        }}

        .article-content li {{
            margin-bottom: 6px;
            line-height: 1.6;
        }}

        .article-content strong {{
            color: #323130;
        }}

        .article-content em {{
            font-style: italic;
            color: #605e5c;
        }}

        .article-content code {{
            background: #f3f2f1;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: 'Consolas', 'Monaco', monospace;
            font-size: 0.9em;
            color: #e81123;
        }}

        .article-content pre {{
            background: #f3f2f1;
            padding: 12px;
            border-radius: 6px;
            overflow-x: auto;
            margin: 15px 0;
        }}

        .article-content pre code {{
            background: none;
            padding: 0;
            color: #323130;
        }}

        .article-content blockquote {{
            border-left: 4px solid #0078d4;
            padding-left: 15px;
            margin: 15px 0;
            color: #605e5c;
            font-style: italic;
        }}

        @keyframes slideDown {{
            from {{ opacity: 0; transform: translateY(-10px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}

        .iocs-section {{
            background: #fff4e5;
            padding: 15px;
            border-radius: 6px;
            margin-top: 15px;
            border-left: 3px solid #ff8c00;
        }}

        .ioc-title {{
            font-weight: 600;
            color: #323130;
            margin-bottom: 10px;
        }}

        .ioc {{
            display: inline-block;
            font-family: 'Consolas', 'Monaco', monospace;
            background: white;
            padding: 4px 10px;
            margin: 3px;
            border-radius: 4px;
            font-size: 0.9em;
            border: 1px solid #d2d0ce;
        }}

        .expand-icon {{
            float: right;
            color: #0078d4;
            font-size: 0.9em;
            transition: transform 0.3s;
        }}

        .article.expanded .expand-icon {{
            transform: rotate(180deg);
        }}

        @media print {{
            body {{ background: white; }}
            .article {{ page-break-inside: avoid; }}
            .source-nav {{ display: none; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{title}</h1>
            <div class="subtitle">{subtitle}</div>
            <div class="date">Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</div>
            <div class="ai-model">
                {ai_model_info['display']}
                <span class="badge">{ai_model_info['provider_type']}</span>
            </div>
        </div>

        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value">{len(articles)}</div>
                <div class="stat-label">Total Threats</div>
            </div>
            <div class="stat-card critical">
                <div class="stat-value">{priority_counts['CRITICAL']}</div>
                <div class="stat-label">Critical</div>
            </div>
            <div class="stat-card high">
                <div class="stat-value">{priority_counts['HIGH']}</div>
                <div class="stat-label">High Priority</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{ioc_count}</div>
                <div class="stat-label">IOCs Identified</div>
            </div>
        </div>
"""

        # Add overall executive summary if available
        if executive_summary:
            exec_text = executive_summary.get('executive_summary', '')
            # Fix formatting issues before conversion
            exec_text = self._fix_markdown_formatting(exec_text)
            # Apply Claude-specific formatting fixes if using Claude provider
            exec_text = self._fix_claude_formatting(exec_text)
            exec_summary_html = markdown.markdown(
                exec_text,
                extensions=['tables', 'fenced_code', 'nl2br', 'sane_lists', 'md_in_html']
            )
            html += f"""
        <div class="executive-summary">
            <h3>📊 Executive Summary</h3>
            {exec_summary_html}
        </div>
"""

        html += f"""
        <div class="source-nav">
            <h2>📰 Quick Navigation - {len(sources)} Sources</h2>
            <div class="source-grid">
"""

        for source_name, source_articles in sources.items():
            safe_id = source_name.replace(' ', '-').replace("'", "")
            html += f'                <a href="#{safe_id}" class="source-link">{source_name}<span class="source-count">{len(source_articles)}</span></a>\n'

        html += """            </div>
        </div>
"""

        # Generate source sections
        for source_name, source_articles in sources.items():
            # Sort articles by published date (newest first)
            from dateutil import parser as date_parser

            def get_article_datetime(article):
                """Helper to parse article published_date for sorting"""
                try:
                    published_dt = date_parser.parse(article.get('published_date', ''))
                    # Convert to naive datetime if timezone-aware
                    if published_dt.tzinfo is not None:
                        published_dt = published_dt.replace(tzinfo=None) - published_dt.utcoffset()
                    return published_dt
                except (ValueError, TypeError):
                    # If can't parse date, put at the end (use epoch)
                    return datetime(1970, 1, 1)

            source_articles.sort(key=get_article_datetime, reverse=True)

            safe_id = source_name.replace(' ', '-').replace("'", "")
            html += f"""
        <div class="source-section" id="{safe_id}">
            <h2>{source_name} ({len(source_articles)} article{'s' if len(source_articles) != 1 else ''})</h2>
"""

            # Add source-specific executive summary if available
            if source_name in source_summaries:
                source_exec_summary = source_summaries[source_name]
                source_text = source_exec_summary.get('executive_summary', '')
                # Fix formatting issues before conversion
                source_text = self._fix_markdown_formatting(source_text)
                # Apply Claude-specific formatting fixes if using Claude provider
                source_text = self._fix_claude_formatting(source_text)
                source_summary_html = markdown.markdown(
                    source_text,
                    extensions=['tables', 'fenced_code', 'nl2br', 'sane_lists', 'md_in_html']
                )
                html += f"""
            <div class="source-summary">
                <h4>📝 {source_name} Summary</h4>
                {source_summary_html}
            </div>
"""

            for article in source_articles:
                priority = article['priority']
                title = article.get('title', 'Untitled')
                url = article.get('url', '#')
                published_date = article.get('published_date', 'Unknown')
                summary = article.get('summary', '')

                # Convert markdown to HTML and downgrade heading levels to avoid conflicts
                # h2 -> h4, h3 -> h5, etc. so they don't interfere with source section h2
                if summary:
                    # First, clean any AI thinking tags
                    summary = self._clean_thinking_tags(summary)
                    # Clean prompt artifacts that may have leaked into summaries
                    summary = clean_summary_artifacts(summary)
                    # Validate CVEs and add warnings for suspicious ones
                    summary, _ = validate_cves_in_text(summary)

                    # Fix common markdown formatting issues (trailing spaces, dashes, etc.)
                    summary = self._fix_markdown_formatting(summary)

                    # Then replace any h2/h3 tags that might already be in the summary content
                    summary = summary.replace('<h2>', '<h4>').replace('</h2>', '</h4>')
                    summary = summary.replace('<h3>', '<h5>').replace('</h3>', '</h5>')

                    # Then convert markdown to HTML with ALL necessary extensions
                    summary_html = markdown.markdown(
                        summary,
                        extensions=[
                            'tables',           # Support for markdown tables
                            'fenced_code',      # Support for code blocks
                            'nl2br',           # Convert newlines to <br>
                            'sane_lists',      # Better list handling
                            'md_in_html'       # Allow markdown inside HTML tags
                        ]
                    )

                    # Finally, replace any h2/h3 that might have come from markdown conversion
                    summary_html = summary_html.replace('<h2>', '<h4>').replace('</h2>', '</h4>')
                    summary_html = summary_html.replace('<h3>', '<h5>').replace('</h3>', '</h5>')
                else:
                    summary_html = '<p>No summary available</p>'

                # Extract preview (first sentence or 150 chars) - use cleaned summary before HTML changes
                preview_text = self._clean_thinking_tags(article.get('summary', ''))
                preview_text = clean_summary_artifacts(preview_text)
                preview = preview_text[:150] + '...' if len(preview_text) > 150 else preview_text

                html += f"""
            <div class="article {priority['level']}" onclick="this.classList.toggle('expanded')">
                <div class="article-header">
                    <div>
                        <span class="priority-badge {priority['level']}">{priority['level']}</span>
                    </div>
                    <span class="expand-icon">▼</span>
                </div>
                <h3 class="article-title"><a href="{url}" target="_blank" onclick="event.stopPropagation()">{title}</a></h3>
                <div class="article-meta">Published: {published_date}</div>
                <div class="article-preview">{preview}</div>
                <div class="article-content">
                    {summary_html}
"""

                # IOC section removed - was generating too many false positives
                # (e.g., news site domains being flagged as IOCs)

                html += """                </div>
            </div>
"""

            html += "        </div>\n"

        html += """    </div>
    <script>
        // Keyboard shortcuts
        document.addEventListener('keydown', function(e) {
            if (e.key === 'e') {
                document.querySelectorAll('.article').forEach(a => a.classList.add('expanded'));
            } else if (e.key === 'c') {
                document.querySelectorAll('.article').forEach(a => a.classList.remove('expanded'));
            }
        });
    </script>
</body>
</html>"""

        return html
