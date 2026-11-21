"""MacTube Pro: a desktop frontend for yt-dlp. Start with: python3 mactube.py"""
from __future__ import annotations

import queue
import os
import sys
import traceback
import platform
import shutil
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from config import FORMATS, QUALITIES, load_settings, save_settings, valid_url
from downloader import DownloadRunner, inspect_video, missing_dependencies


def dependency_instructions():
    if sys.platform == 'win32':
        return 'Install with: winget install yt-dlp.yt-dlp && winget install Gyan.FFmpeg'
    if sys.platform == 'darwin':
        return 'Install with: brew install yt-dlp ffmpeg'
    return 'Install yt-dlp and FFmpeg using your package manager or pip.'


class MacTube:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title('MacTube Pro')
        root.geometry('850x790')
        root.minsize(690, 660)
        self.messages = queue.Queue()
        self.jobs: list[dict] = []
        self.active = False
        self.stop_requested = False
        self.worker = None
        self.runner = DownloadRunner(self.emit)
        self.settings = load_settings()
        self.url_var = tk.StringVar()
        self.folder_var = tk.StringVar(value=self.settings['folder'])
        self.quality_var = tk.StringVar(value=self.settings['quality'] if self.settings['quality'] in QUALITIES else 'Best available')
        self.format_var = tk.StringVar(value=self.settings['format'] if self.settings['format'] in FORMATS else 'MP4')
        self.playlist_var = tk.BooleanVar(value=self.settings['playlist'])
        self.subtitles_var = tk.BooleanVar(value=self.settings['subtitles'])
        self.embed_var = tk.BooleanVar(value=self.settings['embed_subtitles'])
        self.thumbnail_var = tk.BooleanVar(value=self.settings['thumbnail'])
        self.metadata_var = tk.BooleanVar(value=self.settings['metadata'])
        self.archive_var = tk.BooleanVar(value=self.settings['archive'])
        self.language_var = tk.StringVar(value=self.settings['language'])
        self.status_var = tk.StringVar(value='Ready')
        self.detail_var = tk.StringVar(value='')
        self.preview_var = tk.StringVar(value='Paste a YouTube URL and click Preview to inspect it.')
        self.configure_styles()
        self.build_ui()
        self.format_changed()
        self.check_deps()
        root.after(100, self.drain_messages)
        root.protocol('WM_DELETE_WINDOW', self.close)

    def configure_styles(self):
        style = ttk.Style()
        themes = style.theme_names()
        preferred = ('vista', 'xpnative', 'clam') if sys.platform == 'win32' else ('aqua', 'clam')
        style.theme_use(next((name for name in preferred if name in themes), themes[0]))
        font_family = 'Segoe UI' if sys.platform == 'win32' else 'Helvetica'
        style.configure('Header.TLabel', font=(font_family, 23, 'bold'))
        style.configure('Sub.TLabel', font=(font_family, 10))
        style.configure('TButton', padding=6)

    def build_ui(self):
        shell = ttk.Frame(self.root, padding=18)
        shell.pack(fill='both', expand=True)
        ttk.Label(shell, text='MacTube Pro', style='Header.TLabel').pack(anchor='w')
        ttk.Label(shell, text='Local YouTube downloader  •  powered by yt-dlp', style='Sub.TLabel').pack(anchor='w', pady=(0, 12))

        ttk.Label(shell, text='Video or playlist URL').pack(anchor='w')
        url_row = ttk.Frame(shell)
        url_row.pack(fill='x', pady=(4, 6))
        self.url_entry = ttk.Entry(url_row, textvariable=self.url_var)
        self.url_entry.pack(side='left', fill='x', expand=True)
        self.url_entry.bind('<Return>', lambda _e: self.add_to_queue())
        ttk.Button(url_row, text='Paste', command=self.paste).pack(side='left', padx=(7, 0))
        ttk.Button(url_row, text='Preview', command=self.preview).pack(side='left', padx=(7, 0))
        ttk.Label(shell, textvariable=self.preview_var, wraplength=770, justify='left').pack(anchor='w', pady=(0, 10))

        settings_row = ttk.Frame(shell)
        settings_row.pack(fill='x', pady=(0, 8))
        for col in range(2):
            settings_row.columnconfigure(col, weight=1)
        left = ttk.Frame(settings_row)
        left.grid(row=0, column=0, sticky='ew', padx=(0, 8))
        right = ttk.Frame(settings_row)
        right.grid(row=0, column=1, sticky='ew', padx=(8, 0))
        ttk.Label(left, text='Quality ceiling').pack(anchor='w')
        self.quality_box = ttk.Combobox(left, textvariable=self.quality_var, values=list(QUALITIES), state='readonly')
        self.quality_box.pack(fill='x', pady=(4, 0))
        ttk.Label(right, text='Output format').pack(anchor='w')
        self.format_box = ttk.Combobox(right, textvariable=self.format_var, values=FORMATS, state='readonly')
        self.format_box.pack(fill='x', pady=(4, 0))
        self.format_box.bind('<<ComboboxSelected>>', lambda _e: self.format_changed())

        ttk.Label(shell, text='Destination folder').pack(anchor='w')
        folder_row = ttk.Frame(shell)
        folder_row.pack(fill='x', pady=(4, 8))
        ttk.Entry(folder_row, textvariable=self.folder_var, state='readonly').pack(side='left', fill='x', expand=True)
        ttk.Button(folder_row, text='Choose…', command=self.choose_folder).pack(side='left', padx=(7, 0))
        ttk.Button(folder_row, text='Open', command=self.open_folder).pack(side='left', padx=(7, 0))

        flags = ttk.LabelFrame(shell, text='Advanced options', padding=8)
        flags.pack(fill='x', pady=(0, 9))
        ttk.Checkbutton(flags, text='Full playlist', variable=self.playlist_var).grid(row=0, column=0, sticky='w', padx=5, pady=3)
        ttk.Checkbutton(flags, text='Save subtitles', variable=self.subtitles_var).grid(row=0, column=1, sticky='w', padx=5, pady=3)
        self.embed_check = ttk.Checkbutton(flags, text='Embed subtitles', variable=self.embed_var)
        self.embed_check.grid(row=0, column=2, sticky='w', padx=5, pady=3)
        ttk.Checkbutton(flags, text='Thumbnail / cover art', variable=self.thumbnail_var).grid(row=1, column=0, sticky='w', padx=5, pady=3)
        ttk.Checkbutton(flags, text='Embed metadata', variable=self.metadata_var).grid(row=1, column=1, sticky='w', padx=5, pady=3)
        ttk.Checkbutton(flags, text='Skip previously downloaded', variable=self.archive_var).grid(row=1, column=2, sticky='w', padx=5, pady=3)
        lang = ttk.Frame(flags)
        lang.grid(row=2, column=0, columnspan=3, sticky='w', pady=(6, 0))
        ttk.Label(lang, text='Subtitle language:').pack(side='left')
        ttk.Entry(lang, textvariable=self.language_var, width=10).pack(side='left', padx=8)
        ttk.Label(lang, text='Examples: en, hi, fr').pack(side='left')

        actions = ttk.Frame(shell)
        actions.pack(fill='x', pady=(0, 7))
        ttk.Button(actions, text='＋ Add to queue', command=self.add_to_queue).pack(side='left')
        self.start_btn = ttk.Button(actions, text='▶ Start queue', command=self.start_queue)
        self.start_btn.pack(side='left', padx=7)
        self.cancel_btn = ttk.Button(actions, text='■ Cancel current', command=self.cancel_current, state='disabled')
        self.cancel_btn.pack(side='left')
        ttk.Button(actions, text='Remove selected', command=self.remove_selected).pack(side='right')

        queue_frame = ttk.LabelFrame(shell, text='Download queue', padding=6)
        queue_frame.pack(fill='both', expand=True, pady=(0, 10))
        self.jobs_box = tk.Listbox(queue_frame, height=6, exportselection=False, font=('Consolas' if sys.platform == 'win32' else 'Menlo', 10))
        self.jobs_box.pack(side='left', fill='both', expand=True)
        scrollbar = ttk.Scrollbar(queue_frame, orient='vertical', command=self.jobs_box.yview)
        scrollbar.pack(side='right', fill='y')
        self.jobs_box.configure(yscrollcommand=scrollbar.set)
        self.jobs_box.bind('<Double-Button-1>', lambda _e: self.open_selected_url())

        ttk.Label(shell, text='Progress').pack(anchor='w')
        self.progress = ttk.Progressbar(shell, maximum=100)
        self.progress.pack(fill='x', pady=(5, 3))
        ttk.Label(shell, textvariable=self.status_var).pack(anchor='w')
        ttk.Label(shell, textvariable=self.detail_var).pack(anchor='w')

        log_header = ttk.Frame(shell)
        log_header.pack(fill='x', pady=(9, 3))
        ttk.Label(log_header, text='Activity log').pack(side='left')
        ttk.Button(log_header, text='Clear log', command=self.clear_log).pack(side='right')
        self.log = tk.Text(shell, height=5, wrap='word', font=('Consolas' if sys.platform == 'win32' else 'Menlo', 9), state='disabled')
        self.log.pack(fill='both', expand=True)

    def current_options(self):
        return {'folder': self.folder_var.get(), 'quality': self.quality_var.get(),
                'format': self.format_var.get(), 'playlist': self.playlist_var.get(),
                'subtitles': self.subtitles_var.get(), 'embed_subtitles': self.embed_var.get(),
                'thumbnail': self.thumbnail_var.get(), 'metadata': self.metadata_var.get(),
                'archive': self.archive_var.get(), 'language': self.language_var.get()}

    def persist(self):
        try:
            save_settings(self.current_options())
        except OSError as exc:
            self.write_log(f'Could not save preferences: {exc}')

    def format_changed(self):
        audio = self.format_var.get() in ('MP3', 'M4A', 'Original audio')
        self.quality_box.configure(state='disabled' if audio else 'readonly')
        self.embed_check.configure(state='disabled' if audio else 'normal')

    def check_deps(self):
        missing = missing_dependencies()
        if missing:
            self.write_log('Missing dependencies: ' + ', '.join(missing) + '\n' + dependency_instructions() + '\n')

    def paste(self):
        try:
            self.url_var.set(self.root.clipboard_get().strip())
        except tk.TclError:
            messagebox.showinfo('Clipboard', 'Clipboard contains no text.')

    def choose_folder(self):
        folder = filedialog.askdirectory(initialdir=self.folder_var.get())
        if folder:
            self.folder_var.set(folder)
            self.persist()

    def open_folder(self):
        folder = Path(self.folder_var.get()).expanduser()
        try:
            folder.mkdir(parents=True, exist_ok=True)
            if sys.platform == 'win32':
                os.startfile(str(folder))
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', str(folder)])
            else:
                subprocess.Popen(['xdg-open', str(folder)])
        except OSError as exc:
            messagebox.showerror('Open folder', str(exc))

    def preview(self):
        url = self.url_var.get().strip()
        if not valid_url(url):
            messagebox.showerror('Invalid URL', 'Enter a YouTube video or playlist URL.')
            return
        if not shutil.which('yt-dlp'):
            self.check_deps()
            return
        self.preview_var.set('Inspecting URL…')
        playlist = self.playlist_var.get()
        threading.Thread(target=self._preview_worker, args=(url, playlist), daemon=True).start()

    def _preview_worker(self, url, playlist):
        try:
            info = inspect_video(url, playlist)
            title = info.get('title') or 'Untitled'
            author = info.get('uploader') or info.get('channel') or 'Unknown channel'
            count = info.get('playlist_count') or info.get('n_entries')
            duration = info.get('duration')
            duration_text = f'  •  {int(duration)//60}:{int(duration)%60:02}' if isinstance(duration, (float, int)) else ''
            count_text = f'  •  {count} entries' if count else ''
            self.emit('preview', f'{title}  •  {author}{duration_text}{count_text}')
        except Exception as exc:
            self.emit('preview', f'Preview unavailable: {str(exc)[:220]}')

    def add_to_queue(self):
        url = self.url_var.get().strip()
        if not valid_url(url):
            messagebox.showerror('Invalid URL', 'Enter a valid YouTube video or playlist URL.')
            return
        options = self.current_options().copy()  # Each queued job keeps its own settings.
        job = {'url': url, 'options': options, 'status': 'Waiting'}
        self.jobs.append(job)
        self.refresh_jobs()
        self.url_var.set('')
        self.preview_var.set('Paste a YouTube URL and click Preview to inspect it.')
        self.persist()
        self.write_log('Added: ' + url)

    def refresh_jobs(self):
        selection = self.jobs_box.curselection()
        self.jobs_box.delete(0, 'end')
        for i, job in enumerate(self.jobs):
            self.jobs_box.insert('end', f'{i+1:02} [{job["status"]}] {job["url"]}')
        if selection and selection[0] < len(self.jobs):
            self.jobs_box.selection_set(selection[0])

    def remove_selected(self):
        selection = self.jobs_box.curselection()
        if not selection:
            return
        i = selection[0]
        if self.jobs[i]['status'] == 'Downloading':
            messagebox.showinfo('Active download', 'Cancel the current download first.')
            return
        self.jobs.pop(i)
        self.refresh_jobs()

    def open_selected_url(self):
        # Deliberately does not open external URLs automatically.
        selection = self.jobs_box.curselection()
        if selection:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.jobs[selection[0]]['url'])
            self.status_var.set('Selected URL copied to clipboard')

    def start_queue(self):
        if self.active:
            return
        missing = missing_dependencies()
        if missing:
            messagebox.showerror('Dependencies missing', 'Missing: ' + ', '.join(missing) + '\n' + dependency_instructions())
            return
        if not any(job['status'] in ('Waiting', 'Failed', 'Cancelled') for job in self.jobs):
            messagebox.showinfo('Queue', 'Add a URL to the queue first.')
            return
        self.active = True
        self.stop_requested = False
        self.runner.cancelled.clear()
        self.start_btn.configure(state='disabled')
        self.cancel_btn.configure(state='normal')
        self.worker = threading.Thread(target=self._queue_worker, daemon=True)
        self.worker.start()

    def _queue_worker(self):
        # UI edits are intentionally marshalled through the message queue.
        for job in self.jobs[:]:
            if self.stop_requested:
                break
            if job['status'] not in ('Waiting', 'Failed', 'Cancelled'):
                continue
            self.emit('job_status', job, 'Downloading')
            self.emit('begin', job['url'])
            result = self.runner.run(job['url'], job['options'])
            self.emit('job_status', job, {'done': 'Done', 'failed': 'Failed', 'cancelled': 'Cancelled'}[result])
            self.emit('finished_item', result)
            if result == 'cancelled':
                break
        self.emit('queue_finished')

    def cancel_current(self):
        if not self.active:
            return
        self.stop_requested = True
        self.runner.cancel()
        self.status_var.set('Stopping current download…')

    def emit(self, kind, *payload):
        self.messages.put((kind, *payload))

    def drain_messages(self):
        try:
            for _ in range(150):
                msg = self.messages.get_nowait()
                kind = msg[0]
                if kind == 'preview':
                    self.preview_var.set(msg[1])
                elif kind == 'job_status':
                    job, status = msg[1:]
                    job['status'] = status
                    self.refresh_jobs()
                elif kind == 'begin':
                    self.progress['value'] = 0
                    self.status_var.set('Downloading: ' + msg[1][:90])
                    self.detail_var.set('')
                    self.write_log('Starting: ' + msg[1])
                elif kind == 'progress':
                    self.progress['value'] = min(100, max(0, msg[1]))
                    self.detail_var.set(f'{msg[1]:.1f}%   •   Speed: {msg[2]}   •   ETA: {msg[3]}')
                elif kind == 'log':
                    self.write_log(msg[1])
                elif kind == 'finished_item':
                    result = msg[1]
                    if result == 'done':
                        self.progress['value'] = 100
                    self.status_var.set({'done': 'Download completed', 'failed': 'Download failed — see log',
                                         'cancelled': 'Download cancelled'}[result])
                elif kind == 'queue_finished':
                    self.active = False
                    self.start_btn.configure(state='normal')
                    self.cancel_btn.configure(state='disabled')
                    self.write_log('Queue finished.')
        except queue.Empty:
            pass
        self.root.after(100, self.drain_messages)

    def write_log(self, text):
        self.log.configure(state='normal')
        self.log.insert('end', text + ('\n' if not text.endswith('\n') else ''))
        # Keep Tk's buffer bounded for long playlists.
        if int(self.log.index('end-1c').split('.')[0]) > 1000:
            self.log.delete('1.0', '200.0')
        self.log.see('end')
        self.log.configure(state='disabled')

    def clear_log(self):
        self.log.configure(state='normal')
        self.log.delete('1.0', 'end')
        self.log.configure(state='disabled')

    def close(self):
        if self.active:
            if not messagebox.askyesno('Quit MacTube Pro?', 'Stop the active download and quit?'):
                return
            self.stop_requested = True
            self.runner.cancel()
        self.persist()
        self.root.destroy()


if __name__ == '__main__':
    try:
        app_root = tk.Tk()
        MacTube(app_root)
        app_root.mainloop()
    except Exception:
        error = traceback.format_exc()
        log_path = Path.home() / 'mactube-startup-error.log'
        log_path.write_text(error, encoding='utf-8')
        print(error, file=sys.stderr)
        try:
            messagebox.showerror('MacTube Pro startup error', f'Details saved to {log_path}\n\n{error[-1000:]}')
        except Exception:
            pass
        raise
