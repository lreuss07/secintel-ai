# Changelog

All notable changes to SecIntel AI are documented here.

## [Unreleased]

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
