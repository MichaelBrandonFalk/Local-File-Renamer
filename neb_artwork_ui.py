from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from local_file_renamer_core import APP_NAME, default_copy_output_folder
from neb_artwork import COMBINED_TYPE, NEBError, build_artwork_plan, fetch_current_profile, profile_cache_path, read_profile


def background(owner, operation, success, failure):
    results = queue.Queue()
    scheduler = owner.master or owner

    def work():
        try:
            results.put((True, operation()))
        except Exception as exc:
            results.put((False, exc))

    def poll():
        if not owner.winfo_exists():
            return
        try:
            ok, value = results.get_nowait()
        except queue.Empty:
            scheduler.after(100, poll)
            return
        (success if ok else failure)(value)

    threading.Thread(target=work, daemon=True).start()
    scheduler.after(100, poll)


class NEBArtworkDialog(tk.Toplevel):
    def __init__(self, parent, profile=None, auto_refresh=True):
        super().__init__(parent)
        self.parent = parent
        self.title("NEB Artwork")
        self.geometry("840x640")
        self.minsize(760, 600)
        self.transient(parent)
        self.configure(bg="#F6F2FA")
        if profile is None:
            try:
                profile = read_profile(profile_cache_path())
            except NEBError:
                profile = read_profile()
        self.profile = profile
        self.folder = tk.StringVar(value=parent.folder_var.get())
        self.output = tk.StringVar(value=str(default_copy_output_folder()))
        self.selected_type = tk.StringVar(value="Movie")
        self.recursive = tk.BooleanVar(value=True)
        self.required_only = tk.BooleanVar(value=True)
        self.group_output = tk.BooleanVar(value=True)
        self.profile_status = tk.StringVar(value="Bundled or cached NEB Standard; live verification pending")
        self.values = {}
        body = ttk.Frame(self, style="App.TFrame", padding=20)
        body.pack(fill=tk.BOTH, expand=True)
        body.columnconfigure(1, weight=1)
        ttk.Label(body, text="NEB Artwork", style="CardTitle.TLabel", background="#F6F2FA").grid(row=0, column=0, columnspan=3, sticky=tk.W)
        ttk.Label(body, textvariable=self.profile_status, style="Status.TLabel", wraplength=570).grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=(8, 16))
        self.refresh_button = ttk.Button(body, text="Refresh Defaults", command=self.refresh_profile, style="Secondary.TButton")
        self.refresh_button.grid(row=1, column=2, sticky=tk.E, padx=(10, 0))
        ttk.Label(body, text="Source folder", style="Status.TLabel").grid(row=2, column=0, sticky=tk.W, padx=(0, 12))
        ttk.Entry(body, textvariable=self.folder).grid(row=2, column=1, sticky=tk.EW)
        ttk.Button(body, text="Browse", command=lambda: self.browse(self.folder), style="Secondary.TButton").grid(row=2, column=2, padx=(10, 0))
        ttk.Label(body, text="Art type", style="Status.TLabel").grid(row=3, column=0, sticky=tk.W, pady=(12, 0))
        self.type_menu = ttk.Combobox(body, textvariable=self.selected_type, state="readonly")
        self.type_menu.grid(row=3, column=1, sticky=tk.EW, pady=(12, 0))
        self.type_menu.bind("<<ComboboxSelected>>", lambda event: self.show_fields())
        self.fields = ttk.Frame(body, style="App.TFrame")
        self.fields.grid(row=4, column=0, columnspan=3, sticky=tk.EW, pady=(12, 0))
        self.fields.columnconfigure(1, weight=1)
        self.fields.columnconfigure(3, weight=1)
        options = ttk.Frame(body, style="App.TFrame")
        options.grid(row=5, column=0, columnspan=3, sticky=tk.EW, pady=(14, 12))
        ttk.Checkbutton(options, text="Include subfolders", variable=self.recursive).pack(side=tk.LEFT)
        ttk.Checkbutton(options, text="Required art only", variable=self.required_only).pack(side=tk.LEFT, padx=(14, 0))
        ttk.Checkbutton(options, text="Group by type / episode", variable=self.group_output).pack(side=tk.LEFT, padx=(14, 0))
        ttk.Label(body, text="Output folder", style="Status.TLabel").grid(row=6, column=0, sticky=tk.W, padx=(0, 12))
        ttk.Entry(body, textvariable=self.output).grid(row=6, column=1, sticky=tk.EW)
        ttk.Button(body, text="Browse", command=lambda: self.browse(self.output), style="Secondary.TButton").grid(row=6, column=2, padx=(10, 0))
        body.rowconfigure(7, weight=1)
        self.build_button = ttk.Button(body, text="Build Preview", command=self.build_preview, style="Primary.TButton")
        self.build_button.grid(row=8, column=2, sticky=tk.E, pady=(18, 0))
        ttk.Button(body, text="Cancel", command=self.destroy, style="Secondary.TButton").grid(row=8, column=1, sticky=tk.E, padx=(0, 12), pady=(18, 0))
        self.update_profile(profile)
        if auto_refresh:
            parent.after(50, lambda: self.refresh_profile() if self.winfo_exists() else None)

    def browse(self, variable):
        folder = filedialog.askdirectory(parent=self, title="Choose folder", mustexist=False)
        if folder:
            variable.set(folder)

    def update_profile(self, profile):
        self.profile = profile
        names = list(profile.types)
        if "Series" in names and "Season Placeholder" in names:
            names.insert(names.index("Series") + 1, COMBINED_TYPE)
        self.type_menu.configure(values=names)
        if self.selected_type.get() not in names:
            self.selected_type.set(names[0])
        if profile.fetched_at:
            self.profile_status.set(f"NEB Standard | verified {profile.fetched_at} | {profile.revision[:10]}")
        self.show_fields()

    def show_fields(self):
        for widget in self.fields.winfo_children():
            widget.destroy()
        for index, definition in enumerate(self.profile.fields(self.selected_type.get())):
            key = definition["key"]
            initial = "English" if key == "language" else ""
            variable = self.values.setdefault(key, tk.StringVar(value=initial))
            label = "Title override" if key == "title" else "Episode(s)" if key == "episode" else definition["label"]
            row, column = index // 2, (index % 2) * 2
            ttk.Label(self.fields, text=label, style="Status.TLabel").grid(row=row, column=column, sticky=tk.W, padx=(0 if column == 0 else 20, 10), pady=6)
            if definition["type"] == "select":
                control = ttk.Combobox(self.fields, textvariable=variable, state="readonly", values=definition.get("options", []), width=15)
                if not variable.get() and definition.get("options"):
                    variable.set(definition["options"][0])
            else:
                control = ttk.Entry(self.fields, textvariable=variable, width=15)
            control.grid(row=row, column=column + 1, sticky=tk.EW, pady=6)

    def busy(self, value):
        state = tk.DISABLED if value else tk.NORMAL
        self.refresh_button.configure(state=state)
        self.build_button.configure(state=state)

    def failed(self, error):
        self.busy(False)
        self.profile_status.set("Live profile verification failed. No files changed.")
        messagebox.showerror(APP_NAME, str(error), parent=self)

    def refresh_profile(self):
        self.busy(True)
        self.profile_status.set("Checking the current NEB Standard profile...")

        def loaded(profile):
            self.busy(False)
            self.update_profile(profile)

        background(self, fetch_current_profile, loaded, self.failed)

    def build_preview(self):
        folder, output, selected = self.folder.get().strip(), self.output.get().strip(), self.selected_type.get()
        if not folder or not output:
            messagebox.showerror(APP_NAME, "Source and output folders are required.", parent=self)
            return
        values = {key: variable.get().strip() for key, variable in self.values.items()}
        recursive, required, grouped = self.recursive.get(), self.required_only.get(), self.group_output.get()
        self.busy(True)
        self.profile_status.set("Verifying NEB defaults and matching source artwork...")

        def build():
            profile = fetch_current_profile()
            return build_artwork_plan(folder, profile, selected, values, recursive=recursive, required_only=required, group_output=grouped)

        def complete(plan):
            self.parent.accept_neb_plan(plan, output)
            self.destroy()

        background(self, build, complete, self.failed)
