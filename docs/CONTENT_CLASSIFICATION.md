# Content Classification Feature

## Overview

The SecIntel AI Unified Tracker now includes an AI-powered content pre-classification system that prevents hallucination of threat intelligence in non-threat articles. This feature automatically classifies articles before summarization and applies appropriate summarization strategies based on content type.

## Problem Solved

Previously, all articles were summarized using the same threat intelligence prompt template. This caused the AI to fabricate IOCs, threat actors, and attack details when processing non-threat content such as:
- Industry news articles
- Opinion pieces
- Product announcements
- General cybersecurity explainer articles

## Solution

The new classification system:

1. **Pre-classifies** each article into one of three categories before summarization
2. **Applies different prompts** based on the classification to prevent hallucination
3. **Stores the classification** in the database for future reference and filtering

## Content Categories

### 1. Threat Advisory (`threat_advisory`)

**Characteristics:**
- CVEs, vulnerabilities, security patches
- Malware analysis and threat actor reports
- Breach reports and incident analysis
- Active exploitation campaigns
- IOCs (Indicators of Compromise)
- Security advisories and alerts

**Summarization Approach:**
- Full technical analysis (250-350 words)
- IOC extraction and listing
- Threat actor attribution
- MITRE ATT&CK mapping
- Mitigation recommendations

**Example Articles:**
- "APT29 Exploits CVE-2024-12345 in Campaign Against Healthcare Sector"
- "New Emotet Variant Targets Financial Institutions"
- "Zero-Day Vulnerability in Apache Log4j Actively Exploited"

### 2. Product Update (`product_update`)

**Characteristics:**
- Vendor product changelogs
- Feature announcements and release notes
- Product updates and new capabilities
- Beta/preview feature releases
- Version updates and roadmaps

**Summarization Approach:**
- Focused on what changed (150-250 words)
- New features and improvements
- Availability information
- Security benefits
- **No fabricated IOCs or threat actors**

**Example Articles:**
- "Microsoft Defender ATP Adds New EDR Capabilities"
- "EDR Platform 7.0 Released with Performance Improvements"
- "SIEM Platform 8.0 Now Generally Available"

### 3. Industry News (`industry_news`)

**Characteristics:**
- General cybersecurity news
- Opinion pieces and editorials
- Policy updates and regulations
- Industry trends and analysis
- Explainer articles and how-to guides
- Company announcements
- Market analysis and research

**Summarization Approach:**
- Brief, factual summary (2-3 sentences, max 100 words)
- Main topic and relevance
- Key implications
- **No fabricated technical details**

**Example Articles:**
- "CISA Issues New Cybersecurity Guidelines for Critical Infrastructure"
- "The State of Ransomware in 2024: A Market Analysis"
- "Why Zero Trust is More Important Than Ever"

## Architecture

### Classification Flow

```
Article → AI Classification → Content Type → Appropriate Prompt → Summary
```

### Components

#### 1. Database Schema (`core/database.py`)

The `articles` table now includes a `content_type` column:

```sql
CREATE TABLE articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tracker_name TEXT,
    source TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    author TEXT,
    published_date TEXT,
    content TEXT NOT NULL,
    summary TEXT,
    content_type TEXT,  -- NEW: 'threat_advisory', 'product_update', or 'industry_news'
    scraped_date TEXT NOT NULL,
    analyzed_date TEXT,
    UNIQUE(tracker_name, url)
)
```

#### 2. AI Classification (`core/ai_client.py`)

New method `classify_content()` in the `AIClient` class:

```python
def classify_content(self, title: str, content: str) -> str:
    """
    Classify article content into one of three categories.

    Returns:
        str: 'threat_advisory', 'product_update', or 'industry_news'
    """
```

**Key Features:**
- Uses only first 2000 characters for speed
- Temperature set to 0.0 for deterministic results
- Robust validation and fallback logic
- Defaults to 'industry_news' on error (safest option)

#### 3. Prompt Templates (`trackers/threat_intel/summarizer.py`)

Three specialized prompt methods:
- `_get_threat_advisory_prompt()` - Full threat intel analysis
- `_get_product_update_prompt()` - Product-focused summary
- `_get_industry_news_prompt()` - Brief informational summary

#### 4. Updated Summarizer

The `ArticleSummarizer.summarize()` method now:

1. Classifies the article first
2. Selects the appropriate prompt template
3. Adjusts max_tokens based on content type
4. Returns `(summary, content_type)` tuple instead of just summary

## Usage

### For Existing Databases

Run the migration script to add the `content_type` column:

```bash
cd .
python migrate_add_content_type.py
```

### Normal Operation

The classification happens automatically during the `--analyze` step:

```bash
# Standard workflow (classification happens automatically)
python secintel.py --scrape
python secintel.py --analyze  # Classification occurs here
python secintel.py --report
```

### Logs

The classification results are logged during analysis:

```
INFO - Classifying content type for 'New Ransomware Campaign Targets Healthcare...'
INFO - Content classified as 'threat_advisory'
INFO - ✓ Summary generated for article ID: 123 (classified as 'threat_advisory')
```

### Viewing Classifications

Classifications are stored in the database and can be queried:

```python
from core.database import DatabaseManager

db = DatabaseManager('data/secintel.db')
conn = db.get_connection()
cursor = conn.cursor()

# Count articles by content type
cursor.execute("""
    SELECT content_type, COUNT(*) as count
    FROM articles
    WHERE content_type IS NOT NULL
    GROUP BY content_type
""")

for row in cursor.fetchall():
    print(f"{row['content_type']}: {row['count']} articles")
```

## Configuration

No additional configuration is required. The feature uses the existing AI configuration:

```yaml
# config.yaml
ai:
  provider: 'lmstudio'  # or 'claude'
  lmstudio:
    base_url: 'http://localhost:1234/v1'
    api_key: 'lm-studio'
    model: 'local-model'
  temperature: 0.1
```

## Performance Considerations

### Classification Speed

- Classification uses only first 2000 characters of content
- Maximum 10 tokens output (single word response)
- Temperature 0.0 for fastest, deterministic results
- Typical classification time: 1-2 seconds per article

### Token Usage

Compared to previous approach:

| Content Type | Old Tokens | New Tokens (Classify + Summarize) | Savings |
|--------------|------------|-----------------------------------|---------|
| Threat Advisory | 2000 | ~300 + 2000 = 2300 | -15% |
| Product Update | 2000 | ~300 + 1500 = 1800 | +10% |
| Industry News | 2000 | ~300 + 500 = 800 | +60% |

**Overall:** Approximately 20-30% token savings on mixed content feeds.

## Error Handling

### Classification Failures

If classification fails or returns invalid results:
- Logs a warning with the error
- Defaults to `'industry_news'` (safest option to prevent hallucination)
- Summarization continues with the brief news prompt

### Backward Compatibility

- Existing articles without `content_type` are not re-classified
- The `content_type` column is optional in database queries
- Old reports continue to work without modification

## Testing

### Manual Testing

Test the classification with a sample article:

```python
from core.ai_client import AIClient
import yaml

# Load config
with open('config.yaml', 'r') as f:
    config = yaml.safe_load(f)

# Initialize AI client
client = AIClient(config['ai'])

# Test classification
title = "New Ransomware Campaign Targets Healthcare Sector"
content = """
A new ransomware campaign has been observed targeting healthcare
organizations across North America. The threat actors, believed to
be linked to the LockBit group, are exploiting CVE-2024-12345 to
gain initial access to networks...
"""

classification = client.classify_content(title, content)
print(f"Classification: {classification}")  # Should be 'threat_advisory'
```

### Integration Testing

Run the full analysis pipeline on test data:

```bash
# Scrape some articles
python secintel.py --scrape

# Analyze with new classification system
python secintel.py --analyze

# Check logs for classification results
tail -f logs/secintel.log | grep "classified as"
```

## Troubleshooting

### Issue: All articles classified as 'industry_news'

**Possible Causes:**
- AI model not properly loaded in LM Studio
- Classification prompt not compatible with the model
- Network connectivity issues

**Solutions:**
1. Test AI connection: `python secintel.py --test-connection`
2. Check LM Studio is running and model is loaded
3. Try a different model (recommend Llama 3 8B or Mistral 7B)

### Issue: Classifications seem incorrect

**Possible Causes:**
- Model hallucinating or not following instructions
- Content sample (first 2000 chars) not representative

**Solutions:**
1. Increase content sample size in `classify_content()` (e.g., to 3000 chars)
2. Try with `temperature=0.0` for more deterministic results
3. Use Claude API instead of LM Studio for more accurate classification

### Issue: Migration script fails

**Possible Causes:**
- Database locked by another process
- Insufficient permissions
- Database corruption

**Solutions:**
1. Stop all SecIntel AI processes before running migration
2. Check file permissions on database files
3. Make backup before migration: `cp data/secintel.db data/secintel.db.backup`

## Future Enhancements

Potential improvements for future releases:

1. **Confidence Scores**: Return classification confidence to flag uncertain cases
2. **Multi-label Classification**: Articles could have multiple types
3. **Custom Categories**: Allow users to define custom content types
4. **Re-classification**: Tool to re-classify existing articles
5. **Classification Dashboard**: Visualize content type distribution over time
6. **Fine-tuning**: Train custom classification model on SecIntel AI data

## References

- Main implementation: `./core/ai_client.py` (line 242)
- Database schema: `./core/database.py` (line 62)
- Summarizer logic: `./trackers/threat_intel/summarizer.py` (line 156)
- Migration script: `./migrate_add_content_type.py`
