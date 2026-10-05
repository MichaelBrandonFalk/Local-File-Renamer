import errno
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from local_file_renamer_app import LocalFileRenamerApp
from local_file_renamer_core import RenameRow, load_rename_plan


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


if __name__ == "__main__":
    unittest.main()
