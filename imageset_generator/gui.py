"""
CustomTkinter GUI for imageset-generator.
"""

from __future__ import annotations

import io
import re
import threading
import webbrowser
from pathlib import Path
from typing import Callable

import requests
from PIL import Image, ImageDraw
import customtkinter as ctk
from tkinter import filedialog, messagebox

from imageset_generator import __version__
from imageset_generator.config import DEFAULT_IMAGE_SIZE, DEFAULT_LIMIT, OUTPUT_DIR
from imageset_generator.core import build_set
from imageset_generator.providers import tvmaze

# ── Theme ──────────────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Premium Cyber-Dark Theme
BG        = "#09090b"  # Zinc 950
SURFACE   = "#18181b"  # Zinc 900
SURFACE2  = "#27272a"  # Zinc 800
ACCENT    = "#6366f1"  # Indigo 500
ACCENT2   = "#8b5cf6"  # Violet 500
SUCCESS   = "#10b981"  # Emerald 500
WARNING   = "#f59e0b"  # Amber 500
DANGER    = "#ef4444"  # Red 500
TEXT      = "#fafafa"  # Zinc 50
MUTED     = "#a1a1aa"  # Zinc 400
BORDER    = "#3f3f46"  # Zinc 700


# ── Helpers ────────────────────────────────────────────────────────────────────
def load_image_async(url: str, size: tuple[int, int], callback: Callable[[ctk.CTkImage], None], corner_radius: int = 0):
    def worker():
        try:
            r = requests.get(url, timeout=5)
            r.raise_for_status()
            img = Image.open(io.BytesIO(r.content)).convert("RGBA")
            
            # Crop to fill
            target_ratio = size[0] / size[1]
            img_ratio = img.width / img.height
            if img_ratio > target_ratio:
                new_w = int(img.height * target_ratio)
                off = (img.width - new_w) // 2
                img = img.crop((off, 0, off + new_w, img.height))
            elif img_ratio < target_ratio:
                new_h = int(img.width / target_ratio)
                off = (img.height - new_h) // 2
                img = img.crop((0, off, img.width, off + new_h))
            
            img = img.resize(size, Image.Resampling.LANCZOS)
            
            if corner_radius > 0:
                mask = Image.new("L", size, 0)
                draw = ImageDraw.Draw(mask)
                draw.rounded_rectangle((0, 0, size[0], size[1]), corner_radius, fill=255)
                img.putalpha(mask)

            ctk_img = ctk.CTkImage(light_image=img, size=size)
            callback(ctk_img)
        except Exception:
            pass
    threading.Thread(target=worker, daemon=True).start()


# ══════════════════════════════════════════════════════════════════════════════
# Entry Card Widget
# ══════════════════════════════════════════════════════════════════════════════

class EntryCard(ctk.CTkFrame):
    """A beautiful card displaying an actor/character with a large avatar."""
    def __init__(self, master, entry: dict, **kwargs):
        super().__init__(
            master, fg_color=SURFACE2, corner_radius=16,
            border_width=1, border_color=BORDER, **kwargs
        )
        self.entry = entry
        self._var = ctk.BooleanVar(value=True)

        self._img_label = ctk.CTkLabel(
            self, text="👤", width=140, height=140,
            fg_color=SURFACE, corner_radius=12,
            font=ctk.CTkFont(size=50)
        )
        self._img_label.pack(pady=(16, 12), padx=16)
        self._img_label.pack_propagate(False)

        if entry.get("fallback_img"):
            def _on_img(img):
                try:
                    self._img_label.configure(image=img, text="")
                except Exception:
                    pass
            load_image_async(entry["fallback_img"], (140, 140), _on_img, corner_radius=12)

        ctk.CTkLabel(
            self, text=entry.get("label", ""), font=ctk.CTkFont(size=15, weight="bold"),
            text_color=TEXT, anchor="center"
        ).pack(padx=12, fill="x")

        ctk.CTkLabel(
            self, text=entry.get("person", ""), font=ctk.CTkFont(size=12),
            text_color=MUTED, anchor="center"
        ).pack(padx=12, pady=(0, 12), fill="x")

        self._cb = ctk.CTkCheckBox(
            self, text="Include", variable=self._var,
            fg_color=ACCENT, hover_color=ACCENT2, border_color=BORDER,
            font=ctk.CTkFont(size=13)
        )
        self._cb.pack(pady=(0, 16))

    @property
    def selected(self) -> bool:
        return self._var.get()

    def select_all(self):
        self._var.set(True)

    def deselect_all(self):
        self._var.set(False)


# ══════════════════════════════════════════════════════════════════════════════
# Progress Widget
# ══════════════════════════════════════════════════════════════════════════════

class ProgressRow(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color=SURFACE2, corner_radius=12, **kwargs)
        self._label = ctk.CTkLabel(self, text="Initialising…", font=ctk.CTkFont(size=13, weight="bold"), text_color=TEXT, anchor="w")
        self._label.pack(fill="x", padx=20, pady=(16, 6))

        self._bar = ctk.CTkProgressBar(self, mode="determinate", progress_color=ACCENT, fg_color=SURFACE, height=10)
        self._bar.set(0)
        self._bar.pack(fill="x", padx=20, pady=(0, 6))

        self._status = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=12), text_color=MUTED, anchor="w")
        self._status.pack(fill="x", padx=20, pady=(0, 16))

    def update_progress(self, current: int, total: int, label: str, status: str):
        fraction = current / total if total else 0
        self._bar.set(fraction)
        self._label.configure(text=f"[{current}/{total}]  {label}")
        colour = {"ok": SUCCESS, "cached": ACCENT2, "no_image": WARNING}.get(status, MUTED)
        readable = {"ok": "✓ Downloaded", "cached": "⚡ Cached", "no_image": "⚠ No image found", "downloading": "⬇ Downloading…"}.get(status, status)
        self._status.configure(text=readable, text_color=colour)


# ══════════════════════════════════════════════════════════════════════════════
# Settings Sidebar
# ══════════════════════════════════════════════════════════════════════════════

class SettingsPanel(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color=SURFACE, corner_radius=16, border_width=1, border_color=BORDER, **kwargs)

        ctk.CTkLabel(self, text="Settings", font=ctk.CTkFont(size=18, weight="bold"), text_color=TEXT).pack(padx=20, pady=(24, 16), anchor="w")
        self._sep()

        self._limit = self._add_input("Max entries", str(DEFAULT_LIMIT))
        self._sep()

        self._size = self._add_dropdown("Image size (px)", ["256", "512", "768", "1024"], str(DEFAULT_IMAGE_SIZE[0]))
        self._sep()

        self._fmt = self._add_dropdown("Image format", ["JPEG", "PNG"], "JPEG")
        self._sep()

        ctk.CTkLabel(self, text="Output folder", text_color=MUTED, font=ctk.CTkFont(size=12, weight="bold"), anchor="w").pack(fill="x", padx=20, pady=(16, 4))
        self._out_var = ctk.StringVar(value=str(OUTPUT_DIR))
        ctk.CTkEntry(self, textvariable=self._out_var, fg_color=SURFACE2, border_color=BORDER, text_color=MUTED, font=ctk.CTkFont(size=11), height=32).pack(padx=20, pady=(0, 8), fill="x")
        ctk.CTkButton(self, text="Browse Folder", command=self._pick_folder, fg_color=SURFACE2, hover_color=BORDER, text_color=TEXT, height=32, font=ctk.CTkFont(size=12, weight="bold")).pack(padx=20, pady=(0, 24), fill="x")

    def _add_input(self, label, default):
        ctk.CTkLabel(self, text=label, text_color=MUTED, font=ctk.CTkFont(size=12, weight="bold"), anchor="w").pack(fill="x", padx=20, pady=(16, 4))
        entry = ctk.CTkEntry(self, placeholder_text=default, fg_color=SURFACE2, border_color=BORDER, text_color=TEXT, height=32)
        entry.insert(0, default)
        entry.pack(padx=20, pady=(0, 16), anchor="w", fill="x")
        return entry

    def _add_dropdown(self, label, options, default):
        ctk.CTkLabel(self, text=label, text_color=MUTED, font=ctk.CTkFont(size=12, weight="bold"), anchor="w").pack(fill="x", padx=20, pady=(16, 4))
        menu = ctk.CTkOptionMenu(self, values=options, fg_color=SURFACE2, button_color=ACCENT, button_hover_color=ACCENT2, dropdown_fg_color=SURFACE2, text_color=TEXT, height=32)
        menu.set(default)
        menu.pack(padx=20, pady=(0, 16), fill="x")
        return menu

    def _sep(self):
        ctk.CTkFrame(self, height=1, fg_color=BORDER).pack(fill="x", padx=20)

    def _pick_folder(self):
        d = filedialog.askdirectory(title="Choose output folder")
        if d: self._out_var.set(d)

    @property
    def limit(self) -> int:
        try: return max(1, int(self._limit.get()))
        except ValueError: return DEFAULT_LIMIT

    @property
    def image_size(self) -> tuple[int, int]:
        v = int(self._size.get())
        return (v, v)

    @property
    def image_format(self) -> str: return self._fmt.get()
    
    @property
    def output_dir(self) -> Path: return Path(self._out_var.get())


# ══════════════════════════════════════════════════════════════════════════════
# Main App
# ══════════════════════════════════════════════════════════════════════════════

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(f"Image Set Generator  v{__version__}")
        self.geometry("1200x800")
        self.minsize(900, 600)
        self.configure(fg_color=BG)

        self._entries: list[dict] = []
        self._cards: list[EntryCard] = []
        self._current_show: dict | None = None
        self._search_results: list[dict] = []
        self._running = False
        
        self.bind("<Configure>", self._on_resize)
        self._last_width = 0

        self._build_ui()

    def _build_ui(self):
        # Top App Bar
        topbar = ctk.CTkFrame(self, fg_color=SURFACE, corner_radius=0, height=70)
        topbar.pack(fill="x", side="top")
        topbar.pack_propagate(False)

        ctk.CTkLabel(topbar, text="⚡ Set Generator", font=ctk.CTkFont(size=24, weight="bold"), text_color=ACCENT).pack(side="left", padx=24, pady=20)
        ctk.CTkLabel(topbar, text=f"v{__version__}", font=ctk.CTkFont(size=12), text_color=MUTED).pack(side="left", padx=(0, 0), pady=24)

        # Search inside topbar (centered and bigger)
        search_frame = ctk.CTkFrame(topbar, fg_color=SURFACE2, corner_radius=12, border_width=1, border_color=BORDER, height=48, width=500)
        search_frame.place(relx=0.5, rely=0.5, anchor="center")
        search_frame.pack_propagate(False)

        ctk.CTkLabel(search_frame, text="🔍", font=ctk.CTkFont(size=18), text_color=MUTED).pack(side="left", padx=(16, 8))
        self._search_var = ctk.StringVar()
        self._search_entry = ctk.CTkComboBox(
            search_frame, variable=self._search_var, values=[],
            command=self._on_show_selected,
            fg_color=SURFACE2, border_width=0, text_color=TEXT,
            font=ctk.CTkFont(size=16), height=36,
            button_color=SURFACE2, button_hover_color=BORDER, dropdown_fg_color=SURFACE2
        )
        self._search_entry.pack(side="left", fill="both", expand=True, pady=6)
        self._search_entry.bind("<Return>", lambda _: self._do_search())

        self._search_btn = ctk.CTkButton(search_frame, text="Search", command=self._do_search, fg_color=ACCENT, hover_color=ACCENT2, font=ctk.CTkFont(size=14, weight="bold"), corner_radius=8, width=80, height=36)
        self._search_btn.pack(side="right", padx=6, pady=6)

        # Content Layout
        content = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        content.pack(fill="both", expand=True)

        self._settings = SettingsPanel(content, width=260)
        self._settings.pack(side="right", fill="y", padx=(12, 24), pady=24)

        main = ctk.CTkFrame(content, fg_color=BG, corner_radius=0)
        main.pack(side="left", fill="both", expand=True, padx=(24, 12), pady=24)

        # Bottom
        bottom = ctk.CTkFrame(main, fg_color="transparent")
        bottom.pack(side="bottom", fill="x")

        self._build_btn = ctk.CTkButton(bottom, text="🚀 Generate ZIP Pack", command=self._do_build, fg_color=ACCENT, hover_color=ACCENT2, font=ctk.CTkFont(size=16, weight="bold"), height=54, corner_radius=14, state="disabled")
        self._build_btn.pack(side="left", fill="x", expand=True, padx=(0, 12))

        self._open_btn = ctk.CTkButton(bottom, text="📂 Output Folder", command=self._open_output, fg_color=SURFACE, hover_color=BORDER, text_color=TEXT, font=ctk.CTkFont(size=14, weight="bold"), height=54, corner_radius=14, width=160, border_width=1, border_color=BORDER)
        self._open_btn.pack(side="right")

        # Show Picker (Removed: unified into search combobox)

        # Show Hero Header
        self._hero = ctk.CTkFrame(main, fg_color=SURFACE, corner_radius=16, border_width=1, border_color=BORDER)
        
        self._hero_poster = ctk.CTkLabel(self._hero, text="", width=140, height=200, fg_color=SURFACE2, corner_radius=12)
        self._hero_poster.pack(side="left", padx=20, pady=20)
        self._hero_poster.pack_propagate(False)

        hero_info = ctk.CTkFrame(self._hero, fg_color="transparent")
        hero_info.pack(side="left", fill="both", expand=True, pady=20, padx=(0, 20))
        
        self._hero_title = ctk.CTkLabel(hero_info, text="", font=ctk.CTkFont(size=28, weight="bold"), text_color=TEXT, anchor="w")
        self._hero_title.pack(fill="x")
        self._hero_summary = ctk.CTkLabel(hero_info, text="", font=ctk.CTkFont(size=14), text_color=MUTED, anchor="nw", justify="left", wraplength=550)
        self._hero_summary.pack(fill="both", expand=True, pady=(8, 0))

        # Status & Select All
        self._controls = ctk.CTkFrame(main, fg_color="transparent")
        self._status_var = ctk.StringVar(value="Ready to search.")
        self._status_label = ctk.CTkLabel(self._controls, textvariable=self._status_var, font=ctk.CTkFont(size=14), text_color=MUTED, anchor="w")
        self._status_label.pack(side="left")

        ctk.CTkButton(self._controls, text="Select All", command=self._select_all, fg_color=SURFACE2, hover_color=BORDER, text_color=TEXT, font=ctk.CTkFont(size=12, weight="bold"), height=32, width=90).pack(side="right")
        ctk.CTkButton(self._controls, text="Deselect All", command=self._deselect_all, fg_color=SURFACE2, hover_color=BORDER, text_color=TEXT, font=ctk.CTkFont(size=12, weight="bold"), height=32, width=90).pack(side="right", padx=(0, 10))

        # Grid List
        self._list_frame = ctk.CTkScrollableFrame(main, fg_color=SURFACE, corner_radius=16, border_width=1, border_color=BORDER)
        self._list_frame.pack(fill="both", expand=True, pady=(20, 20))

        # Progress
        self._progress_row = ProgressRow(main)

    def _on_resize(self, event):
        # Re-grid cards if width changes significantly
        w = self._list_frame.winfo_width()
        if abs(w - self._last_width) > 50 and self._cards:
            self._last_width = w
            self._layout_cards()

    def _layout_cards(self):
        w = max(1, self._list_frame.winfo_width())
        cols = max(1, w // 200) # Each card is ~180px + padding
        
        for widget in self._list_frame.winfo_children():
            widget.grid_forget()

        for i, card in enumerate(self._cards):
            row = i // cols
            col = i % cols
            card.grid(row=row, column=col, padx=12, pady=12, sticky="nsew")

        # Configure columns to distribute equally
        for c in range(cols):
            self._list_frame.columnconfigure(c, weight=1)

    # ── Logic ──────────────────────────────────────────────────────────────────
    
    def _set_status(self, text: str, colour: str = MUTED):
        self._status_var.set(text)
        self._status_label.configure(text_color=colour)

    def _do_search(self):
        query = self._search_var.get().strip()
        if not query: return
        self._set_status("Searching…", ACCENT)
        self._search_btn.configure(state="disabled")
        self._build_btn.configure(state="disabled")
        self._hero.pack_forget()
        self._controls.pack_forget()
        self._clear_list()

        def _w():
            try: res = tvmaze.search(query)
            except Exception as e:
                self.after(0, self._set_status, f"Error: {e}", DANGER)
                self.after(0, self._search_btn.configure, {"state": "normal"})
                return
            self.after(0, self._on_search_done, res)
        threading.Thread(target=_w, daemon=True).start()

    def _on_search_done(self, results):
        self._search_btn.configure(state="normal")
        self._search_results = results
        if not results:
            self._set_status("No results found.", DANGER)
            self._search_entry.configure(values=[])
            return
        
        labels = [f"{r['name']} ({r['year']})" if r.get('year') else r['name'].strip() for r in results]
        self._search_entry.configure(values=labels)
        self._search_var.set(labels[0])
        
        self._list_frame.pack_forget()
        self._controls.pack(fill="x", pady=(10, 0))
        self._list_frame.pack(fill="both", expand=True, pady=(20, 20))
        
        if len(results) > 1:
            self._set_status(f"Found {len(results)} matches. Pick from the search bar drop-down.", ACCENT2)
        
        self._load_show(results[0])

    def _on_show_selected(self, label):
        labels = [f"{r['name']} ({r['year']})" if r.get('year') else r['name'].strip() for r in self._search_results]
        try: idx = labels.index(label)
        except ValueError: return
        self._load_show(self._search_results[idx])

    def _load_show(self, show):
        self._current_show = show
        self._clear_list()
        self._set_status(f"Loading cast for '{show['name']}'…", ACCENT)
        
        # Repack everything in the correct order
        self._controls.pack_forget()
        self._list_frame.pack_forget()
        
        self._hero.pack(fill="x", pady=(0, 20))
        self._controls.pack(fill="x", pady=(10, 0))
        self._list_frame.pack(fill="both", expand=True, pady=(20, 20))

        self._hero_title.configure(text=f"{show['name']} ({show.get('year', '')})")
        summary = re.sub(r'<[^>]+>', '', show.get("summary", ""))
        self._hero_summary.configure(text=(summary[:400] + "...") if len(summary) > 400 else summary)
        
        self._hero_poster.configure(image="", text="Loading...")
        if show.get("image_url"):
            def _cb(img):
                try: self._hero_poster.configure(image=img, text="")
                except Exception: pass
            load_image_async(show["image_url"], (140, 200), _cb, corner_radius=12)
        else:
            self._hero_poster.configure(text="No Poster")

        limit = self._settings.limit
        def _w():
            try: entries = tvmaze.fetch_entries(show["id"], limit=limit)
            except Exception as e:
                self.after(0, self._set_status, f"Failed: {e}", DANGER)
                return
            self.after(0, self._on_entries_loaded, entries, show["name"])
        threading.Thread(target=_w, daemon=True).start()

    def _on_entries_loaded(self, entries, show_name):
        self._entries = entries
        self._cards.clear()
        
        if not entries:
            self._set_status("No cast found.", WARNING)
            return

        for entry in entries:
            card = EntryCard(self._list_frame, entry)
            self._cards.append(card)

        self._layout_cards()
        self._set_status(f"Loaded {len(entries)} characters.", SUCCESS)
        self._build_btn.configure(state="normal")

    def _clear_list(self):
        self._cards.clear()
        for w in self._list_frame.winfo_children(): w.destroy()

    def _select_all(self):
        for c in self._cards: c.select_all()

    def _deselect_all(self):
        for c in self._cards: c.deselect_all()

    def _do_build(self):
        if self._running: return
        selected = [self._entries[i] for i, c in enumerate(self._cards) if c.selected]
        if not selected:
            messagebox.showwarning("Empty", "Select at least one character.")
            return

        self._running = True
        self._build_btn.configure(state="disabled", text="Generating...")
        
        self._list_frame.pack_forget()
        self._progress_row.pack(fill="x", pady=(0, 20))
        self._list_frame.pack(fill="both", expand=True, pady=(20, 20))
        
        sn = self._current_show["name"]
        sz = self._settings.image_size
        fmt = self._settings.image_format
        out = self._settings.output_dir

        def _p(c, t, l, s): self.after(0, self._progress_row.update_progress, c, t, l, s)
        def _w():
            try:
                zp = build_set(sn, selected, image_size=sz, image_format=fmt, output_dir=out, on_progress=_p)
                self.after(0, self._on_build_done, zp)
            except Exception as e:
                self.after(0, self._on_build_error, str(e))
        threading.Thread(target=_w, daemon=True).start()

    def _on_build_done(self, zp):
        self._running = False
        self._build_btn.configure(state="normal", text="🚀 Generate ZIP Pack")
        self._set_status(f"✓ Created: {zp.name}", SUCCESS)
        self._progress_row.pack_forget()

    def _on_build_error(self, msg):
        self._running = False
        self._build_btn.configure(state="normal", text="🚀 Generate ZIP Pack")
        self._set_status(f"Error: {msg}", DANGER)
        self._progress_row.pack_forget()

    def _open_output(self):
        d = self._settings.output_dir
        d.mkdir(parents=True, exist_ok=True)
        webbrowser.open(d.as_uri())

def main():
    App().mainloop()

if __name__ == "__main__":
    main()
