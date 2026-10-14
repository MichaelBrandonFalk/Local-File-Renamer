from __future__ import annotations

import json
import platform
import tempfile
import traceback
from pathlib import Path
from unittest.mock import patch

from local_file_renamer_core import APP_VERSION, RenameRow, load_rename_plan, write_rename_plan


def run_checks(report_path: Path) -> None:
    from local_file_renamer_app import LocalFileRenamerApp

    report = {"version": APP_VERSION, "platform": platform.platform(), "checks": []}
    app = None
    try:
        app = LocalFileRenamerApp()
        app.update_idletasks()
        for size in ("1020x620", "1120x720"):
            app.geometry(size)
            app.copy_mode_var.set(True)
            app.update_output_controls()
            app.update_idletasks()
            assert app.output_controls.winfo_ismapped()
            assert app.run_button.cget("text") == "Copy & Rename"
            left, top = app.winfo_rootx(), app.winfo_rooty()
            width, height = app.winfo_width(), app.winfo_height()
            pending = list(app.winfo_children())
            while pending:
                widget = pending.pop()
                pending.extend(widget.winfo_children())
                if widget.winfo_ismapped():
                    x, y = widget.winfo_rootx() - left, widget.winfo_rooty() - top
                    assert x >= 0 and y >= 0 and x + widget.winfo_width() <= width + 1 and y + widget.winfo_height() <= height + 1, str(widget)
            report["checks"].append(f"layout-{size}")
        if platform.system() != "Darwin":
            assert hasattr(app, "app_icon")
            report["checks"].append("bundled-icon")

        with tempfile.TemporaryDirectory(prefix="local-file-renamer-check-") as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            content = b"Local File Renamer portable package verification\n"
            (source / "original.txt").write_bytes(content)
            app.folder_var.set(str(source))
            app.recursive_var.set(False)
            for suffix in (".csv", ".xlsx"):
                plan = root / f"plan{suffix}"
                with patch("local_file_renamer_app.filedialog.asksaveasfilename", return_value=str(plan)), patch(
                    "local_file_renamer_app.messagebox.showerror"
                ) as error:
                    app.export_scan(suffix)
                assert not error.called, error.call_args
                assert load_rename_plan(str(plan)) == [RenameRow(str(source), "original.txt")]
                write_rename_plan(str(plan), [RenameRow(str(source), "original.txt", "renamed.txt")])
                app.plan_var.set(str(plan))
                app.load_plan()
                output = root / f"copies-{suffix[1:]}"
                app.output_folder_var.set(str(output))
                app.copy_mode_var.set(True)
                with patch("local_file_renamer_app.messagebox.askyesno", return_value=True), patch(
                    "local_file_renamer_app.messagebox.showerror"
                ) as error:
                    app.run_renames()
                assert not error.called, error.call_args
                assert (output / "renamed.txt").read_bytes() == content
                assert (source / "original.txt").read_bytes() == content
                assert app.rows[0].status.startswith("Copied:")
                assert load_rename_plan(str(plan))[0].desired_name == "renamed.txt"
                assert load_rename_plan(str(output / f"plan_results{suffix}"))[0].status.startswith("Copied:")
                report["checks"].append(f"export-load-copy-results-{suffix[1:]}")
            app.copy_mode_var.set(False)
            app.update_output_controls()
            with patch("local_file_renamer_app.messagebox.askyesno", return_value=True), patch(
                "local_file_renamer_app.messagebox.showerror"
            ) as error:
                app.run_renames()
            assert not error.called, error.call_args
            assert (source / "renamed.txt").read_bytes() == content
            assert not (source / "original.txt").exists()
            report["checks"].append("rename-in-place")
        report["success"] = True
    except Exception:
        report["success"] = False
        report["error"] = traceback.format_exc()
        raise
    finally:
        if app is not None:
            app.destroy()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
