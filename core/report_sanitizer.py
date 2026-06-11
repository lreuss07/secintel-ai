"""
Report Sanitizer - escaping and sanitization helpers for HTML report generation.

Scraped article fields (titles, URLs, sources) and AI-generated summaries are
untrusted input: a hostile or compromised source could embed HTML/JavaScript
that would execute in the browser of anyone reading a generated report
(stored XSS). Reporting modules that build HTML with f-strings must route
every interpolated value through these helpers. (Jinja2-rendered templates
with autoescape enabled are already safe and don't need them.)

Usage:
    from core.report_sanitizer import esc, safe_url, sanitize_html

    html += f'<a href="{safe_url(article["url"])}">{esc(article["title"])}</a>'
    html += f'<div class="summary">{sanitize_html(summary_html)}</div>'
"""

import html
import logging
import re

logger = logging.getLogger(__name__)

try:
    import nh3
    _NH3_AVAILABLE = True
except ImportError:
    nh3 = None
    _NH3_AVAILABLE = False
    logger.warning(
        "nh3 is not installed - AI summary HTML will be stripped to plain text "
        "in reports. Install it (pip install nh3) to keep summary formatting."
    )

# Tags legitimately produced by markdown-converted AI summaries.
_ALLOWED_TAGS = {
    'a', 'b', 'blockquote', 'br', 'code', 'em', 'h1', 'h2', 'h3', 'h4', 'h5',
    'h6', 'hr', 'i', 'li', 'ol', 'p', 'pre', 'strong', 'sub', 'sup', 'table',
    'tbody', 'td', 'th', 'thead', 'tr', 'ul', 'span', 'div',
}

# class is needed because some reporters style summary internals (badges, etc.)
_ALLOWED_ATTRIBUTES = {
    'a': {'href', 'title'},
    'span': {'class'},
    'div': {'class'},
    'td': {'align'},
    'th': {'align'},
    'code': {'class'},
}

_SAFE_URL_RE = re.compile(r'^https?://', re.IGNORECASE)
_TAG_RE = re.compile(r'<[^>]+>')


def esc(value):
    """
    HTML-escape a scalar value for safe interpolation into markup text or
    a quoted attribute. None becomes an empty string.
    """
    if value is None:
        return ''
    return html.escape(str(value), quote=True)


def safe_url(url, fallback='#'):
    """
    Return the URL only if it uses an http(s) scheme, otherwise the fallback.
    The result is also HTML-escaped so it is safe inside a quoted attribute.
    Blocks javascript:, data:, vbscript: and similar scriptable schemes.
    """
    if url is None:
        return fallback
    candidate = str(url).strip()
    if not _SAFE_URL_RE.match(candidate):
        if candidate and candidate != fallback:
            logger.debug(f"Rejected non-http(s) URL in report: {candidate[:80]!r}")
        return fallback
    return html.escape(candidate, quote=True)


def sanitize_html(fragment):
    """
    Sanitize an HTML fragment that legitimately contains markup (e.g. a
    markdown-rendered AI summary) down to a safe allowlist of tags and
    attributes. Scripts, event handlers, and scriptable URLs are removed.

    Falls back to stripping all tags (plain text, escaped) if nh3 is not
    installed - degraded formatting, but never unsafe.
    """
    if fragment is None:
        return ''
    fragment = str(fragment)
    if _NH3_AVAILABLE:
        return nh3.clean(
            fragment,
            tags=_ALLOWED_TAGS,
            attributes=_ALLOWED_ATTRIBUTES,
            url_schemes={'http', 'https'},
            link_rel="noopener noreferrer",
        )
    return html.escape(_TAG_RE.sub('', fragment), quote=True)
