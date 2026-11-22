# MacTube Pro

A lightweight cross-platform Tkinter frontend for `yt-dlp` and FFmpeg.

## Install and launch on macOS

```bash
brew install python-tk yt-dlp ffmpeg
cd MacTube-Pro
python3 mactube.py
```

If Tkinter is unavailable, use the matching Homebrew versioned package (for example `python-tk@3.13` with `python@3.13`). Check with `python3 -m tkinter`.

## Install and launch on Windows

Install Python 3.10+ from python.org (make sure Python and Tcl/Tk are installed).

In PowerShell:

```powershell
winget install yt-dlp.yt-dlp
winget install Gyan.FFmpeg
python -m tkinter
cd MacTube-Pro
python mactube.py
```

Restart PowerShell after installing tools so new PATH entries are recognized.
If `python -m tkinter` opens a **blank window** too, your Python/Tk installation or display environment is likely the issue, not MacTube. Reinstall Python with Tcl/Tk support or try a current python.org installer.
If only MacTube is blank, run `python -u mactube.py` from a PowerShell window and inspect terminal output and `%USERPROFILE%\mactube-startup-error.log` (only created if an exception occurs).

## Features

- Queue multiple YouTube URLs and process them in order
- Preview a video's title, uploader and duration (when provided by yt-dlp)
- Single videos or entire playlists
- Best-quality or resolution-capped video (MP4, MKV, WEBM)
- MP3, M4A, or original audio
- Subtitle files, optional embedding for video output, subtitle language
- Embed metadata and optional thumbnails (compatibility depends on output codecs/container)
- Cancel running downloads
- Remember preferences between launches in `~/.mactube-pro/settings.json`
- Skip successful previous downloads using `~/.mactube-pro/download-archive.txt`
- Open destination folder, copy URL from queue by double-clicking

Each item snapshots the settings when it enters the queue. Failed/cancelled items can be retried with **Start queue**. The queue itself is **not** persisted across launches.

## Notes

- Downloads are processed **sequentially**, not concurrently.
- YouTube restrictions, age limits, authentication requirements, unavailable formats, and changes to YouTube may prevent some downloads.
- The displayed percentage tracks the current yt-dlp transfer, not necessarily the whole playlist or all post-processing work.
- `yt-dlp` may pick compatible formats available for each video; requesting MP4 does not guarantee all original codecs will be MP4-native.
- For some videos, embedding subtitles and cover art is not supported by the chosen container.
- Download content only when you own it or are otherwise permitted to download it, and follow the platform's rules.

## Structure

- `mactube.py` — interface, queue and thread-to-UI events
- `downloader.py` — yt-dlp command generation, previews, process management
- `config.py` — validation and local settings
