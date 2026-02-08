# SecIntel AI - File Reference

A comprehensive guide to all files in the SecIntel AI codebase.

## Table of Contents

- [Root-Level Files](#root-level-files)
- [Core Modules](#core-modules)
- [Tracker Implementations](#tracker-implementations)
- [Utility Scripts](#utility-scripts)
- [Test Files](#test-files)
- [Documentation](#documentation)
- [Data and Output Directories](#data-and-output-directories)

---

## Root-Level Files

| File | Purpose |
|------|---------|
| `secintel.py` | Main CLI entry point. Handles argument parsing and orchestrates the scrape → analyze → report workflow. |
| `config.yaml` | Global configuration for AI provider settings, database path, and tracker enablement. |
| `requirements.txt` | Python package dependencies. |
| `CLAUDE.md` | Developer documentation for Claude Code (technical architecture reference). |

### secintel.py

The primary command-line interface for SecIntel AI. Key functions:

- `parse_arguments()` - Defines CLI flags (`--scrape`, `--analyze`, `--report`, `--tier`, etc.)
- `get_trackers()` - Loads and initializes enabled tracker plugins
- `list_trackers()` - Displays available trackers and their status
- `main()` - Entry point that coordinates the workflow

### config.yaml

Controls global behavior:

```yaml
ai:
  provider: 'lmstudio'    # or 'claude'
  lmstudio:
    base_url: 'http://localhost:1234/v1'
  temperature: 0.1

database:
  path: data/secintel.db

trackers:
  defender:
    enabled: true
  # ... other trackers
```

---

## Core Modules

Located in `core/`. These provide shared functionality used by all trackers.

| File | Purpose |
|------|---------|
| `__init__.py` | Package initializer |
| `base_tracker.py` | Abstract base class that all trackers must extend |
| `database.py` | SQLite database operations (articles, IOCs, tags) |
| `ai_client.py` | Unified AI client for LM Studio and Claude |
| `config.py` | YAML configuration file loader |
| `ioc_extractor.py` | Extracts Indicators of Compromise from text |
| `lm_studio_connection.py` | LM Studio connection testing and fallback logic |
| `source_validator.py` | Validates tracker source configurations |

### base_tracker.py

Defines the `BaseTracker` abstract class. All trackers must implement:

- `scrape()` - Fetch updates from configured sources
- `analyze()` - Generate AI summaries for scraped content
- `report(tier)` - Produce tiered reports (HTML/Markdown)
- `test_connection()` - Verify AI provider connectivity

### database.py

The `DatabaseManager` class handles all SQLite operations:

**Tables:**
- `trackers` - Registered tracker metadata
- `articles` - Scraped content with AI summaries
- `iocs` - Extracted indicators (IPs, domains, hashes, CVEs)
- `tags` - Article metadata tags

**Key methods:**
- `store_article()` - Save scraped article to database
- `get_articles_without_summary()` - Retrieve articles needing AI analysis
- `get_recent_articles_with_summary()` - Retrieve articles for reporting
- `store_ioc()` - Save extracted IOC with context

### ai_client.py

The `AIClient` class provides a unified interface for AI providers:

- Automatically selects LM Studio or Claude based on config
- `chat_completion(prompt)` - Generate AI responses
- `classify_content(text)` - Pre-classify articles (threat_advisory, product_update, industry_news)
- `test_connection()` - Verify provider connectivity

### ioc_extractor.py

The `IOCExtractor` class extracts security indicators using regex patterns:

**Supported IOC types:**
- IP addresses (IPv4/IPv6)
- Domains and URLs
- File hashes (MD5, SHA1, SHA256)
- Email addresses
- CVE identifiers
- MITRE ATT&CK IDs
- Registry keys and file paths
- Cryptocurrency addresses
- YARA rule names

Includes false positive filtering to prevent misidentification of common domains and test IPs.

### source_validator.py

The `SourceValidator` class validates tracker configurations:

- Schema validation for RSS, Web, API, and Headless source types
- Connectivity testing for configured endpoints
- Detects configuration typos and provides helpful hints

---

## Tracker Implementations

Located in `trackers/`. Each tracker follows a consistent plugin pattern.

### Tracker Structure

Every tracker directory contains:

| File | Purpose |
|------|---------|
| `__init__.py` | Tracker class extending `BaseTracker` |
| `config.yaml` | Source definitions (URLs, feed types, keywords) |
| `scraper_*.py` | Fetches content from configured sources |
| `summarizer_*.py` | Generates AI summaries and extracts IOCs |
| `reporting_*.py` | Produces tiered HTML/Markdown reports |

### Available Trackers

#### defender/

Tracks Microsoft Defender product updates (XDR, Endpoint, Office 365, Identity, Vulnerability Management).

- **DefenderTracker** - Main tracker class
- **MicrosoftSecurityProductScraper** - Fetches from Defender RSS feeds
- **MicrosoftSecurityProductSummarizer** - AI-powered summarization
- **MicrosoftSecurityReportGenerator** - Tiered report generation

#### microsoft_products/

Tracks Microsoft security products (Entra, Intune, Purview, Sentinel, Teams, SharePoint, Exchange).

- **MicrosoftProductsTracker** - Main tracker class
- Sources include Tech Community blogs and Microsoft Learn documentation

#### threat_intel/

Tracks threat intelligence from security blogs, CISA alerts, and vendor advisories.

- **ThreatIntelTracker** - Main tracker class
- **ThreatIntelScraper** - RSS-based feed scraping
- **ArticleSummarizer** / **ExecutiveSummarizer** - Threat-focused summarization

#### thirdparty_security/

Tracks third-party security tools and vendors. Supports multiple source types and custom parsers.

- **ThirdPartySecurityTracker** - Main tracker class
- **ThirdPartySecurityScraper** - Supports RSS, web scraping, JSON APIs, and headless browser (Playwright)
- **ThirdPartySecurityReportGenerator** - Tiered report generation with configurable vendor styling
- Configurable sources, vendor styles, and parser types in `config.yaml`

#### llm_news/

Tracks LLM/AI provider news and updates (OpenAI, Anthropic, Google, Meta, Perplexity).

- **LLMNewsTracker** - Main tracker class
- **LLMNewsScraper** - Fetches from AI provider blogs and news feeds

#### _template/

Template for creating new trackers:

- `README.md` - Instructions for adding new trackers
- `source_templates.yaml` - Copy-paste ready source configuration templates

---

## Utility Scripts

Located in `scripts/`. Helper utilities for maintenance and debugging.

| Script | Purpose |
|--------|---------|
| `migrate_add_content_type.py` | Database migration to add `content_type` column |
| `reextract_iocs.py` | Re-extract IOCs from articles after IOCExtractor improvements |
| `debug_headless.py` | Debug utility for examining HTML structure of dynamic pages |

### migrate_add_content_type.py

Run this after upgrading to add content classification support:

```bash
python scripts/migrate_add_content_type.py
```

### reextract_iocs.py

Re-processes all articles with the latest IOC extraction logic:

```bash
python scripts/reextract_iocs.py
```

### debug_headless.py

Saves rendered HTML from JavaScript-heavy pages for inspection:

```bash
python scripts/debug_headless.py "https://example.com/page"
```

---

## Test Files

Located in `tests/`. Unit and integration tests for core functionality.

| Test File | What It Tests |
|-----------|---------------|
| `test_ai_client.py` | AI client initialization, chat completion, provider switching |
| `test_classification.py` | Content classification (threat_advisory, product_update, industry_news) |
| `test_feeds.py` | RSS feed parsing and article metadata extraction |
| `test_sources.py` | Source configuration validation and schema compliance |
| `test_fixed_sources.py` | Edge cases and source-specific workarounds |
| `test_lm_connection.py` | LM Studio connection management and fallback logic |
| `test_headless_final.py` | Playwright-based headless browser integration |
| `test_headless_scrapers.py` | Individual headless scraper unit tests |

Run tests with:

```bash
python -m pytest tests/
```

---

## Documentation

Located in `docs/`.

| Document | Purpose |
|----------|---------|
| `AI_PROVIDER_SETUP.md` | Setup instructions for LM Studio and Claude |
| `ADDING_SOURCES.md` | Guide for adding new data sources to trackers |
| `CONTENT_CLASSIFICATION.md` | How content classification prevents AI hallucination |
| `MIGRATION_GUIDE.md` | Upgrading from legacy versions |
| `ROADMAP.md` | Planned features and improvements |
| `FILE_REFERENCE.md` | This file |
| `examples/` | Sample reports showing expected output format |

---

## Data and Output Directories

### data/

Contains the SQLite database:

```
data/
└── secintel.db    # Main database (articles, IOCs, tags)
```

Created automatically on first run. Path configurable in `config.yaml`.

### reports/

Generated reports are organized by tracker:

```
reports/
├── defender/
│   ├── defender_tier0_report_20260130_120000.html
│   ├── defender_tier0_report_20260130_120000.md
│   └── ...
├── microsoft_products/
├── threat_intel/
├── thirdparty_security/
└── llm_news/
```

**Report naming:** `{tracker}_tier{N}_report_{YYYYMMDD}_{HHMMSS}.{html|md}`

### logs/

Application logs:

```
logs/
└── secintel.log
```

---

## Quick Reference

### Adding a New Tracker

1. Copy `trackers/_template/` to `trackers/your_tracker/`
2. Implement the tracker class extending `BaseTracker`
3. Create `config.yaml` with source definitions
4. Implement scraper, summarizer, and reporting modules
5. Register in global `config.yaml`
6. Import in `secintel.py`

### Source Types

| Type | Use Case | Requirements |
|------|----------|--------------|
| `rss` | RSS/Atom feeds | `feed_url` parameter |
| `web` | Static HTML pages | `content_selector` for targeting |
| `api` | JSON endpoints | `headers` for authentication |
| `headless` | JavaScript-rendered pages | Playwright installed |

### Database Schema

```sql
articles (
    id, tracker_name, source, title, url, author,
    published_date, content, summary, content_type,
    scraped_date, analyzed_date
)

iocs (
    id, article_id, type, value, context
)

tags (
    id, article_id, tag
)
```

---

## See Also

- [README.md](../README.md) - Quick start and usage guide
- [AI_PROVIDER_SETUP.md](AI_PROVIDER_SETUP.md) - AI configuration details
- [ADDING_SOURCES.md](ADDING_SOURCES.md) - Adding new data sources
