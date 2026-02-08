# Source Templates

This directory contains copy-paste ready templates for adding new sources to SecIntel AI trackers.

## How to Use

1. Open `source_templates.yaml`
2. Find the template matching your source type (RSS, Web, API, or Headless)
3. Copy the template
4. Paste into the appropriate tracker's `config.yaml` file
5. Fill in your source details
6. Validate with: `python secintel.py --validate-sources`

## Which Tracker?

| Source Type | Tracker Directory |
|------------|-------------------|
| Microsoft Defender updates | `trackers/defender/config.yaml` |
| Microsoft security products (Entra, Intune) | `trackers/microsoft_products/config.yaml` |
| Threat intel blogs, CVEs, advisories | `trackers/threat_intel/config.yaml` |
| Third-party security vendors | `trackers/thirdparty_security/config.yaml` |
| AI/LLM news and updates | `trackers/llm_news/config.yaml` |

## Template Files

- `source_templates.yaml` - Copy-paste templates for all source types
- `config_example.yaml` - Complete example showing all possible fields

## Quick Reference

```bash
# Validate your changes
python secintel.py --validate-sources

# Test connectivity
python secintel.py --validate-sources --test-connections

# Scrape a specific tracker
python secintel.py --scrape --tracker <tracker_name>
```

For detailed instructions, see `ADDING_SOURCES.md` in the project root.
