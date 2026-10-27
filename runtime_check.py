from __future__ import annotations

import json
import platform
import tempfile
import time
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
                    "local_file_renamer_app.messagebox.askyesno", return_value=False
                ), patch(
                    "local_file_renamer_app.messagebox.showerror"
                ) as error:
                    app.export_scan(suffix)
                assert not error.called, error.call_args
                assert load_rename_plan(str(plan)) == [RenameRow(str(source), "original.txt")]
                write_rename_plan(str(plan), [RenameRow(str(source), "original.txt", "renamed.txt")])
                app.plan_var.set(str(plan))
                with patch("local_file_renamer_app.messagebox.showerror") as error:
                    app.load_plan()
                assert not error.called, error.call_args
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
            from neb_artwork import build_artwork_plan, read_profile
            from neb_artwork_ui import NEBArtworkDialog
            import certifi
            import ssl

            ssl.create_default_context(cafile=certifi.where())
            profile = read_profile()
            dialog = NEBArtworkDialog(app, profile=profile, auto_refresh=False)
            dialog.geometry("760x600")
            for type_name in (*profile.types, "Series + Season"):
                dialog.selected_type.set(type_name)
                dialog.show_fields()
                dialog.update_idletasks()
                pending = list(dialog.winfo_children())
                left, top = dialog.winfo_rootx(), dialog.winfo_rooty()
                while pending:
                    widget = pending.pop()
                    pending.extend(widget.winfo_children())
                    if widget.winfo_ismapped():
                        x, y = widget.winfo_rootx() - left, widget.winfo_rooty() - top
                        assert x >= 0 and y >= 0 and x + widget.winfo_width() <= dialog.winfo_width() + 1 and y + widget.winfo_height() <= dialog.winfo_height() + 1, str(widget)
            dialog.destroy()
            art = root / "art"
            art.mkdir()
            for episode in (1, 2):
                for dimensions in ("3840x2160", "1920x1080", "2560x1440"):
                    (art / f"TITLE_s01_e{episode:02d}_eng_bg_16x9_{dimensions}.jpg").write_bytes(content)
            plan = build_artwork_plan(str(art), profile, "Episode", {"title": "When Hope Calls", "language": "English"})
            destination = root / "neb-copies"
            app.accept_neb_plan(plan, str(destination))
            with patch("local_file_renamer_app.fetch_current_profile", return_value=profile), patch(
                "local_file_renamer_app.messagebox.askyesno", return_value=True
            ), patch("local_file_renamer_app.messagebox.showerror") as error:
                app.run_renames()
                deadline = time.monotonic() + 8
                while time.monotonic() < deadline and not (destination / "neb_artwork_results.csv").exists():
                    app.update()
                    time.sleep(0.01)
            assert not error.called, error.call_args
            assert len(list(destination.rglob("*.jpg"))) == 4
            assert len(list(art.glob("*.jpg"))) == 6
            assert (destination / "neb_artwork_results.csv").is_file()
            report["checks"].extend(["neb-profile-conformance", "neb-dialog-all-art-types", "bundled-tls-certificates", "neb-two-episodes-required-only-copy-and-report"])
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
