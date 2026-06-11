"""
YouTube Security reporting module.
Generates HTML reports for security YouTube channel content.
"""

import os
import logging
import re
from datetime import datetime
import markdown
from markdown.extensions.tables import TableExtension
from markdown.extensions.nl2br import Nl2BrExtension
from core.report_sanitizer import esc, safe_url, sanitize_html

logger = logging.getLogger(__name__)


class YouTubeSecurityReportGenerator:
    """Generates YouTube security channel reports."""

    LAST_REPORT_FILE = '.last_report_time'

    def _remove_trailing_questions(self, text):
        """Remove trailing questions the AI might have added."""
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
        for article in articles:
            if 'summary' in article and article['summary']:
                article['summary'] = self._remove_trailing_questions(article['summary'])

            article['channel_info'] = self._get_channel_info(article.get('product', ''))
            article['date_info'] = self._format_date_info(article.get('published_date'))

        return articles

    def _format_date_info(self, published_date):
        """Format date information for display."""
        if not published_date or published_date == 'None' or str(published_date).strip() == '':
            return {'formatted_date': 'Date not available', 'age_category': 'unknown', 'age_text': 'Recently added'}

        try:
            from dateutil import parser as date_parser
            if isinstance(published_date, str):
                pub_date = date_parser.parse(published_date)
            else:
                pub_date = published_date

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

    def _get_channel_info(self, channel):
        """Get channel display info with color."""
        channel_lower = channel.lower() if channel else ''

        channel_colors = {
            'john hammond': {'label': 'John Hammond', 'color': '#e53e3e'},
            'ippsec': {'label': 'IppSec', 'color': '#38a169'},
            'sans': {'label': 'SANS ISC', 'color': '#3182ce'},
            'black hills': {'label': 'Black Hills InfoSec', 'color': '#805ad5'},
            'networkchuck': {'label': 'NetworkChuck', 'color': '#dd6b20'},
            'cyber mentor': {'label': 'The Cyber Mentor', 'color': '#d69e2e'},
        }

        for key, info in channel_colors.items():
            if key in channel_lower:
                return info

        return {'label': channel or 'Unknown', 'color': '#718096'}

    def _categorize_by_channel(self, articles):
        """Group articles by channel (product field)."""
        channels = {}
        for article in articles:
            channel = article.get('product', article.get('source', 'Unknown'))
            if channel not in channels:
                channels[channel] = []
            channels[channel].append(article)
        return channels

    def _calculate_stats(self, articles):
        """Calculate content type statistics."""
        stats = {
            'threat_advisories': 0,
            'ctf_walkthroughs': 0,
            'tutorials': 0,
            'tool_reviews': 0,
            'security_news': 0,
            'general': 0
        }

        for article in articles:
            content_type = article.get('content_type', 'general_security')
            if isinstance(content_type, list):
                for ct in content_type:
                    ct_lower = ct.lower()
                    if 'threat' in ct_lower or 'advisory' in ct_lower:
                        stats['threat_advisories'] += 1
                    elif 'ctf' in ct_lower or 'walkthrough' in ct_lower:
                        stats['ctf_walkthroughs'] += 1
                    elif 'tutorial' in ct_lower:
                        stats['tutorials'] += 1
                    elif 'tool' in ct_lower or 'review' in ct_lower:
                        stats['tool_reviews'] += 1
                    elif 'news' in ct_lower:
                        stats['security_news'] += 1
                    else:
                        stats['general'] += 1
            else:
                ct_lower = content_type.lower() if content_type else 'general'
                if 'threat' in ct_lower or 'advisory' in ct_lower:
                    stats['threat_advisories'] += 1
                elif 'ctf' in ct_lower or 'walkthrough' in ct_lower:
                    stats['ctf_walkthroughs'] += 1
                elif 'tutorial' in ct_lower:
                    stats['tutorials'] += 1
                elif 'tool' in ct_lower or 'review' in ct_lower:
                    stats['tool_reviews'] += 1
                elif 'news' in ct_lower:
                    stats['security_news'] += 1
                else:
                    stats['general'] += 1

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
        """Identify articles new since last report."""
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

    def generate_report(self, executive_summary, articles, output_dir, time_period="last 30 days",
                        channel_summaries=None, model_name=None):
        """Generate a YouTube security report."""
        os.makedirs(output_dir, exist_ok=True)

        last_report_time = self._get_last_report_time(output_dir)
        new_articles, existing_articles = self._identify_new_articles(articles, last_report_time)

        prepared_articles = self._prepare_articles(articles)
        channels = self._categorize_by_channel(prepared_articles)
        stats = self._calculate_stats(prepared_articles)

        # Convert executive summary markdown to HTML
        exec_summary_html = ""
        if executive_summary and executive_summary.get('summary'):
            md = markdown.Markdown(extensions=[TableExtension(), Nl2BrExtension()])
            exec_summary_html = md.convert(executive_summary['summary'])
            # Downshift headings: the container already uses <h3>, so AI-generated
            # h3 -> h4 and h4 -> h5 to maintain proper hierarchy
            exec_summary_html = re.sub(r'<h4([^>]*)>', r'<h5\1>', exec_summary_html)
            exec_summary_html = re.sub(r'</h4>', '</h5>', exec_summary_html)
            exec_summary_html = re.sub(r'<h3([^>]*)>', r'<h4\1>', exec_summary_html)
            exec_summary_html = re.sub(r'</h3>', '</h4>', exec_summary_html)

        # Convert article summaries to HTML
        for article in prepared_articles:
            if article.get('summary'):
                md = markdown.Markdown(extensions=[TableExtension(), Nl2BrExtension()])
                article['summary'] = md.convert(article['summary'])

        new_articles_prepared = self._prepare_articles(new_articles) if new_articles else []

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"youtube_security_report_{timestamp}.html"
        filepath = os.path.join(output_dir, filename)

        html = self._generate_html(
            title="Security YouTube Channels Report",
            time_period=time_period,
            executive_summary=exec_summary_html,
            channels=channels,
            stats=stats,
            total_articles=len(prepared_articles),
            new_articles=new_articles_prepared,
            new_count=len(new_articles),
            existing_count=len(existing_articles),
            last_report_time=last_report_time.strftime('%B %d, %Y at %I:%M %p') if last_report_time else None,
            channel_summaries=channel_summaries or {},
            model_name=model_name
        )

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html)

        self._save_last_report_time(output_dir)
        logger.info(f"Generated report: {filepath}")
        return filepath

    def generate_tier1_digest(self, executive_summary, articles, output_dir, summarizer=None,
                              channel_summaries=None, model_name=None):
        """Generate Tier 1 weekly digest."""
        return self.generate_report(executive_summary, articles, output_dir,
                                    time_period="last 7 days", channel_summaries=channel_summaries,
                                    model_name=model_name)

    def generate_tier2_biweekly(self, executive_summary, articles, output_dir, summarizer=None,
                                channel_summaries=None, model_name=None):
        """Generate Tier 2 bi-weekly report."""
        return self.generate_report(executive_summary, articles, output_dir,
                                    time_period="last 14 days", channel_summaries=channel_summaries,
                                    model_name=model_name)

    def generate_tier3_archive(self, executive_summary, articles, output_dir, summarizer=None,
                               channel_summaries=None, model_name=None):
        """Generate Tier 3 monthly archive."""
        return self.generate_report(executive_summary, articles, output_dir,
                                    time_period="last 30 days", channel_summaries=channel_summaries,
                                    model_name=model_name)

    def _generate_report_with_tier(self, executive_summary, articles, output_dir, time_period,
                                   tier, tier_name, summarizer=None, channel_summaries=None,
                                   model_name=None):
        """Generate report with specific tier."""
        return self.generate_report(executive_summary, articles, output_dir,
                                    time_period=time_period, channel_summaries=channel_summaries,
                                    model_name=model_name)

    def _generate_html(self, title, time_period, executive_summary, channels, stats,
                       total_articles, new_articles, new_count, existing_count, last_report_time,
                       channel_summaries=None, model_name=None):
        """Generate inline HTML report."""

        channel_summaries = channel_summaries or {}
        model_name = model_name or "Unknown"
        current_date = datetime.now().strftime('%B %d, %Y')

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        html {{ scroll-behavior: smooth; }}
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #333; background: #f5f5f5; padding: 20px; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; box-shadow: 0 2px 10px rgba(0,0,0,0.1); border-radius: 8px; overflow: hidden; }}

        /* Header - YouTube red theme */
        .header {{ background: linear-gradient(135deg, #cc0000 0%, #8b0000 100%); color: white; padding: 40px; text-align: center; }}
        .header h1 {{ font-size: 2.5em; margin-bottom: 10px; font-weight: 300; }}
        .header .subtitle {{ font-size: 1.1em; opacity: 0.9; }}
        .header .ai-model {{ margin-top: 15px; padding: 10px 20px; background: rgba(255, 255, 255, 0.15); border-radius: 6px; font-size: 0.9em; display: inline-block; border: 1px solid rgba(255, 255, 255, 0.3); }}
        .header .ai-model .badge {{ background: rgba(255, 255, 255, 0.25); padding: 3px 10px; border-radius: 4px; margin-left: 8px; font-weight: 600; font-size: 0.95em; }}

        /* Stats Grid */
        .summary-stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; padding: 40px; background: #f9f9f9; border-bottom: 1px solid #e0e0e0; }}
        .stat-card {{ background: white; padding: 20px; border-radius: 8px; text-align: center; box-shadow: 0 2px 5px rgba(0,0,0,0.05); border-left: 4px solid #cc0000; }}
        .stat-card.threats {{ border-left-color: #e53e3e; }}
        .stat-card.ctf {{ border-left-color: #38a169; }}
        .stat-card.tutorials {{ border-left-color: #3182ce; }}
        .stat-number {{ font-size: 2.5em; font-weight: bold; color: #cc0000; margin-bottom: 5px; }}
        .stat-card.threats .stat-number {{ color: #e53e3e; }}
        .stat-card.ctf .stat-number {{ color: #38a169; }}
        .stat-card.tutorials .stat-number {{ color: #3182ce; }}
        .stat-label {{ font-size: 0.9em; color: #666; text-transform: uppercase; letter-spacing: 0.5px; }}

        /* Channel Summary Grid */
        .channel-summary {{ padding: 30px 40px; background: white; border-bottom: 1px solid #e0e0e0; }}
        .channel-summary h2 {{ color: #cc0000; font-size: 1.5em; margin-bottom: 20px; text-align: center; }}
        .channel-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 15px; }}
        .channel-item {{ background: #f9f9f9; padding: 15px 20px; border-radius: 5px; display: flex; justify-content: space-between; align-items: center; border-left: 3px solid #cc0000; transition: all 0.2s ease; cursor: pointer; text-decoration: none; color: inherit; }}
        .channel-item:hover {{ background: #fff0f0; transform: translateX(5px); box-shadow: 0 2px 8px rgba(204, 0, 0, 0.2); }}
        .channel-name {{ font-weight: 600; color: #333; font-size: 0.95em; }}
        .channel-count {{ background: #cc0000; color: white; padding: 5px 12px; border-radius: 15px; font-weight: bold; font-size: 0.9em; min-width: 30px; text-align: center; }}

        /* What's New Section */
        .whats-new-section {{ padding: 30px 40px; background: linear-gradient(135deg, #fff4e6 0%, #ffe8cc 100%); border-bottom: 3px solid #ff8800; }}
        .whats-new-section h2 {{ color: #ff6600; font-size: 1.8em; margin-bottom: 15px; text-align: center; }}
        .whats-new-summary {{ text-align: center; font-size: 1.1em; color: #555; margin-bottom: 25px; padding: 15px; background: white; border-radius: 8px; border: 2px solid #ff8800; }}
        .whats-new-summary strong {{ color: #ff6600; font-size: 1.3em; }}
        .whats-new-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); gap: 15px; }}
        .whats-new-item {{ background: white; padding: 15px; border-radius: 8px; border-left: 4px solid #ff8800; box-shadow: 0 2px 5px rgba(255, 136, 0, 0.15); }}
        .whats-new-item h4 a {{ color: #cc0000; text-decoration: none; }}
        .whats-new-item h4 a:hover {{ text-decoration: underline; }}
        .whats-new-item .meta {{ font-size: 0.85em; color: #666; margin-top: 5px; }}
        .new-badge {{ display: inline-block; background: #ff6600; color: white; padding: 2px 8px; border-radius: 10px; font-size: 0.75em; font-weight: bold; text-transform: uppercase; margin-left: 8px; }}

        /* Content Area */
        .content {{ padding: 40px; }}
        .section {{ margin-bottom: 40px; }}
        .section h2 {{ color: #cc0000; font-size: 1.8em; margin-bottom: 20px; padding-bottom: 10px; border-bottom: 2px solid #cc0000; }}

        /* Executive Summary */
        .executive-summary {{ background: #fff5f5; padding: 40px; border-radius: 8px; border-left: 4px solid #cc0000; margin-bottom: 30px; }}
        .executive-summary h3 {{ color: #cc0000; margin-bottom: 25px; font-size: 1.8em; border-bottom: 2px solid #cc0000; padding-bottom: 10px; }}
        .executive-summary h4, .executive-summary h5 {{ color: #8b0000; margin-top: 20px; margin-bottom: 10px; }}
        .executive-summary > p {{ margin-bottom: 18px; line-height: 1.8; }}
        .executive-summary > p:first-of-type {{ font-size: 1.15em; font-weight: 600; color: #cc0000; margin-bottom: 25px; padding-bottom: 15px; border-bottom: 1px solid #f0c0c0; }}
        .executive-summary > hr {{ margin: 25px 0; border: none; border-top: 2px solid #f0c0c0; }}
        .executive-summary table {{ width: 100%; border-collapse: collapse; margin: 20px 0; background: white; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .executive-summary table th {{ background: #cc0000; color: white; padding: 12px; text-align: left; font-weight: 600; border: 1px solid #8b0000; }}
        .executive-summary table td {{ padding: 12px; border: 1px solid #ddd; vertical-align: top; }}
        .executive-summary table tr:nth-child(even) {{ background: #f9f9f9; }}
        .executive-summary table tr:hover {{ background: #fff5f5; }}
        .executive-summary ul {{ margin: 15px 0 25px 0; padding: 20px 20px 20px 45px; background: white; border-radius: 5px; border-left: 3px solid #cc0000; }}
        .executive-summary li {{ margin: 12px 0; line-height: 1.8; }}
        .executive-summary li strong {{ color: #cc0000; }}
        .executive-summary strong {{ color: #8b0000; }}
        .executive-summary code {{ background: #f5f5f5; padding: 2px 6px; border-radius: 3px; font-family: 'Consolas', 'Monaco', monospace; font-size: 0.9em; color: #d13438; }}

        /* Channel Section */
        .channel-section {{ margin-bottom: 40px; background: #fafafa; padding: 30px; border-radius: 8px; scroll-margin-top: 20px; transition: background-color 0.3s ease; }}
        .channel-section:target {{ background: #fff5f5; box-shadow: 0 0 0 3px #cc0000; }}
        .channel-section h3 {{ color: #8b0000; font-size: 1.5em; margin-bottom: 20px; padding-bottom: 10px; border-bottom: 1px solid #ddd; display: flex; justify-content: space-between; align-items: center; }}
        .channel-section h3 .back-link {{ font-size: 0.6em; color: #cc0000; text-decoration: none; font-weight: normal; padding: 5px 12px; border: 1px solid #cc0000; border-radius: 4px; transition: all 0.2s ease; }}
        .channel-section h3 .back-link:hover {{ background: #cc0000; color: white; }}

        /* Expand/Collapse Controls */
        .expand-collapse-controls {{ display: flex; justify-content: center; gap: 15px; margin-bottom: 20px; padding: 15px; background: #fff5f5; border-radius: 8px; }}
        .control-btn {{ background: #cc0000; color: white; border: none; padding: 10px 20px; border-radius: 5px; cursor: pointer; font-size: 0.9em; font-weight: 600; transition: all 0.2s ease; box-shadow: 0 2px 5px rgba(204, 0, 0, 0.3); }}
        .control-btn:hover {{ background: #8b0000; transform: translateY(-2px); }}

        /* Article Details (Collapsible) */
        .article-details {{ background: white; margin-bottom: 20px; border-radius: 5px; border-left: 3px solid #cc0000; box-shadow: 0 1px 3px rgba(0,0,0,0.05); transition: all 0.3s ease; }}
        .article-details:hover {{ box-shadow: 0 2px 6px rgba(0,0,0,0.1); }}
        .article-details summary {{ padding: 20px; cursor: pointer; list-style: none; user-select: none; position: relative; outline: none; }}
        .article-details summary::-webkit-details-marker {{ display: none; }}
        .article-details summary::before {{ content: '+'; position: absolute; left: -8px; top: 50%; transform: translateY(-50%); width: 28px; height: 28px; background: #cc0000; color: white; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 20px; font-weight: bold; transition: all 0.3s ease; box-shadow: 0 2px 5px rgba(204, 0, 0, 0.3); }}
        .article-details[open] summary::before {{ content: '\u2212'; background: #8b0000; transform: translateY(-50%) rotate(180deg); }}
        .article-details summary:hover::before {{ background: #8b0000; transform: translateY(-50%) scale(1.1); }}
        .article-details[open] summary:hover::before {{ transform: translateY(-50%) rotate(180deg) scale(1.1); }}
        .article-summary-header h4 {{ color: #cc0000; margin-bottom: 10px; font-size: 1.2em; }}
        .article-summary-header h4 a {{ color: #cc0000; text-decoration: none; }}
        .article-summary-header h4 a:hover {{ text-decoration: underline; }}
        .meta-preview {{ display: flex; align-items: center; flex-wrap: wrap; gap: 10px; margin-top: 8px; font-size: 0.85em; color: #666; }}
        .article-content {{ padding: 0 20px 20px 20px; animation: slideDown 0.3s ease-out; }}
        @keyframes slideDown {{ from {{ opacity: 0; transform: translateY(-10px); }} to {{ opacity: 1; transform: translateY(0); }} }}

        /* Date Badges */
        .date-badge {{ display: inline-block; padding: 4px 12px; border-radius: 12px; font-size: 0.85em; font-weight: 600; white-space: nowrap; }}
        .date-badge.today {{ background: #ff4444; color: white; animation: pulse 2s ease-in-out infinite; }}
        .date-badge.new {{ background: #ff8800; color: white; }}
        .date-badge.recent {{ background: #cc0000; color: white; }}
        .date-badge.older {{ background: #e0e0e0; color: #666; }}
        .date-badge.unknown {{ background: #f0f0f0; color: #999; }}
        @keyframes pulse {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0.7; }} }}

        /* Tags */
        .tag {{ display: inline-block; background: #fff5f5; color: #cc0000; padding: 3px 10px; border-radius: 3px; font-size: 0.85em; margin: 2px; }}

        /* Channel AI Summary */
        .channel-ai-summary {{ background: linear-gradient(135deg, #fff8f8 0%, #ffe8e8 100%); padding: 20px; border-radius: 8px; margin-bottom: 20px; border-left: 4px solid #cc0000; box-shadow: 0 2px 5px rgba(204, 0, 0, 0.1); }}
        .channel-ai-summary .summary-label {{ display: inline-block; background: #cc0000; color: white; padding: 3px 10px; border-radius: 12px; font-size: 0.75em; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 12px; }}
        .channel-ai-summary p {{ margin: 0; line-height: 1.7; color: #444; font-size: 0.95em; }}

        /* Article Summary Content */
        .article-summary {{ color: #444; line-height: 1.7; }}
        .article-summary table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
        .article-summary th {{ background: #cc0000; color: white; padding: 10px; text-align: left; }}
        .article-summary td {{ padding: 10px; border: 1px solid #ddd; }}
        .article-summary ul, .article-summary ol {{ margin: 12px 0; padding-left: 25px; }}
        .article-summary li {{ margin: 8px 0; }}
        .article-summary code {{ background: #f5f5f5; padding: 2px 6px; border-radius: 3px; font-family: monospace; font-size: 0.9em; }}

        /* Footer */
        .footer {{ background: #f5f5f5; padding: 30px; text-align: center; color: #666; }}
    </style>
    <script>
        function expandAll(sectionId) {{
            var section = document.getElementById(sectionId);
            var details = section.querySelectorAll('details');
            details.forEach(function(d) {{ d.open = true; }});
        }}
        function collapseAll(sectionId) {{
            var section = document.getElementById(sectionId);
            var details = section.querySelectorAll('details');
            details.forEach(function(d) {{ d.open = false; }});
        }}
    </script>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{title}</h1>
            <div class="subtitle">{current_date}</div>
            <div class="subtitle">Report Period: {time_period}</div>
            <div class="ai-model">
                AI Model: {esc(model_name)}
                <span class="badge">Transcript Analysis</span>
            </div>
        </div>

        <div class="summary-stats">
            <div class="stat-card">
                <div class="stat-number">{total_articles}</div>
                <div class="stat-label">Videos Analyzed</div>
            </div>
            <div class="stat-card threats">
                <div class="stat-number">{stats.get('threat_advisories', 0)}</div>
                <div class="stat-label">Threat Advisories</div>
            </div>
            <div class="stat-card ctf">
                <div class="stat-number">{stats.get('ctf_walkthroughs', 0)}</div>
                <div class="stat-label">CTF Walkthroughs</div>
            </div>
            <div class="stat-card tutorials">
                <div class="stat-number">{stats.get('tutorials', 0)}</div>
                <div class="stat-label">Tutorials</div>
            </div>
        </div>

        <div class="channel-summary">
            <h2>Videos by Channel</h2>
            <div class="channel-grid">
"""
        # Channel summary grid
        for channel_name, articles_list in channels.items():
            channel_id = channel_name.lower().replace(' ', '-')
            channel_info = self._get_channel_info(channel_name)
            color = channel_info['color']
            html += f"""                <a href="#channel-{esc(channel_id)}" class="channel-item" style="border-left-color: {color};">
                    <span class="channel-name">{esc(channel_name)}</span>
                    <span class="channel-count">{len(articles_list)}</span>
                </a>
"""
        html += """            </div>
        </div>
"""

        # What's New section
        if new_count > 0 and new_articles:
            html += f"""
        <div class="whats-new-section">
            <h2>New Since Last Report</h2>
            <div class="whats-new-summary">
                <strong>{new_count}</strong> new video{'s' if new_count != 1 else ''} analyzed
                {f'since {last_report_time}' if last_report_time else ''}
            </div>
            <div class="whats-new-grid">
"""
            for article in new_articles[:6]:
                html += f"""                <div class="whats-new-item">
                    <h4><a href="{safe_url(article.get('url', '#'))}" target="_blank">{esc(article.get('title', 'Unknown'))}</a><span class="new-badge">New</span></h4>
                    <div class="meta">{esc(article.get('product', 'Unknown'))} &bull; {esc(article.get('date_info', {}).get('formatted_date', 'Unknown date'))}</div>
                </div>
"""
            html += """            </div>
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
                {sanitize_html(executive_summary)}
            </div>
"""

        # Channel sections
        html += """
            <div class="section">
                <h2>Detailed Videos by Channel</h2>
"""

        for channel_name, articles_list in channels.items():
            if not articles_list:
                continue

            channel_id = channel_name.lower().replace(' ', '-')
            channel_info = self._get_channel_info(channel_name)
            channel_summary = channel_summaries.get(channel_name, '')

            html += f"""
                <div class="channel-section" id="channel-{esc(channel_id)}">
                    <h3>
                        {esc(channel_name)} ({len(articles_list)})
                        <a href="#" class="back-link">Back to Top</a>
                    </h3>
"""
            if channel_summary:
                html += f"""
                    <div class="channel-ai-summary">
                        <span class="summary-label">AI Summary</span>
                        <p>{sanitize_html(channel_summary)}</p>
                    </div>
"""
            html += f"""
                    <div class="expand-collapse-controls">
                        <button class="control-btn" onclick="expandAll('channel-{esc(channel_id)}')">Expand All</button>
                        <button class="control-btn" onclick="collapseAll('channel-{esc(channel_id)}')">Collapse All</button>
                    </div>
"""
            for article in articles_list:
                summary_html = article.get('summary', 'No summary available.')
                content_type = article.get('content_type', ['general_security'])
                if isinstance(content_type, list):
                    tags_html = ''.join([f'<span class="tag">{esc(ct)}</span>' for ct in content_type])
                else:
                    tags_html = f'<span class="tag">{esc(content_type)}</span>'

                date_info = article.get('date_info', {})
                age_category = date_info.get('age_category', 'unknown')
                formatted_date = date_info.get('formatted_date', 'Date not available')

                # Extract preview
                preview = ''
                if summary_html:
                    preview_text = re.sub(r'<[^>]+>', '', summary_html)[:150]
                    if len(preview_text) == 150:
                        preview_text += '...'
                    preview = preview_text

                html += f"""
                    <details class="article-details">
                        <summary>
                            <div class="article-summary-header">
                                <h4><a href="{safe_url(article.get('url', '#'))}" target="_blank">{esc(article.get('title', 'Unknown'))}</a></h4>
                                <div class="meta-preview">
                                    <span class="date-badge {age_category}">{esc(formatted_date)}</span>
                                    {tags_html}
                                </div>
                                <p style="margin-top: 10px; color: #666; font-size: 0.9em;">{esc(preview)}</p>
                            </div>
                        </summary>
                        <div class="article-content">
                            <div class="article-summary">{sanitize_html(summary_html)}</div>
                        </div>
                    </details>
"""
            html += """
                </div>
"""

        html += """
            </div>
        </div>

        <div class="footer">
            <p><strong>SecIntel AI - Security Intelligence Tracker</strong></p>
            <p>Security YouTube Channels Tracker</p>
            <p>Generated on """ + current_date + """</p>
        </div>
    </div>
</body>
</html>"""

        return html
