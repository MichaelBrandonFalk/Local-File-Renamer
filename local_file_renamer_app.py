from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from local_file_renamer_core import (
    APP_NAME,
    APP_VERSION,
    EmptyScanError,
    RenameError,
    load_rename_plan,
    rename_rows,
    scan_folder,
    write_rename_plan,
)


PALETTE = {
    "page": "#F6F2FA",
    "panel": "#FFFFFF",
    "panel_soft": "#FBF8FE",
    "ink": "#2B2533",
    "muted": "#6F6578",
    "line": "#DED4E8",
    "accent": "#8B5CF6",
    "accent_dark": "#6D3FD8",
    "accent_soft": "#EEE7FF",
    "grey_button": "#E5E1EA",
    "tree": "#FEFCFF",
    "tree_alt": "#F5F0FA",
}


class LocalFileRenamerApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME} v{APP_VERSION}")
        self.geometry("1120x720")
        self.minsize(1020, 620)
        self.configure(bg=PALETTE["page"])

        self.folder_var = tk.StringVar()
        self.plan_var = tk.StringVar()
        self.recursive_var = tk.BooleanVar(value=False)
        self.allow_overwrite_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Ready")
        self.rows = []

        self._configure_styles()
        self._build_ui()

    def _configure_styles(self) -> None:
        self.style = ttk.Style(self)
        self.style.theme_use("clam")
        self.style.configure(".", background=PALETTE["page"], foreground=PALETTE["ink"], font=("Helvetica Neue", 12))
        self.style.configure("App.TFrame", background=PALETTE["page"])
        self.style.configure("Header.TFrame", background=PALETTE["page"])
        self.style.configure("Card.TFrame", background=PALETTE["panel"], relief="solid", borderwidth=1)
        self.style.configure("Soft.TFrame", background=PALETTE["panel_soft"])
        self.style.configure("Title.TLabel", background=PALETTE["page"], foreground=PALETTE["ink"], font=("Helvetica Neue", 28, "bold"))
        self.style.configure("Subtitle.TLabel", background=PALETTE["page"], foreground=PALETTE["muted"], font=("Helvetica Neue", 12))
        self.style.configure("CardTitle.TLabel", background=PALETTE["panel"], foreground=PALETTE["ink"], font=("Helvetica Neue", 14, "bold"))
        self.style.configure("Body.TLabel", background=PALETTE["panel"], foreground=PALETTE["muted"], font=("Helvetica Neue", 11))
        self.style.configure("Field.TLabel", background=PALETTE["panel"], foreground=PALETTE["ink"], font=("Helvetica Neue", 11, "bold"))
        self.style.configure("Status.TLabel", background=PALETTE["page"], foreground=PALETTE["muted"], font=("Helvetica Neue", 11))
        self.style.configure("Version.TLabel", background=PALETTE["accent_soft"], foreground=PALETTE["accent_dark"], font=("Helvetica Neue", 11, "bold"))
        self.style.configure("TEntry", fieldbackground="#FFFFFF", foreground=PALETTE["ink"], bordercolor=PALETTE["line"], lightcolor=PALETTE["line"], darkcolor=PALETTE["line"], padding=8)
        self.style.configure("TCheckbutton", background=PALETTE["panel"], foreground=PALETTE["ink"], font=("Helvetica Neue", 11))
        self.style.map("TCheckbutton", background=[("active", PALETTE["panel"])])
        self.style.configure("Primary.TButton", background=PALETTE["accent"], foreground="#FFFFFF", bordercolor=PALETTE["accent"], lightcolor=PALETTE["accent"], darkcolor=PALETTE["accent"], padding=(16, 9), font=("Helvetica Neue", 11, "bold"))
        self.style.map("Primary.TButton", background=[("active", PALETTE["accent_dark"]), ("pressed", PALETTE["accent_dark"])], foreground=[("active", "#FFFFFF")])
        self.style.configure("Secondary.TButton", background=PALETTE["grey_button"], foreground=PALETTE["ink"], bordercolor=PALETTE["line"], lightcolor=PALETTE["line"], darkcolor=PALETTE["line"], padding=(14, 8), font=("Helvetica Neue", 11, "bold"))
        self.style.map("Secondary.TButton", background=[("active", "#D9D2E4"), ("pressed", "#D0C7DD")])
        self.style.configure("Danger.TButton", background="#EEE8F4", foreground=PALETTE["muted"], bordercolor=PALETTE["line"], lightcolor=PALETTE["line"], darkcolor=PALETTE["line"], padding=(14, 8), font=("Helvetica Neue", 11, "bold"))
        self.style.configure("Treeview", background=PALETTE["tree"], fieldbackground=PALETTE["tree"], foreground=PALETTE["ink"], bordercolor=PALETTE["line"], rowheight=30, font=("Helvetica Neue", 11))
        self.style.configure("Treeview.Heading", background=PALETTE["accent_soft"], foreground=PALETTE["ink"], relief="flat", font=("Helvetica Neue", 11, "bold"))
        self.style.map("Treeview.Heading", background=[("active", "#E4DAFA")])
        self.style.map("Treeview", background=[("selected", "#DCCBFF")], foreground=[("selected", PALETTE["ink"])])
        self.style.configure("Vertical.TScrollbar", background=PALETTE["grey_button"], troughcolor=PALETTE["panel_soft"], bordercolor=PALETTE["line"], arrowcolor=PALETTE["muted"])
        self.style.configure("Horizontal.TScrollbar", background=PALETTE["grey_button"], troughcolor=PALETTE["panel_soft"], bordercolor=PALETTE["line"], arrowcolor=PALETTE["muted"])

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=(22, 18), style="App.TFrame")
        root.pack(fill=tk.BOTH, expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=1)

        header = ttk.Frame(root, style="Header.TFrame")
        header.grid(row=0, column=0, sticky=tk.EW)
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="Local File Renamer", style="Title.TLabel").grid(row=0, column=0, sticky=tk.W)
        ttk.Label(header, text=f"v{APP_VERSION}", style="Version.TLabel", padding=(12, 5)).grid(row=0, column=1, sticky=tk.E)
        ttk.Label(
            header,
            text="Scan folders, export a rename plan, load the edited CSV or spreadsheet, then run the rename.",
            style="Subtitle.TLabel",
        ).grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=(2, 0))

        controls = ttk.Frame(root, style="App.TFrame")
        controls.grid(row=1, column=0, sticky=tk.EW, pady=(18, 14))
        controls.columnconfigure(0, weight=1)
        controls.columnconfigure(1, weight=1)

        folder_card = self._card(controls)
        folder_card.grid(row=0, column=0, sticky=tk.NSEW, padx=(0, 8))
        folder_card.columnconfigure(1, weight=1)
        ttk.Label(folder_card, text="Folder Export", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=3, sticky=tk.W, pady=(0, 12))
        ttk.Label(folder_card, text="Folder location", style="Field.TLabel").grid(row=1, column=0, sticky=tk.W, padx=(0, 10))
        ttk.Entry(folder_card, textvariable=self.folder_var).grid(row=1, column=1, sticky=tk.EW)
        ttk.Button(folder_card, text="Browse", style="Secondary.TButton", command=self.browse_folder).grid(row=1, column=2, padx=(10, 0))
        ttk.Checkbutton(folder_card, text="Include subfolders", variable=self.recursive_var).grid(row=2, column=1, sticky=tk.W, pady=(14, 0))
        export_buttons = ttk.Frame(folder_card, style="Card.TFrame")
        export_buttons.grid(row=3, column=0, columnspan=3, sticky=tk.E, pady=(16, 0))
        ttk.Button(export_buttons, text="Export CSV", style="Secondary.TButton", command=lambda: self.export_scan(".csv")).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(export_buttons, text="Export Spreadsheet", style="Primary.TButton", command=lambda: self.export_scan(".xlsx")).pack(side=tk.LEFT)

        plan_card = self._card(controls)
        plan_card.grid(row=0, column=1, sticky=tk.NSEW, padx=(8, 0))
        plan_card.columnconfigure(1, weight=1)
        ttk.Label(plan_card, text="Rename Plan", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=3, sticky=tk.W, pady=(0, 12))
        ttk.Label(plan_card, text="Plan location", style="Field.TLabel").grid(row=1, column=0, sticky=tk.W, padx=(0, 10))
        ttk.Entry(plan_card, textvariable=self.plan_var).grid(row=1, column=1, sticky=tk.EW)
        ttk.Button(plan_card, text="Browse Plan", style="Secondary.TButton", command=self.browse_plan).grid(row=1, column=2, padx=(10, 0))
        ttk.Label(plan_card, text="CSV and .xlsx files use the same four columns.", style="Body.TLabel").grid(
            row=2, column=1, sticky=tk.W, pady=(12, 0)
        )
        ttk.Button(plan_card, text="Load Plan", style="Primary.TButton", command=self.load_plan).grid(row=3, column=2, sticky=tk.E, pady=(16, 0))

        table_frame = ttk.Frame(root)
        table_frame.grid(row=2, column=0, sticky=tk.NSEW)
        table_frame.configure(style="App.TFrame")
        table_frame.rowconfigure(1, weight=1)
        table_frame.columnconfigure(0, weight=1)
        ttk.Label(table_frame, text="Plan Preview", style="CardTitle.TLabel", background=PALETTE["page"]).grid(row=0, column=0, sticky=tk.W, pady=(0, 8))

        columns = ("folder_location", "current_name", "desired_name", "status")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="extended")
        self.tree.heading("folder_location", text="Folder Location")
        self.tree.heading("current_name", text="Current Name")
        self.tree.heading("desired_name", text="Desired Name")
        self.tree.heading("status", text="Status")
        self.tree.column("folder_location", width=390, minwidth=220)
        self.tree.column("current_name", width=220, minwidth=120)
        self.tree.column("desired_name", width=220, minwidth=120)
        self.tree.column("status", width=240, minwidth=160)
        self.tree.grid(row=1, column=0, sticky=tk.NSEW)

        y_scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        x_scroll = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        y_scroll.grid(row=1, column=1, sticky=tk.NS)
        x_scroll.grid(row=2, column=0, sticky=tk.EW)

        action_frame = ttk.Frame(root, style="App.TFrame")
        action_frame.grid(row=3, column=0, sticky=tk.EW, pady=(14, 0))
        ttk.Checkbutton(action_frame, text="Allow overwrite existing files", variable=self.allow_overwrite_var).pack(
            side=tk.LEFT
        )
        ttk.Button(action_frame, text="Remove Selected Rows", style="Danger.TButton", command=self.remove_selected_rows).pack(
            side=tk.LEFT, padx=(12, 0)
        )
        ttk.Button(action_frame, text="Run Renames", style="Primary.TButton", command=self.run_renames).pack(side=tk.RIGHT)

        status_bar = ttk.Label(root, textvariable=self.status_var, anchor=tk.W, style="Status.TLabel")
        status_bar.grid(row=4, column=0, sticky=tk.EW, pady=(10, 0))

    def _card(self, parent: ttk.Widget) -> ttk.Frame:
        card = ttk.Frame(parent, padding=16, style="Card.TFrame")
        return card

    def browse_folder(self) -> None:
        folder = filedialog.askdirectory(title="Choose folder")
        if folder:
            self.folder_var.set(folder)

    def browse_plan(self) -> None:
        plan_path = filedialog.askopenfilename(
            title="Open rename plan",
            filetypes=[("Rename plans", "*.csv *.xlsx"), ("CSV files", "*.csv"), ("Excel spreadsheets", "*.xlsx"), ("All files", "*.*")],
        )
        if plan_path:
            self.plan_var.set(plan_path)

    def export_scan(self, extension: str) -> None:
        folder = self.folder_var.get().strip()
        if not folder:
            self.browse_folder()
            folder = self.folder_var.get().strip()
        if not folder:
            return

        try:
            self.set_status(f"Scanning {folder}...")
            self.update_idletasks()
            recursive = self.recursive_var.get()
            rows = scan_folder(folder, recursive=recursive)
            if not rows and not recursive:
                include_subfolders = messagebox.askyesno(
                    APP_NAME,
                    f"No files were found directly in:\n{folder}\n\nScan its subfolders too?",
                )
                if include_subfolders:
                    recursive = True
                    self.recursive_var.set(True)
                    rows = scan_folder(folder, recursive=True)
            if not rows:
                raise EmptyScanError(folder, recursive)
            self.set_status(f"Found {len(rows)} file(s) in {folder}.")
        except Exception as exc:
            self.set_status("Scan failed. No export was saved.")
            messagebox.showerror(APP_NAME, str(exc))
            return

        if extension == ".xlsx":
            default_name = "local_file_rename_plan.xlsx"
            title = "Save spreadsheet rename plan"
            filetypes = [("Excel spreadsheets", "*.xlsx"), ("All files", "*.*")]
        else:
            default_name = "local_file_rename_plan.csv"
            title = "Save CSV rename plan"
            filetypes = [("CSV files", "*.csv"), ("All files", "*.*")]

        plan_path = filedialog.asksaveasfilename(
            title=title,
            initialfile=default_name,
            defaultextension=extension,
            filetypes=filetypes,
        )
        if not plan_path:
            self.set_status(f"Found {len(rows)} file(s). Export canceled.")
            return

        try:
            write_rename_plan(plan_path, rows)
            self.rows = rows
            self.plan_var.set(plan_path)
            self.refresh_table()
            self.set_status(f"Scanned {len(self.rows)} file(s) and wrote {Path(plan_path).name}.")
        except Exception as exc:
            self.set_status("Export failed.")
            messagebox.showerror(APP_NAME, str(exc))

    def load_plan(self) -> None:
        plan_path = self.plan_var.get().strip()
        if not plan_path:
            self.browse_plan()
            plan_path = self.plan_var.get().strip()
        if not plan_path:
            return

        try:
            self.rows = load_rename_plan(plan_path)
            self.refresh_table()
            self.set_status(f"Loaded {len(self.rows)} row(s) from {Path(plan_path).name}.")
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc))

    def remove_selected_rows(self) -> None:
        selected = set(self.tree.selection())
        if not selected:
            return

        kept_rows: list[RenameRow] = []
        for index, item_id in enumerate(self.tree.get_children()):
            if item_id not in selected:
                kept_rows.append(self.rows[index])

        self.rows = kept_rows
        self.refresh_table()
        self.set_status(f"Removed {len(selected)} row(s).")

    def run_renames(self) -> None:
        if not self.rows:
            messagebox.showerror(APP_NAME, "Load a CSV or spreadsheet rename plan first.")
            return

        runnable = [row for row in self.rows if row.desired_name.strip()]
        if not runnable:
            messagebox.showerror(APP_NAME, "No rows have a desired_name to rename to.")
            return

        confirmed = messagebox.askyesno(
            APP_NAME,
            f"Rename {len(runnable)} file(s) on this computer now?",
        )
        if not confirmed:
            return

        try:
            self.rows = rename_rows(self.rows, allow_overwrite=self.allow_overwrite_var.get())
            plan_path = self.plan_var.get().strip()
            if plan_path:
                write_rename_plan(plan_path, self.rows)
            self.refresh_table()
            renamed_count = sum(1 for row in self.rows if row.status.startswith("Renamed"))
            self.set_status(f"Finished. Renamed {renamed_count} file(s).")
        except RenameError as exc:
            messagebox.showerror(APP_NAME, str(exc))
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Unexpected error: {exc}")

    def refresh_table(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for row in self.rows:
            self.tree.insert(
                "",
                tk.END,
                values=(row.folder_location, row.current_name, row.desired_name, row.status),
            )

    def set_status(self, message: str) -> None:
        self.status_var.set(message)


def main() -> None:
    app = LocalFileRenamerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
