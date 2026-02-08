"""
Third-party Security Product reporting module.
Handles generation of security product update reports for third-party security tools.
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


class ThirdPartySecurityReportGenerator:
    """Generates third-party security product update reports"""

    LAST_REPORT_FILE = '.last_report_time'

    def __init__(self, template_dir=None, ai_config=None, tracker_config=None):
        """
        Initialize the third-party security report generator.

        Args:
            template_dir (str, optional): Directory containing report templates
            ai_config (dict, optional): AI configuration for model attribution
            tracker_config (dict, optional): Tracker configuration with vendor_styles
        """
        if template_dir is None:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            template_dir = os.path.join(current_dir, 'templates')

        os.makedirs(template_dir, exist_ok=True)

        self.env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=select_autoescape(['html', 'xml'])
        )

        # Store AI config for model attribution in reports
        self.ai_config = ai_config

        # Store tracker config for vendor styles
        self.tracker_config = tracker_config or {}

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
        """Remove trailing questions that the AI might have added."""
        if not text:
            return text

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
        """Prepare articles for reporting."""
        logger.info(f"Processing {len(articles)} security product updates for report")

        for article in articles:
            if 'summary' in article and article['summary']:
                article['summary'] = self._remove_trailing_questions(article['summary'])

            article['source_type'] = self._get_source_type(article.get('vendor', ''))
            article['preview'] = self._extract_preview(article.get('summary', ''))
            article['availability'] = self._detect_availability(article)
            article['date_info'] = self._format_date_info(article.get('published_date'))

        return articles

    def _format_date_info(self, published_date):
        """Format date information for display."""
        if not published_date:
            return {'formatted_date': 'Unknown', 'age_category': 'unknown', 'age_text': 'Unknown'}

        try:
            from dateutil import parser as date_parser
            if isinstance(published_date, str):
                pub_date = date_parser.parse(published_date)
            else:
                pub_date = published_date

            # Make timezone-naive
            if hasattr(pub_date, 'tzinfo') and pub_date.tzinfo:
                pub_date = pub_date.replace(tzinfo=None)

            now = datetime.now()
            delta = now - pub_date

            formatted_date = pub_date.strftime('%B %d, %Y')

            if delta.days == 0:
                return {'formatted_date': formatted_date, 'age_category': 'today', 'age_text': 'Today'}
            elif delta.days <= 3:
                return {'formatted_date': formatted_date, 'age_category': 'new', 'age_text': f'{delta.days}d ago'}
            elif delta.days <= 7:
                return {'formatted_date': formatted_date, 'age_category': 'recent', 'age_text': f'{delta.days}d ago'}
            else:
                return {'formatted_date': formatted_date, 'age_category': 'older', 'age_text': formatted_date}

        except Exception:
            return {'formatted_date': str(published_date), 'age_category': 'unknown', 'age_text': str(published_date)}

    def _detect_availability(self, article):
        """Detect the availability status of a feature/update."""
        title = article.get('title', '').lower()
        summary = article.get('summary', '').lower()
        content = article.get('content', '').lower()
        combined = f"{title} {summary} {content}"

        # Check for deprecated features
        deprecation_phrases = [
            'deprecated', 'end of life', 'eol', 'retiring', 'retired',
            'sunset', 'discontinued', 'no longer supported'
        ]

        if any(phrase in combined for phrase in deprecation_phrases):
            return {
                'status': 'deprecated',
                'label': 'Deprecated',
                'color': '#d13438'
            }

        # Check for preview features
        preview_keywords = ['preview', 'beta', 'coming soon', 'early access']
        ga_keywords = ['generally available', 'now available', 'ga release', 'released', 'launched']

        has_preview = any(keyword in combined for keyword in preview_keywords)
        has_ga = any(keyword in combined for keyword in ga_keywords)

        if has_ga and not has_preview:
            return {
                'status': 'ga',
                'label': 'GA',
                'color': '#107c10'
            }
        elif has_preview:
            return {
                'status': 'preview',
                'label': 'Preview',
                'color': '#ffb900'
            }

        return None

    def _extract_preview(self, summary, max_chars=200):
        """Extract a short preview from the article summary."""
        if not summary:
            return ''

        # Remove markdown formatting
        clean_text = summary
        clean_text = re.sub(r'^\|.*\|$', '', clean_text, flags=re.MULTILINE)
        clean_text = re.sub(r'^[\s]*[-|:]+[\s]*$', '', clean_text, flags=re.MULTILINE)
        clean_text = re.sub(r'^#+\s+.*$', '', clean_text, flags=re.MULTILINE)
        clean_text = re.sub(r'\*+([^*]+)\*+', r'\1', clean_text)
        clean_text = re.sub(r'^[\s]*[-*•]\s+', '', clean_text, flags=re.MULTILINE)
        clean_text = ' '.join(clean_text.split())

        if not clean_text:
            return ''

        if len(clean_text) > max_chars:
            clean_text = clean_text[:max_chars].rsplit(' ', 1)[0] + '...'

        return clean_text.strip()

    def _get_source_type(self, vendor):
        """Classify the vendor into a source type for display."""
        vendor_lower = vendor.lower() if vendor else ''

        # Get vendor styles from config (if available)
        vendor_styles = self.tracker_config.get('vendor_styles', {})

        for key, info in vendor_styles.items():
            if key.lower() in vendor_lower:
                return info

        # Fallback for unknown vendors - generate consistent styling
        return {'type': 'other', 'label': vendor or 'Other', 'color': '#666666'}

    def _categorize_by_vendor(self, articles):
        """Categorize articles by vendor dynamically based on actual article data."""
        products = defaultdict(list)

        for article in articles:
            # Use vendor field if available, fall back to product, then source, then 'Other'
            vendor = article.get('vendor', '').strip()
            if not vendor:
                vendor = article.get('product', '').strip()
            if not vendor:
                vendor = article.get('source', '').strip()
            if not vendor:
                vendor = 'Other'

            products[vendor].append(article)

        # Sort vendors alphabetically, but put 'Other' at the end
        sorted_products = {}
        for vendor in sorted(products.keys()):
            if vendor != 'Other':
                sorted_products[vendor] = products[vendor]
        if 'Other' in products:
            sorted_products['Other'] = products['Other']

        return sorted_products

    def _calculate_stats(self, articles):
        """Calculate statistics for the report."""
        stats = {
            'new_features': 0,
            'bug_fixes': 0,
            'security_patches': 0,
            'performance_improvements': 0,
            'deprecations': 0,
            'integrations': 0,
            'platform_updates': 0
        }

        for article in articles:
            update_types = article.get('update_type', [])
            for update_type in update_types:
                ut_lower = update_type.lower()
                if 'feature' in ut_lower:
                    stats['new_features'] += 1
                elif 'bug' in ut_lower or 'fix' in ut_lower:
                    stats['bug_fixes'] += 1
                elif 'security' in ut_lower:
                    stats['security_patches'] += 1
                elif 'performance' in ut_lower:
                    stats['performance_improvements'] += 1
                elif 'deprecat' in ut_lower:
                    stats['deprecations'] += 1
                elif 'integration' in ut_lower:
                    stats['integrations'] += 1
                elif 'platform' in ut_lower or 'general' in ut_lower:
                    stats['platform_updates'] += 1

        return stats

    def _get_last_report_time(self, output_dir):
        """Get the timestamp of the last report generation."""
        last_report_file = os.path.join(output_dir, self.LAST_REPORT_FILE)
        if os.path.exists(last_report_file):
            try:
                with open(last_report_file, 'r') as f:
                    timestamp = f.read().strip()
                    return datetime.fromisoformat(timestamp)
            except Exception:
                pass
        return None

    def _save_last_report_time(self, output_dir):
        """Save the current timestamp as the last report time."""
        last_report_file = os.path.join(output_dir, self.LAST_REPORT_FILE)
        try:
            with open(last_report_file, 'w') as f:
                f.write(datetime.now().isoformat())
        except Exception as e:
            logger.warning(f"Could not save last report time: {e}")

    def _identify_new_articles(self, articles, last_report_time):
        """Identify which articles are new since the last report."""
        if not last_report_time:
            return articles, []

        new_articles = []
        existing_articles = []

        from dateutil import parser as date_parser

        for article in articles:
            scraped_date = article.get('scraped_date')
            if scraped_date:
                try:
                    if isinstance(scraped_date, str):
                        scraped = date_parser.parse(scraped_date)
                    else:
                        scraped = scraped_date

                    if hasattr(scraped, 'tzinfo') and scraped.tzinfo:
                        scraped = scraped.replace(tzinfo=None)

                    if scraped > last_report_time:
                        new_articles.append(article)
                    else:
                        existing_articles.append(article)
                except Exception:
                    existing_articles.append(article)
            else:
                existing_articles.append(article)

        return new_articles, existing_articles

    def generate_security_product_report(self, executive_summary, articles, output_dir, time_period="last 30 days", summarizer=None):
        """Generate the main security product report."""
        os.makedirs(output_dir, exist_ok=True)

        # Get last report time and identify new articles
        last_report_time = self._get_last_report_time(output_dir)
        new_articles, existing_articles = self._identify_new_articles(articles, last_report_time)

        # Prepare articles
        prepared_articles = self._prepare_articles(articles)

        # Categorize by vendor
        products = self._categorize_by_vendor(prepared_articles)

        # Calculate stats
        stats = self._calculate_stats(prepared_articles)

        # Convert executive summary markdown to HTML
        exec_summary_html = ""
        if executive_summary and executive_summary.get('summary'):
            md = markdown.Markdown(extensions=[TableExtension(), Nl2BrExtension()])
            exec_summary_html = md.convert(executive_summary['summary'])

        # Generate vendor-specific summaries if summarizer is provided
        product_summaries = {}
        if summarizer and len(products) > 0:
            logger.info("Generating vendor-specific summaries...")
            # Create a dict of raw articles (before HTML conversion) by vendor for summarization
            raw_articles_by_vendor = self._categorize_by_vendor(self._prepare_articles(articles))
            product_summaries = summarizer.create_vendor_summaries(raw_articles_by_vendor, time_period)

        # Convert article summaries to HTML
        for article in prepared_articles:
            if article.get('summary'):
                md = markdown.Markdown(extensions=[TableExtension(), Nl2BrExtension()])
                article['summary'] = md.convert(article['summary'])

        # Prepare new articles for display
        new_articles_prepared = self._prepare_articles(new_articles) if new_articles else []

        # Generate report using template
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"thirdparty_security_report_{timestamp}.html"
        filepath = os.path.join(output_dir, filename)

        html = self._generate_tier_html(
            title="3rd Party Security Product Report",
            time_period=time_period,
            executive_summary=exec_summary_html,
            products=products,
            stats=stats,
            total_updates=len(prepared_articles),
            new_articles=new_articles_prepared,
            new_count=len(new_articles),
            existing_count=len(existing_articles),
            last_report_time=last_report_time.strftime('%B %d, %Y at %I:%M %p') if last_report_time else None,
            product_summaries=product_summaries
        )

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html)

        # Save last report time
        self._save_last_report_time(output_dir)

        logger.info(f"Generated report: {filepath}")
        return filepath

    def generate_tier1_digest(self, executive_summary, articles, output_dir, summarizer=None):
        """Generate Tier 1 weekly digest (7 days)."""
        return self.generate_security_product_report(
            executive_summary=executive_summary,
            articles=articles,
            output_dir=output_dir,
            time_period="last 7 days",
            summarizer=summarizer
        )

    def generate_tier2_biweekly(self, executive_summary, articles, output_dir, summarizer=None):
        """Generate Tier 2 bi-weekly report (14 days)."""
        return self.generate_security_product_report(
            executive_summary=executive_summary,
            articles=articles,
            output_dir=output_dir,
            time_period="last 14 days",
            summarizer=summarizer
        )

    def generate_tier3_archive(self, executive_summary, articles, output_dir, summarizer=None):
        """Generate Tier 3 monthly archive (30 days)."""
        return self.generate_security_product_report(
            executive_summary=executive_summary,
            articles=articles,
            output_dir=output_dir,
            time_period="last 30 days",
            summarizer=summarizer
        )

    def _generate_tier_html(self, title, time_period, executive_summary, products, stats,
                           total_updates, new_articles, new_count, existing_count, last_report_time,
                           product_summaries=None):
        """Generate HTML report content."""
        current_date = datetime.now().strftime('%B %d, %Y')

        # Get AI model attribution for display in report
        ai_model_info = self._get_ai_model_attribution()

        # Try to load template, fallback to inline HTML
        try:
            template = self.env.get_template('security_product_report_tiered.html')
            return template.render(
                title=title,
                date=current_date,
                time_period=time_period,
                executive_summary=executive_summary,
                products=products,
                stats=stats,
                total_updates=total_updates,
                new_articles=new_articles,
                new_count=new_count,
                existing_count=existing_count,
                last_report_time=last_report_time,
                product_summaries=product_summaries or {},
                ai_model_info=ai_model_info
            )
        except Exception as e:
            logger.warning(f"Template not found, using inline HTML: {e}")
            return self._generate_inline_html(
                title, current_date, time_period, executive_summary, products,
                stats, total_updates, new_articles, new_count, existing_count, last_report_time
            )

    def _generate_inline_html(self, title, current_date, time_period, executive_summary, products,
                              stats, total_updates, new_articles, new_count, existing_count, last_report_time):
        """Generate inline HTML when template is not available."""
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Segoe UI', sans-serif; line-height: 1.6; color: #333; background: #f5f5f5; padding: 20px; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; box-shadow: 0 2px 10px rgba(0,0,0,0.1); border-radius: 8px; }}
        .header {{ background: linear-gradient(135deg, #2d5a27 0%, #1a3518 100%); color: white; padding: 40px; text-align: center; }}
        .header h1 {{ font-size: 2.5em; margin-bottom: 10px; font-weight: 300; }}
        .header .subtitle {{ font-size: 1.1em; opacity: 0.9; }}
        .summary-stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 20px; padding: 40px; background: #f9f9f9; }}
        .stat-card {{ background: white; padding: 20px; border-radius: 8px; text-align: center; border-left: 4px solid #2d5a27; }}
        .stat-number {{ font-size: 2em; font-weight: bold; color: #2d5a27; }}
        .stat-label {{ font-size: 0.9em; color: #666; text-transform: uppercase; }}
        .content {{ padding: 40px; }}
        .section {{ margin-bottom: 40px; }}
        .section h2 {{ color: #2d5a27; font-size: 1.8em; margin-bottom: 20px; padding-bottom: 10px; border-bottom: 2px solid #2d5a27; }}
        .executive-summary {{ background: #e8f5e9; padding: 30px; border-radius: 8px; border-left: 4px solid #2d5a27; margin-bottom: 30px; }}
        .executive-summary h3 {{ color: #2d5a27; margin-bottom: 20px; }}
        .product-section {{ margin-bottom: 30px; background: #fafafa; padding: 25px; border-radius: 8px; }}
        .product-section h3 {{ color: #1a3518; margin-bottom: 15px; padding-bottom: 10px; border-bottom: 1px solid #ddd; }}
        .article {{ background: white; padding: 20px; margin-bottom: 15px; border-radius: 5px; border-left: 3px solid #2d5a27; }}
        .article h4 {{ color: #2d5a27; margin-bottom: 10px; }}
        .article h4 a {{ color: #2d5a27; text-decoration: none; }}
        .article h4 a:hover {{ text-decoration: underline; }}
        .article-meta {{ font-size: 0.85em; color: #666; margin-bottom: 10px; }}
        .article-summary {{ color: #444; line-height: 1.7; }}
        .article-summary table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
        .article-summary th {{ background: #2d5a27; color: white; padding: 10px; text-align: left; }}
        .article-summary td {{ padding: 10px; border: 1px solid #ddd; }}
        .tag {{ display: inline-block; background: #e8f5e9; color: #2d5a27; padding: 3px 10px; border-radius: 3px; font-size: 0.85em; margin: 2px; }}
        .footer {{ background: #f5f5f5; padding: 30px; text-align: center; color: #666; }}
        .new-badge {{ background: #ff6600; color: white; padding: 2px 8px; border-radius: 10px; font-size: 0.75em; margin-left: 8px; }}
        .whats-new-section {{ padding: 30px; background: #fff4e6; border-bottom: 3px solid #ff8800; margin-bottom: 20px; }}
        .whats-new-section h2 {{ color: #ff6600; text-align: center; margin-bottom: 15px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{title}</h1>
            <div class="subtitle">{current_date}</div>
            <div class="subtitle">Report Period: {time_period}</div>
        </div>

        <div class="summary-stats">
            <div class="stat-card">
                <div class="stat-number">{total_updates}</div>
                <div class="stat-label">Total Updates</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{stats.get('new_features', 0)}</div>
                <div class="stat-label">New Features</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{stats.get('bug_fixes', 0)}</div>
                <div class="stat-label">Bug Fixes</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{stats.get('security_patches', 0)}</div>
                <div class="stat-label">Security Patches</div>
            </div>
        </div>
"""

        # What's New section
        if new_count > 0:
            html += f"""
        <div class="whats-new-section">
            <h2>What's New Since Last Report</h2>
            <p style="text-align: center; margin-bottom: 20px;">
                <strong>{new_count}</strong> new update{'s' if new_count != 1 else ''} added
                {f'since {last_report_time}' if last_report_time else ''}
            </p>
        </div>
"""

        html += """
        <div class="content">
"""

        # Executive Summary
        if executive_summary:
            html += f"""
            <div class="executive-summary">
                <h3>Executive Summary</h3>
                {executive_summary}
            </div>
"""

        # Product sections
        html += """
            <div class="section">
                <h2>Updates by Vendor</h2>
"""

        for product_name, articles in products.items():
            html += f"""
                <div class="product-section">
                    <h3>{product_name} ({len(articles)} update{'s' if len(articles) != 1 else ''})</h3>
"""
            for article in articles:
                summary_html = article.get('summary', 'No summary available.')
                tags_html = ''
                if article.get('update_type'):
                    tags_html = ''.join([f'<span class="tag">{tag}</span>' for tag in article['update_type']])

                html += f"""
                    <div class="article">
                        <h4>
                            <a href="{article.get('url', '#')}" target="_blank">{article.get('title', 'Unknown')}</a>
                        </h4>
                        <div class="article-meta">
                            <span><strong>Published:</strong> {article.get('date_info', {}).get('formatted_date', 'Unknown')}</span>
                            <span style="margin-left: 15px;"><strong>Product:</strong> {article.get('product', 'Unknown')}</span>
                        </div>
                        <div class="article-summary">{summary_html}</div>
                        <div class="tags">{tags_html}</div>
                    </div>
"""
            html += """
                </div>
"""

        html += """
            </div>
        </div>

        <div class="footer">
            <p><strong>SecIntel AI - Security Intelligence Tracker</strong></p>
            <p>3rd Party Security Product Tracker</p>
            <p>Generated on """ + current_date + """</p>
        </div>
    </div>
</body>
</html>"""

        return html
