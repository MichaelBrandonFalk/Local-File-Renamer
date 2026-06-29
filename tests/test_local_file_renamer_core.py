import csv
import tempfile
import unittest
from pathlib import Path

from local_file_renamer_core import (
    RenameRow,
    load_rename_csv,
    rename_rows,
    scan_folder,
    write_scan_csv,
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
