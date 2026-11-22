"""Settings and URL validation for MacTube Pro."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

APP_DIR = Path.home() / '.mactube-pro'
SETTINGS_PATH = APP_DIR / 'settings.json'
ARCHIVE_PATH = APP_DIR / 'download-archive.txt'
DEFAULTS = {
    'folder': str(Path.home() / 'Downloads'),
    'quality': 'Best available',
    'format': 'MP4',
    'playlist': False,
    'subtitles': False,
    'embed_subtitles': False,
    'thumbnail': False,
    'metadata': True,
    'archive': True,
    'language': 'en',
}
QUALITIES = {'Best available': None, '4K (2160p)': 2160,
             '2K (1440p)': 1440, '1080p': 1080, '720p': 720,
             '480p': 480, '360p': 360}
FORMATS = ('MP4', 'MKV', 'WEBM', 'MP3', 'M4A', 'Original audio')


def load_settings() -> dict:
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding='utf-8'))
        if isinstance(data, dict):
            return {**DEFAULTS, **{k: v for k, v in data.items() if k in DEFAULTS}}
    except (OSError, ValueError):
        pass
    return DEFAULTS.copy()


def save_settings(settings: dict) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    temp = SETTINGS_PATH.with_suffix('.tmp')
    temp.write_text(json.dumps(settings, indent=2), encoding='utf-8')
    temp.replace(SETTINGS_PATH)


def valid_url(url: str) -> bool:
    try:
        parsed = urlparse(url.strip())
        host = (parsed.hostname or '').lower()
        return (parsed.scheme in ('http', 'https') and
                (host in ('youtube.com', 'www.youtube.com', 'm.youtube.com',
                          'music.youtube.com', 'youtu.be', 'www.youtu.be')) and
                bool(parsed.path and parsed.path != '/' or parsed.query))
    except ValueError:
        return False