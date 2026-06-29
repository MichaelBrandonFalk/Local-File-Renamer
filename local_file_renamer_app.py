from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from local_file_renamer_core import (
    APP_NAME,
    APP_VERSION,
    RenameError,
    RenameRow,
    load_rename_csv,
    rename_rows,
    write_rename_csv,
    write_scan_csv,
)


class LocalFileRenamerApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME} v{APP_VERSION}")
        self.geometry("1100x680")
        self.minsize(980, 560)

        self.folder_var = tk.StringVar()
        self.csv_var = tk.StringVar()
        self.current_name_var = tk.StringVar()
        self.desired_name_var = tk.StringVar()
        self.recursive_var = tk.BooleanVar(value=False)
        self.allow_overwrite_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Ready")
        self.rows: list[RenameRow] = []

        self._build_ui()

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=14)
        root.pack(fill=tk.BOTH, expand=True)

        folder_frame = ttk.LabelFrame(root, text="Folder")
        folder_frame.pack(fill=tk.X)
        folder_frame.columnconfigure(1, weight=1)

        ttk.Label(folder_frame, text="Folder location").grid(row=0, column=0, padx=8, pady=8, sticky=tk.W)
        ttk.Entry(folder_frame, textvariable=self.folder_var).grid(row=0, column=1, padx=8, pady=8, sticky=tk.EW)
        ttk.Button(folder_frame, text="Browse", command=self.browse_folder).grid(row=0, column=2, padx=8, pady=8)

        ttk.Checkbutton(folder_frame, text="Include subfolders when scanning", variable=self.recursive_var).grid(
            row=1, column=1, padx=8, pady=(0, 8), sticky=tk.W
        )
        ttk.Button(folder_frame, text="Scan Folder + Write CSV", command=self.scan_folder_to_csv).grid(
            row=1, column=2, padx=8, pady=(0, 8), sticky=tk.E
        )

        csv_frame = ttk.LabelFrame(root, text="CSV Rename Plan")
        csv_frame.pack(fill=tk.X, pady=(12, 0))
        csv_frame.columnconfigure(1, weight=1)

        ttk.Label(csv_frame, text="CSV location").grid(row=0, column=0, padx=8, pady=8, sticky=tk.W)
        ttk.Entry(csv_frame, textvariable=self.csv_var).grid(row=0, column=1, padx=8, pady=8, sticky=tk.EW)
        ttk.Button(csv_frame, text="Load CSV", command=self.load_csv).grid(row=0, column=2, padx=8, pady=8)

        manual_frame = ttk.LabelFrame(root, text="Single Rename Row")
        manual_frame.pack(fill=tk.X, pady=(12, 0))
        manual_frame.columnconfigure(1, weight=1)
        manual_frame.columnconfigure(3, weight=1)

        ttk.Label(manual_frame, text="Current name").grid(row=0, column=0, padx=8, pady=8, sticky=tk.W)
        ttk.Entry(manual_frame, textvariable=self.current_name_var).grid(row=0, column=1, padx=8, pady=8, sticky=tk.EW)
        ttk.Label(manual_frame, text="Desired name").grid(row=0, column=2, padx=8, pady=8, sticky=tk.W)
        ttk.Entry(manual_frame, textvariable=self.desired_name_var).grid(row=0, column=3, padx=8, pady=8, sticky=tk.EW)
        ttk.Button(manual_frame, text="Add Row", command=self.add_manual_row).grid(row=0, column=4, padx=8, pady=8)

        table_frame = ttk.Frame(root)
        table_frame.pack(fill=tk.BOTH, expand=True, pady=(12, 0))
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

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
        self.tree.grid(row=0, column=0, sticky=tk.NSEW)

        y_scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        x_scroll = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        y_scroll.grid(row=0, column=1, sticky=tk.NS)
        x_scroll.grid(row=1, column=0, sticky=tk.EW)

        action_frame = ttk.Frame(root)
        action_frame.pack(fill=tk.X, pady=(12, 0))
        ttk.Checkbutton(action_frame, text="Allow overwrite existing files", variable=self.allow_overwrite_var).pack(
            side=tk.LEFT
        )
        ttk.Button(action_frame, text="Remove Selected Rows", command=self.remove_selected_rows).pack(
            side=tk.LEFT, padx=(12, 0)
        )
        ttk.Button(action_frame, text="Run Renames", command=self.run_renames).pack(side=tk.RIGHT)

        status_bar = ttk.Label(root, textvariable=self.status_var, anchor=tk.W)
        status_bar.pack(fill=tk.X, pady=(10, 0))

    def browse_folder(self) -> None:
        folder = filedialog.askdirectory(title="Choose folder")
        if folder:
            self.folder_var.set(folder)

    def scan_folder_to_csv(self) -> None:
        folder = self.folder_var.get().strip()
        if not folder:
            self.browse_folder()
            folder = self.folder_var.get().strip()
        if not folder:
            return

        default_name = "local_file_rename_plan.csv"
        csv_path = filedialog.asksaveasfilename(
            title="Save rename CSV",
            initialfile=default_name,
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not csv_path:
            return

        try:
            self.rows = write_scan_csv(folder, csv_path, recursive=self.recursive_var.get())
            self.csv_var.set(csv_path)
            self.refresh_table()
            self.set_status(f"Scanned {len(self.rows)} file(s) and wrote {Path(csv_path).name}.")
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc))

    def load_csv(self) -> None:
        csv_path = self.csv_var.get().strip()
        if not csv_path:
            csv_path = filedialog.askopenfilename(
                title="Open rename CSV",
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            )
            if csv_path:
                self.csv_var.set(csv_path)
        if not csv_path:
            return

        try:
            self.rows = load_rename_csv(csv_path)
            self.refresh_table()
            self.set_status(f"Loaded {len(self.rows)} row(s) from {Path(csv_path).name}.")
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc))

    def add_manual_row(self) -> None:
        folder = self.folder_var.get().strip()
        current = self.current_name_var.get().strip()
        desired = self.desired_name_var.get().strip()

        if not folder or not current or not desired:
            messagebox.showerror(APP_NAME, "Folder location, current name, and desired name are required.")
            return

        self.rows.append(RenameRow(folder_location=folder, current_name=current, desired_name=desired))
        self.current_name_var.set("")
        self.desired_name_var.set("")
        self.refresh_table()
        self.set_status("Added 1 rename row.")

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
            try:
                self.add_manual_row()
            except tk.TclError:
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
            csv_path = self.csv_var.get().strip()
            if csv_path:
                write_rename_csv(csv_path, self.rows)
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
