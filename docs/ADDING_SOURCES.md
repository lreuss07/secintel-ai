# Adding Sources to SecIntel AI

This guide explains how to add new data sources to SecIntel AI without requiring AI assistance. By following these steps, you can expand the threat intelligence coverage to include your preferred security blogs, vendor release notes, and other sources.

## Quick Start

1. **Decide which tracker** matches your source (see table below)
2. **Copy a template** from `trackers/_template/source_templates.yaml`
3. **Add to the tracker's `config.yaml`** and validate

```bash
# Validate your configuration
python secintel.py --validate-sources

# Test that sources are reachable
python secintel.py --validate-sources --test-connections

# Run a scrape to test
python secintel.py --scrape --tracker <tracker_name>
```

---

## Which Tracker Should I Use?

| If your source covers...                        | Use this tracker       |
|-------------------------------------------------|------------------------|
| Microsoft Defender products (XDR, Endpoint, etc.) | `defender`           |
| Other Microsoft security (Entra, Intune, Purview) | `microsoft_products` |
| General threat intel, CVEs, advisories, APTs    | `threat_intel`         |
| Third-party security vendors                    | `thirdparty_security`  |
| AI/LLM updates (OpenAI, Anthropic, etc.)        | `llm_news`             |

---

## Source Types Explained

SecIntel AI supports four source types. Choose based on how the target site delivers content:

### 1. RSS Feeds (`type: rss`)

**Best for:** Blogs, news sites, release feeds, GitHub releases

**When to use:** The site has an RSS or Atom feed (look for orange RSS icon, `/feed/`, `/rss.xml`, or `/feed.xml` in URLs)

**Required fields:**
- `name` - Display name for the source
- `url` - Main website URL
- `type: rss`
- `feed_url` - URL to the RSS/Atom feed

**Optional fields:**
- `vendor` - Vendor name (for third-party tracking)
- `product` / `products` - Product name(s) to filter
- `filter_pattern` - Regex pattern to filter entries
- `filter_by_title` - Filter entries by title matching products
- `keywords` - Keywords to filter content

**Example:**
```yaml
- name: Krebs on Security
  url: https://krebsonsecurity.com
  type: rss
  feed_url: https://krebsonsecurity.com/feed/
```

**Example with filtering:**
```yaml
- name: "Vendor Firmware Updates"
  type: rss
  url: "https://support.vendor.com/rss/firmware.xml"
  vendor: "Vendor Name"
  products:
    - "Product A"
    - "Product B"
  filter_by_title: true
```

---

### 2. Web Scraping (`type: web`)

**Best for:** "What's New" pages, release notes pages, static HTML

**When to use:** The site doesn't have an RSS feed, but content is in static HTML

**Required fields:**
- `name` - Display name
- `url` - Page URL to scrape
- `type: web`

**Optional fields:**
- `content_selector` - CSS selector for main content area
- `article_selector` - CSS selector for article links
- `single_page` - Set to `true` if all content is on one page
- `selectors` - Dict of CSS selectors for specific elements
- `vendor` / `product` - For tracking metadata

**Example (simple):**
```yaml
- name: Microsoft Security Blog
  url: https://www.microsoft.com/en-us/security/blog
  type: web
  article_selector: h3.c-heading-4 a
  content_selector: div.c-content-card
```

**Example (with selectors):**
```yaml
- name: "Security Vendor Releases"
  type: web
  url: "https://www.vendor.com/releases"
  vendor: "Vendor Name"
  product: "Platform Name"
  selectors:
    release_container: ".release"
    date_attr: "data-release-date"
    title: "h2, h3"
    content: ".release-content, p"
```

---

### 3. JSON API (`type: api`)

**Best for:** Sites with REST API endpoints that return JSON

**When to use:** The site has a documented API or you can find JSON endpoints in browser DevTools

**Required fields:**
- `name` - Display name
- `url` - API endpoint URL
- `type: api`

**Optional fields:**
- `params` - Query parameters as key-value pairs
- `headers` - HTTP headers for the request
- `vendor` / `product` - For tracking metadata

**Example:**
```yaml
- name: "Security Vendor API"
  type: api
  url: "https://api.vendor.com/search"
  vendor: "Vendor Name"
  product: "Platform Name"
  params:
    groupByPub: "false"
    rpp: 50
    "sort.field": "lastRevised"
    "sort.value": "desc"
```

---

### 4. Headless Browser (`type: headless`)

**Best for:** JavaScript-heavy sites that require browser rendering

**When to use:** The page content is loaded dynamically with JavaScript (check by disabling JS in browser - if content disappears, you need headless)

**Required fields:**
- `name` - Display name
- `type: headless`
- `url` OR `url_template` - Page URL (template can include `{year}`)

**Optional fields:**
- `wait_for` - CSS selector to wait for before scraping
- `dynamic_year` - Auto-substitute current year in URL template
- `fallback_to_previous_year` - Try previous year if current fails
- `vendor` / `product` - For tracking metadata

**Note:** Requires Playwright to be installed:
```bash
pip install playwright
playwright install firefox   # Recommended - better at bypassing bot detection
playwright install chromium  # Optional fallback
```

**Bot Protection:** The scraper includes stealth settings to bypass common bot detection (hides webdriver flag, fakes plugins, etc.). Firefox generally works better than Chromium for bypassing Cloudflare and similar protections.

**Example (simple):**
```yaml
- name: "Security Vendor Docs"
  type: headless
  url: "https://docs.vendor.com/release-notes"
  vendor: "Vendor Name"
  product: "Platform Name"
  wait_for: ".content_block_text, article"
```

**Example (site with bot protection):**
```yaml
- name: "Perplexity Changelog"
  type: headless
  url: "https://www.perplexity.ai/changelog"
  provider: "Perplexity"
  product: "Perplexity"
  wait_for: "h4"  # Wait for heading elements to load
```

**Example (with year template):**
```yaml
- name: "Vendor Annual Release Notes"
  type: headless
  url_template: "https://help.vendor.com/release-summary-{year}"
  vendor: "Vendor Name"
  product: "Product Name"
  dynamic_year: true
  fallback_to_previous_year: true
  wait_for: ".release-notes, article"
```

---

## Finding RSS Feeds

Many sites have RSS feeds but don't advertise them. Try these approaches:

1. **Look for RSS icon** - Usually in the header, footer, or sidebar
2. **Check common paths:**
   - `/feed/`
   - `/rss/`
   - `/rss.xml`
   - `/feed.xml`
   - `/atom.xml`
   - `/index.xml`
3. **View page source** - Search for `type="application/rss+xml"` or `type="application/atom+xml"`
4. **Use browser extensions** - "RSS Feed Reader" or similar can auto-detect feeds
5. **Check GitHub** - Many GitHub repos have release feeds at `github.com/owner/repo/releases.atom`

**Example GitHub release feed:**
```yaml
- name: "F5-TTS Releases"
  type: rss
  url: "https://github.com/SWivid/F5-TTS"
  feed_url: "https://github.com/SWivid/F5-TTS/releases.atom"
```

---

## Finding CSS Selectors

For `web` and `headless` sources, you need CSS selectors. Here's how to find them:

### Using Browser DevTools

1. **Open DevTools** - Right-click the element → "Inspect" (or F12)
2. **Identify the element** - Look at the HTML structure
3. **Build a selector:**
   - By class: `.class-name`
   - By ID: `#element-id`
   - By tag: `article`, `main`, `div`
   - By attribute: `[data-type="article"]`
   - Combined: `article.post-content h2`

### Common Selectors

| Content Type | Common Selectors |
|--------------|------------------|
| Main content | `main`, `article`, `[role="main"]`, `.content` |
| Article list | `.post`, `.article`, `.entry`, `article` |
| Titles | `h1`, `h2`, `h3`, `.title`, `.heading` |
| Dates | `time`, `[datetime]`, `.date`, `.published` |
| Links | `a[href*="/blog/"]`, `a[href*="/news/"]` |

### Tips

- Use multiple selectors separated by commas: `main, article, [role="main"]`
- Be specific enough to avoid false matches
- Test in browser console: `document.querySelectorAll('your-selector')`

---

## Testing Your Source

### Step 1: Validate Configuration

```bash
# Validate schema (fast, no network)
python secintel.py --validate-sources

# Validate a specific tracker
python secintel.py --validate-sources --tracker threat_intel
```

Expected output for valid config:
```
Validating sources...

[threat_intel] 35 sources
  Schema valid

Summary: All sources valid
```

### Step 2: Test Connectivity

```bash
# Test all sources can be reached
python secintel.py --validate-sources --test-connections

# Test specific tracker
python secintel.py --validate-sources --test-connections --tracker threat_intel
```

Expected output:
```
Testing Connections
======================================================================

  Testing connections for threat_intel...
    [OK] Krebs on Security (rss) - 200 OK, 10 items
    [OK] The Hacker News (rss) - 200 OK, 15 items
    [FAIL] BrokenSource (rss) - HTTP 404

Connection Summary: 1 source(s) failed
```

### Step 3: Run a Scrape

```bash
# Scrape just the tracker you modified
python secintel.py --scrape --tracker threat_intel
```

Check the logs (`logs/secintel.log`) for any errors.

---

## Troubleshooting

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `Missing required field: feed_url` | RSS source missing feed URL | Add `feed_url` field |
| `HTTP 403` | Site blocking automated requests | Try `headless` type or different User-Agent |
| `HTTP 404` | URL doesn't exist | Check URL is correct |
| `Feed parse error` | Invalid RSS/Atom format | Try `web` scraping instead |
| `Timeout` | Slow or unresponsive server | Increase timeout or try later |
| `Unknown field` | Typo in field name | Check spelling (e.g., `feed_url` not `feedurl`) |

### Site Blocks Requests

Some sites block automated requests. Options:
1. **Try headless browser** - More closely mimics real browser
2. **Check for API** - Some sites have official APIs
3. **Look for RSS alternative** - Feedburner, Medium, etc. often work

### JavaScript-Heavy Sites

If content doesn't appear when you disable JavaScript:
1. Use `type: headless`
2. Set `wait_for` to a CSS selector that appears after JS loads
3. Install Playwright: `pip install playwright && playwright install`

### Rate Limiting

If you're adding many sources:
- Spread scrapes across time (use different `--tracker` runs)
- Some sites rate-limit; respect their robots.txt

---

## Configuration Reference

### All Fields by Source Type

#### RSS Sources
```yaml
- name: "Source Name"           # Required: Display name
  url: "https://example.com"    # Required: Main website URL
  type: rss                     # Required: Source type
  feed_url: "https://ex.com/feed.xml"  # Required: RSS feed URL
  vendor: "Vendor Name"         # Optional: Vendor for tracking
  product: "Product"            # Optional: Single product name
  products:                     # Optional: Multiple products
    - "Product A"
    - "Product B"
  filter_pattern: "regex"       # Optional: Filter by regex
  filter_by_title: true         # Optional: Filter by title
  keywords:                     # Optional: Content keywords
    - "keyword1"
```

#### Web Sources
```yaml
- name: "Source Name"           # Required: Display name
  url: "https://example.com/page"  # Required: Page URL
  type: web                     # Required: Source type
  base_url: "https://example.com"  # Optional: Base URL for relative links
  parser: "generic"             # Optional: Parser type (generic, release_page, version_list)
  content_selector: "main"      # Optional: Main content CSS
  article_selector: "a.post"    # Optional: Article links CSS
  single_page: true             # Optional: Single page mode
  selectors:                    # Optional: Custom selectors
    title: "h2"
    date: "time"
    content: "p"
  vendor: "Vendor"              # Optional: Vendor name
  product: "Product"            # Optional: Product name
```

**Parser types for web sources:**
- `generic` (default) - Standard article/changelog detection
- `release_page` - Pages with dated release sections (data-release-date attributes)
- `version_list` - Version group lists with release note links

#### API Sources
```yaml
- name: "Source Name"           # Required: Display name
  url: "https://api.example.com/endpoint"  # Required: API URL
  type: api                     # Required: Source type
  base_url: "https://example.com"  # Optional: Base URL for relative links
  params:                       # Optional: Query parameters
    key: "value"
    limit: 50
  headers:                      # Optional: HTTP headers
    Authorization: "Bearer xxx"
  vendor: "Vendor"              # Optional: Vendor name
  product: "Product"            # Optional: Product name
```

#### Headless Sources
```yaml
- name: "Source Name"           # Required: Display name
  type: headless                # Required: Source type
  url: "https://example.com"    # Required*: Page URL
  url_template: "https://ex.com/{year}"  # Required*: URL with year
  parser: "generic"             # Optional: Parser type (see below)
  wait_for: ".content"          # Optional: Wait for selector
  dynamic_year: true            # Optional: Use current year
  fallback_to_previous_year: true  # Optional: Fallback
  vendor: "Vendor"              # Optional: Vendor name
  product: "Product"            # Optional: Product name
# *Either url or url_template required
```

**Parser types for headless sources:**
- `generic` (default) - Standard article/changelog detection
- `release_notes_dated` - Release notes with date headers and feature entries
- `changelog_table` - Table-based changelogs (Release Date | Description columns)
- `monthly_sections` - Content organized by monthly h2 headers

---

## Examples by Use Case

### Adding a Security Blog (RSS)
```yaml
- name: "Security Blog Name"
  url: https://securityblog.example.com
  type: rss
  feed_url: https://securityblog.example.com/feed/
```

### Adding Vendor Release Notes (Web)
```yaml
- name: "Vendor Release Notes"
  type: web
  url: "https://docs.vendor.com/release-notes"
  vendor: "Vendor Name"
  product: "Product Name"
  content_selector: "article, main"
  single_page: true
```

### Adding GitHub Releases (RSS)
```yaml
- name: "Project Releases"
  type: rss
  url: "https://github.com/owner/repo"
  feed_url: "https://github.com/owner/repo/releases.atom"
```

### Adding a JavaScript Site (Headless)
```yaml
- name: "Dynamic Site"
  type: headless
  url: "https://dynamicsite.com/changelog"
  vendor: "Vendor"
  product: "Product"
  wait_for: ".changelog-content, article"
```

---

## Getting Help

If you're stuck:
1. Check existing sources in `trackers/*/config.yaml` for similar examples
2. Use `--validate-sources --test-connections` for diagnostic info
3. Check `logs/secintel.log` for detailed error messages
4. Look at the validation report files in `trackers/threat_intel/*.md` for known issues

Happy source hunting!
