# SecIntel AI - Security Intelligence Tracker

AI-powered security intelligence aggregation and reporting platform. SecIntel AI scrapes updates from Microsoft security products, threat intelligence feeds, third-party security tools, and LLM providers, then generates AI-powered summaries and executive reports using local LLMs (LM Studio) or cloud APIs (Claude).

## Report Examples

<details>
<summary><b>Microsoft Defender Report</b></summary>

![Header and stats](docs/images/security_product_tier1_report_20260214_094747_01_header_stats.png)
![Products overview](docs/images/security_product_tier1_report_20260214_094747_02_products_overview.png)
![What's new](docs/images/security_product_tier1_report_20260214_094747_04_whats_new.png)
![Executive summary](docs/images/security_product_tier1_report_20260214_094747_07_exec_summary.png)

</details>

<details>
<summary><b>Microsoft Security Products Report</b></summary>

![Header and stats](docs/images/security_product_tier1_report_20260214_101511_01_header_stats.png)
![Products overview](docs/images/security_product_tier1_report_20260214_101511_02_products_overview.png)
![What's new](docs/images/security_product_tier1_report_20260214_101511_04_whats_new.png)
![Executive summary](docs/images/security_product_tier1_report_20260214_101511_06_exec_summary.png)

</details>

<details>
<summary><b>Threat Intelligence Report</b></summary>

![Header](docs/images/threat_intel_tier1_report_20260214_103030_01_header.png)
![Threat overview](docs/images/threat_intel_tier1_report_20260214_103030_02_threat_overview.png)
![Top threats](docs/images/threat_intel_tier1_report_20260214_103030_03_top_threats.png)
![Impact and actions](docs/images/threat_intel_tier1_report_20260214_103030_04_impact_actions.png)
![IOCs and navigation](docs/images/threat_intel_tier1_report_20260214_103030_05_iocs_nav.png)

</details>

<details>
<summary><b>3rd Party Security Report</b></summary>

![Header and stats](docs/images/thirdparty_security_report_20260214_103621_01_header_stats.png)
![Products overview](docs/images/thirdparty_security_report_20260214_103621_02_products_overview.png)
![What's new](docs/images/thirdparty_security_report_20260214_103621_04_whats_new.png)
![Executive summary](docs/images/thirdparty_security_report_20260214_103621_06_exec_summary.png)

</details>

<details>
<summary><b>LLM News Report</b></summary>

![Header and stats](docs/images/llm_news_report_20260214_104026_01_header_stats.png)
![Providers overview](docs/images/llm_news_report_20260214_104026_02_providers_overview.png)
![Executive summary](docs/images/llm_news_report_20260214_104026_03_whats_new.png)
![Detailed provider coverage](docs/images/llm_news_report_20260214_104026_06_detailed_anthropic.png)

</details>

## Prerequisites

- **Python 3.8+**
- **LM Studio** running with a model loaded (for AI summarization)
  - Download from: https://lmstudio.ai
  - Recommended models: Llama 3 8B, Mistral 7B, or any 20B+ parameter model
  - Default endpoint: `http://localhost:1234/v1`
- **ffmpeg** (only if using the `youtube_security` tracker, for audio extraction)
  - Debian/Ubuntu: `sudo apt install ffmpeg`
  - macOS: `brew install ffmpeg`
  - Windows: `choco install ffmpeg` or download from https://ffmpeg.org/
- **NVIDIA GPU + CUDA 12** (optional, for faster Whisper transcription on YouTube videos)
  - Any RTX 20-series or newer
  - On Windows + WSL2, the NVIDIA driver installed on Windows is enough — WSL2 sees it transparently
  - CUDA libraries are installed via pip (see Installation), no manual CUDA setup needed

> **AI Model Note:** Local 20B+ parameter models provide comparable accuracy to cloud APIs at zero cost. We recommend LM Studio for most users. See [docs/AI_PROVIDER_SETUP.md](docs/AI_PROVIDER_SETUP.md) for setup instructions.

## Installation

```bash
# Clone the repository
git clone https://github.com/lreuss07/secintel-ai.git
cd secintel-ai

# Install Python dependencies
pip install -r requirements.txt

# Optional: Install NVIDIA CUDA libraries for GPU Whisper transcription
# (only needed if you use the youtube_security tracker and have an NVIDIA GPU)
pip install -r requirements-gpu.txt

# Copy example configs and edit with your settings
# (config.yaml files are not included - they contain API keys and reveal your security stack)
cp config.yaml.example config.yaml

# Copy tracker configs (customize with your own vendors/sources)
for f in trackers/*/config.yaml.example; do cp "$f" "${f%.example}"; done

# Install Playwright browsers (required for thirdparty_security and llm_news trackers)
# Firefox is recommended - better at bypassing bot protection than Chromium
pip install playwright
playwright install firefox

# Optional: Install Chromium as fallback
playwright install chromium

# On Linux/WSL, you may need to install system dependencies:
playwright install-deps firefox
```

## LM Studio Setup

SecIntel AI uses LM Studio as the default AI backend for generating summaries. Here's how to set it up:

### 1. Install LM Studio

Download and install from [lmstudio.ai](https://lmstudio.ai) (available for Windows, macOS, and Linux).

### 2. Download a Model

1. Open LM Studio
2. Go to the **Discover** tab
3. Search for and download a model. Recommended options:
   - **GPT-OSS-20B** - Best balance of quality and speed (used for most SecIntel AI reports)
   - **Llama 3 8B** - Faster, good for testing
   - **Mistral 7B Instruct** - Lightweight alternative
4. Download the **Q4_K_M** quantized version for best performance/quality balance

### 3. Start the Local Server

1. Go to the **Local Server** tab in LM Studio
2. Load your downloaded model
3. Click **Start Server**
4. Note the server address (default: `http://localhost:1234/v1`)

### 4. Configure SecIntel AI

Edit `config.yaml` to point to your LM Studio server:

```yaml
ai:
  provider: 'lmstudio'
  lmstudio:
    base_url: 'http://localhost:1234/v1'  # Your LM Studio address
    api_key: 'lm-studio'                   # Can be any string
    model: 'local-model'                   # Can be any string
  temperature: 0.1
```

### 5. Test the Connection

```bash
python secintel.py --test-connection
```

You should see: `Connection to LM Studio successful!`

For Claude API setup and advanced configuration, see [docs/AI_PROVIDER_SETUP.md](docs/AI_PROVIDER_SETUP.md).

## Quick Start

```bash
# Test LM Studio connection
python secintel.py --test-connection

# List available trackers
python secintel.py --list

# Run full workflow for all trackers
python secintel.py --full-run

# Run specific tracker
python secintel.py --tracker thirdparty_security --full-run

# Generate tier 1 weekly report
python secintel.py --report --tier 1
```

## Available Trackers

| Tracker | Description | Sources |
|---------|-------------|---------|
| `defender` | Microsoft Defender product updates | XDR, Endpoint, Office 365, Identity, Vulnerability Management |
| `microsoft_products` | Microsoft security products | Entra, Intune, Purview, Sentinel, etc. |
| `threat_intel` | Threat intelligence news | Security blogs, CISA alerts, vendor advisories |
| `thirdparty_security` | 3rd party security tools | Configurable - see `trackers/thirdparty_security/config.yaml.example` |
| `llm_news` | LLM/AI provider updates | Anthropic, OpenAI, Google, Meta, Perplexity, etc. |
| `youtube_security` | Security YouTube channels | John Hammond, IppSec, BHIS, Troy Hunt, Simply Cyber, NetworkChuck, TCM, Tyler Ramsbey (configurable) |

### 3rd Party Security Tools

The `thirdparty_security` tracker supports monitoring updates from various security vendors. Configure your own sources in `trackers/thirdparty_security/config.yaml`.

**Supported source types:**
- RSS feeds
- JSON APIs
- Web scraping
- Headless browser (for JavaScript-rendered pages)

See `trackers/thirdparty_security/config.yaml.example` for example configurations covering EDR/XDR, SIEM, vulnerability management, network security, identity, and email security vendors.

### YouTube Security Channels

The `youtube_security` tracker pulls recent uploads from security YouTube channels and summarizes them via their transcripts. It uses a layered transcript strategy:

1. **`youtube-transcript-api`** for the fast path — reads YouTube's existing captions in ~1 second per video. Free, but YouTube rate-limits this aggressively from non-residential IPs.
2. **yt-dlp + faster-whisper fallback** — if the captions endpoint is throttled or the video has no captions, the tracker downloads the audio (~20–150 MB) and transcribes it locally. Audio files are deleted right after transcription. GPU acceleration is auto-detected.

**Discovery** uses the YouTube Data API when a key is configured (recommended — see `trackers/youtube_security/config.yaml.example` for setup; ~1 quota unit per channel per run against a 10,000/day free quota). Without a key, discovery falls back to YouTube's Atom RSS feeds.

**Why YouTube is special:** the tracker is dramatically more expensive than the RSS-based ones when the captions endpoint is throttled, since every video routes through Whisper. Because of this, it is **opt-in per run**: an interactive `--tracker all` / `--full-run` asks whether to include it, defaulting to **no** after 10 seconds. Non-interactive runs (cron, piped) skip it automatically — no flags needed. To run it, answer `y` at the prompt or invoke it explicitly:

```bash
# Routine run — prompts for YouTube (auto-skips after 10s, or in cron)
python secintel.py --full-run

# YouTube only, no prompt
python secintel.py --tracker youtube_security --full-run

# Suppress the prompt entirely on interactive full runs
python secintel.py --full-run --exclude youtube_security
```

## Commands

| Command | Description |
|---------|-------------|
| `--scrape` | Scrape new updates from sources |
| `--analyze` | Generate AI summaries for scraped updates |
| `--report` | Generate HTML/Markdown reports |
| `--tier {0,1,2,3}` | Report tier: 0=Daily (1d), 1=Weekly (7d), 2=Bi-Weekly (14d), 3=Monthly (30d) |
| `--full-run` | Complete workflow (scrape -> analyze -> report) |
| `--tracker NAME` | Select tracker: `defender`, `microsoft_products`, `threat_intel`, `thirdparty_security`, `llm_news`, `youtube_security`, or `all` |
| `--exclude NAME [NAME ...]` | Skip one or more trackers from a `--tracker=all` run (e.g. `--exclude youtube_security` for a faster daily run) |
| `--test-connection` | Test LM Studio connection |
| `--list` | List available trackers |
| `--config FILE` | Specify configuration file (default: config.yaml) |
| `--verbose` | Enable verbose logging |

## Configuration

### Global Configuration (`config.yaml`)

```yaml
# AI settings (LM Studio endpoint)
ai:
  base_url: 'http://localhost:1234/v1'  # Change to your LM Studio address
  api_key: 'lm-studio'
  model: 'local-model'
  temperature: 0.1

# Database
database:
  path: data/secintel.db

# Enable/disable trackers
trackers:
  defender:
    enabled: true
  microsoft_products:
    enabled: true
  threat_intel:
    enabled: true
  thirdparty_security:
    enabled: true
```

### Tracker-Specific Configuration

Each tracker has its own configuration in `trackers/<name>/config.yaml` for defining sources, keywords, and scraping parameters.

> **Note:** The repository includes `.example` files as templates. Copy them to `config.yaml` and customize with your own vendors and sources. Your `config.yaml` files are gitignored to keep your security stack private.

## Directory Structure

```
secintel-ai/
├── secintel.py                 # Main CLI entry point
├── config.yaml                 # Global configuration
├── requirements.txt            # Python dependencies
├── core/                       # Shared modules
│   ├── ai_client.py            # Unified AI client (LM Studio + Claude)
│   ├── base_tracker.py         # Base tracker class
│   ├── config.py               # YAML config loading
│   ├── database.py             # SQLite operations
│   ├── ioc_extractor.py        # IOC extraction utilities
│   ├── lm_studio_connection.py # LM Studio connection manager
│   ├── microsoft_security_scraper.py    # Shared scraper (defender + microsoft_products)
│   ├── microsoft_security_summarizer.py # Shared summarizer (defender + microsoft_products)
│   ├── prompt_library.py       # Loads externalized prompts from prompts/
│   ├── report_helpers.py       # Shared report utilities
│   ├── report_sanitizer.py     # HTML escaping/XSS protection
│   └── source_validator.py     # Source configuration validator
├── prompts/                    # Externalized LLM prompt templates (YAML)
│   ├── classify.yaml
│   ├── common.yaml
│   ├── llm_news.yaml
│   ├── microsoft_products.yaml
│   ├── thirdparty.yaml
│   ├── threat_intel.yaml
│   └── youtube.yaml
├── trackers/                   # Tracker plugins
│   ├── defender/               # Microsoft Defender tracker
│   ├── microsoft_products/     # Microsoft Products tracker
│   ├── threat_intel/           # Threat Intelligence tracker
│   ├── thirdparty_security/    # 3rd Party Security tracker
│   │   ├── __init__.py
│   │   ├── config.yaml         # Source definitions
│   │   ├── scraper_thirdparty.py
│   │   ├── summarizer_thirdparty.py
│   │   ├── reporting_thirdparty.py
│   │   └── templates/
│   ├── llm_news/               # LLM/AI provider updates tracker
│   └── youtube_security/       # Security YouTube channels tracker (opt-in)
├── data/                       # SQLite database
├── reports/                    # Generated reports
│   ├── defender/
│   ├── microsoft_products/
│   ├── threat_intel/
│   ├── thirdparty_security/
│   ├── llm_news/
│   └── youtube_security/
└── logs/                       # Log files
```

## Examples

```bash
# Scrape 3rd party security tool updates only
python secintel.py --tracker thirdparty_security --scrape

# Analyze all pending updates across all trackers
python secintel.py --analyze

# Generate weekly digest for Defender tracker
python secintel.py --tracker defender --tier 1 --report

# Full workflow for threat intelligence
python secintel.py --tracker threat_intel --full-run

# Generate daily report for 3rd party tools
python secintel.py --tracker thirdparty_security --tier 0 --full-run
```

## Report Tiers

| Tier | Time Window | Use Case |
|------|-------------|----------|
| 0 | 1 day | Daily digest |
| 1 | 7 days | Weekly summary |
| 2 | 14 days | Bi-weekly review |
| 3 | 30 days | Monthly archive |

## Troubleshooting

### LM Studio Connection Failed

```bash
# Verify LM Studio is running and model is loaded
python secintel.py --test-connection

# Check the endpoint in config.yaml matches your LM Studio address
```

### Playwright Browser Issues

Some sources require Playwright headless browser to bypass bot protection.

```bash
# Install Playwright and Firefox (recommended - better at bypassing bot detection)
pip install playwright
playwright install firefox

# Also install Chromium as fallback
playwright install chromium

# If you get missing library errors on Linux/WSL, install dependencies:
playwright install-deps firefox
```

**Required for:** `thirdparty_security` and `llm_news` trackers (headless sources)

### No Articles Scraped

- Check `logs/secintel.log` for errors
- Verify network connectivity to source URLs
- Some sources may have changed their HTML structure

### 403 Forbidden Errors

Some sites block automated requests. The `thirdparty_security` and `llm_news` trackers use Playwright with a headless browser and stealth settings to bypass bot detection. Ensure Playwright is installed:

```bash
pip install playwright
playwright install firefox
```

**Note:** Firefox generally works better than Chromium for bypassing bot protection.

## Output

Reports are generated in both HTML and Markdown formats:

- `reports/<tracker>/<tracker>_tier<N>_report_YYYYMMDD_HHMMSS.html`
- `reports/<tracker>/<tracker>_tier<N>_report_YYYYMMDD_HHMMSS.md`

### Example Reports

See [docs/examples/](docs/examples/) for sample reports demonstrating the output format:

- [Defender Weekly Report](docs/examples/defender_weekly_report.html)
- [Microsoft Products Weekly Report](docs/examples/microsoft_products_weekly_report.html)
- [Threat Intel Weekly Report](docs/examples/threat_intel_weekly_report.html)
- [LLM News Weekly Report](docs/examples/llm_news_weekly_report.html)

## Dependencies

See `requirements.txt` for the full list. Key dependencies:

| Package | Purpose |
|---------|---------|
| `openai` | LM Studio API client (OpenAI-compatible) |
| `anthropic` | Claude API client |
| `requests` | HTTP requests |
| `feedparser` | RSS feed parsing |
| `beautifulsoup4` | HTML parsing |
| `playwright` | Headless browser for JS-rendered pages |
| `jinja2` | Report templating |
| `pyyaml` | Configuration files |
| `youtube-transcript-api` | YouTube captions (fast path for the `youtube_security` tracker) |
| `yt-dlp` | Audio download fallback when YouTube captions are unavailable / throttled |
| `faster-whisper` | Local speech-to-text for the YouTube Whisper fallback (CPU or NVIDIA GPU) |

## Acknowledgments

Special thanks to **Joff Thyer** and **Derek Banks** for their course [AI for Cybersecurity Professionals](https://www.antisyphontraining.com/product/ai-for-cybersecurity-professionals-with-joff-thyer-and-derek-banks). This project was inspired by sample code and concepts from that course, which demonstrated scraping cybersecurity news and summarizing it via API calls to frontier LLM models.

That sparked the idea: why not take this concept further and track security vendor updates? I also didn't want to pay for API calls, so I set up the script to work with my local LLM.

I coded the majority of this program spending countless hours prompting Claude Code to get it exactly how I wanted. There are still bugs to fix, and local LLMs lack some accuracy compared to frontier models, but they do a fairly good job. Most reports were generated using **GPT-OSS-20B** running locally via LM Studio.

The course was a game-changer for me - it took me from thinking LLMs were just chatbots to being able to use them to write scripts that automate real work. I highly recommend it to anyone interested in applying AI to cybersecurity.

I have a lot of ideas for improving this project and hope to keep developing it. If you have feedback or want to connect:
- LinkedIn: [levireuss.com](https://www.levireuss.com)
- X: [@levi_reuss](https://x.com/levi_reuss)

## Contributing

Contributions are welcome! To contribute:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Make your changes
4. Submit a pull request

**Adding new sources:** See [docs/ADDING_SOURCES.md](docs/ADDING_SOURCES.md) for detailed instructions on adding new data sources.

**Adding new trackers:** Use `trackers/_template/` as a starting point for creating new tracker plugins.

## License

MIT License - See [LICENSE](LICENSE) for details.
