"""
LLM News reporting module.
Handles generation of LLM news and update reports.
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


class LLMNewsReportGenerator:
    """Generates LLM news and update reports"""

    LAST_REPORT_FILE = '.last_report_time'

    def __init__(self, template_dir=None):
        """
        Initialize the LLM news report generator.

        Args:
            template_dir (str, optional): Directory containing report templates
        """
        if template_dir is None:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            template_dir = os.path.join(current_dir, 'templates')

        os.makedirs(template_dir, exist_ok=True)

        self.env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=select_autoescape(['html', 'xml'])
        )

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

    def _fix_provider_updates_section(self, exec_summary_html, providers, provider_summaries):
        """
        Fix the Provider Updates section in executive summary using actual data.
        The AI sometimes misses providers, so we replace with accurate data.
        """
        if not exec_summary_html:
            return exec_summary_html

        # Build accurate provider updates HTML
        provider_order = [
            ('Anthropic', 'Anthropic Claude'),
            ('OpenAI', 'OpenAI'),
            ('Google', 'Google Gemini'),
            ('Meta', 'Meta Llama'),
            ('LM Studio', 'LM Studio'),
            ('Mistral AI', 'Mistral AI'),
            ('Microsoft', 'Microsoft Copilot'),
            ('Perplexity', 'Perplexity'),
            ('Hugging Face', 'Hugging Face'),
        ]

        # Build the replacement HTML
        provider_updates_html = "<h3>Provider Updates</h3>\n"

        for provider_key, display_name in provider_order:
            provider_articles = providers.get(provider_key, [])
            summary = provider_summaries.get(provider_key, '')

            provider_updates_html += f"<h4>{display_name}</h4>\n<ul>\n"

            if provider_articles and summary:
                # Use the AI-generated provider summary
                provider_updates_html += f"<li>{summary}</li>\n"
            elif provider_articles:
                # Have articles but no summary - list article titles
                titles = [a.get('title', 'Unknown')[:80] for a in provider_articles[:3]]
                provider_updates_html += f"<li>{len(provider_articles)} update(s): {'; '.join(titles)}</li>\n"
            else:
                provider_updates_html += "<li>No updates reported.</li>\n"

            provider_updates_html += "</ul>\n"

        # Add Others section for remaining providers
        other_providers = [p for p in providers.keys() if p not in [po[0] for po in provider_order]]
        if other_providers:
            provider_updates_html += "<h4>Others</h4>\n<ul>\n"
            for provider_key in other_providers:
                provider_articles = providers.get(provider_key, [])
                summary = provider_summaries.get(provider_key, '')
                if provider_articles:
                    if summary:
                        provider_updates_html += f"<li><strong>{provider_key}</strong>: {summary}</li>\n"
                    else:
                        provider_updates_html += f"<li><strong>{provider_key}</strong>: {len(provider_articles)} update(s)</li>\n"
            provider_updates_html += "</ul>\n"

        # Replace the AI-generated Provider Updates section
        # Pattern to match from "<h3>Provider Updates</h3>" to the next <h3> or <hr />
        pattern = r'<h3>Provider Updates</h3>.*?(?=<h3>|<hr\s*/?>|$)'
        replacement = provider_updates_html

        fixed_html = re.sub(pattern, replacement, exec_summary_html, flags=re.DOTALL)

        return fixed_html

    def _prepare_articles(self, articles):
        """Prepare articles for reporting."""
        logger.info(f"Processing {len(articles)} LLM news articles for report")

        for article in articles:
            if 'summary' in article and article['summary']:
                article['summary'] = self._remove_trailing_questions(article['summary'])

            article['provider_info'] = self._get_provider_info(article.get('provider', ''))
            article['preview'] = self._extract_preview(article.get('summary', ''))
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

    def _get_provider_info(self, provider):
        """Get provider display information with colors."""
        provider_lower = provider.lower() if provider else ''

        provider_colors = {
            'anthropic': {'type': 'provider', 'label': 'Anthropic', 'color': '#d97757'},
            'openai': {'type': 'provider', 'label': 'OpenAI', 'color': '#10a37f'},
            'google': {'type': 'provider', 'label': 'Google', 'color': '#4285f4'},
            'meta': {'type': 'provider', 'label': 'Meta', 'color': '#0668e1'},
            'lm studio': {'type': 'provider', 'label': 'LM Studio', 'color': '#8b5cf6'},
            'mistral': {'type': 'provider', 'label': 'Mistral AI', 'color': '#ff7000'},
            'microsoft': {'type': 'provider', 'label': 'Microsoft', 'color': '#00a4ef'},
            'perplexity': {'type': 'provider', 'label': 'Perplexity', 'color': '#20b2aa'},
            'hugging face': {'type': 'provider', 'label': 'Hugging Face', 'color': '#ffd21e'},
            'ollama': {'type': 'provider', 'label': 'Ollama', 'color': '#1a1a1a'},
            'langchain': {'type': 'provider', 'label': 'LangChain', 'color': '#00875a'},
        }

        for key, info in provider_colors.items():
            if key in provider_lower:
                return info

        return {'type': 'other', 'label': provider or 'Other', 'color': '#666666'}

    def _categorize_by_provider(self, articles):
        """Categorize articles by provider."""
        # Define providers in order
        providers = [
            'Anthropic',
            'OpenAI',
            'Google',
            'Meta',
            'LM Studio',
            'Mistral AI',
            'Microsoft',
            'Perplexity',
            'Hugging Face',
            'Ollama',
            'LangChain',
            'Other'
        ]

        categorized = {provider: [] for provider in providers}

        for article in articles:
            provider = article.get('provider', 'Other')
            source = article.get('source', '').lower()
            title = article.get('title', '').lower()
            matched = False

            # Check provider field first
            for known_provider in providers[:-1]:  # Exclude 'Other'
                if known_provider.lower() in provider.lower():
                    categorized[known_provider].append(article)
                    matched = True
                    break

            # If not matched, check source and title for Ollama/LangChain
            if not matched:
                if 'ollama' in source or 'ollama' in title:
                    categorized['Ollama'].append(article)
                    matched = True
                elif 'langchain' in source or 'langchain' in title:
                    categorized['LangChain'].append(article)
                    matched = True

            if not matched:
                categorized['Other'].append(article)

        # Remove empty providers
        return {k: v for k, v in categorized.items() if v}

    def _calculate_stats(self, articles):
        """Calculate statistics for the report."""
        stats = {
            'model_releases': 0,
            'api_updates': 0,
            'feature_announcements': 0,
            'research': 0,
            'pricing_changes': 0,
            'security_notices': 0,
            'general_updates': 0
        }

        for article in articles:
            content_type = article.get('content_type', 'general_update')
            if isinstance(content_type, list):
                for ct in content_type:
                    ct_lower = ct.lower()
                    if 'model' in ct_lower or 'release' in ct_lower:
                        stats['model_releases'] += 1
                    elif 'api' in ct_lower:
                        stats['api_updates'] += 1
                    elif 'feature' in ct_lower:
                        stats['feature_announcements'] += 1
                    elif 'research' in ct_lower:
                        stats['research'] += 1
                    elif 'pricing' in ct_lower:
                        stats['pricing_changes'] += 1
                    elif 'security' in ct_lower:
                        stats['security_notices'] += 1
                    else:
                        stats['general_updates'] += 1
            else:
                ct_lower = content_type.lower() if content_type else 'general'
                if 'model' in ct_lower or 'release' in ct_lower:
                    stats['model_releases'] += 1
                elif 'api' in ct_lower:
                    stats['api_updates'] += 1
                elif 'feature' in ct_lower:
                    stats['feature_announcements'] += 1
                elif 'research' in ct_lower:
                    stats['research'] += 1
                elif 'pricing' in ct_lower:
                    stats['pricing_changes'] += 1
                elif 'security' in ct_lower:
                    stats['security_notices'] += 1
                else:
                    stats['general_updates'] += 1

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

    def generate_llm_news_report(self, executive_summary, articles, output_dir, time_period="last 30 days", provider_summaries=None, model_name=None):
        """Generate the main LLM news report."""
        os.makedirs(output_dir, exist_ok=True)

        # Get last report time and identify new articles
        last_report_time = self._get_last_report_time(output_dir)
        new_articles, existing_articles = self._identify_new_articles(articles, last_report_time)

        # Prepare articles
        prepared_articles = self._prepare_articles(articles)

        # Categorize by provider
        providers = self._categorize_by_provider(prepared_articles)

        # Calculate stats
        stats = self._calculate_stats(prepared_articles)

        # Convert executive summary markdown to HTML
        exec_summary_html = ""
        if executive_summary and executive_summary.get('summary'):
            md = markdown.Markdown(extensions=[TableExtension(), Nl2BrExtension()])
            exec_summary_html = md.convert(executive_summary['summary'])

            # Fix the Provider Updates section with accurate data
            # (AI sometimes misses providers or incorrectly says "No updates")
            exec_summary_html = self._fix_provider_updates_section(
                exec_summary_html, providers, provider_summaries or {}
            )

        # Convert article summaries to HTML
        for article in prepared_articles:
            if article.get('summary'):
                md = markdown.Markdown(extensions=[TableExtension(), Nl2BrExtension()])
                article['summary'] = md.convert(article['summary'])

        # Prepare new articles for display
        new_articles_prepared = self._prepare_articles(new_articles) if new_articles else []

        # Generate report
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"llm_news_report_{timestamp}.html"
        filepath = os.path.join(output_dir, filename)

        html = self._generate_html(
            title="LLM News & Updates Report",
            time_period=time_period,
            executive_summary=exec_summary_html,
            providers=providers,
            stats=stats,
            total_articles=len(prepared_articles),
            new_articles=new_articles_prepared,
            new_count=len(new_articles),
            existing_count=len(existing_articles),
            last_report_time=last_report_time.strftime('%B %d, %Y at %I:%M %p') if last_report_time else None,
            provider_summaries=provider_summaries or {},
            model_name=model_name
        )

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html)

        # Save last report time
        self._save_last_report_time(output_dir)

        logger.info(f"Generated report: {filepath}")
        return filepath

    def generate_tier1_digest(self, executive_summary, articles, output_dir, summarizer=None, provider_summaries=None, model_name=None):
        """Generate Tier 1 weekly digest (7 days)."""
        return self.generate_llm_news_report(
            executive_summary=executive_summary,
            articles=articles,
            output_dir=output_dir,
            time_period="last 7 days",
            provider_summaries=provider_summaries,
            model_name=model_name
        )

    def generate_tier2_biweekly(self, executive_summary, articles, output_dir, summarizer=None, provider_summaries=None, model_name=None):
        """Generate Tier 2 bi-weekly report (14 days)."""
        return self.generate_llm_news_report(
            executive_summary=executive_summary,
            articles=articles,
            output_dir=output_dir,
            time_period="last 14 days",
            provider_summaries=provider_summaries,
            model_name=model_name
        )

    def generate_tier3_archive(self, executive_summary, articles, output_dir, summarizer=None, provider_summaries=None, model_name=None):
        """Generate Tier 3 monthly archive (30 days)."""
        return self.generate_llm_news_report(
            executive_summary=executive_summary,
            articles=articles,
            output_dir=output_dir,
            time_period="last 30 days",
            provider_summaries=provider_summaries,
            model_name=model_name
        )

    def _generate_report_with_tier(self, executive_summary, articles, output_dir, time_period, tier, tier_name, summarizer=None, provider_summaries=None, model_name=None):
        """Generate a report with specific tier configuration."""
        return self.generate_llm_news_report(
            executive_summary=executive_summary,
            articles=articles,
            output_dir=output_dir,
            time_period=time_period,
            provider_summaries=provider_summaries,
            model_name=model_name
        )

    def _generate_html(self, title, time_period, executive_summary, providers, stats,
                       total_articles, new_articles, new_count, existing_count, last_report_time,
                       provider_summaries=None, model_name=None):
        """Generate HTML report content."""
        current_date = datetime.now().strftime('%B %d, %Y')

        # Try to load template, fallback to inline HTML
        try:
            template = self.env.get_template('llm_news_report.html')
            return template.render(
                title=title,
                date=current_date,
                time_period=time_period,
                executive_summary=executive_summary,
                providers=providers,
                stats=stats,
                total_articles=total_articles,
                new_articles=new_articles,
                new_count=new_count,
                existing_count=existing_count,
                last_report_time=last_report_time,
                provider_summaries=provider_summaries or {},
                model_name=model_name
            )
        except Exception as e:
            logger.warning(f"Template not found, using inline HTML: {e}")
            return self._generate_inline_html(
                title, current_date, time_period, executive_summary, providers,
                stats, total_articles, new_articles, new_count, existing_count, last_report_time,
                provider_summaries=provider_summaries or {},
                model_name=model_name
            )

    def _generate_inline_html(self, title, current_date, time_period, executive_summary, providers,
                              stats, total_articles, new_articles, new_count, existing_count, last_report_time,
                              provider_summaries=None, model_name=None):
        """Generate inline HTML matching defender report format."""

        provider_summaries = provider_summaries or {}
        model_name = model_name or "Unknown"

        provider_colors = {
            'Anthropic': '#d97757',
            'OpenAI': '#10a37f',
            'Google': '#4285f4',
            'Meta': '#0668e1',
            'LM Studio': '#8b5cf6',
            'Mistral AI': '#ff7000',
            'Microsoft': '#00a4ef',
            'Perplexity': '#20b2aa',
            'Hugging Face': '#ffd21e',
            'Ollama': '#1a1a1a',
            'LangChain': '#00875a',
            'vLLM': '#6366f1',
            'Other': '#666666'
        }

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

        /* Header */
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 40px; text-align: center; }}
        .header h1 {{ font-size: 2.5em; margin-bottom: 10px; font-weight: 300; }}
        .header .subtitle {{ font-size: 1.1em; opacity: 0.9; }}
        .header .ai-model {{ margin-top: 15px; padding: 10px 20px; background: rgba(255, 255, 255, 0.15); border-radius: 6px; font-size: 0.9em; display: inline-block; border: 1px solid rgba(255, 255, 255, 0.3); }}
        .header .ai-model .badge {{ background: rgba(255, 255, 255, 0.25); padding: 3px 10px; border-radius: 4px; margin-left: 8px; font-weight: 600; font-size: 0.95em; }}

        /* Stats Grid */
        .summary-stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; padding: 40px; background: #f9f9f9; border-bottom: 1px solid #e0e0e0; }}
        .stat-card {{ background: white; padding: 20px; border-radius: 8px; text-align: center; box-shadow: 0 2px 5px rgba(0,0,0,0.05); border-left: 4px solid #667eea; }}
        .stat-card.models {{ border-left-color: #10a37f; }}
        .stat-card.apis {{ border-left-color: #4285f4; }}
        .stat-card.features {{ border-left-color: #ff7000; }}
        .stat-number {{ font-size: 2.5em; font-weight: bold; color: #667eea; margin-bottom: 5px; }}
        .stat-card.models .stat-number {{ color: #10a37f; }}
        .stat-card.apis .stat-number {{ color: #4285f4; }}
        .stat-card.features .stat-number {{ color: #ff7000; }}
        .stat-label {{ font-size: 0.9em; color: #666; text-transform: uppercase; letter-spacing: 0.5px; }}

        /* Provider Summary Grid */
        .provider-summary {{ padding: 30px 40px; background: white; border-bottom: 1px solid #e0e0e0; }}
        .provider-summary h2 {{ color: #667eea; font-size: 1.5em; margin-bottom: 20px; text-align: center; }}
        .provider-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 15px; }}
        .provider-item {{ background: #f9f9f9; padding: 15px 20px; border-radius: 5px; display: flex; justify-content: space-between; align-items: center; border-left: 3px solid #667eea; transition: all 0.2s ease; cursor: pointer; text-decoration: none; color: inherit; }}
        .provider-item:hover {{ background: #f0f4ff; transform: translateX(5px); box-shadow: 0 2px 8px rgba(102, 126, 234, 0.2); }}
        .provider-name {{ font-weight: 600; color: #333; font-size: 0.95em; }}
        .provider-count {{ background: #667eea; color: white; padding: 5px 12px; border-radius: 15px; font-weight: bold; font-size: 0.9em; min-width: 30px; text-align: center; }}
        .provider-count.zero {{ background: #d0d0d0; color: #666; }}

        /* What's New Section */
        .whats-new-section {{ padding: 30px 40px; background: linear-gradient(135deg, #fff4e6 0%, #ffe8cc 100%); border-bottom: 3px solid #ff8800; }}
        .whats-new-section h2 {{ color: #ff6600; font-size: 1.8em; margin-bottom: 15px; text-align: center; }}
        .whats-new-summary {{ text-align: center; font-size: 1.1em; color: #555; margin-bottom: 25px; padding: 15px; background: white; border-radius: 8px; border: 2px solid #ff8800; }}
        .whats-new-summary strong {{ color: #ff6600; font-size: 1.3em; }}
        .whats-new-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); gap: 15px; }}
        .whats-new-item {{ background: white; padding: 15px; border-radius: 8px; border-left: 4px solid #ff8800; box-shadow: 0 2px 5px rgba(255, 136, 0, 0.15); transition: all 0.2s ease; }}
        .whats-new-item:hover {{ transform: translateY(-2px); box-shadow: 0 4px 12px rgba(255, 136, 0, 0.3); }}
        .whats-new-item h4 {{ font-size: 1.1em; margin-bottom: 8px; }}
        .whats-new-item h4 a {{ color: #667eea; text-decoration: none; }}
        .whats-new-item h4 a:hover {{ text-decoration: underline; }}
        .whats-new-item .meta {{ font-size: 0.85em; color: #666; }}
        .new-badge {{ display: inline-block; background: #ff6600; color: white; padding: 2px 8px; border-radius: 10px; font-size: 0.75em; font-weight: bold; text-transform: uppercase; margin-left: 8px; }}

        /* Content Area */
        .content {{ padding: 40px; }}
        .section {{ margin-bottom: 40px; }}
        .section h2 {{ color: #667eea; font-size: 1.8em; margin-bottom: 20px; padding-bottom: 10px; border-bottom: 2px solid #667eea; }}

        /* Executive Summary */
        .executive-summary {{ background: #f0f4ff; padding: 40px; border-radius: 8px; border-left: 4px solid #667eea; margin-bottom: 30px; }}
        .executive-summary h3 {{ color: #667eea; margin-bottom: 25px; font-size: 1.8em; border-bottom: 2px solid #667eea; padding-bottom: 10px; }}
        .executive-summary h4, .executive-summary h5 {{ color: #5a67d8; margin-top: 20px; margin-bottom: 10px; }}
        .executive-summary > p {{ margin-bottom: 18px; line-height: 1.8; }}
        .executive-summary > p:first-of-type {{ font-size: 1.15em; font-weight: 600; color: #667eea; margin-bottom: 25px; padding-bottom: 15px; border-bottom: 1px solid #cce0ff; }}
        .executive-summary > hr {{ margin: 25px 0; border: none; border-top: 2px solid #cce0ff; }}
        .executive-summary table {{ width: 100%; border-collapse: collapse; margin: 20px 0; background: white; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .executive-summary table th {{ background: #667eea; color: white; padding: 12px; text-align: left; font-weight: 600; border: 1px solid #5a67d8; }}
        .executive-summary table td {{ padding: 12px; border: 1px solid #ddd; vertical-align: top; }}
        .executive-summary table tr:nth-child(even) {{ background: #f9f9f9; }}
        .executive-summary table tr:hover {{ background: #f0f4ff; }}
        .executive-summary ul {{ margin: 15px 0 25px 0; padding: 20px 20px 20px 45px; background: white; border-radius: 5px; border-left: 3px solid #667eea; }}
        .executive-summary li {{ margin: 12px 0; line-height: 1.8; }}
        .executive-summary li strong {{ color: #667eea; }}
        .executive-summary code {{ background: #f5f5f5; padding: 2px 6px; border-radius: 3px; font-family: 'Consolas', 'Monaco', monospace; font-size: 0.9em; color: #d13438; }}
        .executive-summary strong {{ color: #5a67d8; }}

        /* Provider Section */
        .provider-section {{ margin-bottom: 40px; background: #fafafa; padding: 30px; border-radius: 8px; scroll-margin-top: 20px; transition: background-color 0.3s ease; }}
        .provider-section:target {{ background: #f0f4ff; box-shadow: 0 0 0 3px #667eea; }}
        .provider-section h3 {{ color: #5a67d8; font-size: 1.5em; margin-bottom: 20px; padding-bottom: 10px; border-bottom: 1px solid #ddd; display: flex; justify-content: space-between; align-items: center; }}
        .provider-section h3 .back-link {{ font-size: 0.6em; color: #667eea; text-decoration: none; font-weight: normal; padding: 5px 12px; border: 1px solid #667eea; border-radius: 4px; transition: all 0.2s ease; display: inline-flex; align-items: center; gap: 5px; }}
        .provider-section h3 .back-link:hover {{ background: #667eea; color: white; transform: translateY(-2px); box-shadow: 0 2px 5px rgba(102, 126, 234, 0.3); }}
        .provider-badge {{ display: inline-block; padding: 4px 12px; border-radius: 15px; font-size: 0.85em; color: white; margin-left: 10px; }}

        /* Expand/Collapse Controls */
        .expand-collapse-controls {{ display: flex; justify-content: center; gap: 15px; margin-bottom: 20px; padding: 15px; background: #f0f4ff; border-radius: 8px; }}
        .control-btn {{ background: #667eea; color: white; border: none; padding: 10px 20px; border-radius: 5px; cursor: pointer; font-size: 0.9em; font-weight: 600; transition: all 0.2s ease; box-shadow: 0 2px 5px rgba(102, 126, 234, 0.3); }}
        .control-btn:hover {{ background: #5a67d8; transform: translateY(-2px); box-shadow: 0 4px 8px rgba(102, 126, 234, 0.4); }}

        /* Article Details (Collapsible) */
        .article-details {{ background: white; margin-bottom: 20px; border-radius: 5px; border-left: 3px solid #667eea; box-shadow: 0 1px 3px rgba(0,0,0,0.05); transition: all 0.3s ease; }}
        .article-details:hover {{ box-shadow: 0 2px 6px rgba(0,0,0,0.1); }}
        .article-details summary {{ padding: 20px; cursor: pointer; list-style: none; user-select: none; position: relative; outline: none; }}
        .article-details summary::-webkit-details-marker {{ display: none; }}
        .article-details summary::before {{ content: '+'; position: absolute; left: -8px; top: 50%; transform: translateY(-50%); width: 28px; height: 28px; background: #667eea; color: white; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 20px; font-weight: bold; transition: all 0.3s ease; box-shadow: 0 2px 5px rgba(102, 126, 234, 0.3); }}
        .article-details[open] summary::before {{ content: '−'; background: #5a67d8; transform: translateY(-50%) rotate(180deg); }}
        .article-details summary:hover::before {{ background: #5a67d8; transform: translateY(-50%) scale(1.1); }}
        .article-details[open] summary:hover::before {{ transform: translateY(-50%) rotate(180deg) scale(1.1); }}
        .article-summary-header h4 {{ color: #667eea; margin-bottom: 10px; font-size: 1.2em; }}
        .article-summary-header h4 a {{ color: #667eea; text-decoration: none; }}
        .article-summary-header h4 a:hover {{ text-decoration: underline; }}
        .meta-preview {{ display: flex; align-items: center; flex-wrap: wrap; gap: 10px; margin-top: 8px; font-size: 0.85em; color: #666; }}
        .article-content {{ padding: 0 20px 20px 20px; animation: slideDown 0.3s ease-out; }}
        @keyframes slideDown {{ from {{ opacity: 0; transform: translateY(-10px); }} to {{ opacity: 1; transform: translateY(0); }} }}

        /* Article Meta */
        .article-meta {{ font-size: 0.85em; color: #666; margin-bottom: 15px; padding-bottom: 10px; border-bottom: 1px solid #eee; display: flex; align-items: center; flex-wrap: wrap; gap: 10px; }}

        /* Date Badges */
        .date-badge {{ display: inline-block; padding: 4px 12px; border-radius: 12px; font-size: 0.85em; font-weight: 600; white-space: nowrap; }}
        .date-badge.today {{ background: #ff4444; color: white; animation: pulse 2s ease-in-out infinite; }}
        .date-badge.new {{ background: #ff8800; color: white; }}
        .date-badge.recent {{ background: #667eea; color: white; }}
        .date-badge.older {{ background: #e0e0e0; color: #666; }}
        .date-badge.unknown {{ background: #f0f0f0; color: #999; }}
        @keyframes pulse {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0.7; }} }}

        /* Tags */
        .tag {{ display: inline-block; background: #f0f4ff; color: #667eea; padding: 3px 10px; border-radius: 3px; font-size: 0.85em; margin: 2px; }}

        /* Provider AI Summary */
        .provider-ai-summary {{ background: linear-gradient(135deg, #f8f9ff 0%, #eef1ff 100%); padding: 20px; border-radius: 8px; margin-bottom: 20px; border-left: 4px solid #667eea; box-shadow: 0 2px 5px rgba(102, 126, 234, 0.1); }}
        .provider-ai-summary .summary-label {{ display: inline-block; background: #667eea; color: white; padding: 3px 10px; border-radius: 12px; font-size: 0.75em; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 12px; }}
        .provider-ai-summary p {{ margin: 0; line-height: 1.7; color: #444; font-size: 0.95em; }}

        /* Article Summary Content */
        .article-summary {{ color: #444; line-height: 1.7; }}
        .article-summary table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
        .article-summary th {{ background: #667eea; color: white; padding: 10px; text-align: left; }}
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
                AI Model: {model_name} (Local - LM Studio)
                <span class="badge">Local</span>
            </div>
        </div>

        <div class="summary-stats">
            <div class="stat-card">
                <div class="stat-number">{total_articles}</div>
                <div class="stat-label">Total Updates</div>
            </div>
            <div class="stat-card models">
                <div class="stat-number">{stats.get('model_releases', 0)}</div>
                <div class="stat-label">Model Releases</div>
            </div>
            <div class="stat-card apis">
                <div class="stat-number">{stats.get('api_updates', 0)}</div>
                <div class="stat-label">API Updates</div>
            </div>
            <div class="stat-card features">
                <div class="stat-number">{stats.get('feature_announcements', 0)}</div>
                <div class="stat-label">New Features</div>
            </div>
        </div>

        <div class="provider-summary">
            <h2>Updates by Provider</h2>
            <div class="provider-grid">
"""
        # Provider summary grid
        for provider_name, articles in providers.items():
            provider_id = provider_name.lower().replace(' ', '-')
            color = provider_colors.get(provider_name, '#666666')
            count_class = '' if len(articles) > 0 else 'zero'
            html += f"""                <a href="#provider-{provider_id}" class="provider-item" style="border-left-color: {color};">
                    <span class="provider-name">{provider_name}</span>
                    <span class="provider-count {count_class}">{len(articles)}</span>
                </a>
"""
        html += """            </div>
        </div>
"""

        # What's New section
        if new_count > 0 and new_articles:
            html += f"""
        <div class="whats-new-section">
            <h2>🆕 What's New Since Last Report</h2>
            <div class="whats-new-summary">
                <strong>{new_count}</strong> new update{'s' if new_count != 1 else ''} added
                {f'since {last_report_time}' if last_report_time else ''}
            </div>
            <div class="whats-new-grid">
"""
            for article in new_articles[:6]:  # Show up to 6 new items
                html += f"""                <div class="whats-new-item">
                    <h4><a href="{article.get('url', '#')}" target="_blank">{article.get('title', 'Unknown')}</a><span class="new-badge">New</span></h4>
                    <div class="meta">{article.get('provider', 'Unknown')} • {article.get('product', 'Unknown')}</div>
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
                {executive_summary}
            </div>
"""

        # Provider sections
        html += """
            <div class="section">
                <h2>Detailed Updates by Provider</h2>
"""

        for provider_name, articles in providers.items():
            if not articles:
                continue

            color = provider_colors.get(provider_name, '#666666')
            provider_id = provider_name.lower().replace(' ', '-')
            # Get AI summary for this provider
            provider_summary = provider_summaries.get(provider_name, '')

            html += f"""
                <div class="provider-section" id="provider-{provider_id}">
                    <h3>
                        {provider_name} ({len(articles)})
                        <a href="#" class="back-link">↑ Back to Top</a>
                    </h3>
"""
            # Add AI-generated provider summary if available
            if provider_summary:
                html += f"""
                    <div class="provider-ai-summary">
                        <span class="summary-label">AI Summary</span>
                        <p>{provider_summary}</p>
                    </div>
"""
            html += f"""
                    <div class="expand-collapse-controls">
                        <button class="control-btn" onclick="expandAll('provider-{provider_id}')">📖 Expand All</button>
                        <button class="control-btn" onclick="collapseAll('provider-{provider_id}')">📕 Collapse All</button>
                    </div>
"""
            for article in articles:
                summary_html = article.get('summary', 'No summary available.')
                content_type = article.get('content_type', ['general_update'])
                if isinstance(content_type, list):
                    tags_html = ''.join([f'<span class="tag">{ct}</span>' for ct in content_type])
                else:
                    tags_html = f'<span class="tag">{content_type}</span>'

                # Date badge
                date_info = article.get('date_info', {})
                age_category = date_info.get('age_category', 'unknown')
                formatted_date = date_info.get('formatted_date', 'Date not available')

                # Extract preview (first 150 chars of summary text)
                preview = ''
                if summary_html:
                    import re
                    preview_text = re.sub(r'<[^>]+>', '', summary_html)[:150]
                    if len(preview_text) == 150:
                        preview_text += '...'
                    preview = preview_text

                html += f"""
                    <details class="article-details">
                        <summary>
                            <div class="article-summary-header">
                                <h4><a href="{article.get('url', '#')}" target="_blank">{article.get('title', 'Unknown')}</a></h4>
                                <div class="meta-preview">
                                    <span class="date-badge {age_category}">{formatted_date}</span>
                                    <span><strong>Product:</strong> {article.get('product', 'Unknown')}</span>
                                    {tags_html}
                                </div>
                                <p style="margin-top: 10px; color: #666; font-size: 0.9em;">{preview}</p>
                            </div>
                        </summary>
                        <div class="article-content">
                            <div class="article-summary">{summary_html}</div>
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
            <p>LLM News & Updates Tracker</p>
            <p>Generated on """ + current_date + """</p>
        </div>
    </div>
</body>
</html>"""

        return html
