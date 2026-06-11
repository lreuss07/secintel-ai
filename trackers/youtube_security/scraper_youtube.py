"""
YouTube Security Scraper for SecIntel AI.
Discovers videos via YouTube RSS feeds and fetches transcripts for analysis.
"""

import logging
import os
import tempfile
import feedparser
import requests
import time
import random
from datetime import datetime, timedelta
from dateutil import parser as date_parser
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    TranscriptsDisabled,
    NoTranscriptFound,
    CouldNotRetrieveTranscript,
    VideoUnavailable,
)
try:
    from youtube_transcript_api._errors import RequestBlocked, IpBlocked
    _BLOCK_EXCEPTIONS = (RequestBlocked, IpBlocked)
except ImportError:
    _BLOCK_EXCEPTIONS = ()

logger = logging.getLogger(__name__)

YOUTUBE_FEED_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
YOUTUBE_WATCH_URL = "https://www.youtube.com/watch?v={video_id}"
YOUTUBE_API_PLAYLIST_ITEMS_URL = "https://www.googleapis.com/youtube/v3/playlistItems"

# Browser-like UA to avoid YouTube serving HTML error pages to feedparser's default UA
FEED_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

# Retry backoff (seconds) for transient feed 404s/HTML responses. Length = number of retries.
FEED_RETRY_BACKOFF_SECONDS = (15, 45)


class YouTubeSecurityScraper:
    """Scrapes security YouTube channels via RSS feeds and fetches transcripts."""

    def __init__(self, sources_config, time_window_days=None, max_articles_per_source=None,
                 transcript_config=None, api_key=None):
        self.sources = sources_config
        self.time_window_days = time_window_days or 30
        self.max_articles_per_source = max_articles_per_source
        self.transcript_config = transcript_config or {}
        self.max_transcript_chars = self.transcript_config.get('max_chars', 15000)
        self.min_transcript_chars = self.transcript_config.get('min_chars', 200)
        self.transcript_languages = self.transcript_config.get('languages', ['en'])
        self.api_key = api_key
        self.ytt_api = YouTubeTranscriptApi()

        whisper_cfg = self.transcript_config.get('whisper', {}) or {}
        self.whisper_enabled = whisper_cfg.get('enabled', False)
        self.whisper_model_size = whisper_cfg.get('model_size', 'small')
        self.whisper_device = whisper_cfg.get('device', 'auto')
        self.whisper_compute_type = whisper_cfg.get('compute_type', 'auto')
        self.whisper_audio_tmpdir = whisper_cfg.get('audio_tmpdir', tempfile.gettempdir())
        self._whisper_model = None  # Loaded lazily on first fallback

        # Once we detect YouTube has throttled our IP on the transcript endpoint,
        # stop hitting it for the rest of this run — continuing only delays
        # recovery and wastes time before each Whisper fallback.
        self.transcript_api_max_consecutive_failures = self.transcript_config.get(
            'max_consecutive_failures', 3
        )
        self._transcript_api_blocked = False
        self._transcript_api_consecutive_failures = 0

        if self.api_key:
            logger.info("YouTube Data API key configured — using API for video discovery")
        else:
            logger.info("No YouTube Data API key — falling back to Atom RSS feeds for discovery")
        if self.whisper_enabled:
            logger.info(
                f"Whisper fallback enabled (model={self.whisper_model_size}, device={self.whisper_device})"
            )

    def scrape_all_sources(self):
        """
        Scrape all configured YouTube channels.

        Returns:
            dict: {source_name: [article_dicts]}
        """
        results = {}
        cutoff_date = datetime.now() - timedelta(days=self.time_window_days)

        for source in self.sources:
            source_name = source.get('name', 'Unknown')
            channel_id = source.get('channel_id')

            if not channel_id:
                logger.warning(f"No channel_id for source '{source_name}', skipping")
                continue

            logger.info(f"Scraping YouTube channel: {source_name} ({channel_id})")

            try:
                articles = self._scrape_channel(source, cutoff_date)
                results[source_name] = articles
                logger.info(f"Found {len(articles)} videos with transcripts from {source_name}")
            except Exception as e:
                logger.error(f"Error scraping {source_name}: {e}")
                results[source_name] = []

            # Rate limiting between sources — bursty requests get 404'd by YouTube's edge
            time.sleep(random.uniform(3.0, 7.0))

        return results

    def _scrape_channel(self, source, cutoff_date):
        """
        Scrape a single YouTube channel via RSS feed and fetch transcripts.

        Args:
            source (dict): Source config with channel_id, name, provider, product
            cutoff_date (datetime): Only include videos published after this date

        Returns:
            list: List of article dicts ready for store_article()
        """
        channel_id = source['channel_id']
        source_name = source.get('name', 'Unknown')
        provider = source.get('provider', 'YouTube')
        product = source.get('product', source_name)

        entries = self._discover_videos(channel_id, source_name)
        if not entries:
            return []

        articles = []

        if self.max_articles_per_source:
            entries = entries[:self.max_articles_per_source]

        for entry in entries:
            try:
                # Parse published date
                published = entry.get('published', '')
                try:
                    pub_date = date_parser.parse(published)
                    if pub_date.tzinfo:
                        pub_date = pub_date.replace(tzinfo=None)
                    if pub_date < cutoff_date:
                        continue
                except (ValueError, TypeError):
                    pub_date = datetime.now()

                # Extract video ID from the entry link
                video_id = self._extract_video_id(entry)
                if not video_id:
                    logger.debug(f"Could not extract video ID from entry: {entry.get('title', '?')}")
                    continue

                title = entry.get('title', 'Untitled Video')
                url = YOUTUBE_WATCH_URL.format(video_id=video_id)
                author = entry.get('author', source_name)

                logger.info(f"  Fetching transcript for: {title}")

                # Fetch transcript
                transcript_text = self._fetch_transcript(video_id)
                if not transcript_text:
                    logger.info(f"  No transcript available for: {title}")
                    continue

                if len(transcript_text) < self.min_transcript_chars:
                    logger.info(f"  Transcript too short ({len(transcript_text)} chars) for: {title}")
                    continue

                # Truncate transcript to max storage limit
                if len(transcript_text) > self.max_transcript_chars:
                    transcript_text = transcript_text[:self.max_transcript_chars] + "\n\n[Transcript truncated]"

                article = {
                    'source': source_name,
                    'title': title,
                    'url': url,
                    'author': author,
                    'published_date': pub_date.isoformat(),
                    'content': transcript_text,
                    'provider': provider,
                    'product': product,
                }

                articles.append(article)
                logger.info(f"  Got transcript ({len(transcript_text)} chars) for: {title}")

                # Rate limiting between video transcript fetches
                time.sleep(random.uniform(0.5, 1.5))

            except Exception as e:
                logger.error(f"Error processing entry '{entry.get('title', '?')}': {e}")
                continue

        return articles

    def _discover_videos(self, channel_id, source_name):
        """Return recent uploads for a channel as a list of feedparser-compatible dicts.

        Uses the YouTube Data API when api_key is set (1 quota unit/call),
        otherwise falls back to the public Atom feed.
        """
        if self.api_key:
            return self._discover_via_api(channel_id, source_name)

        feed_url = YOUTUBE_FEED_URL.format(channel_id=channel_id)
        feed = self._fetch_feed_with_retry(feed_url, source_name)
        return list(feed.entries) if feed else []

    def _discover_via_api(self, channel_id, source_name):
        """List a channel's recent uploads via YouTube Data API v3.

        Uses the uploads-playlist convention: replace 'UC' prefix on the
        channel ID with 'UU' to get the uploads playlist ID. This skips a
        separate channels.list call and costs ~1 quota unit per channel.
        """
        if not channel_id.startswith('UC'):
            logger.warning(f"Channel ID for {source_name} doesn't start with 'UC'; can't derive uploads playlist")
            return []

        uploads_playlist_id = 'UU' + channel_id[2:]
        params = {
            'part': 'snippet',
            'playlistId': uploads_playlist_id,
            'maxResults': 50,
            'key': self.api_key,
        }
        try:
            resp = requests.get(YOUTUBE_API_PLAYLIST_ITEMS_URL, params=params, timeout=15)
            if resp.status_code != 200:
                logger.warning(f"YouTube API returned {resp.status_code} for {source_name}: {resp.text[:200]}")
                return []
            data = resp.json()
        except requests.RequestException as e:
            logger.warning(f"YouTube API request failed for {source_name}: {e}")
            return []

        entries = []
        for item in data.get('items', []):
            snippet = item.get('snippet', {})
            resource = snippet.get('resourceId', {})
            video_id = resource.get('videoId')
            if not video_id:
                continue
            entries.append({
                'yt_videoid': video_id,
                'title': snippet.get('title', 'Untitled Video'),
                'published': snippet.get('publishedAt', ''),
                'author': snippet.get('videoOwnerChannelTitle') or snippet.get('channelTitle') or source_name,
                'link': YOUTUBE_WATCH_URL.format(video_id=video_id),
            })
        return entries

    def _fetch_feed_with_retry(self, feed_url, source_name):
        """Fetch a YouTube Atom feed, retrying with backoff on transient 404/HTML responses.

        Returns the parsed feed on success, or None if all retries fail.
        """
        attempts = 1 + len(FEED_RETRY_BACKOFF_SECONDS)
        for attempt in range(1, attempts + 1):
            feed = feedparser.parse(feed_url, agent=FEED_USER_AGENT)
            if not (feed.bozo and not feed.entries):
                return feed

            if attempt < attempts:
                wait = FEED_RETRY_BACKOFF_SECONDS[attempt - 1]
                logger.warning(
                    f"Feed parse failed for {source_name} (attempt {attempt}/{attempts}): "
                    f"{feed.bozo_exception}. Retrying in {wait}s..."
                )
                time.sleep(wait)
            else:
                logger.warning(
                    f"Failed to parse feed for {source_name} after {attempts} attempts: "
                    f"{feed.bozo_exception}"
                )
        return None

    def _extract_video_id(self, entry):
        """Extract YouTube video ID from a feed entry."""
        # YouTube Atom feed entries have 'yt_videoid' field
        video_id = entry.get('yt_videoid')
        if video_id:
            return video_id

        # Fallback: extract from link
        link = entry.get('link', '')
        if 'watch?v=' in link:
            return link.split('watch?v=')[1].split('&')[0]

        return None

    def _fetch_transcript(self, video_id):
        """
        Fetch transcript for a YouTube video.

        Tries youtube-transcript-api first (manual then auto-generated captions).
        Once an IP-block is detected (explicit RequestBlocked/IpBlocked exception
        or N consecutive non-captions failures), short-circuits the API path for
        the rest of the run and goes straight to Whisper, avoiding doomed
        requests that worsen the throttle.

        Args:
            video_id (str): YouTube video ID

        Returns:
            str or None: Transcript text, or None if unavailable
        """
        if not self._transcript_api_blocked:
            text = self._fetch_transcript_via_api(video_id)
            if text:
                return text

            if (
                not self._transcript_api_blocked
                and self._transcript_api_consecutive_failures
                    >= self.transcript_api_max_consecutive_failures
            ):
                logger.warning(
                    f"  transcript-api: {self._transcript_api_consecutive_failures} "
                    f"consecutive failures; treating IP as throttled and skipping "
                    f"transcript-api for the rest of this run"
                )
                self._transcript_api_blocked = True

        if self.whisper_enabled:
            logger.info(f"  Falling back to Whisper transcription for {video_id}")
            return self._fetch_transcript_via_whisper(video_id)
        return None

    def _fetch_transcript_via_api(self, video_id):
        """Fetch transcript via youtube-transcript-api (manual + auto fallback).

        Updates the run-level throttle state: a block exception trips the
        blocked flag immediately; other failures increment the consecutive
        failure counter; a success resets it.
        """
        try:
            transcript = self.ytt_api.fetch(video_id, languages=self.transcript_languages)
            text = ' '.join(snippet.text for snippet in transcript)
            self._transcript_api_consecutive_failures = 0
            return text.strip()
        except _BLOCK_EXCEPTIONS as e:
            logger.warning(
                f"  transcript-api IP blocked on {video_id}: {e}. "
                f"Skipping transcript-api for the rest of this run."
            )
            self._transcript_api_blocked = True
            return None
        except (TranscriptsDisabled, NoTranscriptFound):
            # Legitimate "no captions" — try auto-generated, don't count toward throttle
            text = self._fetch_auto_generated(video_id)
            if text:
                self._transcript_api_consecutive_failures = 0
            return text
        except (CouldNotRetrieveTranscript, VideoUnavailable) as e:
            logger.debug(f"Transcript unavailable for {video_id}: {e}")
            self._transcript_api_consecutive_failures += 1
            return None
        except Exception as e:
            logger.debug(f"Unexpected error fetching transcript for {video_id}: {e}")
            self._transcript_api_consecutive_failures += 1
            return None

    def _preload_cuda_libraries(self):
        """Make bundled CUDA shared libraries findable by ctranslate2.

        When users install `nvidia-cublas-cu12` and `nvidia-cudnn-cu12` from
        PyPI, the .so files land inside the Python site-packages tree, not on
        the dynamic linker's search path. Preloading them via ctypes with
        RTLD_GLOBAL puts their symbols into the process address space, so
        ctranslate2's later dlopen() calls succeed regardless of whether the
        user is on conda, pip+venv, or system Python.

        No-op if the pip packages aren't installed (CPU mode still works).
        """
        import ctypes
        import glob
        import importlib.util

        loaded = []
        for pkg in ('nvidia.cublas', 'nvidia.cudnn'):
            spec = importlib.util.find_spec(pkg)
            if not spec or not spec.submodule_search_locations:
                continue
            for base in spec.submodule_search_locations:
                lib_dir = os.path.join(base, 'lib')
                if not os.path.isdir(lib_dir):
                    continue
                for so in sorted(glob.glob(os.path.join(lib_dir, 'lib*.so*'))):
                    try:
                        ctypes.CDLL(so, mode=ctypes.RTLD_GLOBAL)
                        loaded.append(os.path.basename(so))
                    except OSError:
                        pass
        if loaded:
            logger.debug(f"Preloaded CUDA libs from pip packages: {loaded}")
        return bool(loaded)

    def _get_whisper_model(self):
        """Lazily load the faster-whisper model on first use.

        Falls back from GPU to CPU if GPU init fails (e.g. missing CUDA libs),
        so the pipeline keeps working even on machines without a configured GPU.
        """
        if self._whisper_model is not None:
            return self._whisper_model
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            logger.warning("faster-whisper not installed; Whisper fallback disabled. pip install faster-whisper")
            self.whisper_enabled = False
            return None

        if self.whisper_device in ('auto', 'cuda'):
            self._preload_cuda_libraries()

        try:
            logger.info(
                f"Loading faster-whisper model '{self.whisper_model_size}' "
                f"(device={self.whisper_device}, compute={self.whisper_compute_type})..."
            )
            self._whisper_model = WhisperModel(
                self.whisper_model_size,
                device=self.whisper_device,
                compute_type=self.whisper_compute_type,
            )
            logger.info("Whisper model loaded")
            return self._whisper_model
        except Exception as e:
            if self.whisper_device in ('cpu',):
                logger.error(f"Whisper CPU init failed: {e}; disabling Whisper fallback")
                self.whisper_enabled = False
                return None
            logger.warning(
                f"Whisper GPU init failed ({e}); retrying on CPU. "
                f"To enable GPU, ensure nvidia-cublas-cu12 and nvidia-cudnn-cu12 are "
                f"installed and on LD_LIBRARY_PATH."
            )
            self.whisper_device = 'cpu'
            self.whisper_compute_type = 'int8' if self.whisper_compute_type == 'float16' else self.whisper_compute_type
            try:
                self._whisper_model = WhisperModel(
                    self.whisper_model_size,
                    device='cpu',
                    compute_type=self.whisper_compute_type,
                )
                logger.info("Whisper model loaded on CPU (fallback)")
                return self._whisper_model
            except Exception as e2:
                logger.error(f"Whisper CPU fallback also failed: {e2}; disabling Whisper")
                self.whisper_enabled = False
                return None

    def _fetch_transcript_via_whisper(self, video_id):
        """Download audio with yt-dlp and transcribe locally via faster-whisper."""
        model = self._get_whisper_model()
        if model is None:
            return None

        try:
            import yt_dlp
        except ImportError:
            logger.warning("yt-dlp not installed; Whisper fallback disabled. pip install yt-dlp")
            self.whisper_enabled = False
            return None

        os.makedirs(self.whisper_audio_tmpdir, exist_ok=True)
        audio_path_template = os.path.join(self.whisper_audio_tmpdir, f"{video_id}.%(ext)s")
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': audio_path_template,
            'quiet': True,
            'no_warnings': True,
            'extract_audio': True,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '64',
            }],
        }

        audio_file = os.path.join(self.whisper_audio_tmpdir, f"{video_id}.mp3")
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([YOUTUBE_WATCH_URL.format(video_id=video_id)])
        except Exception as e:
            logger.warning(f"yt-dlp failed for {video_id}: {e}")
            return None

        if not os.path.exists(audio_file):
            logger.warning(f"Audio file missing after yt-dlp run: {audio_file}")
            return None

        try:
            segments, _ = model.transcribe(audio_file, language=self.transcript_languages[0])
            text = ' '.join(seg.text.strip() for seg in segments)
            return text.strip() or None
        except Exception as e:
            logger.warning(f"Whisper transcription failed for {video_id}: {e}")
            return None
        finally:
            try:
                os.remove(audio_file)
            except OSError:
                pass

    def _fetch_auto_generated(self, video_id):
        """
        Try to fetch auto-generated captions as fallback.

        Block-type exceptions are propagated so the outer handler can trip the
        run-level throttle flag; other exceptions are swallowed.

        Args:
            video_id (str): YouTube video ID

        Returns:
            str or None: Transcript text, or None if unavailable
        """
        try:
            transcript_list = self.ytt_api.list(video_id)
            # Look for any auto-generated English transcript
            for transcript in transcript_list:
                if transcript.is_generated and transcript.language_code.startswith('en'):
                    fetched = transcript.fetch()
                    text = ' '.join(snippet.text for snippet in fetched)
                    return text.strip()
            # If no English auto-generated, try any available transcript
            for transcript in transcript_list:
                if transcript.language_code.startswith('en'):
                    fetched = transcript.fetch()
                    text = ' '.join(snippet.text for snippet in fetched)
                    return text.strip()
        except _BLOCK_EXCEPTIONS:
            raise
        except Exception as e:
            logger.debug(f"Auto-generated transcript also unavailable for {video_id}: {e}")
        return None
