"""
Summarizer module for SecIntel AI.
Handles AI-powered summarization of threat intelligence articles using AI backends (LM Studio or Claude).
"""

import logging
import json
import re
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from core.ai_client import AIClient

logger = logging.getLogger(__name__)

# =============================================================================
# IOC Validation Layer - Detects and filters fabricated/hallucinated IOCs
# =============================================================================

# Patterns that indicate fabricated IOCs
FAKE_IOC_PATTERNS = [
    # Placeholder domains
    r'example\.(com|org|net)',
    r'malicious[-_]?domain\.(com|org|net)',
    r'attacker[-_]?(server|domain|site)\.(com|org|net)',
    r'c2[-_]?server\.(com|org|net)',
    r'evil\.(com|org|net)',
    r'bad[-_]?(domain|site)\.(com|org|net)',
    r'fake[-_]?(domain|site)\.(com|org|net)',
    r'test\.(com|org|net)',
    r'placeholder',
    r'xxx+\.xxx+',
    r'\[domain\]',
    r'\[url\]',
    r'\[ip\]',

    # Private/reserved IP ranges (shouldn't appear as threat IOCs)
    r'^192\.168\.\d{1,3}\.\d{1,3}$',
    r'^10\.\d{1,3}\.\d{1,3}\.\d{1,3}$',
    r'^172\.(1[6-9]|2[0-9]|3[0-1])\.\d{1,3}\.\d{1,3}$',
    r'^127\.\d{1,3}\.\d{1,3}\.\d{1,3}$',
    r'^0\.0\.0\.0$',

    # Documentation IP ranges (RFC 5737)
    r'^192\.0\.2\.\d{1,3}$',      # TEST-NET-1
    r'^198\.51\.100\.\d{1,3}$',   # TEST-NET-2
    r'^203\.0\.113\.\d{1,3}$',    # TEST-NET-3

    # Obvious placeholder hashes
    r'^[a-f0-9]{32}$',  # Will be checked for patterns below
    r'^[a-f0-9]{40}$',  # Will be checked for patterns below
    r'^[a-f0-9]{64}$',  # Will be checked for patterns below

    # Sequential/repeating patterns in hashes
    r'^(01234|abcd|1234|aaaa|0000|ffff)',
    r'(0123456789|abcdefgh)',

    # Placeholder extension IDs
    r'^abcd[0-9a-f]{20,}',
    r'^[a-z]{4}[0-9]{4}[a-z]{4}[0-9]{4}',

    # Generic placeholder CVEs (future years with very high numbers)
    r'CVE-20[3-9]\d-\d{5,}',  # CVE numbers in far future

    # Placeholder URLs
    r'https?://.*exfil.*example',
    r'https?://.*collect.*example',
    r'https?://api\.[^/]+/collect$',
]

# Patterns for suspicious hash values (too uniform/sequential)
SUSPICIOUS_HASH_PATTERNS = [
    r'^(.)\1{7,}',           # Repeating single character (aaaaaaaa...)
    r'^(..)\1{3,}',          # Repeating two characters (abababab...)
    r'^0{8,}',               # Leading zeros
    r'^f{8,}',               # Leading f's
    r'0123456789',           # Sequential digits
    r'abcdef',               # Sequential hex letters
    r'^[0-9a-f]{8}\.{3}$',   # Truncated with ellipsis indicator
]


def is_fake_ioc(value: str, ioc_type: str = None) -> bool:
    """
    Check if an IOC value appears to be fabricated/hallucinated.

    Args:
        value: The IOC value to check
        ioc_type: Optional type hint (ip, domain, hash, url, cve)

    Returns:
        True if the IOC appears to be fake, False otherwise
    """
    if not value or not isinstance(value, str):
        return True

    value_lower = value.lower().strip()

    # Check against fake patterns
    for pattern in FAKE_IOC_PATTERNS:
        if re.search(pattern, value_lower, re.IGNORECASE):
            logger.warning(f"Detected fake IOC pattern: {value} (matched: {pattern})")
            return True

    # Additional hash-specific checks
    if ioc_type in ('hash', 'md5', 'sha1', 'sha256') or (len(value_lower) in (32, 40, 64) and re.match(r'^[0-9a-f]+$', value_lower)):
        for pattern in SUSPICIOUS_HASH_PATTERNS:
            if re.search(pattern, value_lower):
                logger.warning(f"Detected suspicious hash pattern: {value}")
                return True

    # Check for obviously fake CVEs
    if ioc_type == 'cve' or value_lower.startswith('cve-'):
        # CVE format: CVE-YYYY-NNNNN
        cve_match = re.match(r'cve-(\d{4})-(\d+)', value_lower)
        if cve_match:
            year = int(cve_match.group(1))
            number = int(cve_match.group(2))
            # Flag CVEs with impossibly high numbers for their year
            # or CVEs too far in the future
            if year > 2026 or (year == 2026 and number > 50000):
                logger.warning(f"Detected likely fake CVE: {value}")
                return True

    # Check for "N/A", "none", "unknown" type values
    if value_lower in ('n/a', 'na', 'none', 'unknown', 'not available', 'not provided',
                       'see individual reports', 'various', 'error', 'extraction_failed'):
        return True  # Not fake per se, but should be filtered from IOC lists

    return False


def is_valid_cve(cve_string: str) -> tuple[bool, str]:
    """
    Validate a CVE identifier for plausibility.

    Args:
        cve_string: A CVE identifier like "CVE-2024-12345"

    Returns:
        Tuple of (is_valid, reason) where reason explains why it's invalid
    """
    if not cve_string:
        return False, "Empty CVE string"

    cve_upper = cve_string.upper().strip()

    # Check basic format
    cve_match = re.match(r'^CVE-(\d{4})-(\d+)$', cve_upper)
    if not cve_match:
        return False, f"Invalid CVE format: {cve_string}"

    year = int(cve_match.group(1))
    number = int(cve_match.group(2))
    current_year = 2026  # Hardcoded since we know the date context

    # CVE program started in 1999
    if year < 1999:
        return False, f"CVE year {year} is before CVE program started (1999)"

    # Future years are invalid
    if year > current_year:
        return False, f"CVE year {year} is in the future"

    # Check for implausibly high sequence numbers based on year
    # These are approximate limits based on historical CVE counts
    max_cve_by_year = {
        1999: 1100, 2000: 1100, 2001: 1200, 2002: 1200, 2003: 1100,
        2004: 2500, 2005: 4800, 2006: 7000, 2007: 6700, 2008: 7500,
        2009: 7200, 2010: 7200, 2011: 7600, 2012: 8500, 2013: 8500,
        2014: 9800, 2015: 10000, 2016: 11000, 2017: 18000, 2018: 18000,
        2019: 18500, 2020: 19500, 2021: 22000, 2022: 26000, 2023: 30000,
        2024: 35000, 2025: 40000, 2026: 15000,  # Partial year estimate
    }

    max_for_year = max_cve_by_year.get(year, 50000)

    # For the current year, be more lenient since we're partway through
    if year == current_year:
        # January 2026 - only allow up to ~5000
        max_for_year = 5000

    if number > max_for_year:
        return False, f"CVE-{year}-{number} has implausibly high sequence number (max ~{max_for_year} for {year})"

    # Check for suspicious patterns in the number (only obviously fake ones)
    number_str = str(number)
    if len(number_str) >= 5:
        # Repeating digits like 11111, 99999, 00000
        if len(set(number_str)) == 1:
            return False, f"CVE number {number} has suspicious repeating pattern"
        # Exact sequential patterns like 12345, 23456, 54321
        if number_str == '12345' or number_str == '54321' or number_str == '123456':
            return False, f"CVE number {number} has suspicious sequential pattern"

    return True, "Valid"


def validate_cves_in_text(text: str) -> tuple[str, list]:
    """
    Scan text for CVE identifiers and validate them.

    Args:
        text: Text that may contain CVE references

    Returns:
        Tuple of (cleaned_text, list_of_invalid_cves)
    """
    if not text:
        return text, []

    invalid_cves = []

    # Find all CVE patterns in the text
    cve_pattern = r'CVE-\d{4}-\d+'
    cves_found = re.findall(cve_pattern, text, re.IGNORECASE)

    for cve in set(cves_found):  # Deduplicate
        is_valid, reason = is_valid_cve(cve)
        if not is_valid:
            invalid_cves.append({'cve': cve, 'reason': reason})
            logger.warning(f"Detected potentially fabricated CVE: {cve} - {reason}")

    # If there are invalid CVEs, add a warning to the text
    if invalid_cves:
        cve_list = ', '.join([c['cve'] for c in invalid_cves[:3]])
        warning = f"\n\n⚠️ **CVE Validation Warning**: The following CVE(s) could not be verified and may be AI-generated: {cve_list}"
        if len(invalid_cves) > 3:
            warning += f" and {len(invalid_cves) - 3} more"
        warning += ". Please verify against official sources (NVD, MITRE)."
        return text + warning, invalid_cves

    return text, []


def validate_ioc_list(iocs: list) -> list:
    """
    Filter a list of IOC dictionaries to remove fabricated entries.

    Args:
        iocs: List of IOC dicts with 'type', 'value', and optionally 'description'

    Returns:
        Filtered list with fake IOCs removed
    """
    if not iocs or not isinstance(iocs, list):
        return []

    validated = []
    for ioc in iocs:
        if not isinstance(ioc, dict):
            continue

        value = ioc.get('value', '')
        ioc_type = ioc.get('type', '')

        if not is_fake_ioc(value, ioc_type):
            validated.append(ioc)
        else:
            logger.info(f"Filtered out fabricated IOC: {ioc_type}={value}")

    return validated


def sanitize_summary_text(text: str) -> str:
    """
    Scan summary text for inline fabricated IOCs and add warnings.

    This doesn't remove them (as they're embedded in prose) but adds
    a note if suspicious patterns are detected.

    Args:
        text: The summary text to scan

    Returns:
        Original text, potentially with a warning appended
    """
    if not text:
        return text

    suspicious_found = []

    # Look for IP-like patterns
    ip_pattern = r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b'
    for match in re.finditer(ip_pattern, text):
        ip = match.group(1)
        if is_fake_ioc(ip, 'ip'):
            suspicious_found.append(f"IP: {ip}")

    # Look for domain-like patterns
    domain_pattern = r'\b([a-zA-Z0-9][-a-zA-Z0-9]*\.(com|org|net|io|xyz|example))\b'
    for match in re.finditer(domain_pattern, text, re.IGNORECASE):
        domain = match.group(1)
        if is_fake_ioc(domain, 'domain'):
            suspicious_found.append(f"Domain: {domain}")

    # Look for hash-like patterns (32, 40, or 64 hex chars)
    hash_pattern = r'\b([0-9a-fA-F]{32}|[0-9a-fA-F]{40}|[0-9a-fA-F]{64})\b'
    for match in re.finditer(hash_pattern, text):
        hash_val = match.group(1)
        if is_fake_ioc(hash_val, 'hash'):
            suspicious_found.append(f"Hash: {hash_val[:16]}...")

    if suspicious_found:
        warning = f"\n\n⚠️ **Validation Warning**: Some IOCs in this summary may be AI-generated placeholders and should be verified against the original source: {', '.join(suspicious_found[:3])}"
        if len(suspicious_found) > 3:
            warning += f" and {len(suspicious_found) - 3} more"
        logger.warning(f"Summary contains {len(suspicious_found)} suspicious IOC patterns")
        return text + warning

    return text


def escape_newlines_in_strings(text):
    """
    Escape literal newlines and tabs that appear inside JSON string values.

    This fixes cases where the LLM outputs actual newlines in JSON string content,
    which causes json.loads() to fail with "Invalid control character" errors.

    Args:
        text: JSON text that may contain unescaped newlines in strings

    Returns:
        JSON text with newlines/tabs properly escaped inside string values
    """
    result = []
    in_string = False
    escape_next = False
    for char in text:
        if escape_next:
            result.append(char)
            escape_next = False
            continue
        if char == '\\':
            result.append(char)
            escape_next = True
            continue
        if char == '"' and not escape_next:
            in_string = not in_string
            result.append(char)
            continue
        if in_string and char == '\n':
            result.append('\\n')  # Escape the newline
        elif in_string and char == '\t':
            result.append('\\t')  # Escape tabs too
        else:
            result.append(char)
    return ''.join(result)


def clean_summary_artifacts(text):
    """
    Remove prompt-related artifacts and headers that the LLM sometimes includes in output.

    Args:
        text: Summary text that may contain prompt artifacts

    Returns:
        Cleaned text with artifacts removed
    """
    if not text:
        return text

    # Patterns to remove from the beginning of summaries
    # These are headers/instructions that leak from the prompt
    artifact_patterns = [
        # Word count instructions (entire line)
        r'^\s*\*{0,2}Threat Intelligence Summary\s*[-–—]\s*\d+\s*[-–—]\s*\d+\s*words?\*{0,2}\s*\n*',
        r'^\s*\*{0,2}Technical Threat Intelligence Summary\s*[-–—]\s*\d+\s*[-–—]\s*\d+\s*words?\*{0,2}\s*\n*',
        r'^\s*\*{0,2}Summary\s*[-–—]\s*\d+\s*[-–—]\s*\d+\s*words?\*{0,2}\s*\n*',

        # Full header lines with titles (remove entire first line if it's a summary header)
        r'^\s*\*{0,2}Threat Intelligence Summary\s*[-–—][^\n]*\*{0,2}\s*\n*',
        r'^\s*\*{0,2}Technical Threat Intelligence Summary\s*[-–—][^\n]*\*{0,2}\s*\n*',

        # Standalone header lines without content after
        r'^\s*\*{0,2}Threat Intelligence Summary\*{0,2}\s*\n+',
        r'^\s*\*{0,2}Technical Threat Intelligence Summary\*{0,2}\s*\n+',

        # Source citations that should be at the end, not the beginning
        r'^\s*\*?Source:\s*["\'][^"\']+["\']\*?\s*\n*',
        r'^\s*\*?Source:\s*[^\n]+\*?\s*\n*',

        # Instruction-like prefixes
        r'^\s*Here is (?:the |a )?(?:concise |technical )?(?:threat intelligence )?summary[:\s]*\n*',
        r'^\s*Below is (?:the |a )?(?:concise |technical )?(?:threat intelligence )?summary[:\s]*\n*',
    ]

    cleaned = text
    for pattern in artifact_patterns:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE | re.MULTILINE)

    # Also clean up any leading horizontal rules or empty headers
    cleaned = re.sub(r'^\s*[-–—]{3,}\s*', '', cleaned)
    cleaned = re.sub(r'^\s*#{1,3}\s*$', '', cleaned, flags=re.MULTILINE)

    # Clean up excessive leading whitespace/newlines
    cleaned = cleaned.lstrip('\n\r\t ')

    return cleaned


class ArticleSummarizer:
    """Generates summaries for individual threat intelligence articles"""

    def __init__(self, ai_config=None, base_url=None, api_key=None, model=None):
        """
        Initialize the article summarizer.

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

    def _get_threat_advisory_prompt(self, title, content, iocs_text):
        """
        Get the prompt template for threat advisory content.

        Args:
            title (str): Article title
            content (str): Article content
            iocs_text (str): Formatted IOC text

        Returns:
            str: Prompt for threat advisory summarization
        """
        # Check for source-specific customization
        if "Volexity" in title or "volexity" in title.lower():
            return f"""You are a cybersecurity threat intelligence analyst. You need to create a concise, technical summary of the following Volexity threat intelligence article.

Title: {title}

Content:
{content}

{iocs_text}

Volexity is known for detailed threat actor attribution and technical analysis of advanced threats. Please provide a summary that:
1. Identifies the key threat actors mentioned (including any APT group names or attributions)
2. Extracts the specific TTPs (Tactics, Techniques, and Procedures)
3. Summarizes the technical details of the attack, malware, or vulnerability
4. Highlights the most significant IOCs and any MITRE ATT&CK mappings
5. Notes the industries, sectors, or geographic regions targeted
6. Explains the potential impact, severity, and recommended mitigations

Your summary should be technical but clear, aimed at cybersecurity professionals. Keep the summary concise (250-350 words) and emphasize attribution details and actionable intelligence.

CRITICAL ACCURACY REQUIREMENTS:
- ONLY include IOCs (IPs, domains, hashes, URLs, CVEs) that are EXPLICITLY mentioned in the article text above
- If the article does not provide specific IOCs, state "No specific IOCs provided in source"
- If the article does not name specific threat actors, state "Threat actor not attributed" - do NOT invent names
- If CVE numbers are not mentioned, do NOT fabricate them - say "CVE not assigned" or omit
- NEVER generate example or placeholder IOCs like "example.com", "192.168.x.x", or "abcd1234..."
- If CVSS scores are not provided in the article, do NOT assign them
- Stick strictly to facts stated in the article - do not extrapolate or infer technical details not present
"""
        else:
            return f"""You are a cybersecurity threat intelligence analyst. You need to create a concise, technical summary of the following threat intelligence article.

Title: {title}

Content:
{content}

{iocs_text}

Please provide a summary that:
1. Identifies the key threat actors, malware, or attack vectors
2. Summarizes the technical details of the attack or vulnerability
3. Highlights the most significant IOCs
4. Notes the industries or sectors targeted
5. Explains the potential impact and severity
6. Provides any recommended mitigations or defensive measures

Your summary should be technical but clear, aimed at cybersecurity professionals. Keep the summary concise (250-350 words) and focus on actionable intelligence.

CRITICAL ACCURACY REQUIREMENTS:
- ONLY include IOCs (IPs, domains, hashes, URLs, CVEs) that are EXPLICITLY mentioned in the article text above
- If the article does not provide specific IOCs, state "No specific IOCs provided in source"
- If the article does not name specific threat actors, state "Threat actor not attributed" - do NOT invent names
- If CVE numbers are not mentioned, do NOT fabricate them - say "CVE not assigned" or omit
- NEVER generate example or placeholder IOCs like "example.com", "192.168.x.x", or "abcd1234..."
- If CVSS scores are not provided in the article, do NOT assign them
- Stick strictly to facts stated in the article - do not extrapolate or infer technical details not present
"""

    def _get_product_update_prompt(self, title, content):
        """
        Get the prompt template for product update content.

        Args:
            title (str): Article title
            content (str): Article content

        Returns:
            str: Prompt for product update summarization
        """
        return f"""You are a cybersecurity product analyst. Summarize the following security product update or announcement.

Title: {title}

Content:
{content}

Please provide a brief, informative summary that:
1. **What Changed**: Identify the product/feature that was updated
2. **Key Updates**: List the main changes, new features, or improvements
3. **Availability**: Note when/how users can access these updates
4. **Why It Matters**: Explain the security or operational benefits

Keep the summary concise (150-250 words) and focus on practical information for security teams evaluating or using this product.

IMPORTANT: Do NOT fabricate IOCs, threat actors, or attack details. This is a product update, not a threat advisory.
"""

    def _get_industry_news_prompt(self, title, content):
        """
        Get the prompt template for industry news content.

        Args:
            title (str): Article title
            content (str): Article content

        Returns:
            str: Prompt for industry news summarization
        """
        return f"""You are a cybersecurity industry analyst. Provide a brief summary of the following cybersecurity news article.

Title: {title}

Content:
{content}

Please provide a concise summary (2-3 sentences, max 100 words) that:
1. States the main topic or announcement
2. Explains why it's relevant to the cybersecurity industry
3. Notes any key implications or takeaways

Keep the summary brief and informational. This is general industry news, not a technical threat report.

IMPORTANT: Do NOT fabricate IOCs, CVEs, threat actors, or specific attack details. Stick to the facts presented in the article.
"""
    
    def summarize(self, title, content, iocs=None):
        """
        Generate a summary for an article using AI with pre-classification.

        This method first classifies the content type, then uses the appropriate
        summarization prompt to prevent hallucination of threat content in
        non-threat articles.

        Args:
            title (str): Article title
            content (str): Article content
            iocs (dict, optional): Extracted IOCs

        Returns:
            tuple: (summary_text, content_type) where content_type is one of:
                   'threat_advisory', 'product_update', or 'industry_news'
        """
        try:
            # Validate content length - skip if too short (likely ads or scraping errors)
            if not content or len(content.strip()) < 200:
                logger.warning(f"Content too short ({len(content) if content else 0} chars) for '{title}' - skipping AI summarization")
                return (f"*Content unavailable or insufficient for analysis (only {len(content) if content else 0} characters scraped). This may be due to a temporary scraping issue or paywall.*", 'industry_news')

            # Check for common ad/promotional text patterns
            ad_patterns = [
                "Essential Checklist for Modern AI-Driven Cloud Defense",
                "Discover how agentic AI transforms",
                "Subscribe to our newsletter",
                "Sign up for free"
            ]
            for pattern in ad_patterns:
                if pattern.lower() in content.lower():
                    logger.warning(f"Detected promotional/ad content in '{title}' - skipping AI summarization")
                    return (f"*Article content appears to be promotional material or was not properly scraped. Manual review may be required. Visit the article URL for full content.*", 'industry_news')

            # STEP 1: Classify the content type
            logger.info(f"Classifying content type for '{title[:50]}...'")
            content_type = self.ai_client.classify_content(title, content)
            logger.info(f"Content classified as '{content_type}'")

            # Prepare IOCs section if available (only for threat advisories)
            iocs_text = ""
            if iocs and content_type == 'threat_advisory':
                iocs_text = "Extracted Indicators of Compromise (IOCs):\n"
                for ioc_type, ioc_list in iocs.items():
                    iocs_text += f"\n{ioc_type.upper()}:\n"
                    for ioc in ioc_list:
                        iocs_text += f"- {ioc['value']}"
                        if ioc.get('context'):
                            iocs_text += f" (Context: {ioc['context']})"
                        iocs_text += "\n"

            # STEP 2: Select the appropriate prompt template based on classification
            if content_type == 'threat_advisory':
                prompt = self._get_threat_advisory_prompt(title, content, iocs_text)
                system_prompt = """You are a cybersecurity threat intelligence analyst assistant. Provide accurate, concise, technical summaries of threat intelligence.

ACCURACY IS PARAMOUNT: You must NEVER fabricate, invent, or hallucinate any of the following:
- IOCs (IP addresses, domains, URLs, file hashes, email addresses)
- CVE numbers or CVSS scores
- Threat actor names or APT group designations
- Specific technical details not present in the source

If information is not provided in the source article, explicitly state it is "not provided" or "not specified" rather than inventing plausible-sounding data. Fabricated IOCs in threat intelligence can mislead security teams and waste investigative resources."""
                max_tokens = 2000
            elif content_type == 'product_update':
                prompt = self._get_product_update_prompt(title, content)
                system_prompt = "You are a cybersecurity product analyst. Provide clear, informative summaries of security product updates."
                max_tokens = 1500
            else:  # industry_news
                prompt = self._get_industry_news_prompt(title, content)
                system_prompt = "You are a cybersecurity industry analyst. Provide brief, factual summaries of cybersecurity news."
                max_tokens = 500

            # STEP 3: Call the AI API with the appropriate prompt
            summary = self.ai_client.chat_completion(
                messages=[
                    {
                        "role": "system",
                        "content": system_prompt
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                max_tokens=max_tokens,
                temperature=0.0  # Use a low temperature for more deterministic output
            )

            logger.info(f"Generated {content_type} summary for article: {title}")

            # Clean up any prompt artifacts that leaked into the output
            summary = clean_summary_artifacts(summary)

            # Validate summary for fabricated IOCs and CVEs (only for threat advisories)
            if content_type == 'threat_advisory':
                summary, invalid_cves = validate_cves_in_text(summary)
                summary = sanitize_summary_text(summary)

            return (summary, content_type)

        except Exception as e:
            logger.error(f"Error generating summary: {str(e)}")
            return (f"Error generating summary: {str(e)}", 'industry_news')


class ExecutiveSummarizer:
    """Generates executive summaries from multiple article summaries"""

    def __init__(self, ai_config=None, base_url=None, api_key=None, model=None):
        """
        Initialize the executive summarizer.

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
    
    def create_summary(self, articles, max_articles=20):
        """
        Create an executive summary from multiple articles.
        
        Args:
            articles (list): List of article dictionaries with summaries
            max_articles (int): Maximum number of articles to include
        
        Returns:
            dict: Dictionary containing:
                - executive_summary: Overall summary
                - key_actors: List of key threat actors
                - critical_iocs: List of most critical IOCs
                - recommendations: List of recommendations
        """
        try:
            # Limit the number of articles to avoid token limits
            articles = articles[:max_articles]
            
            # Extract summaries and titles
            article_data = []
            for article in articles:
                article_data.append({
                    'title': article['title'],
                    'summary': article['summary'],
                    'source': article['source'],
                    'url': article['url'],
                    'published_date': article.get('published_date', 'Unknown')
                })
                
                # Also collect IOCs for better summary generation
                if 'iocs' in article and article['iocs']:
                    # Extract top IOCs for each type 
                    top_iocs = {}
                    for ioc_type, iocs in article['iocs'].items():
                        if iocs:
                            # Take up to 5 IOCs of each type
                            top_iocs[ioc_type] = iocs[:5]
                    
                    if top_iocs:
                        article_data[-1]['iocs'] = top_iocs
            
            # Construct the prompt
            prompt = f"""You are a senior cybersecurity threat intelligence analyst preparing an executive summary for C-level executives and board members. You have the following summaries of recent threat intelligence articles:

{json.dumps(article_data, indent=2)}

Please create an executive summary that:

1. Identifies the 3-5 most significant cybersecurity threats from these articles
2. Focuses on business impact rather than technical details
3. Highlights industry trends and emerging threats
4. Identifies the most critical threat actors and their targets
5. Provides clear, actionable recommendations for organizational security

FORMAT YOUR EXECUTIVE SUMMARY WITH CLEAR SECTIONS using markdown:

The executive_summary field MUST use this exact structure with markdown headings and bullet lists:

## Threat Landscape Overview
(2-3 sentences providing context on the current threat environment)

## Top Threats This Period
(Use a numbered list for the 3-5 most critical threats)

1. **Threat Name**: Brief description of the threat and why it matters to the business
2. **Threat Name**: Brief description...
(etc.)

## Business Impact Assessment
(Use bullet points to describe potential business impacts)

- **Financial Risk**: Description of financial exposure
- **Operational Risk**: Description of operational disruption potential
- **Reputational Risk**: Description of brand/trust implications
- **Regulatory Risk**: Description of compliance concerns

## Key Threat Actors
(Brief paragraph or bullet list of the most significant actors)

## Priority Actions
(Use a numbered list for immediate actions executives should authorize)

1. Action item one
2. Action item two
(etc.)

Format your response as a structured JSON object with the following keys:
- executive_summary: The main executive summary text using the EXACT markdown structure above with ## headings and bullet/numbered lists
- key_actors: Array of objects with "name" and "description" fields for each key threat actor
- critical_iocs: Array of objects with "type", "value", and "description" fields for the most important IOCs
- recommendations: Array of strategic recommendation strings (3-5 bullet points)

Example format:
{{
  "executive_summary": "## Threat Landscape Overview\\n\\nThe cybersecurity landscape continues to evolve with sophisticated attacks...\\n\\n## Top Threats This Period\\n\\n1. **Ransomware Operations**: Criminal groups are targeting...\\n2. **Supply Chain Attacks**: Software dependencies are being...\\n\\n## Business Impact Assessment\\n\\n- **Financial Risk**: Ransomware demands averaging $2M...\\n- **Operational Risk**: Average downtime of 21 days...\\n\\n## Key Threat Actors\\n\\nAPT29 and FIN7 remain the most active...\\n\\n## Priority Actions\\n\\n1. Implement MFA across all systems\\n2. Review backup procedures...",
  "key_actors": [
    {{
      "name": "APT29",
      "description": "Russian state-sponsored group targeting government and defense sectors"
    }},
    {{
      "name": "FIN7",
      "description": "Financially motivated actor targeting retail and hospitality"
    }}
  ],
  "critical_iocs": [
    {{
      "type": "domain",
      "value": "malicious-domain.com",
      "description": "C2 server for Emotet campaign"
    }},
    {{
      "type": "ip",
      "value": "192.168.1.1",
      "description": "Scanning host for vulnerability XYZ"
    }}
  ],
  "recommendations": [
    "Implement MFA across all remote access services",
    "Patch vulnerable systems against CVE-2023-12345 immediately",
    "Update EDR signatures to detect the Lazarus campaign IOCs"
  ]
}}

IMPORTANT: Use markdown ## headings and proper bullet/numbered lists in the executive_summary. Keep it non-technical and easily understandable by executives without cybersecurity background.

CRITICAL ACCURACY REQUIREMENTS - DO NOT FABRICATE DATA:
- For critical_iocs: ONLY include IOCs that are EXPLICITLY mentioned in the article summaries above. If no specific IOCs are mentioned, return an empty array [] or use "value": "See individual reports"
- For key_actors: ONLY name threat actors that are EXPLICITLY attributed in the source articles. If articles say "unknown actor" or don't attribute, reflect that honestly
- NEVER invent CVE numbers, IP addresses, domains, hashes, or threat actor names
- NEVER use placeholder patterns like "example.com", "192.168.x.x", "abcd1234...", or obviously fake IDs
- If the source articles lack specific technical indicators, state "No specific IOCs provided in source reports" rather than fabricating plausible-looking data
- Fabricated IOCs are DANGEROUS in threat intelligence - they waste analyst time and can lead to false positives
"""

            system_prompt = """You are a senior cybersecurity threat intelligence analyst assistant. Distill complex technical information into clear, business-focused executive summaries.

Always provide structured output in valid JSON format when requested. Be concise and direct in your summaries.

CRITICAL: NEVER FABRICATE OR HALLUCINATE DATA
- Only include IOCs, CVEs, threat actor names, and technical details that are EXPLICITLY stated in the source articles
- If specific data is not available, say so honestly rather than inventing plausible-looking fake data
- Fabricated IOCs are dangerous and can mislead security teams

For the executive_summary field:
1. ALWAYS use markdown formatting with ## headings to create clear sections
2. Use numbered lists (1. 2. 3.) for prioritized items like top threats and priority actions
3. Use bullet lists (- item) for non-prioritized items like risk categories
4. Use **bold text** to highlight key terms and threat names
5. Do NOT include phrases like "Here is the executive summary" or "Based on the analyzed intelligence"
6. Do NOT include references to the JSON structure or other sections
7. Write in a clear, professional style appropriate for business executives
8. Structure MUST include: Threat Landscape Overview, Top Threats This Period, Business Impact Assessment, Key Threat Actors, Priority Actions

For the key_actors, critical_iocs, and recommendations fields:
1. Follow the exact format requested
2. ONLY include data explicitly mentioned in the source articles - never invent IOCs or actor names
3. If no specific IOCs are provided in sources, use an empty array or "See individual reports"
4. Ensure information is accurate and directly traceable to source articles"""

            # Call the AI API
            response_text = self.ai_client.chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=4000,
                temperature=0.3
            )
            
            # Find and extract the JSON part
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_text = response_text[json_start:json_end]
                
                # Clean up the JSON text to handle control characters
                json_text = json_text.replace('\r\n', '\n')
                json_text = json_text.replace('\r', '\n')

                # Remove problematic control characters (except tab and newline)
                json_text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', json_text)

                # Fix unescaped newlines inside JSON string values
                json_text = escape_newlines_in_strings(json_text)

                try:
                    summary_data = json.loads(json_text)
                    logger.info("Generated executive summary successfully")
                    
                    # Ensure all expected fields are present
                    if 'executive_summary' not in summary_data:
                        summary_data['executive_summary'] = "Executive summary could not be generated."
                        
                    if 'key_actors' not in summary_data or not summary_data['key_actors']:
                        summary_data['key_actors'] = [
                            {
                                "name": "Unknown Threat Actor",
                                "description": "No specific threat actors were identified in the analyzed reports."
                            }
                        ]
                        
                    if 'critical_iocs' not in summary_data or not summary_data['critical_iocs']:
                        # Extract some IOCs from the articles as a fallback
                        critical_iocs = []
                        for article in articles:
                            if 'iocs' in article and article['iocs']:
                                for ioc_type, iocs in article['iocs'].items():
                                    if iocs and len(iocs) > 0:
                                        critical_iocs.append({
                                            "type": ioc_type,
                                            "value": iocs[0]['value'],
                                            "description": f"Found in {article['title']}"
                                        })
                                        if len(critical_iocs) >= 3:
                                            break
                                if len(critical_iocs) >= 3:
                                    break
                        
                        if critical_iocs:
                            summary_data['critical_iocs'] = critical_iocs
                        else:
                            summary_data['critical_iocs'] = [
                                {
                                    "type": "N/A",
                                    "value": "N/A",
                                    "description": "No critical IOCs were identified in the analyzed reports."
                                }
                            ]
                    
                    if 'recommendations' not in summary_data or not summary_data['recommendations']:
                        summary_data['recommendations'] = [
                            "Maintain regular security patches and updates for all systems",
                            "Implement multi-factor authentication for critical services",
                            "Conduct regular security awareness training for employees",
                            "Review and update incident response plans",
                            "Maintain offline backups of critical data"
                        ]

                    # Validate and filter fabricated IOCs from the response
                    if 'critical_iocs' in summary_data:
                        original_count = len(summary_data['critical_iocs'])
                        summary_data['critical_iocs'] = validate_ioc_list(summary_data['critical_iocs'])
                        filtered_count = original_count - len(summary_data['critical_iocs'])
                        if filtered_count > 0:
                            logger.info(f"Filtered {filtered_count} fabricated IOCs from executive summary")

                        # If all IOCs were filtered, add a placeholder
                        if not summary_data['critical_iocs']:
                            summary_data['critical_iocs'] = [{
                                "type": "info",
                                "value": "No verified IOCs",
                                "description": "No specific IOCs were provided in the source articles or AI-generated IOCs were filtered out. See individual reports for details."
                            }]

                    # Clean up prompt artifacts, validate CVEs, and sanitize the executive summary text
                    if 'executive_summary' in summary_data:
                        summary_data['executive_summary'] = clean_summary_artifacts(summary_data['executive_summary'])
                        summary_data['executive_summary'], invalid_cves = validate_cves_in_text(summary_data['executive_summary'])
                        if invalid_cves:
                            logger.info(f"Found {len(invalid_cves)} potentially fabricated CVEs in executive summary")
                        summary_data['executive_summary'] = sanitize_summary_text(summary_data['executive_summary'])

                    return summary_data
                    
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse JSON response: {e}")
                    logger.debug(f"Problematic JSON text (first 500 chars): {json_text[:500]}")
                    
                    # Try alternative parsing approach
                    try:
                        # Sometimes models wrap JSON in markdown code blocks
                        if '```json' in response_text and '```' in response_text:
                            json_start = response_text.find('```json') + 7
                            json_end = response_text.find('```', json_start)
                            if json_end > json_start:
                                json_text = response_text[json_start:json_end].strip()
                                # Clean control characters and fix unescaped newlines
                                json_text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', json_text)
                                json_text = escape_newlines_in_strings(json_text)
                                summary_data = json.loads(json_text)
                                logger.info("Successfully parsed JSON from markdown code block")

                                # Apply IOC validation to this path as well
                                if 'critical_iocs' in summary_data:
                                    summary_data['critical_iocs'] = validate_ioc_list(summary_data['critical_iocs'])
                                    if not summary_data['critical_iocs']:
                                        summary_data['critical_iocs'] = [{
                                            "type": "info",
                                            "value": "No verified IOCs",
                                            "description": "No specific IOCs were provided in the source articles."
                                        }]
                                if 'executive_summary' in summary_data:
                                    summary_data['executive_summary'] = clean_summary_artifacts(summary_data['executive_summary'])
                                    summary_data['executive_summary'], _ = validate_cves_in_text(summary_data['executive_summary'])
                                    summary_data['executive_summary'] = sanitize_summary_text(summary_data['executive_summary'])

                                return summary_data
                    except json.JSONDecodeError:
                        pass
                        
                    # Try extracting individual sections manually if JSON parsing completely fails
                    logger.warning("Attempting manual section extraction from response")
                    return self.extract_sections_manually(response_text, articles)
            
            # Fallback if JSON parsing fails
            logger.warning("Using fallback for executive summary")
            return {
                'executive_summary': """## Threat Landscape Overview

The current threat landscape shows elevated activity across multiple threat vectors. Analysis of recent intelligence indicates ongoing campaigns targeting enterprise infrastructure, cloud services, and end-user systems.

## Top Threats This Period

1. **Ransomware Operations**: Sophisticated ransomware groups continue to target organizations across all sectors, with increasing focus on data exfiltration before encryption.
2. **Zero-Day Exploitation**: Active exploitation of recently disclosed vulnerabilities in enterprise software, requiring immediate patching attention.
3. **Advanced Persistent Threats**: State-sponsored actors maintaining persistent access to sensitive networks for intelligence gathering.
4. **Supply Chain Attacks**: Compromises of third-party software and services used to gain access to downstream targets.

## Business Impact Assessment

- **Financial Risk**: Ransomware demands and recovery costs can exceed millions of dollars, with additional regulatory fines for data breaches.
- **Operational Risk**: System downtime from attacks can halt business operations for days or weeks.
- **Reputational Risk**: Public disclosure of breaches erodes customer trust and can impact market position.
- **Regulatory Risk**: Data breaches may trigger compliance violations under GDPR, CCPA, and industry-specific regulations.

## Key Threat Actors

Multiple threat actors were identified in the analyzed reports. See individual report sections for specific attribution details.

## Priority Actions

1. Review and apply all critical security patches within 48 hours
2. Implement or verify multi-factor authentication across all remote access services
3. Conduct security awareness training focused on current phishing techniques
4. Review and test incident response procedures
5. Verify backup integrity and offline storage of critical data""",
                'key_actors': [
                    {
                        "name": "Various Threat Actors",
                        "description": "Multiple threat actors were mentioned in the reports but specific details could not be extracted."
                    }
                ],
                'critical_iocs': [
                    {
                        "type": "various",
                        "value": "See individual reports",
                        "description": "Various IOCs were identified in the individual reports."
                    }
                ],
                'recommendations': [
                    "Maintain regular security patches and updates for all systems",
                    "Implement multi-factor authentication for critical services",
                    "Conduct regular security awareness training for employees",
                    "Review and update incident response plans",
                    "Maintain offline backups of critical data"
                ]
            }
            
        except Exception as e:
            logger.error(f"Error generating executive summary: {str(e)}")
            return {
                'executive_summary': f"Error generating executive summary: {str(e)}",
                'key_actors': [
                    {
                        "name": "Error",
                        "description": "An error occurred while generating the threat actor information."
                    }
                ],
                'critical_iocs': [
                    {
                        "type": "error",
                        "value": "error",
                        "description": "An error occurred while generating the IOC information."
                    }
                ],
                'recommendations': [
                    "Unable to generate recommendations due to an error.",
                    "Please check the system logs for more information."
                ]
            }
    
    def extract_sections_manually(self, response_text, articles):
        """
        Manually extract sections from the response when JSON parsing fails.
        
        Args:
            response_text (str): The raw response text from the model
            articles (list): List of articles for fallback IOC extraction
            
        Returns:
            dict: Dictionary with extracted sections
        """
        import re
        
        logger.info("Attempting manual extraction of executive summary sections")
        
        # Initialize result structure
        result = {
            'executive_summary': "",
            'key_actors': [],
            'critical_iocs': [],
            'recommendations': []
        }
        
        try:
            # Try to extract executive summary (look for text before any structured sections)
            exec_match = re.search(r'executive[_\s]*summary["\s]*:?\s*["\s]*([^"}\]]+)', response_text, re.IGNORECASE | re.DOTALL)
            if exec_match:
                exec_text = exec_match.group(1).strip()
                # Clean up common artifacts
                exec_text = re.sub(r'[,\]\}]+$', '', exec_text)  # Remove trailing punctuation
                exec_text = exec_text.replace('\n', ' ').strip()
                if len(exec_text) > 50:  # Only use if it's substantial
                    result['executive_summary'] = exec_text
            
            # Extract key actors
            actors_section = re.search(r'key[_\s]*actors["\s]*:?\s*\[(.*?)\]', response_text, re.IGNORECASE | re.DOTALL)
            if actors_section:
                actors_text = actors_section.group(1)
                # Look for name/description pairs
                actor_matches = re.findall(r'["\s]*name["\s]*:?\s*["\s]*([^"}\],]+)["\s]*.*?["\s]*description["\s]*:?\s*["\s]*([^"}\]]+)', actors_text, re.IGNORECASE | re.DOTALL)
                for name, desc in actor_matches:
                    result['key_actors'].append({
                        'name': name.strip(),
                        'description': desc.strip()
                    })
            
            # Extract IOCs
            iocs_section = re.search(r'critical[_\s]*iocs["\s]*:?\s*\[(.*?)\]', response_text, re.IGNORECASE | re.DOTALL)
            if iocs_section:
                iocs_text = iocs_section.group(1)
                # Look for type/value/description triplets
                ioc_matches = re.findall(r'["\s]*type["\s]*:?\s*["\s]*([^"}\],]+)["\s]*.*?["\s]*value["\s]*:?\s*["\s]*([^"}\],]+)["\s]*.*?["\s]*description["\s]*:?\s*["\s]*([^"}\]]+)', iocs_text, re.IGNORECASE | re.DOTALL)
                for ioc_type, value, desc in ioc_matches:
                    result['critical_iocs'].append({
                        'type': ioc_type.strip(),
                        'value': value.strip(),
                        'description': desc.strip()
                    })
            
            # Extract recommendations
            recs_section = re.search(r'recommendations["\s]*:?\s*\[(.*?)\]', response_text, re.IGNORECASE | re.DOTALL)
            if recs_section:
                recs_text = recs_section.group(1)
                # Look for quoted strings
                rec_matches = re.findall(r'["\s]*([^"}\],]+)["\s]*', recs_text)
                for rec in rec_matches:
                    clean_rec = rec.strip().rstrip(',')
                    if len(clean_rec) > 10:  # Only include substantial recommendations
                        result['recommendations'].append(clean_rec)
            
            # Apply fallbacks for empty sections
            if not result['executive_summary']:
                result['executive_summary'] = """## Threat Landscape Overview

Analysis of recent intelligence reveals an active threat environment requiring vigilance across multiple security domains.

## Top Threats This Period

1. **Emerging Threats**: Multiple threat vectors identified in analyzed reports.
2. **Active Campaigns**: Ongoing malicious activity targeting enterprise environments.

## Business Impact Assessment

- **Operational Risk**: Potential for service disruption from active threat campaigns.
- **Security Risk**: Organizations should review their security posture against identified threats.

## Priority Actions

1. Review individual threat reports for specific indicators
2. Assess exposure to identified vulnerabilities
3. Update security controls as recommended"""
            
            if not result['key_actors']:
                result['key_actors'] = [
                    {
                        "name": "Various Threat Actors",
                        "description": "Multiple threat actors were mentioned in the reports but specific details could not be extracted."
                    }
                ]
            
            if not result['critical_iocs']:
                # Try to extract some IOCs from the articles as fallback
                critical_iocs = []
                for article in articles:
                    if 'iocs' in article and article['iocs']:
                        for ioc_type, iocs in article['iocs'].items():
                            if iocs and len(iocs) > 0:
                                critical_iocs.append({
                                    "type": ioc_type,
                                    "value": iocs[0]['value'],
                                    "description": f"Found in {article['title']}"
                                })
                                if len(critical_iocs) >= 3:
                                    break
                        if len(critical_iocs) >= 3:
                            break
                
                if critical_iocs:
                    result['critical_iocs'] = critical_iocs
                else:
                    result['critical_iocs'] = [
                        {
                            "type": "various",
                            "value": "See individual reports",
                            "description": "Various IOCs were identified in the individual reports."
                        }
                    ]
            
            if not result['recommendations']:
                result['recommendations'] = [
                    "Maintain regular security patches and updates for all systems",
                    "Implement multi-factor authentication for critical services",
                    "Conduct regular security awareness training for employees",
                    "Review and update incident response plans",
                    "Maintain offline backups of critical data"
                ]
            
            # Apply IOC validation to manually extracted data
            if 'critical_iocs' in result:
                result['critical_iocs'] = validate_ioc_list(result['critical_iocs'])
                if not result['critical_iocs']:
                    result['critical_iocs'] = [{
                        "type": "info",
                        "value": "No verified IOCs",
                        "description": "No specific IOCs were provided in the source articles."
                    }]
            if 'executive_summary' in result:
                result['executive_summary'] = clean_summary_artifacts(result['executive_summary'])
                result['executive_summary'], _ = validate_cves_in_text(result['executive_summary'])
                result['executive_summary'] = sanitize_summary_text(result['executive_summary'])

            logger.info("Manual extraction completed successfully")
            return result
            
        except Exception as e:
            logger.error(f"Manual extraction failed: {str(e)}")
            # Return basic fallback structure
            return {
                'executive_summary': "Manual extraction of executive summary failed. Please check logs for details.",
                'key_actors': [
                    {
                        "name": "Extraction Error",
                        "description": "Unable to extract threat actor information due to parsing errors."
                    }
                ],
                'critical_iocs': [
                    {
                        "type": "error",
                        "value": "extraction_failed",
                        "description": "Unable to extract IOC information due to parsing errors."
                    }
                ],
                'recommendations': [
                    "Manual extraction failed. Please review the raw response data.",
                    "Consider adjusting the model prompt for better JSON formatting."
                ]
            }