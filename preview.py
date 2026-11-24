"""Video metadata and format/size choices extracted from yt-dlp's JSON."""
from __future__ import annotations

import json
import subprocess
from urllib.request import Request, urlopen


def inspect_video(url: str, playlist: bool = False) -> dict:
    cmd = ['yt-dlp', '--dump-single-json', '--skip-download', '--no-warnings',
           '--flat-playlist' if playlist else '--no-playlist', url]
    done = subprocess.run(cmd, text=True, capture_output=True, timeout=60,
                          encoding='utf-8', errors='replace')
    if done.returncode:
        raise RuntimeError((done.stderr or done.stdout).strip()[-600:] or 'Metadata request failed')
    return json.loads(done.stdout)


def size_of(fmt: dict) -> tuple[int | None, bool]:
    """Bytes and whether yt-dlp provided an actual content length."""
    if isinstance(fmt.get('filesize'), (int, float)) and fmt['filesize'] > 0:
        return int(fmt['filesize']), True
    if isinstance(fmt.get('filesize_approx'), (int, float)) and fmt['filesize_approx'] > 0:
        return int(fmt['filesize_approx']), False
    return None, False


def human_bytes(size: int | float | None) -> str:
    if size is None:
        return 'Unknown'
    num = float(size)
    for suffix in ('B', 'KB', 'MB', 'GB', 'TB'):
        if num < 1024 or suffix == 'TB':
            return f'{num:.0f} {suffix}' if suffix == 'B' else f'{num:.1f} {suffix}'
        num /= 1024
    return 'Unknown'


def describe_formats(info: dict) -> list[dict]:
    """Selectable download variants. Sizes are per-stream or summed estimates.

    A size marked estimated can differ after merging/remuxing. Unknown sizes
    remain unknown; they are never guessed from bitrate.
    """
    raw = info.get('formats') or []
    audio = [f for f in raw if f.get('acodec') not in (None, 'none') and
             f.get('vcodec') == 'none' and f.get('format_id')]
    videos = [f for f in raw if f.get('vcodec') not in (None, 'none') and f.get('format_id')]
    def audio_rank(f):
        return (1 if f.get('ext') == 'm4a' else 0, float(f.get('abr') or f.get('tbr') or 0))
    best_audio = max(audio, key=audio_rank, default=None)
    rows = []
    for f in videos:
        fmt_id = str(f['format_id'])
        has_audio = f.get('acodec') not in (None, 'none')
        extra = None if has_audio else best_audio
        if not has_audio and extra is None:
            continue
        sz, exact = size_of(f)
        if extra:
            az, aexact = size_of(extra)
            sz = sz + az if sz is not None and az is not None else None
            exact = exact and aexact
        height = f.get('height')
        fps = f.get('fps')
        quality = f'{height}p' if height else (f.get('resolution') or 'Video')
        codec = f.get('vcodec') or 'video'
        if len(codec) > 16:
            codec = codec[:16]
        rows.append({'kind': 'video', 'id': fmt_id,
                     'selector': fmt_id + ('+' + str(extra['format_id']) if extra else ''),
                     'label': quality, 'ext': (f.get('ext') or '').upper(),
                     'fps': str(round(fps)) if fps else '—', 'codec': codec,
                     'size': sz, 'exact': exact, 'height': height or 0,
                     'note': 'Video + audio' if extra else 'Video with audio'})
    for f in audio:
        sz, exact = size_of(f)
        rows.append({'kind': 'audio', 'id': str(f['format_id']),
                     'selector': str(f['format_id']),
                     'label': 'Audio only', 'ext': (f.get('ext') or '').upper(),
                     'fps': '—', 'codec': str(f.get('acodec') or 'audio')[:16],
                     'size': sz, 'exact': exact, 'height': 0, 'note': 'Audio only'})
    rows.sort(key=lambda f: (f['kind'] == 'audio', -(f['height'] or 0),
                             -(f['size'] or 0)))
    return rows[:100]


def thumbnail_url(info: dict) -> str | None:
    thumbs = [t for t in info.get('thumbnails', []) if isinstance(t, dict) and
              str(t.get('url', '')).startswith('https://')]
    thumbs.sort(key=lambda t: (t.get('width') or 0) * (t.get('height') or 0))
    if thumbs:
        return thumbs[-1]['url']
    url = info.get('thumbnail')
    return url if isinstance(url, str) and url.startswith('https://') else None


def load_thumbnail(url: str) -> bytes:
    """Bounded download; Pillow decodes the bytes in the Tk UI thread."""
    request = Request(url, headers={'User-Agent': 'Mozilla/5.0 MacTube-Pro/2'})
    with urlopen(request, timeout=12) as response:
        data = response.read(4 * 1024 * 1024 + 1)
        if len(data) > 4 * 1024 * 1024:
            raise ValueError('Thumbnail exceeds 4 MB')
        return data
