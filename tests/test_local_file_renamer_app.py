import errno
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from local_file_renamer_app import LocalFileRenamerApp
from local_file_renamer_core import RenameRow, load_rename_plan, write_rename_plan


def export_app(folder, recursive=False):
    return SimpleNamespace(
        folder_var=Mock(get=Mock(return_value=str(folder))),
        recursive_var=Mock(get=Mock(return_value=recursive)),
        plan_var=Mock(),
        rows=[RenameRow("previous", "previous.txt")],
        refresh_table=Mock(),
        set_status=Mock(),
        update_idletasks=Mock(),
    )


class FolderExportTests(unittest.TestCase):
    def test_export_buttons_populate_current_names_and_folder_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            (source / "Report 01.txt").write_text("data", encoding="utf-8")
            for extension in (".csv", ".xlsx"):
                with self.subTest(extension=extension):
                    output = root / f"plan{extension}"
                    app = export_app(source)
                    with patch("local_file_renamer_app.filedialog.asksaveasfilename", return_value=str(output)), patch(
                        "local_file_renamer_app.messagebox.showerror"
                    ) as showerror:
                        LocalFileRenamerApp.export_scan(app, extension)
                    showerror.assert_not_called()
                    expected = [RenameRow(str(source), "Report 01.txt")]
                    self.assertEqual(load_rename_plan(str(output)), expected)
                    self.assertEqual(app.rows, expected)
                    app.plan_var.set.assert_called_once_with(str(output))

    def test_subfolder_prompt_can_export_nested_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            nested = source / "nested"
            nested.mkdir(parents=True)
            (nested / "one.txt").write_text("data", encoding="utf-8")
            output = root / "plan.csv"
            app = export_app(source)
            with patch("local_file_renamer_app.messagebox.askyesno", return_value=True) as prompt, patch(
                "local_file_renamer_app.filedialog.asksaveasfilename", return_value=str(output)
            ), patch("local_file_renamer_app.messagebox.showerror") as showerror:
                LocalFileRenamerApp.export_scan(app, ".csv")
            prompt.assert_called_once()
            showerror.assert_not_called()
            app.recursive_var.set.assert_called_once_with(True)
            self.assertEqual(load_rename_plan(str(output)), [RenameRow(str(nested), "one.txt")])

    def test_empty_folder_never_opens_save_dialog(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = export_app(tmp, recursive=True)
            original_rows = app.rows
            with patch("local_file_renamer_app.filedialog.asksaveasfilename") as save, patch(
                "local_file_renamer_app.messagebox.showerror"
            ) as showerror:
                LocalFileRenamerApp.export_scan(app, ".xlsx")
            save.assert_not_called()
            showerror.assert_called_once()
            self.assertIn("No files found", showerror.call_args.args[1])
            self.assertIs(app.rows, original_rows)

    def test_scan_permission_error_never_opens_save_dialog(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = export_app(tmp)
            with patch(
                "local_file_renamer_core.os.scandir",
                side_effect=PermissionError(errno.EACCES, "Access denied"),
            ), patch("local_file_renamer_app.filedialog.asksaveasfilename") as save, patch(
                "local_file_renamer_app.messagebox.showerror"
            ) as showerror:
                LocalFileRenamerApp.export_scan(app, ".csv")
            save.assert_not_called()
            self.assertIn("Permission denied", showerror.call_args.args[1])

    def test_cancel_export_preserves_loaded_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)
            (source / "one.txt").write_text("data", encoding="utf-8")
            app = export_app(source)
            original_rows = app.rows
            with patch("local_file_renamer_app.filedialog.asksaveasfilename", return_value=""):
                LocalFileRenamerApp.export_scan(app, ".csv")
            self.assertIs(app.rows, original_rows)
            app.plan_var.set.assert_not_called()


class CopyModeTests(unittest.TestCase):
    def test_enabling_copy_mode_sets_default_and_exposes_destination(self):
        app = SimpleNamespace(
            copy_mode_var=Mock(get=Mock(return_value=True)),
            output_folder_var=Mock(get=Mock(return_value="")),
            output_controls=Mock(),
            run_button=Mock(),
        )
        output = Path("/example/Downloads/Renamed Files")
        with patch("local_file_renamer_app.default_copy_output_folder", return_value=output):
            LocalFileRenamerApp.update_output_controls(app)
        app.output_folder_var.set.assert_called_once_with(str(output))
        app.output_controls.grid.assert_called_once()
        app.run_button.configure.assert_called_once_with(text="Copy & Rename")

    def test_toggle_preserves_custom_output(self):
        app = SimpleNamespace(
            copy_mode_var=Mock(get=Mock(return_value=False)),
            output_folder_var=Mock(get=Mock(return_value="/custom/output")),
            output_controls=Mock(),
            run_button=Mock(),
        )
        LocalFileRenamerApp.update_output_controls(app)
        app.output_controls.grid_remove.assert_called_once()
        app.copy_mode_var.get.return_value = True
        LocalFileRenamerApp.update_output_controls(app)
        app.output_folder_var.set.assert_not_called()
        app.output_controls.grid.assert_called_once()

    def test_browse_sets_custom_destination(self):
        app = SimpleNamespace(output_folder_var=Mock(get=Mock(return_value="/tmp/new-output")))
        with patch("local_file_renamer_app.filedialog.askdirectory", return_value="/tmp/chosen-output"):
            LocalFileRenamerApp.browse_output_folder(app)
        app.output_folder_var.set.assert_called_once_with("/tmp/chosen-output")

    def test_run_copies_to_selected_output_and_keeps_original_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            (source / "old.txt").write_bytes(b"original")
            for extension in (".csv", ".xlsx"):
                with self.subTest(extension=extension):
                    plan = root / f"plan{extension}"
                    rows = [RenameRow(str(source), "old.txt", "new.txt")]
                    write_rename_plan(str(plan), rows)
                    original_plan = plan.read_bytes()
                    output = root / f"copies-{extension[1:]}"
                    app = SimpleNamespace(
                        rows=rows,
                        copy_mode_var=Mock(get=Mock(return_value=True)),
                        output_folder_var=Mock(get=Mock(return_value=str(output))),
                        allow_overwrite_var=Mock(get=Mock(return_value=False)),
                        plan_var=Mock(get=Mock(return_value=str(plan))),
                        refresh_table=Mock(),
                        set_status=Mock(),
                        update_idletasks=Mock(),
                    )
                    with patch("local_file_renamer_app.messagebox.askyesno", return_value=True) as prompt, patch(
                        "local_file_renamer_app.messagebox.showerror"
                    ) as showerror:
                        LocalFileRenamerApp.run_renames(app)
                    showerror.assert_not_called()
                    self.assertIn(str(output), prompt.call_args.args[1])
                    self.assertEqual((source / "old.txt").read_bytes(), b"original")
                    self.assertEqual((output / "new.txt").read_bytes(), b"original")
                    self.assertEqual(plan.read_bytes(), original_plan)
                    result = load_rename_plan(str(output / f"plan_results{extension}"))
                    self.assertEqual(result[0].current_name, "old.txt")
                    self.assertEqual(result[0].desired_name, "new.txt")
                    self.assertTrue(result[0].status.startswith("Copied:"))
                    self.assertIn("Copied 1 file", app.set_status.call_args.args[0])

    def test_cancel_copy_run_does_not_create_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "copies"
            app = SimpleNamespace(
                rows=[RenameRow(tmp, "old.txt", "new.txt")],
                copy_mode_var=Mock(get=Mock(return_value=True)),
                output_folder_var=Mock(get=Mock(return_value=str(output))),
            )
            with patch("local_file_renamer_app.messagebox.askyesno", return_value=False):
                LocalFileRenamerApp.run_renames(app)
            self.assertFalse(output.exists())

    def test_original_rename_mode_still_renames_in_place(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "old.txt").write_bytes(b"data")
            plan = root / "plan.csv"
            rows = [RenameRow(tmp, "old.txt", "new.txt")]
            write_rename_plan(str(plan), rows)
            app = SimpleNamespace(
                rows=rows,
                copy_mode_var=Mock(get=Mock(return_value=False)),
                allow_overwrite_var=Mock(get=Mock(return_value=False)),
                plan_var=Mock(get=Mock(return_value=str(plan))),
                refresh_table=Mock(),
                set_status=Mock(),
            )
            with patch("local_file_renamer_app.messagebox.askyesno", return_value=True):
                LocalFileRenamerApp.run_renames(app)
            self.assertFalse((root / "old.txt").exists())
            self.assertEqual((root / "new.txt").read_bytes(), b"data")
            self.assertEqual(load_rename_plan(str(plan))[0].current_name, "new.txt")


if __name__ == "__main__":
    unittest.main()
