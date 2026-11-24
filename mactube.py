"""MacTube Pro — Tkinter desktop downloader. Run with python3.13 mactube.py."""
from __future__ import annotations

import io
import os
import queue
import shutil
import subprocess
import sys
import threading
import tkinter as tk
import traceback
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from config import FORMATS, QUALITIES, load_settings, save_settings, valid_url
from downloader import DownloadRunner, missing_dependencies
from preview import describe_formats, human_bytes, inspect_video, load_thumbnail, thumbnail_url

try:
    from PIL import Image, ImageTk
except ImportError:
    Image = ImageTk = None

BG = '#11151d'
SURFACE = '#1b222e'
FIELD = '#141a24'
CONTROL = '#293548'
HOVER = '#354762'
INK = '#edf2fa'
MUTED = '#a9b7cb'
BLUE = '#8ab9ff'
LINE = '#364359'
ACCENT = '#264f9e'
SELECTED = '#31558a'


def ui_button(parent, label, command, primary=False):
    style = 'Primary.TButton' if primary else 'TButton'
    return ttk.Button(parent, text=label, command=command, style=style)


def pack_scrollable(widget):
    scrollbar = ttk.Scrollbar(widget.master, orient='vertical', command=widget.yview)
    widget.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side='right', fill='y')
    widget.pack(side='left', fill='both', expand=True)


def card(parent, **kwargs):
    return tk.Frame(parent, bg=SURFACE, highlightbackground=LINE, highlightthickness=1, **kwargs)


def text(parent, value, size=11, bold=False, color=INK, **kwargs):
    return tk.Label(parent, text=value, bg=parent.cget('bg'), fg=color,
                    font=('Helvetica', size, 'bold' if bold else 'normal'), **kwargs)


class MacTube:
    def __init__(self, root):
        self.root = root
        root.title('MacTube Pro  ·  Media Downloader')
        root.geometry('1120x850')
        root.minsize(850, 710)
        root.configure(bg=BG)
        self.messages = queue.Queue()
        self.settings = load_settings()
        self.jobs = []
        self.active = False
        self.stopping = False
        self.runner = DownloadRunner(self.emit)
        self.preview_generation = 0
        self.preview_url = None
        self.available_formats = []
        self.selected_format = None
        self.preview_photo = None
        self.url_var = tk.StringVar()
        self.folder_var = tk.StringVar(value=self.settings['folder'])
        self.format_var = tk.StringVar(value=self.settings['format'] if self.settings['format'] in FORMATS else 'MP4')
        self.quality_var = tk.StringVar(value=self.settings['quality'] if self.settings['quality'] in QUALITIES else 'Best available')
        self.playlist_var = tk.BooleanVar(value=self.settings['playlist'])
        self.subtitles_var = tk.BooleanVar(value=self.settings['subtitles'])
        self.embed_var = tk.BooleanVar(value=self.settings['embed_subtitles'])
        self.thumbnail_var = tk.BooleanVar(value=self.settings['thumbnail'])
        self.metadata_var = tk.BooleanVar(value=self.settings['metadata'])
        self.archive_var = tk.BooleanVar(value=self.settings['archive'])
        self.language_var = tk.StringVar(value=self.settings['language'])
        self.status_var = tk.StringVar(value='Ready to download')
        self.bytes_var = tk.StringVar(value='Downloaded: —')
        self.speed_var = tk.StringVar(value='Speed: —     ETA: —')
        self.percent_var = tk.StringVar(value='0.0%')
        self.preview_title_var = tk.StringVar(value='Your video preview will appear here')
        self.preview_meta_var = tk.StringVar(value='Paste a YouTube URL above and select Preview')
        self.format_help_var = tk.StringVar(value='Choose Preview to see available formats and their sizes.')
        self.queue_count = tk.StringVar(value='0 items')
        self._styles()
        self._build()
        self.format_changed()
        self._check_dependencies()
        self.url_var.trace_add('write', lambda *_: self.invalidate_preview())
        self.playlist_var.trace_add('write', lambda *_: self.invalidate_preview())
        root.after(100, self.drain)
        root.protocol('WM_DELETE_WINDOW', self.close)

    def _styles(self):
        st = ttk.Style()
        st.theme_use('clam')
        st.configure('.', background=SURFACE, foreground=INK, fieldbackground=FIELD,
                     bordercolor=LINE, lightcolor=LINE, darkcolor=LINE, troughcolor=FIELD,
                     selectbackground=SELECTED, selectforeground=INK, arrowcolor=INK,
                     insertcolor=INK, focuscolor=BLUE)
        st.map('.', foreground=[('disabled', MUTED)])
        st.configure('TButton', background=CONTROL, padding=(13, 7), font=('Helvetica', 11))
        st.map('TButton', background=[('disabled', SURFACE), ('pressed', SELECTED), ('active', HOVER)])
        st.configure('Primary.TButton', background=ACCENT, font=('Helvetica', 11, 'bold'))
        st.map('Primary.TButton', background=[('disabled', SURFACE), ('pressed', SELECTED), ('active', '#3064bd')])
        st.configure('TEntry', padding=4)
        st.configure('TCombobox', padding=4)
        for style in ('TEntry', 'TCombobox'):
            st.map(style, fieldbackground=[('disabled', SURFACE), ('readonly', FIELD)],
                   bordercolor=[('focus', BLUE)])
        st.map('TCombobox', background=[('active', HOVER)])
        self.root.option_add('*TCombobox*Listbox.background', FIELD)
        self.root.option_add('*TCombobox*Listbox.foreground', INK)
        self.root.option_add('*TCombobox*Listbox.selectBackground', SELECTED)
        self.root.option_add('*TCombobox*Listbox.selectForeground', INK)
        st.map('TCheckbutton', indicatorbackground=[('selected', BLUE), ('!selected', FIELD)])
        st.configure('TNotebook', background=BG)
        st.configure('TNotebook.Tab', background=CONTROL, padding=(10, 6))
        st.map('TNotebook.Tab', background=[('selected', SURFACE), ('active', HOVER)])
        st.configure('Modern.Treeview', font=('Helvetica', 10), rowheight=26,
                     background=FIELD, fieldbackground=FIELD)
        st.configure('Modern.Treeview.Heading', background=CONTROL, font=('Helvetica', 10, 'bold'))
        st.map('Modern.Treeview', background=[('selected', SELECTED)], foreground=[('selected', INK)])
        st.map('Modern.Treeview.Heading', background=[('active', HOVER)])
        st.configure('Vertical.TScrollbar', background=CONTROL)
        st.map('Vertical.TScrollbar', background=[('active', HOVER)])
        st.configure('Modern.Horizontal.TProgressbar', background=BLUE, thickness=13)

    def _build_scrollable_tab(self, tab, build):
        canvas = tk.Canvas(tab, bg=BG, highlightthickness=0, yscrollincrement=16)
        content = tk.Frame(canvas, bg=BG, padx=2, pady=12)
        window = canvas.create_window(0, 0, window=content, anchor='nw')
        content.bind('<Configure>', lambda _event: canvas.configure(scrollregion=canvas.bbox(window)))
        canvas.bind('<Configure>', lambda event: canvas.itemconfigure(window, width=event.width))
        pack_scrollable(canvas)

        def scroll(event):
            if event.num in (4, 5):
                units = -3 if event.num == 4 else 3
            elif sys.platform == 'darwin':
                units = -event.delta
            else:
                units = -int(event.delta / 120) * 3
            if units:
                canvas.yview_scroll(units, 'units')
                return 'break'

        for sequence in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
            tab.bind(sequence, scroll)

        # Keep wheel handling local to the tab and preserve nested widget scrolling.
        def add_scroll_bindings(widget):
            if not isinstance(widget, (ttk.Treeview, tk.Text, ttk.Combobox)):
                widget.bindtags((str(tab), *widget.bindtags()))
            for child in widget.winfo_children():
                add_scroll_bindings(child)

        build(content)
        add_scroll_bindings(canvas)

    def _build(self):
        outer = tk.Frame(self.root, bg=BG, padx=22, pady=16)
        outer.pack(fill='both', expand=True)
        head = tk.Frame(outer, bg=BG)
        head.pack(fill='x', pady=(0, 13))
        text(head, 'MacTube', 26, True).pack(side='left')
        text(head, 'PRO', 10, True, BLUE).pack(side='left', padx=(7, 0), pady=(10, 0))
        text(head, 'Videos · Audio · Playlists', 11, color=MUTED).pack(side='right', pady=(13, 0))

        address = card(outer, padx=15, pady=12)
        address.pack(fill='x', pady=(0, 12))
        text(address, 'VIDEO OR PLAYLIST URL', 10, True, MUTED).pack(anchor='w')
        url_line = tk.Frame(address, bg=SURFACE)
        url_line.pack(fill='x', pady=(7, 0))
        self.url_entry = ttk.Entry(url_line, textvariable=self.url_var, font=('Helvetica', 12))
        self.url_entry.pack(side='left', fill='x', expand=True, ipady=5)
        self.url_entry.bind('<Return>', lambda _e: self.preview())
        ui_button(url_line, 'Paste', self.paste).pack(side='left', padx=(9, 6))
        self.preview_button = ui_button(url_line, 'Preview video', self.preview, True)
        self.preview_button.pack(side='left')

        self.tabs = ttk.Notebook(outer)
        download_tab = tk.Frame(self.tabs, bg=BG)
        queue_tab = tk.Frame(self.tabs, bg=BG)
        self.tabs.add(download_tab, text='  Download  ')
        self.tabs.add(queue_tab, text='  Queue & activity  ')
        self._build_scrollable_tab(download_tab, self._download_tab)
        self._build_scrollable_tab(queue_tab, self._queue_tab)

        progress_card = card(outer, padx=15, pady=12)
        progress_card.pack(side='bottom', fill='x', pady=(12, 0))
        self.tabs.pack(fill='both', expand=True)
        progress_header = tk.Frame(progress_card, bg=SURFACE)
        progress_header.pack(fill='x')
        tk.Label(progress_header, textvariable=self.status_var, bg=SURFACE, fg=INK,
                 font=('Helvetica', 11, 'bold')).pack(side='left')
        tk.Label(progress_header, textvariable=self.percent_var, bg=SURFACE, fg=BLUE,
                 font=('Helvetica', 12, 'bold')).pack(side='right')
        self.progress = ttk.Progressbar(progress_card, style='Modern.Horizontal.TProgressbar', maximum=100)
        self.progress.pack(fill='x', pady=(9, 7))
        bar = tk.Frame(progress_card, bg=SURFACE)
        bar.pack(fill='x')
        tk.Label(bar, textvariable=self.bytes_var, bg=SURFACE, fg=MUTED,
                 font=('Helvetica', 10)).pack(side='left')
        tk.Label(bar, textvariable=self.speed_var, bg=SURFACE, fg=MUTED,
                 font=('Helvetica', 10)).pack(side='right')
        text(progress_card, 'Progress and bytes refer to the current stream; separate video/audio streams may download in sequence.',
             9, color=MUTED, anchor='w').pack(fill='x', pady=(8, 0))

    def _download_tab(self, parent):
        preview_card = card(parent, padx=13, pady=13)
        preview_card.pack(fill='x', pady=(0, 12))
        preview_row = tk.Frame(preview_card, bg=SURFACE)
        preview_row.pack(fill='x')
        self.thumbnail_label = tk.Label(preview_row, text='▶\nVIDEO PREVIEW', bg=FIELD,
                                        fg=MUTED, font=('Helvetica', 12, 'bold'), width=29,
                                        height=7, justify='center')
        self.thumbnail_label.pack(side='left', padx=(0, 14))
        content = tk.Frame(preview_row, bg=SURFACE)
        content.pack(side='left', fill='both', expand=True)
        tk.Label(content, textvariable=self.preview_title_var, bg=SURFACE, fg=INK,
                 justify='left', wraplength=600, anchor='nw',
                 font=('Helvetica', 15, 'bold')).pack(anchor='w', fill='x', pady=(6, 10))
        tk.Label(content, textvariable=self.preview_meta_var, bg=SURFACE, fg=MUTED,
                 justify='left', wraplength=600, anchor='nw',
                 font=('Helvetica', 11)).pack(anchor='w', fill='x')

        fmt_card = card(parent, padx=13, pady=10)
        fmt_card.pack(fill='both', expand=True, pady=(0, 12))
        hdr = tk.Frame(fmt_card, bg=SURFACE)
        hdr.pack(fill='x', pady=(0, 5))
        text(hdr, 'Available formats', 13, True).pack(side='left')
        ui_button(hdr, 'Use automatic quality', self.clear_format).pack(side='right')
        columns = ('quality', 'container', 'fps', 'codec', 'size')
        format_list = tk.Frame(fmt_card, bg=SURFACE)
        format_list.pack(fill='both', expand=True)
        self.formats_tree = ttk.Treeview(format_list, columns=columns, show='headings',
                                         height=6, selectmode='browse', style='Modern.Treeview')
        headings = {'quality': 'Resolution / type', 'container': 'File', 'fps': 'FPS',
                    'codec': 'Codec', 'size': 'File size'}
        widths = {'quality': 190, 'container': 75, 'fps': 55, 'codec': 170, 'size': 135}
        for col in columns:
            self.formats_tree.heading(col, text=headings[col])
            self.formats_tree.column(col, width=widths[col], minwidth=45,
                                     stretch=col in ('quality', 'codec'))
        pack_scrollable(self.formats_tree)
        self.formats_tree.bind('<<TreeviewSelect>>', self.choose_format)
        tk.Label(fmt_card, textvariable=self.format_help_var, bg=SURFACE, fg=MUTED,
                 anchor='w', font=('Helvetica', 9), wraplength=950,
                 justify='left').pack(fill='x', pady=(6, 0))

        settings = card(parent, padx=13, pady=11)
        settings.pack(fill='x')
        first = tk.Frame(settings, bg=SURFACE)
        first.pack(fill='x')
        first.columnconfigure(0, weight=1)
        first.columnconfigure(1, weight=1)
        for i, (label, variable, values) in enumerate([
            ('Output format', self.format_var, FORMATS),
            ('Auto quality limit', self.quality_var, list(QUALITIES))
        ]):
            cell = tk.Frame(first, bg=SURFACE)
            cell.grid(row=0, column=i, sticky='ew', padx=(0, 12) if i == 0 else (12, 0))
            text(cell, label, 10, True, MUTED).pack(anchor='w')
            combo = ttk.Combobox(cell, textvariable=variable, values=values, state='readonly')
            combo.pack(fill='x', pady=(5, 0))
            if i == 0:
                self.format_box = combo
                combo.bind('<<ComboboxSelected>>', lambda _e: self.format_changed())
            else:
                self.quality_box = combo
        folder = tk.Frame(settings, bg=SURFACE)
        folder.pack(fill='x', pady=(11, 0))
        ttk.Entry(folder, textvariable=self.folder_var, state='readonly').pack(side='left', fill='x', expand=True)
        ui_button(folder, 'Choose folder', self.choose_folder).pack(side='left', padx=(8, 0))
        ui_button(folder, 'Open', self.open_folder).pack(side='left', padx=(6, 0))
        opts = tk.Frame(settings, bg=SURFACE)
        opts.pack(fill='x', pady=(8, 0))
        self.check_buttons = {}
        options = [('Full playlist', self.playlist_var), ('Subtitles', self.subtitles_var),
                   ('Embed subtitles', self.embed_var), ('Cover art', self.thumbnail_var),
                   ('Metadata', self.metadata_var), ('Skip duplicates', self.archive_var)]
        for i, (label, variable) in enumerate(options):
            cb = ttk.Checkbutton(opts, text=label, variable=variable)
            cb.grid(row=i // 3, column=i % 3, sticky='w', padx=(0, 23), pady=3)
            self.check_buttons[label] = cb
        actions = tk.Frame(settings, bg=SURFACE)
        actions.pack(fill='x', pady=(9, 0))
        ui_button(actions, 'Add to queue', self.add_to_queue).pack(side='left')
        ui_button(actions, 'Download now', self.download_now, True).pack(side='left', padx=(9, 0))
        text(actions, 'Formats with ~ are estimated. Conversion may change final size.',
             9, color=MUTED).pack(side='right')

    def _queue_tab(self, parent):
        wrap = card(parent, padx=14, pady=12)
        wrap.pack(fill='both', expand=True)
        head = tk.Frame(wrap, bg=SURFACE)
        head.pack(fill='x', pady=(0, 10))
        text(head, 'Download queue', 15, True).pack(side='left')
        tk.Label(head, textvariable=self.queue_count, bg=SURFACE, fg=MUTED).pack(side='left', padx=(12, 0))
        ui_button(head, 'Remove selected', self.remove_selected).pack(side='right')
        queue_list = tk.Frame(wrap, bg=SURFACE)
        queue_list.pack(fill='both', expand=True)
        self.queue_tree = ttk.Treeview(queue_list, columns=('status', 'url', 'format'),
                                       show='headings', height=8, selectmode='browse', style='Modern.Treeview')
        for col, label, width in [('status', 'Status', 105), ('url', 'Video URL', 570), ('format', 'Format', 130)]:
            self.queue_tree.heading(col, text=label)
            self.queue_tree.column(col, width=width, stretch=(col == 'url'))
        pack_scrollable(self.queue_tree)
        buttons = tk.Frame(wrap, bg=SURFACE)
        buttons.pack(fill='x', pady=(11, 4))
        self.start_button = ui_button(buttons, 'Start queue', self.start_queue, True)
        self.start_button.pack(side='left')
        self.cancel_button = ui_button(buttons, 'Cancel current', self.cancel_current)
        self.cancel_button.pack(side='left', padx=(7, 0))
        self.cancel_button.configure(state='disabled')
        text(wrap, 'Activity log', 12, True).pack(anchor='w', pady=(12, 5))
        log_panel = tk.Frame(wrap, bg=SURFACE)
        log_panel.pack(fill='both', expand=True)
        self.log = tk.Text(log_panel, height=8, bg=FIELD, fg=INK, selectbackground=SELECTED, selectforeground=INK, relief='flat',
                           font=('Menlo' if sys.platform == 'darwin' else 'Consolas', 10),
                           wrap='word', state='disabled', padx=10, pady=7)
        pack_scrollable(self.log)
        ui_button(wrap, 'Clear log', self.clear_log).pack(anchor='e', pady=(6, 0))

    def _check_dependencies(self):
        missing = missing_dependencies()
        if missing:
            self.write_log('Missing: ' + ', '.join(missing) + ' — on macOS run: brew install yt-dlp ffmpeg')
        if Image is None:
            self.write_log('Thumbnail preview requires Pillow: python3.13 -m pip install Pillow')

    def invalidate_preview(self):
        self.preview_generation += 1
        self.preview_button.configure(state='normal')
        self.preview_url = None
        self.available_formats = []
        self.selected_format = None
        self.formats_tree.delete(*self.formats_tree.get_children())
        self.format_help_var.set('Preview this URL to inspect available sizes. Selecting a format overrides auto quality.')
        self.preview_title_var.set('Your video preview will appear here')
        self.preview_meta_var.set('Paste a URL and select Preview')
        self.thumbnail_label.configure(image='', text='▶\nVIDEO PREVIEW')
        self.preview_photo = None

    def paste(self):
        try:
            self.url_var.set(self.root.clipboard_get().strip())
        except tk.TclError:
            messagebox.showinfo('Clipboard', 'Clipboard does not contain text.')

    def preview(self):
        url = self.url_var.get().strip()
        if not valid_url(url):
            messagebox.showerror('Invalid URL', 'Enter a valid YouTube video or playlist URL.')
            return
        if 'yt-dlp' in missing_dependencies():
            messagebox.showerror('Missing dependency', 'Install yt-dlp: brew install yt-dlp')
            return
        self.invalidate_preview()
        generation = self.preview_generation
        self.preview_title_var.set('Loading video information…')
        self.preview_button.configure(state='disabled')
        threading.Thread(target=self._preview_worker, args=(url, self.playlist_var.get(), generation),
                         daemon=True).start()

    def _preview_worker(self, url, playlist, generation):
        try:
            info = inspect_video(url, playlist)
            rows = [] if playlist or info.get('_type') in ('playlist', 'multi_video') else describe_formats(info)
            self.emit('preview_info', generation, url, info, rows)
            thumb = thumbnail_url(info)
            if thumb and Image is not None:
                try:
                    self.emit('thumbnail', generation, load_thumbnail(thumb))
                except Exception as exc:
                    self.emit('log', 'Thumbnail unavailable: ' + str(exc))
        except Exception as exc:
            self.emit('preview_error', generation, str(exc))

    def _apply_preview(self, generation, url, info, rows):
        if generation != self.preview_generation:
            return
        self.preview_button.configure(state='normal')
        self.preview_url = url
        title = info.get('title') or 'Untitled video'
        self.preview_title_var.set(title)
        channel = info.get('channel') or info.get('uploader') or 'Unknown channel'
        duration = info.get('duration')
        duration_text = (f' · {int(duration)//3600:02}:{int(duration)%3600//60:02}:{int(duration)%60:02}'
                         if isinstance(duration, (float, int)) else '')
        count = info.get('playlist_count') or info.get('n_entries')
        self.preview_meta_var.set(f'{channel}{duration_text}' + (f' · {count} videos' if count else ''))
        self.available_formats = rows
        for i, item in enumerate(rows):
            amount = human_bytes(item['size'])
            if item['size'] is not None and not item['exact']:
                amount = '~' + amount
            self.formats_tree.insert('', 'end', iid=str(i), values=(
                item['label'] + (' · audio' if item['kind'] == 'audio' else ''),
                item['ext'], item['fps'], item['codec'], amount))
        if rows:
            self.format_help_var.set(f'{len(rows)} options found. Click a row to download that exact stream combination. '
                                     '“~” means estimated; size may change after merging.')
        else:
            self.format_help_var.set('No individual format sizes for playlist previews. '
                                     'Choose auto quality; each video may have different formats.')

    def choose_format(self, _event=None):
        chosen = self.formats_tree.selection()
        if not chosen:
            return
        i = int(chosen[0])
        if i >= len(self.available_formats):
            return
        self.selected_format = self.available_formats[i].copy()
        fmt = self.selected_format
        size = ('~' if not fmt['exact'] else '') + human_bytes(fmt['size'])
        self.format_help_var.set(f'Selected: {fmt["label"]} · {fmt["ext"]} · {size}. '
                                 'A file may be converted to the output format selected below.')

    def clear_format(self):
        self.selected_format = None
        for item in self.formats_tree.selection():
            self.formats_tree.selection_remove(item)
        self.format_help_var.set('Automatic quality enabled. The quality limit and output format below apply.')

    def format_changed(self):
        audio = self.format_var.get() in ('MP3', 'M4A', 'Original audio')
        self.quality_box.configure(state='disabled' if audio else 'readonly')
        self.check_buttons['Embed subtitles'].configure(state='disabled' if audio else 'normal')
        # Explicit selection remains visible; a selected audio stream + video output would otherwise be ambiguous.
        if self.selected_format and ((self.selected_format['kind'] == 'audio') != audio):
            self.clear_format()

    def options(self):
        data = {'folder': self.folder_var.get(), 'quality': self.quality_var.get(),
                'format': self.format_var.get(), 'playlist': self.playlist_var.get(),
                'subtitles': self.subtitles_var.get(), 'embed_subtitles': self.embed_var.get(),
                'thumbnail': self.thumbnail_var.get(), 'metadata': self.metadata_var.get(),
                'archive': self.archive_var.get(), 'language': self.language_var.get()}
        if self.selected_format and self.preview_url == self.url_var.get().strip() and not data['playlist']:
            data['selected_format'] = self.selected_format.copy()
        return data

    def persist(self):
        try:
            save_settings({key: value for key, value in self.options().items() if key != 'selected_format'})
        except OSError as exc:
            self.write_log(f'Settings not saved: {exc}')

    def choose_folder(self):
        folder = filedialog.askdirectory(initialdir=self.folder_var.get())
        if folder:
            self.folder_var.set(folder)
            self.persist()

    def open_folder(self):
        target = Path(self.folder_var.get()).expanduser()
        target.mkdir(parents=True, exist_ok=True)
        if sys.platform == 'darwin':
            subprocess.Popen(['open', str(target)])
        elif sys.platform == 'win32':
            os.startfile(str(target))
        else:
            subprocess.Popen(['xdg-open', str(target)])

    def add_to_queue(self):
        url = self.url_var.get().strip()
        if not valid_url(url):
            messagebox.showerror('Invalid URL', 'Enter a valid YouTube URL.')
            return False
        opts = self.options()
        if opts.get('selected_format'):
            selected = opts['selected_format']
            audio = opts['format'] in ('MP3', 'M4A', 'Original audio')
            if (selected['kind'] == 'audio') != audio:
                messagebox.showerror('Format mismatch', 'Choose a matching audio/video output type or use automatic quality.')
                return False
        self.jobs.append({'url': url, 'options': opts, 'status': 'Waiting'})
        self.refresh_jobs()
        self.write_log('Added: ' + url)
        self.persist()
        return True

    def download_now(self):
        if self.add_to_queue():
            self.tabs.select(1)
            self.start_queue()

    def refresh_jobs(self):
        current = self.queue_tree.selection()
        self.queue_tree.delete(*self.queue_tree.get_children())
        for i, job in enumerate(self.jobs):
            selected = job['options'].get('selected_format')
            fmt = selected['label'] if selected else job['options']['format']
            self.queue_tree.insert('', 'end', iid=str(i), values=(job['status'], job['url'], fmt))
        if current and current[0] in self.queue_tree.get_children():
            self.queue_tree.selection_set(current[0])
        self.queue_count.set(f'{len(self.jobs)} items')

    def remove_selected(self):
        indexes = self.queue_tree.selection()
        if not indexes:
            return
        i = int(indexes[0])
        if self.jobs[i]['status'] == 'Downloading':
            messagebox.showinfo('Active download', 'Cancel the active download first.')
            return
        self.jobs.pop(i)
        self.refresh_jobs()

    def start_queue(self):
        if self.active:
            return
        missing = missing_dependencies()
        if missing:
            messagebox.showerror('Missing dependencies', 'Install: brew install yt-dlp ffmpeg\nMissing: ' + ', '.join(missing))
            return
        if not any(j['status'] in ('Waiting', 'Failed', 'Cancelled') for j in self.jobs):
            messagebox.showinfo('Empty queue', 'Add a video to your download queue first.')
            return
        self.active = True
        self.stopping = False
        self.runner.cancelled.clear()
        self.start_button.configure(state='disabled')
        self.cancel_button.configure(state='normal')
        threading.Thread(target=self._queue_worker, daemon=True).start()

    def _queue_worker(self):
        for job in self.jobs[:]:
            if self.stopping:
                break
            if job['status'] not in ('Waiting', 'Failed', 'Cancelled'):
                continue
            self.emit('job_status', job, 'Downloading')
            self.emit('begin', job['url'])
            result = self.runner.run(job['url'], job['options'])
            self.emit('job_status', job, {'done': 'Done', 'failed': 'Failed', 'cancelled': 'Cancelled'}[result])
            self.emit('end', result)
            if result == 'cancelled':
                break
        self.emit('queue_end')

    def cancel_current(self):
        if self.active:
            self.stopping = True
            self.runner.cancel()
            self.status_var.set('Stopping download…')

    def emit(self, *event):
        self.messages.put(event)

    def drain(self):
        try:
            for _ in range(160):
                msg = self.messages.get_nowait()
                kind = msg[0]
                if kind == 'preview_info':
                    self._apply_preview(*msg[1:])
                elif kind == 'preview_error':
                    generation, error = msg[1:]
                    if generation == self.preview_generation:
                        self.preview_button.configure(state='normal')
                        self.preview_title_var.set('Could not load preview')
                        self.preview_meta_var.set(error[:250])
                elif kind == 'thumbnail':
                    generation, data = msg[1:]
                    if generation == self.preview_generation and Image is not None:
                        try:
                            img = Image.open(io.BytesIO(data)).convert('RGB')
                            img.thumbnail((260, 146))
                            self.preview_photo = ImageTk.PhotoImage(img)
                            self.thumbnail_label.configure(image=self.preview_photo, text='', width=260, height=146)
                        except Exception as exc:
                            self.write_log(f'Cannot display thumbnail: {exc}')
                elif kind == 'job_status':
                    job, status = msg[1:]
                    job['status'] = status
                    self.refresh_jobs()
                elif kind == 'begin':
                    self.progress['value'] = 0
                    self.percent_var.set('0.0%')
                    self.bytes_var.set('Downloaded: —')
                    self.speed_var.set('Speed: —     ETA: —')
                    self.status_var.set('Downloading ' + msg[1][:85])
                    self.write_log('Starting: ' + msg[1])
                elif kind == 'progress':
                    p = msg[1]
                    self.progress['value'] = p['percent']
                    self.percent_var.set(f'{p["percent"]:.1f}%')
                    downloaded = human_bytes(p['downloaded'])
                    total = ('~' if p['estimated'] else '') + human_bytes(p['total'])
                    self.bytes_var.set(f'Downloaded: {downloaded}' +
                                       (f' / {total}' if p['total'] is not None else ''))
                    self.speed_var.set(f'Speed: {p["speed"]}     ETA: {p["eta"]}')
                elif kind == 'log':
                    self.write_log(msg[1])
                elif kind == 'end':
                    result = msg[1]
                    self.status_var.set({'done': 'Download completed', 'failed': 'Download failed — check Activity log',
                                         'cancelled': 'Download cancelled'}[result])
                    if result == 'done':
                        self.progress['value'] = 100
                        self.percent_var.set('100%')
                elif kind == 'queue_end':
                    self.active = False
                    self.start_button.configure(state='normal')
                    self.cancel_button.configure(state='disabled')
                    self.write_log('Queue finished')
        except queue.Empty:
            pass
        self.root.after(100, self.drain)

    def write_log(self, message):
        at_bottom = self.log.yview()[1] >= 1
        self.log.configure(state='normal')
        self.log.insert('end', message + ('' if message.endswith('\n') else '\n'))
        if int(self.log.index('end-1c').split('.')[0]) > 1100:
            self.log.delete('1.0', '200.0')
        if at_bottom:
            self.log.see('end')
        self.log.configure(state='disabled')

    def clear_log(self):
        self.log.configure(state='normal')
        self.log.delete('1.0', 'end')
        self.log.configure(state='disabled')

    def close(self):
        if self.active:
            if not messagebox.askyesno('Quit MacTube?', 'Cancel your current download and quit?'):
                return
            self.stopping = True
            self.runner.cancel()
        self.persist()
        self.root.destroy()


if __name__ == '__main__':
    try:
        root = tk.Tk()
        MacTube(root)
        root.mainloop()
    except Exception:
        report = traceback.format_exc()
        target = Path.home() / 'mactube-startup-error.log'
        target.write_text(report, encoding='utf-8')
        print(report, file=sys.stderr)
        raise
