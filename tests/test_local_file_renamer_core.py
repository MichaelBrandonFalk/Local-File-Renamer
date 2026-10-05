import csv
import errno
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from local_file_renamer_core import (
    EmptyScanError,
    RenameError,
    RenameRow,
    load_rename_csv,
    load_rename_plan,
    rename_rows,
    scan_folder,
    write_scan_csv,
    write_scan_plan,
    write_rename_plan,
)


class LocalFileRenamerCoreTests(unittest.TestCase):
    def test_scan_folder_lists_files_without_subfolders_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "one.txt").write_text("1", encoding="utf-8")
            (root / "nested").mkdir()
            (root / "nested" / "two.txt").write_text("2", encoding="utf-8")

            rows = scan_folder(str(root))

            self.assertEqual([row.current_name for row in rows], ["one.txt"])

    def test_scan_folder_can_include_subfolders(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "one.txt").write_text("1", encoding="utf-8")
            (root / "nested").mkdir()
            (root / "nested" / "two.txt").write_text("2", encoding="utf-8")

            rows = scan_folder(str(root), recursive=True)

            self.assertEqual([row.current_name for row in rows], ["two.txt", "one.txt"])

    def test_write_scan_csv_uses_required_headers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "one.txt").write_text("1", encoding="utf-8")
            csv_path = root / "plan.csv"

            write_scan_csv(str(root), str(csv_path))

            with csv_path.open("r", newline="", encoding="utf-8") as handle:
                reader = csv.reader(handle)
                self.assertEqual(next(reader), ["folder_location", "current_name", "desired_name", "status"])

            rows = load_rename_csv(str(csv_path))
            self.assertEqual(rows[0].current_name, "one.txt")

    def test_write_scan_xlsx_round_trips_required_headers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "one.txt").write_text("1", encoding="utf-8")
            xlsx_path = root / "plan.xlsx"

            write_scan_plan(str(root), str(xlsx_path))
            rows = load_rename_plan(str(xlsx_path))

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].folder_location, str(root))
            self.assertEqual(rows[0].current_name, "one.txt")
            self.assertEqual(rows[0].desired_name, "")

    def test_write_rename_xlsx_preserves_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xlsx_path = root / "plan.xlsx"
            rows = [RenameRow(str(root), "old.txt", "new.txt", "Ready")]

            write_rename_plan(str(xlsx_path), rows)
            loaded = load_rename_plan(str(xlsx_path))

            self.assertEqual(loaded[0].status, "Ready")

    def test_empty_scan_does_not_create_or_overwrite_exports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "empty"
            source.mkdir()
            for writer, extension in (
                (write_scan_csv, ".csv"),
                (write_scan_plan, ".csv"),
                (write_scan_plan, ".xlsx"),
            ):
                with self.subTest(writer=writer.__name__, extension=extension):
                    output = root / f"plan{extension}"
                    if output.exists():
                        output.unlink()
                    with self.assertRaises(EmptyScanError):
                        writer(str(source), str(output))
                    self.assertFalse(output.exists())
                    output.write_bytes(b"Existing plan")
                    with self.assertRaises(EmptyScanError):
                        writer(str(source), str(output))
                    self.assertEqual(output.read_bytes(), b"Existing plan")

    def test_subfolder_only_exports_populate_both_formats(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            nested = source / "nested" / "deeper"
            nested.mkdir(parents=True)
            name = "Report, final 01.txt"
            (nested / name).write_text("data", encoding="utf-8")
            for extension in (".csv", ".xlsx"):
                with self.subTest(extension=extension):
                    output = root / f"plan{extension}"
                    write_scan_plan(str(source), str(output), recursive=True)
                    self.assertEqual(
                        load_rename_plan(str(output)),
                        [RenameRow(str(nested), name)],
                    )

    def test_scan_reports_unreadable_file_instead_of_skipping_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            entry = MagicMock()
            entry.path = str(Path(tmp) / "blocked.txt")
            entry.stat.side_effect = PermissionError(errno.EACCES, "Access denied")
            entries = MagicMock()
            entries.__enter__.return_value = iter([entry])
            with patch("local_file_renamer_core.os.scandir", return_value=entries):
                with self.assertRaisesRegex(RenameError, "Permission denied.*") as error:
                    scan_folder(tmp)
            self.assertIn("blocked.txt", str(error.exception))

    def test_recursive_scan_reports_unreadable_subfolder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested = root / "blocked"
            nested.mkdir()
            (root / "one.txt").write_text("data", encoding="utf-8")
            original_scandir = os.scandir

            def deny_subfolder(path):
                if Path(path) == nested:
                    raise PermissionError(errno.EPERM, "Access denied")
                return original_scandir(path)

            with patch("local_file_renamer_core.os.scandir", side_effect=deny_subfolder):
                with self.assertRaisesRegex(RenameError, "Permission denied"):
                    write_scan_plan(str(root), str(root / "plan.csv"), recursive=True)
            self.assertFalse((root / "plan.csv").exists())

    def test_recursive_scan_does_not_follow_directory_symlink_loops(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "one.txt").write_text("data", encoding="utf-8")
            (root / "loop").symlink_to(root, target_is_directory=True)
            self.assertEqual(scan_folder(str(root), recursive=True), [RenameRow(str(root), "one.txt")])

    def test_rename_rows_renames_file_and_updates_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "old.txt").write_text("data", encoding="utf-8")
            rows = [RenameRow(str(root), "old.txt", "new.txt")]

            results = rename_rows(rows)

            self.assertFalse((root / "old.txt").exists())
            self.assertTrue((root / "new.txt").exists())
            self.assertEqual(results[0].current_name, "new.txt")
            self.assertEqual(results[0].desired_name, "")
            self.assertTrue(results[0].status.startswith("Renamed"))

    def test_rename_rows_does_not_overwrite_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "old.txt").write_text("old", encoding="utf-8")
            (root / "new.txt").write_text("new", encoding="utf-8")
            rows = [RenameRow(str(root), "old.txt", "new.txt")]

            results = rename_rows(rows)

            self.assertEqual((root / "old.txt").read_text(encoding="utf-8"), "old")
            self.assertEqual((root / "new.txt").read_text(encoding="utf-8"), "new")
            self.assertEqual(results[0].status, "Skipped: desired_name already exists")


if __name__ == "__main__":
    unittest.main()
