"""Build yt-dlp commands and report byte-level progress without blocking Tk."""
from __future__ import annotations

import re
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Callable

from config import APP_DIR, ARCHIVE_PATH, QUALITIES

# Delimiter unlikely in yt-dlp progress fields.
PROGRESS = re.compile(r'^MACTUBE_PROGRESS\|(.+)$')


def missing_dependencies() -> list[str]:
    return [p for p in ('yt-dlp', 'ffmpeg') if not shutil.which(p)]


def build_command(url: str, options: dict) -> list[str]:
    fmt = options['format']
    cmd = ['yt-dlp', '--newline', '--progress', '--continue', '--no-overwrites',
           '--windows-filenames', '--trim-filenames', '180',
           '--progress-template',
           'download:MACTUBE_PROGRESS|%(progress._percent_str)s|%(progress.downloaded_bytes)s|'
           '%(progress.total_bytes)s|%(progress.total_bytes_estimate)s|'
           '%(progress._speed_str)s|%(progress._eta_str)s',
           '--yes-playlist' if options['playlist'] else '--no-playlist',
           '-P', str(Path(options['folder']).expanduser()),
           '-o', '%(playlist_title,NA)s/%(playlist_index,NA)s - %(title)s [%(id)s].%(ext)s'
           if options['playlist'] else '%(title)s [%(id)s].%(ext)s']
    if options.get('archive'):
        APP_DIR.mkdir(parents=True, exist_ok=True)
        cmd += ['--download-archive', str(ARCHIVE_PATH)]

    selected = options.get('selected_format')
    if selected and not options['playlist']:
        cmd += ['-f', selected['selector']]
        # A format ID is bound to the inspected URL; the UI drops selection when URL changes.
        selected_audio = selected['kind'] == 'audio'
        if selected_audio:
            if fmt in ('MP3', 'M4A'):
                cmd += ['-x', '--audio-format', fmt.lower()]
        elif fmt in ('MP4', 'MKV', 'WEBM'):
            cmd += ['--merge-output-format', fmt.lower()]
            if fmt == 'MP4':
                cmd += ['--remux-video', 'mp4']
    elif fmt in ('MP3', 'M4A', 'Original audio'):
        cmd += ['-f', 'bestaudio/best']
        if fmt != 'Original audio':
            cmd += ['-x', '--audio-format', fmt.lower()]
            if fmt == 'MP3':
                cmd += ['--audio-quality', '0']
    else:
        height = QUALITIES.get(options['quality'])
        selector = 'bv*+ba/b' if height is None else f'bv*[height<={height}]+ba/b[height<={height}]'
        cmd += ['-f', selector, '--merge-output-format', fmt.lower()]
        if fmt == 'MP4':
            cmd += ['--remux-video', 'mp4']

    lang = (options.get('language') or 'en').strip()
    if not re.fullmatch(r'[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*', lang):
        lang = 'en'
    if options.get('subtitles'):
        cmd += ['--write-subs', '--write-auto-subs', '--sub-langs', lang]
        if options.get('embed_subtitles') and fmt in ('MP4', 'MKV', 'WEBM'):
            cmd += ['--embed-subs']
    if options.get('thumbnail'):
        cmd += ['--embed-thumbnail' if fmt in ('MP4', 'MKV', 'MP3', 'M4A') else '--write-thumbnail']
    if options.get('metadata'):
        cmd += ['--add-metadata']
    cmd.append(url)
    return cmd


def parse_progress(line: str) -> dict | None:
    match = PROGRESS.match(line)
    if not match:
        return None
    parts = match.group(1).split('|', 5)
    if len(parts) != 6:
        return None
    def number(text):
        try:
            return int(text) if text not in ('NA', 'None', '') else None
        except ValueError:
            return None
    try:
        percent = float(parts[0].strip().replace('%', ''))
    except ValueError:
        percent = 0.0
    return {'percent': max(0., min(100., percent)), 'downloaded': number(parts[1]),
            'total': number(parts[2]) or number(parts[3]),
            'estimated': not bool(number(parts[2])),
            'speed': parts[4].strip(), 'eta': parts[5].strip()}


class DownloadRunner:
    def __init__(self, emit: Callable):
        self.emit = emit
        self.process: subprocess.Popen | None = None
        self.lock = threading.Lock()
        self.cancelled = threading.Event()

    def run(self, url: str, options: dict) -> str:
        if self.cancelled.is_set():
            return 'cancelled'
        try:
            Path(options['folder']).expanduser().mkdir(parents=True, exist_ok=True)
            process = subprocess.Popen(build_command(url, options), stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, text=True, encoding='utf-8',
                                       errors='replace', bufsize=1)
            with self.lock:
                self.process = process
                if self.cancelled.is_set() and process.poll() is None:
                    process.terminate()
            assert process.stdout is not None
            for raw in process.stdout:
                line = raw.strip()
                progress = parse_progress(line)
                if progress is not None:
                    self.emit('progress', progress)
                elif line:
                    self.emit('log', line)
            code = process.wait()
            if self.cancelled.is_set():
                return 'cancelled'
            if code:
                self.emit('log', f'yt-dlp exited with code {code}')
                return 'failed'
            return 'done'
        except Exception as exc:
            self.emit('log', f'ERROR: {exc}')
            return 'failed'
        finally:
            with self.lock:
                self.process = None

    def cancel(self):
        self.cancelled.set()
        with self.lock:
            if self.process and self.process.poll() is None:
                self.process.terminate()
