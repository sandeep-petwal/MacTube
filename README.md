# MacTube Pro — enhanced edition

Mac-friendly, local Tkinter GUI over `yt-dlp` and FFmpeg. Download only media you have permission to download and follow platform terms.

## Install on your Mac

Your Apple system Python 3.9 / Tk 8.5 produced a blank window. **Use Python 3.13 and `python-tk@3.13`** instead.

```bash
brew install python@3.13 python-tk@3.13 yt-dlp ffmpeg
python3.13 -m pip install Pillow
python3.13 -m tkinter
python3.13 mactube.py
```

Homebrew Python may be externally managed (PEP 668). If `pip install Pillow` is rejected, create a virtual environment instead:

```bash
python3.13 -m venv .venv
.venv/bin/python -m pip install Pillow
.venv/bin/python mactube.py
```

The Finder launcher `run.command` automatically uses `.venv/bin/python` when a virtual environment exists; otherwise it uses `python3.13`. Double-click `run.command` in Finder to launch MacTube.

## Using the enhanced UI

1. Paste a YouTube URL and click **Preview video**. Network access is necessary; yt-dlp returns formats and metadata.
2. View the thumbnail, title/channel, available streams, resolutions, codecs, and per-format size estimates.
3. Click a format row to select its `yt-dlp` stream ID(s), or click **Use automatic quality**. Choose a compatible output type: video rows with MP4/MKV/WEBM, audio rows with MP3/M4A/Original audio.
4. Set the output folder, then click **Download now** or add items to the queue.
5. Track percentage and downloaded bytes under the tabs. For split video/audio downloads, these values represent the **current stream**, and may restart when the next stream begins. Postprocessing/merging can take longer after 100%.

## Size accuracy

`yt-dlp` reports either `filesize` (known stream size), `filesize_approx` (~), or no size (`Unknown`). Summed video+audio sizes are stream sizes; final output files may differ due to remuxing/transcoding, audio conversion, container metadata, subtitle and thumbnail embedding. Size is not guaranteed to be exact. For MP3 transcoding, source audio size is **not** the final MP3 size.

## Layout

- `mactube.py`: Tkinter interface, preview/format selection, queue
- `preview.py`: metadata inspection, format sizes, thumbnails
- `downloader.py`: yt-dlp commands, byte-progress parsing, cancellation
- `config.py`: preferences and URL validation
- `run.command`: Finder launcher using Python 3.13

Stored settings and skip-download archive: `~/.mactube-pro/`.

If thumbnails are blank, check that Pillow is installed for the **same Python interpreter** you use to run the GUI. Playlist inspection uses flat metadata, so per-video formats aren't shown for entire playlists.
