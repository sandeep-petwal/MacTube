"""yt-dlp process isolation: all subprocess work happens outside Tk's UI thread."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Callable

from config import ARCHIVE_PATH, APP_DIR, QUALITIES

PROGRESS = re.compile(r'^PROGRESS:\s*([\d.]+)%\|([^|]*)\|(.*)$')


def missing_dependencies() -> list[str]:
    return [program for program in ('yt-dlp', 'ffmpeg') if not shutil.which(program)]


def inspect_video(url: str, playlist: bool = False) -> dict:
    cmd = ['yt-dlp', '--dump-single-json', '--skip-download', '--no-warnings',
           '--flat-playlist' if playlist else '--no-playlist', url]
    completed = subprocess.run(cmd, capture_output=True, text=True, timeout=40,
                               encoding='utf-8', errors='replace')
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout).strip()[-700:])
    return json.loads(completed.stdout)


def build_command(url: str, options: dict) -> list[str]:
    folder = str(Path(options['folder']).expanduser())
    fmt = options['format']
    cmd = ['yt-dlp', '--newline', '--progress', '--continue', '--no-overwrites',
           '--windows-filenames', '--trim-filenames', '180',
           '--progress-template',
           'download:PROGRESS:%(progress._percent_str)s|%(progress._speed_str)s|%(progress._eta_str)s',
           '--yes-playlist' if options['playlist'] else '--no-playlist',
           '-P', folder, '-o', '%(playlist_title,NA)s/%(playlist_index,NA)s - %(title)s [%(id)s].%(ext)s'
           if options['playlist'] else '%(title)s [%(id)s].%(ext)s']
    if options['archive']:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        cmd += ['--download-archive', str(ARCHIVE_PATH)]
    if fmt == 'MP3':
        cmd += ['-f', 'bestaudio/best', '-x', '--audio-format', 'mp3', '--audio-quality', '0']
    elif fmt == 'M4A':
        cmd += ['-f', 'bestaudio/best', '-x', '--audio-format', 'm4a']
    elif fmt == 'Original audio':
        cmd += ['-f', 'bestaudio/best']
    else:
        height = QUALITIES[options['quality']]
        selector = ('bv*+ba/b' if height is None else
                    f'bv*[height<={height}]+ba/b[height<={height}]')
        cmd += ['-f', selector]
        if fmt == 'MP4':
            cmd += ['--merge-output-format', 'mp4', '--remux-video', 'mp4']
        elif fmt == 'MKV':
            cmd += ['--merge-output-format', 'mkv']
        elif fmt == 'WEBM':
            cmd += ['--merge-output-format', 'webm']

    language = (options.get('language') or 'en').strip()
    if not re.fullmatch(r'[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*', language):
        language = 'en'
    if options.get('subtitles'):
        cmd += ['--write-subs', '--write-auto-subs', '--sub-langs', language]
        if options.get('embed_subtitles') and fmt in ('MP4', 'MKV', 'WEBM'):
            cmd += ['--embed-subs']
    if options.get('thumbnail'):
        cmd += ['--embed-thumbnail' if fmt in ('MP4', 'MKV', 'MP3', 'M4A')
                else '--write-thumbnail']
    if options.get('metadata'):
        cmd += ['--add-metadata']
    cmd.append(url)
    return cmd


class DownloadRunner:
    def __init__(self, emit: Callable):
        self.emit = emit
        self.process: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self.cancelled = threading.Event()

    def run(self, url: str, options: dict) -> str:
        if self.cancelled.is_set():
            return 'cancelled'
        Path(options['folder']).expanduser().mkdir(parents=True, exist_ok=True)
        cmd = build_command(url, options)
        try:
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, text=True,
                                       encoding='utf-8', errors='replace', bufsize=1)
            with self._lock:
                self.process = process
                if self.cancelled.is_set() and process.poll() is None:
                    process.terminate()
            assert process.stdout is not None
            for line in process.stdout:
                line = line.strip()
                match = PROGRESS.match(line)
                if match:
                    self.emit('progress', float(match.group(1)),
                              match.group(2).strip(), match.group(3).strip())
                elif line:
                    self.emit('log', line)
            code = process.wait()
            if self.cancelled.is_set():
                return 'cancelled'
            if code != 0:
                self.emit('log', f'yt-dlp exited with code {code}')
                return 'failed'
            return 'done'
        except Exception as exc:
            self.emit('log', f'ERROR: {exc}')
            return 'failed'
        finally:
            with self._lock:
                self.process = None

    def cancel(self) -> None:
        self.cancelled.set()
        with self._lock:
            if self.process and self.process.poll() is None:
                self.process.terminate()