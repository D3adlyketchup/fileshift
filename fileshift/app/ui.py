"""
ui.py — CustomTkinter GUI for FileShift
"""

from __future__ import annotations

import os
import threading
import queue
import tkinter as tk
import tkinter.filedialog as fd
import tkinter.messagebox as mb
import customtkinter as ctk  # type: ignore

from app.converters import (
    ACCEPTED_EXTENSIONS,
    FORMAT_MAP,
    get_output_formats,
    get_category,
    default_output_path,
    convert,
)

# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("green")

GREEN      = "#1D9E75"
GREEN_DARK = "#0F6E56"
RED        = "#E24B4A"
AMBER      = "#EF9F27"

# ---------------------------------------------------------------------------
# File row widget
# ---------------------------------------------------------------------------

class FileRow(ctk.CTkFrame):
    """
    One row in the conversion queue.
    Shows filename, size, format selector, progress bar, status label,
    and a remove/download button.
    """

    STATUS_WAITING    = "Waiting"
    STATUS_CONVERTING = "Converting…"
    STATUS_DONE       = "Done ✓"
    STATUS_ERROR      = "Error ✗"

    def __init__(self, master, file_path: str, on_remove, **kwargs):
        super().__init__(master, corner_radius=8, **kwargs)

        self.file_path   = file_path
        self.on_remove   = on_remove
        self.output_path: str | list[str] | None = None
        self._status     = self.STATUS_WAITING

        # Gather info
        filename = os.path.basename(file_path)
        size_mb  = os.path.getsize(file_path) / 1_048_576
        formats  = get_output_formats(file_path)
        category = get_category(file_path)

        # --- Layout ----------------------------------------------------------
        self.grid_columnconfigure(1, weight=1)

        # Category tag
        tag_colors = {
            "Video":        ("#E1F5EE", GREEN_DARK),
            "Document":     ("#E6F1FB", "#185FA5"),
            "Presentation": ("#FAEEDA", "#854F0B"),
            "Image":        ("#EEEDFE", "#534AB7"),
        }
        tag_bg, tag_fg = tag_colors.get(category, ("#F1EFE8", "#5F5E5A"))

        self.tag_label = ctk.CTkLabel(
            self, text=category, width=90,
            fg_color=tag_bg, text_color=tag_fg,
            corner_radius=6, font=ctk.CTkFont(size=11, weight="bold"),
        )
        self.tag_label.grid(row=0, column=0, padx=(10, 8), pady=(10, 2), sticky="w")

        # Filename + size
        self.name_label = ctk.CTkLabel(
            self, text=filename, anchor="w",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.name_label.grid(row=0, column=1, padx=4, pady=(10, 2), sticky="ew")

        self.size_label = ctk.CTkLabel(
            self, text=f"{size_mb:.1f} MB",
            font=ctk.CTkFont(size=11), text_color="gray",
        )
        self.size_label.grid(row=0, column=2, padx=8, pady=(10, 2))

        # Format selector
        fmt_frame = ctk.CTkFrame(self, fg_color="transparent")
        fmt_frame.grid(row=0, column=3, padx=8, pady=(10, 2))

        ctk.CTkLabel(fmt_frame, text="→", font=ctk.CTkFont(size=14)).pack(side="left", padx=(0, 4))

        self.fmt_var = ctk.StringVar(value=formats[0] if formats else "N/A")
        self.fmt_menu = ctk.CTkOptionMenu(
            fmt_frame,
            values=formats if formats else ["N/A"],
            variable=self.fmt_var,
            width=80, height=28,
            fg_color=GREEN, button_color=GREEN_DARK,
            font=ctk.CTkFont(size=12),
        )
        self.fmt_menu.pack(side="left")

        # Remove button
        self.remove_btn = ctk.CTkButton(
            self, text="✕", width=30, height=28,
            fg_color="transparent", hover_color="#FCEBEB",
            text_color="gray", font=ctk.CTkFont(size=14),
            command=self._remove,
        )
        self.remove_btn.grid(row=0, column=4, padx=(4, 10), pady=(10, 2))

        # Progress bar
        self.progress = ctk.CTkProgressBar(self, height=6, progress_color=GREEN)
        self.progress.set(0)
        self.progress.grid(row=1, column=0, columnspan=4,
                           padx=10, pady=(2, 4), sticky="ew")

        # Status label
        self.status_label = ctk.CTkLabel(
            self, text=self.STATUS_WAITING,
            font=ctk.CTkFont(size=11), text_color="gray",
        )
        self.status_label.grid(row=1, column=4, padx=10, pady=(2, 4))

        # Separator
        sep = ctk.CTkFrame(self, height=1, fg_color=("gray85", "gray25"))
        sep.grid(row=2, column=0, columnspan=5, sticky="ew", padx=0)

    # -------------------------------------------------------------------------

    @property
    def status(self):
        return self._status

    def set_status(self, status: str, color: str = "gray"):
        self._status = status
        self.status_label.configure(text=status, text_color=color)

    def set_progress(self, value: float):
        """value: 0.0 – 1.0"""
        self.progress.set(value)

    def _remove(self):
        self.on_remove(self)

    def get_selected_format(self) -> str:
        return self.fmt_var.get()

    def lock(self):
        """Disable controls during conversion."""
        self.fmt_menu.configure(state="disabled")
        self.remove_btn.configure(state="disabled")

    def unlock(self):
        self.fmt_menu.configure(state="normal")
        self.remove_btn.configure(state="normal")

    def mark_done(self, output):
        self.output_path = output
        self.set_progress(1.0)
        self.set_status(self.STATUS_DONE, GREEN)
        self.remove_btn.configure(
            text="↓", text_color=GREEN, hover_color="#E1F5EE",
            command=self._open_output,
        )

    def mark_error(self, msg: str):
        self.set_progress(0)
        self.set_status(f"Error: {msg[:40]}", RED)
        self.unlock()

    def _open_output(self):
        """Open the output file or folder in the OS file manager."""
        import subprocess, sys
        target = self.output_path
        if isinstance(target, list):
            target = os.path.dirname(target[0]) if target else None
        if not target:
            return
        if sys.platform == "win32":
            os.startfile(os.path.dirname(target) if os.path.isfile(target) else target)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", os.path.dirname(target)])
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(target)])


# ---------------------------------------------------------------------------
# Drop zone
# ---------------------------------------------------------------------------

class DropZone(ctk.CTkFrame):
    """A frame that accepts drag-and-drop file drops."""

    def __init__(self, master, on_files_added, **kwargs):
        super().__init__(master, corner_radius=12,
                         border_width=2, border_color=("gray70", "gray40"),
                         **kwargs)
        self.on_files_added = on_files_added
        self._setup_ui()
        self._bind_drop()

    def _setup_ui(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        inner = ctk.CTkFrame(self, fg_color="transparent")
        inner.grid(row=0, column=0)

        ctk.CTkLabel(
            inner, text="⇩",
            font=ctk.CTkFont(size=40), text_color=("gray60", "gray50"),
        ).pack(pady=(0, 6))

        ctk.CTkLabel(
            inner, text="Drag & drop files here",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).pack()

        ctk.CTkLabel(
            inner, text="or click Browse to select files",
            font=ctk.CTkFont(size=12), text_color="gray",
        ).pack(pady=(2, 14))

        ctk.CTkButton(
            inner, text="Browse files", width=130, height=34,
            fg_color=GREEN, hover_color=GREEN_DARK,
            font=ctk.CTkFont(size=13),
            command=self._browse,
        ).pack()

        ext_text = "  ".join(sorted(ACCEPTED_EXTENSIONS))
        ctk.CTkLabel(
            inner, text=ext_text,
            font=ctk.CTkFont(size=10), text_color="gray",
            wraplength=420,
        ).pack(pady=(12, 0))

    def _browse(self):
        paths = fd.askopenfilenames(
            title="Select files to convert",
            filetypes=[("All supported", " ".join(f"*{e}" for e in ACCEPTED_EXTENSIONS)),
                       ("All files", "*.*")],
        )
        if paths:
            self.on_files_added(list(paths))

    def _bind_drop(self):
        """Enable tkinterdnd2 drop if available, otherwise silently skip."""
        try:
            self.drop_target_register("DND_Files")  # type: ignore
            self.dnd_bind("<<Drop>>", self._on_drop)  # type: ignore
        except Exception:
            pass

    def _on_drop(self, event):
        raw = event.data
        # tkinterdnd2 returns paths wrapped in braces if they contain spaces
        import re
        paths = re.findall(r'\{[^}]+\}|\S+', raw)
        paths = [p.strip("{}") for p in paths]
        valid = [p for p in paths
                 if os.path.isfile(p)
                 and os.path.splitext(p)[1].lower() in ACCEPTED_EXTENSIONS]
        if valid:
            self.on_files_added(valid)
        else:
            mb.showwarning("Unsupported files",
                           "None of the dropped files are in a supported format.")

    def highlight(self, on: bool):
        color = (GREEN, GREEN_DARK) if on else ("gray70", "gray40")
        self.configure(border_color=color)


# ---------------------------------------------------------------------------
# Main application window
# ---------------------------------------------------------------------------

class FileshiftApp(ctk.CTk):

    def __init__(self):
        super().__init__()

        self.title("FileShift — Universal File Converter")
        self.geometry("800x680")
        self.minsize(640, 500)

        self._file_rows: list[FileRow] = []
        self._result_queue: queue.Queue = queue.Queue()

        self._build_ui()
        self._poll_results()

    # -------------------------------------------------------------------------
    # UI construction
    # -------------------------------------------------------------------------

    def _build_ui(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Top bar
        topbar = ctk.CTkFrame(self, height=52, corner_radius=0,
                               fg_color=("white", "gray17"))
        topbar.grid(row=0, column=0, sticky="ew")
        topbar.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            topbar, text="⇄  FileShift",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=GREEN,
        ).grid(row=0, column=0, padx=16, pady=12)

        self.theme_btn = ctk.CTkButton(
            topbar, text="🌙  Dark", width=90, height=28,
            fg_color="transparent", border_width=1,
            text_color=("gray40", "gray70"),
            font=ctk.CTkFont(size=12),
            command=self._toggle_theme,
        )
        self.theme_btn.grid(row=0, column=2, padx=12)

        # Stats bar
        stats_frame = ctk.CTkFrame(self, fg_color=("gray95", "gray18"),
                                    corner_radius=0, height=48)
        stats_frame.grid(row=1, column=0, sticky="ew")
        stats_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self.stat_queued = self._make_stat(stats_frame, "0", "Queued", 0)
        self.stat_done   = self._make_stat(stats_frame, "0", "Converted", 1)
        self.stat_errors = self._make_stat(stats_frame, "0", "Errors", 2)

        # Main body
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=2, column=0, sticky="nsew", padx=16, pady=12)
        body.grid_rowconfigure(1, weight=1)
        body.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # Drop zone
        self.drop_zone = DropZone(body, on_files_added=self._add_files,
                                   height=180)
        self.drop_zone.grid(row=0, column=0, sticky="ew", pady=(0, 12))

        # Queue label
        queue_header = ctk.CTkFrame(body, fg_color="transparent")
        queue_header.grid(row=1, column=0, sticky="ew")
        queue_header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            queue_header, text="CONVERSION QUEUE",
            font=ctk.CTkFont(size=10, weight="bold"), text_color="gray",
        ).grid(row=0, column=0, sticky="w", padx=2, pady=(0, 6))

        ctk.CTkButton(
            queue_header, text="Clear done", width=90, height=26,
            fg_color="transparent", border_width=1,
            text_color="gray", font=ctk.CTkFont(size=11),
            command=self._clear_done,
        ).grid(row=0, column=1, sticky="e")

        # Scrollable queue frame
        self.queue_scroll = ctk.CTkScrollableFrame(
            body, corner_radius=10,
            fg_color=("white", "gray17"),
            border_width=1, border_color=("gray80", "gray30"),
            label_text="",
        )
        self.queue_scroll.grid(row=2, column=0, sticky="nsew", pady=(0, 12))
        self.queue_scroll.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(2, weight=1)

        self._empty_label = ctk.CTkLabel(
            self.queue_scroll,
            text="No files added yet.\nDrag files above or click Browse.",
            font=ctk.CTkFont(size=13), text_color="gray",
        )
        self._empty_label.grid(row=0, column=0, pady=30)

        # Action bar
        action_bar = ctk.CTkFrame(body, fg_color="transparent")
        action_bar.grid(row=3, column=0, sticky="ew")
        action_bar.grid_columnconfigure(0, weight=1)

        self.output_label = ctk.CTkLabel(
            action_bar,
            text="📁  Output: same folder as source",
            font=ctk.CTkFont(size=11), text_color="gray",
        )
        self.output_label.grid(row=0, column=0, sticky="w")

        btn_frame = ctk.CTkFrame(action_bar, fg_color="transparent")
        btn_frame.grid(row=0, column=1)

        self.clear_btn = ctk.CTkButton(
            btn_frame, text="Clear all", width=90, height=36,
            fg_color="transparent", border_width=1,
            text_color=("gray40", "gray60"),
            command=self._clear_all,
        )
        self.clear_btn.pack(side="left", padx=(0, 8))

        self.convert_btn = ctk.CTkButton(
            btn_frame, text="⚡  Convert all", width=140, height=36,
            fg_color=GREEN, hover_color=GREEN_DARK,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._start_conversion,
        )
        self.convert_btn.pack(side="left")

    def _make_stat(self, parent, value, label, col):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.grid(row=0, column=col, padx=16, pady=8)
        val_lbl = ctk.CTkLabel(
            frame, text=value,
            font=ctk.CTkFont(size=20, weight="bold"),
        )
        val_lbl.pack()
        ctk.CTkLabel(
            frame, text=label,
            font=ctk.CTkFont(size=11), text_color="gray",
        ).pack()
        return val_lbl

    # -------------------------------------------------------------------------
    # File management
    # -------------------------------------------------------------------------

    def _add_files(self, paths: list[str]):
        existing = {row.file_path for row in self._file_rows}
        added = 0
        for path in paths:
            if path in existing:
                continue
            ext = os.path.splitext(path)[1].lower()
            if ext not in ACCEPTED_EXTENSIONS:
                mb.showwarning("Unsupported format",
                               f"{os.path.basename(path)}\n"
                               f"Extension '{ext}' is not supported.")
                continue
            self._add_row(path)
            added += 1

        if added:
            self._refresh_stats()

    def _add_row(self, path: str):
        if self._empty_label.winfo_ismapped():
            self._empty_label.grid_forget()

        row = FileRow(
            self.queue_scroll, path,
            on_remove=self._remove_row,
            fg_color=("gray97", "gray20"),
        )
        idx = len(self._file_rows)
        row.grid(row=idx, column=0, sticky="ew", padx=4, pady=3)
        self._file_rows.append(row)

    def _remove_row(self, row: FileRow):
        if row in self._file_rows:
            self._file_rows.remove(row)
        row.destroy()
        self._reindex_rows()
        self._refresh_stats()
        if not self._file_rows:
            self._empty_label.grid(row=0, column=0, pady=30)

    def _reindex_rows(self):
        for i, row in enumerate(self._file_rows):
            row.grid(row=i, column=0, sticky="ew", padx=4, pady=3)

    def _clear_done(self):
        done = [r for r in self._file_rows if r.status == FileRow.STATUS_DONE]
        for row in done:
            self._remove_row(row)

    def _clear_all(self):
        for row in list(self._file_rows):
            row.destroy()
        self._file_rows.clear()
        self._empty_label.grid(row=0, column=0, pady=30)
        self._refresh_stats()

    # -------------------------------------------------------------------------
    # Stats
    # -------------------------------------------------------------------------

    def _refresh_stats(self):
        total   = len(self._file_rows)
        done    = sum(1 for r in self._file_rows if r.status == FileRow.STATUS_DONE)
        errors  = sum(1 for r in self._file_rows if r.status == FileRow.STATUS_ERROR)
        self.stat_queued.configure(text=str(total))
        self.stat_done.configure(text=str(done))
        self.stat_errors.configure(text=str(errors))

    # -------------------------------------------------------------------------
    # Conversion
    # -------------------------------------------------------------------------

    def _start_conversion(self):
        pending = [r for r in self._file_rows
                   if r.status in (FileRow.STATUS_WAITING, FileRow.STATUS_ERROR)]
        if not pending:
            mb.showinfo("Nothing to convert",
                        "Add files or check that they are not already converted.")
            return

        self.convert_btn.configure(state="disabled", text="Converting…")

        for row in pending:
            row.lock()
            row.set_status(FileRow.STATUS_CONVERTING, AMBER)
            thread = threading.Thread(
                target=self._conversion_worker,
                args=(row,), daemon=True,
            )
            thread.start()

    def _conversion_worker(self, row: FileRow):
        """Runs in a background thread. Posts results back via queue."""
        try:
            in_path  = row.file_path
            out_ext  = row.get_selected_format()
            out_path = default_output_path(in_path, out_ext)

            def cb(frac: float):
                self._result_queue.put(("progress", row, frac))

            result = convert(in_path, out_path, out_ext, progress_cb=cb)
            self._result_queue.put(("done", row, result))
        except Exception as exc:
            self._result_queue.put(("error", row, str(exc)))

    def _poll_results(self):
        """Called every 100 ms on the main thread to drain the result queue."""
        try:
            while True:
                msg = self._result_queue.get_nowait()
                kind = msg[0]
                row: FileRow = msg[1]

                if kind == "progress":
                    row.set_progress(msg[2])
                elif kind == "done":
                    row.mark_done(msg[2])
                    self._refresh_stats()
                    self._check_all_done()
                elif kind == "error":
                    row.mark_error(msg[2])
                    self._refresh_stats()
                    self._check_all_done()
        except queue.Empty:
            pass

        self.after(100, self._poll_results)

    def _check_all_done(self):
        still_running = any(
            r.status == FileRow.STATUS_CONVERTING for r in self._file_rows
        )
        if not still_running:
            self.convert_btn.configure(state="normal", text="⚡  Convert all")

    # -------------------------------------------------------------------------
    # Misc
    # -------------------------------------------------------------------------

    def _toggle_theme(self):
        current = ctk.get_appearance_mode()
        new_mode = "Dark" if current == "Light" else "Light"
        ctk.set_appearance_mode(new_mode)
        icon = "☀️" if new_mode == "Dark" else "🌙"
        label = "Light" if new_mode == "Dark" else "Dark"
        self.theme_btn.configure(text=f"{icon}  {label}")
