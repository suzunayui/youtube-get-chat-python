"""Simple GUI launcher for youtube_chat.py (double-clickable .pyw)."""
from __future__ import annotations

import threading
import tkinter as tk
from tkinter import filedialog, messagebox

import youtube_chat


class LiveChatApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("YouTube Live Chat Fetcher")
        self.geometry("420x220")

        self.worker: threading.Thread | None = None

        tk.Label(self, text="VideoID / ChannelID / @handle").pack(anchor="w", padx=12, pady=(12, 4))
        self.input_var = tk.StringVar()
        tk.Entry(self, textvariable=self.input_var).pack(fill="x", padx=12)

        tk.Label(self, text="Store directory (optional)").pack(anchor="w", padx=12, pady=(10, 4))
        dir_frame = tk.Frame(self)
        dir_frame.pack(fill="x", padx=12)
        self.dir_var = tk.StringVar()
        tk.Entry(dir_frame, textvariable=self.dir_var).pack(side="left", fill="x", expand=True)
        tk.Button(dir_frame, text="Browse", command=self._choose_dir).pack(side="left", padx=(6, 0))

        btn_frame = tk.Frame(self)
        btn_frame.pack(fill="x", padx=12, pady=14)
        tk.Button(btn_frame, text="Start", command=self._start_fetch).pack(side="left")
        tk.Button(btn_frame, text="Stop", command=self._stop_fetch).pack(side="left", padx=8)

        self.print_var = tk.BooleanVar(value=True)
        tk.Checkbutton(self, text="Print comments to console", variable=self.print_var).pack(
            anchor="w", padx=12
        )

        self.status_var = tk.StringVar(value="Stopped")
        tk.Label(self, textvariable=self.status_var, fg="blue").pack(anchor="w", padx=12)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _choose_dir(self) -> None:
        path = filedialog.askdirectory()
        if path:
            self.dir_var.set(path)

    def _start_fetch(self) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("Info", "Already running.")
            return
        input_str = self.input_var.get().strip()
        if not input_str:
            messagebox.showwarning("Input needed", "Enter videoId, channelId, or @handle.")
            return

        store_dir = self.dir_var.get().strip() or None
        print_console = self.print_var.get()
        self.status_var.set("Starting...")

        def run() -> None:
            try:
                youtube_chat.start_live_chat(
                    input_str, store_dir=store_dir, print_console=print_console
                )
            except Exception as exc:  # pylint: disable=broad-except
                self.after(0, lambda: messagebox.showerror("Error", str(exc)))
            finally:
                self.after(0, lambda: self.status_var.set("Stopped"))

        self.worker = threading.Thread(target=run, daemon=True)
        self.worker.start()
        self.status_var.set("Running")

    def _stop_fetch(self) -> None:
        youtube_chat.stop_live_chat()
        self.status_var.set("Stopping...")

    def _on_close(self) -> None:
        youtube_chat.stop_live_chat()
        self.destroy()


if __name__ == "__main__":
    app = LiveChatApp()
    app.mainloop()
