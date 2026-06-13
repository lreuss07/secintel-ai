# Changelog

All notable changes to SecIntel AI are documented here.

## [Unreleased]

## [1.3.0] - 2026-06-13

### Added
- **Reports show the actual loaded local model name.** The "AI Model" line in
  report headers previously showed the `local-model` placeholder from config.
  Reports now query LM Studio's native `/api/v0/models` endpoint at generation
  time to resolve the model that's actually loaded (e.g. `google/gemma-4-12b`),
  falling back to the configured value if the endpoint is unreachable. Resolved
  once per run via a shared `resolve_lmstudio_model()` helper used by all six
  trackers.

### Security
- **Prompt-injection defense in all summarizers.** Scraped article bodies,
  video transcripts, and prior summaries are now wrapped in delimiter tags with
  an explicit "treat as data, not instructions" note, so a hostile or
  compromised source can't hijack the LLM (verified: an "ignore all previous
  instructions" payload and a malicious "disable your firewall" directive were
  both ignored).
- **Anti-fabrication guardrails restored across every tracker.** The IOC / CVE /
  threat-actor accuracy rules previously existed only in the threat_intel
  summarizer; they're now applied (in the appropriate flavor) to defender,
  microsoft_products, thirdparty_security, llm_news, and youtube_security too.

### Changed
- **Testing mode now also bounds report generation.** Previously `--max-summaries`
  (and `--testing`) only limited the scrape and analyze stages; the report stage
  still pulled the entire time-window backlog from the database and generated an
  executive summary per section, so a quick test run could fire dozens of LLM
  calls. `get_recent_articles_with_summary()` now takes an optional `limit`, and
  every tracker's report passes `limit=self.max_summaries` — so in testing mode
  the report summarizes only the N most-recent in-window articles. Production
  reports are unchanged (`limit` is `None` when no testing limit is set).
- **LLM prompts externalized to `prompts/*.yaml`** (loaded via
  `core/prompt_library.py`), replacing the prompt strings that were duplicated
  and drifting across the six summarizers. Shared blocks (guardrails, injection
  delimiters, output rules) are defined once in `prompts/common.yaml`.

### Added
- **Database reliability settings** (all optional, safe defaults). `busy_timeout_ms`
  makes connections wait on a locked DB instead of erroring; a startup
  `PRAGMA quick_check` integrity check logs corruption as an early warning; and
  opt-in pre-run snapshot backups via `VACUUM INTO` (with retention) for
  deployments holding data that can't be regenerated. WAL mode is intentionally
  avoided as unsafe on cloud-synced storage. Configurable under `database:` in
  `config.yaml`.

### Fixed
- `secintel.py` now checks the return value of `initialize_database()` and
  aborts on failure instead of continuing into a run against an uninitialized DB.
- **Summarizers skip too-thin content and no longer store errors as summaries.**
  All summarizers now skip articles with under ~200 characters of scraped
  content (empty RSS stub / paywall) before calling the LLM — this matches the
  guard threat_intel already had, and avoids an edge case where empty content
  could push a local model into a degenerate loop. On a genuine summarization
  failure, the summarizer now returns `None` and the analyze loop leaves the
  article unsummarized for retry on the next run, rather than persisting the
  error message as the article's summary.

## [1.2.0] - 2026-06-10

### Security
- **Fixed stored XSS in HTML reports.** Scraped article titles/URLs and AI-generated summaries were interpolated into report HTML without escaping, so a hostile or compromised source could inject script that runs when a report is opened. New `core/report_sanitizer.py` provides `esc()` (HTML-escape scalars), `safe_url()` (allow only `http(s)` schemes, blocking `javascript:`/`data:`), and `sanitize_html()` (nh3 allowlist that keeps markdown formatting in summaries while stripping scripts/event handlers). Applied across the `threat_intel`, `llm_news`, `thirdparty_security`, and `youtube_security` reporters — including the Jinja2-templated paths where autoescape protects quoted attributes but does not block a `javascript:` URL scheme. Also fixes plain mis-rendering of innocent titles containing `<`, `>`, or `&` (e.g. "Q&A"). Adds `nh3` as a dependency (falls back to tag-stripping if unavailable).

### Added
- **M365 Message Center & Roadmap Archive (Merill) source** added to the `microsoft_products` tracker. The Merill feed (`https://mc.merill.net/rss.xml`) republishes Microsoft 365 Message Center messages and Microsoft 365 Roadmap items, covering ~15 items/day across all M365 services. Per Microsoft, Message Center posts vary by tenant — always use your tenant's Message Center as the authoritative source.
- **Per-article RSS-category routing** in the `microsoft_products` report. Articles with RSS `<category>` tags (e.g. Merill items tagged "Microsoft Teams", "Microsoft Purview", "Microsoft Copilot (Microsoft 365)") now route to the correct product bucket per-item rather than per-source, so a single multi-product feed lands across the right product sections. Specific products are preferred over the generic "Office 365 Security" and "Other Security Updates" fallback buckets when multiple categories match.
- **`service:`-prefixed tag persistence** for the `microsoft_products` tracker. RSS `<category>` values are now stored in the `tags` table alongside update-type tags, namespaced with a `service:` prefix so they're filtered out of the update-type display.
- **`youtube_security` tracker** — pulls recent uploads from configurable security YouTube channels, generates AI summaries from transcripts, and produces the same tiered reports as the other trackers. Default channel set includes John Hammond, IppSec, Simply Cyber, Tyler Ramsbey, Troy Hunt, Black Hills InfoSec, NetworkChuck, and The Cyber Mentor; fully customizable in `trackers/youtube_security/config.yaml`.
- **YouTube Data API v3 integration** for video discovery in the YouTube tracker. ~1 quota unit per channel per run against a 10,000/day free quota; eliminates the rate-limiting that affected Atom RSS feed scraping. Falls back to RSS feeds when no API key is configured.
- **yt-dlp + faster-whisper transcript fallback** for the YouTube tracker. When `youtube-transcript-api` is rate-limited or a video has no captions, the tracker downloads the audio and transcribes it locally. NVIDIA GPU acceleration is auto-detected; CUDA libraries are installed via the new optional `requirements-gpu.txt`. Audio files are deleted immediately after transcription.
- **Throttle-aware transcript routing** — once an IP block is detected (explicit `RequestBlocked`/`IpBlocked` exception or N consecutive non-captions failures, configurable), the scraper skips `youtube-transcript-api` for the rest of the run and goes directly to Whisper, avoiding doomed requests that worsen the throttle.
- **`--exclude TRACKER [TRACKER ...]`** CLI flag to skip specific trackers from a `--tracker=all` run. Useful for excluding the expensive `youtube_security` tracker from routine `--full-run` cron jobs (`--full-run --exclude youtube_security`).
- **`requirements-gpu.txt`** — optional install for NVIDIA CUDA libraries (`nvidia-cublas-cu12`, `nvidia-cudnn-cu12`, `nvidia-cuda-nvrtc-cu12`). Runtime auto-preload of these libraries means no `LD_LIBRARY_PATH` setup is required regardless of install method (conda, pip+venv, system Python).

### Changed
- **`youtube_security` is now opt-in per run.** Because it downloads audio and runs Whisper transcription, an interactive `--tracker all` / `--full-run` now prompts whether to include it, defaulting to **no** after a 10-second timeout. Non-interactive sessions (cron, piped input) skip it automatically with no flags needed; an explicit `--tracker youtube_security` always runs it without prompting, and `--exclude youtube_security` suppresses the prompt entirely.
- Feed-fetch hardening for the YouTube tracker's RSS fallback path: browser User-Agent + retry-with-backoff (15s, 45s) on `bozo + no entries` responses, and longer inter-channel sleep (3–7s) to avoid burst-detection.

## [1.1.1] - 2026-05-13

### Fixed
- Claude AI provider was never used at runtime even when `ai.provider: claude` was set in `config.yaml`. All trackers were hardcoded to route through `LMStudioConnectionManager`, which stripped the `provider` key from the config passed to summarizers, causing `AIClient` to silently fall back to LM Studio. Trackers now branch on `ai.provider` and pass the full AI config through to summarizers, executive summarizers, and `test_connection()`.
- Opus 4.7 (`claude-opus-4-7`) was returning HTTP 400 `temperature is deprecated for this model`. The Claude completion path now omits the `temperature` parameter for models that have deprecated it. Sonnet 4.6 and Haiku 4.5 are unaffected.

### Changed
- `config.yaml.example` Claude default model bumped from `claude-sonnet-4-20250514` to `claude-sonnet-4-6`.

## [1.1.0] - 2026-02-14

### Added
- `--testing` mode for quick pipeline validation with resource limits (`--max-sources`, `--max-articles`, `--max-summaries`)
- Report screenshots in README with collapsible sections for all 5 report types
- CHANGELOG.md for tracking changes
- Release versioning guide (`docs/RELEASING.md`)
