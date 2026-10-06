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
    copy_rows,
    default_copy_output_folder,
    load_rename_csv,
    load_rename_plan,
    rename_rows,
    scan_folder,
    write_scan_csv,
    write_scan_plan,
    write_copy_results,
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

    def test_copy_rows_creates_destination_and_preserves_originals(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            original = source / "old.txt"
            original.write_bytes(b"original content")
            os.utime(original, (1000000000, 1000000000))
            output = root / "new" / "output"
            row = RenameRow(str(source), "old.txt", "new.txt")

            results = copy_rows([row], str(output))

            self.assertEqual(original.read_bytes(), b"original content")
            self.assertFalse((source / "new.txt").exists())
            self.assertEqual((output / "new.txt").read_bytes(), b"original content")
            self.assertEqual((output / "new.txt").stat().st_mtime, original.stat().st_mtime)
            self.assertEqual(results[0].folder_location, str(source))
            self.assertEqual(results[0].current_name, "old.txt")
            self.assertEqual(results[0].desired_name, "new.txt")
            self.assertTrue(results[0].status.startswith("Copied:"))
            self.assertIn(str(output / "new.txt"), results[0].status)
            self.assertEqual(row.status, "")

    def test_copy_accepts_unchanged_name_in_different_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "one.txt").write_bytes(b"data")
            output = root / "copies"
            result = copy_rows([RenameRow(str(root), "one.txt", "one.txt")], str(output))
            self.assertTrue(result[0].status.startswith("Copied:"))
            self.assertEqual((root / "one.txt").read_bytes(), (output / "one.txt").read_bytes())

    def test_copy_skips_blank_missing_and_invalid_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "one.txt").write_text("data", encoding="utf-8")
            output = root / "copies"
            rows = [
                RenameRow(str(root), "one.txt"),
                RenameRow(str(root), "missing.txt", "missing-copy.txt"),
                RenameRow(str(root), "one.txt", "../outside.txt"),
            ]
            results = copy_rows(rows, str(output))
            self.assertEqual(results[0].status, "Skipped: desired_name is blank")
            self.assertEqual(results[1].status, "Not found")
            self.assertTrue(results[2].status.startswith("Error:"))
            self.assertEqual(list(output.iterdir()), [])
            self.assertFalse((root / "outside.txt").exists())

    def test_copy_does_not_create_output_for_blank_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "copies"
            copy_rows([RenameRow(tmp, "one.txt")], str(output))
            self.assertFalse(output.exists())

    def test_copy_skips_existing_destinations_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "one.txt").write_bytes(b"original")
            output = root / "copies"
            output.mkdir()
            (output / "new.txt").write_bytes(b"existing")
            results = copy_rows([RenameRow(tmp, "one.txt", "new.txt")], str(output))
            self.assertTrue(results[0].status.startswith("Skipped:"))
            self.assertEqual((output / "new.txt").read_bytes(), b"existing")
            self.assertEqual((root / "one.txt").read_bytes(), b"original")

    def test_copy_overwrites_only_destination_when_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "one.txt").write_bytes(b"original")
            output = root / "copies"
            output.mkdir()
            (output / "new.txt").write_bytes(b"existing")
            results = copy_rows([RenameRow(tmp, "one.txt", "new.txt")], str(output), allow_overwrite=True)
            self.assertTrue(results[0].status.startswith("Copied:"))
            self.assertEqual((output / "new.txt").read_bytes(), b"original")
            self.assertEqual((root / "one.txt").read_bytes(), b"original")

    def test_failed_overwrite_preserves_existing_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "one.txt").write_bytes(b"original")
            output = root / "copies"
            output.mkdir()
            target = output / "new.txt"
            target.write_bytes(b"existing")
            with patch("local_file_renamer_core.shutil.copy2", side_effect=OSError("Disk full")):
                results = copy_rows([RenameRow(tmp, "one.txt", "new.txt")], str(output), allow_overwrite=True)
            self.assertIn("Disk full", results[0].status)
            self.assertEqual(target.read_bytes(), b"existing")
            self.assertEqual(list(output.iterdir()), [target])

    def test_failed_copy_removes_partial_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "one.txt").write_bytes(b"original")
            output = root / "copies"
            with patch("local_file_renamer_core.shutil.copyfileobj", side_effect=OSError("Disk full")):
                results = copy_rows([RenameRow(tmp, "one.txt", "new.txt")], str(output))
            self.assertIn("Disk full", results[0].status)
            self.assertFalse((output / "new.txt").exists())
            self.assertEqual((root / "one.txt").read_bytes(), b"original")

    def test_copy_rejects_source_folder_and_symlink_alias(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            (source / "one.txt").write_bytes(b"original")
            alias = root / "alias"
            alias.symlink_to(source, target_is_directory=True)
            for output in (source, alias):
                with self.subTest(output=output):
                    with self.assertRaisesRegex(RenameError, "different from the source"):
                        copy_rows([RenameRow(str(source), "one.txt", "new.txt")], str(output), True)
                    self.assertFalse((source / "new.txt").exists())

    def test_copy_overwrite_replaces_link_without_changing_other_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = root / "one.txt"
            other = root / "other.txt"
            original.write_bytes(b"original")
            other.write_bytes(b"other original")
            output = root / "copies"
            output.mkdir()
            (output / "new.txt").symlink_to(other)
            results = copy_rows([RenameRow(tmp, "one.txt", "new.txt")], str(output), True)
            self.assertTrue(results[0].status.startswith("Copied:"))
            self.assertEqual(other.read_bytes(), b"other original")
            self.assertEqual((output / "new.txt").read_bytes(), b"original")
            self.assertFalse((output / "new.txt").is_symlink())

    def test_duplicate_copy_names_do_not_silently_replace_previous_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("one", "two"):
                (root / name).mkdir()
                (root / name / "old.txt").write_text(name, encoding="utf-8")
            rows = [RenameRow(str(root / name), "old.txt", "same.txt") for name in ("one", "two")]
            output = root / "copies"
            results = copy_rows(rows, str(output))
            self.assertTrue(results[0].status.startswith("Copied:"))
            self.assertTrue(results[1].status.startswith("Skipped:"))
            self.assertEqual((output / "same.txt").read_text(encoding="utf-8"), "one")

    def test_default_copy_folder_is_new_and_inside_downloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            with patch("local_file_renamer_core.Path.home", return_value=home):
                folder = default_copy_output_folder()
                self.assertEqual(folder.parent, home / "Downloads")
                self.assertFalse(folder.exists())
                folder.mkdir(parents=True)
                next_folder = default_copy_output_folder()
                self.assertNotEqual(folder, next_folder)
                self.assertFalse(next_folder.exists())

    def test_copy_results_preserve_input_and_existing_outputs_in_both_formats(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "copies"
            output.mkdir()
            rows = [RenameRow(tmp, "old.txt", "new.txt", "Copied: old.txt -> new.txt")]
            for extension in (".csv", ".xlsx"):
                with self.subTest(extension=extension):
                    plan = root / f"plan{extension}"
                    write_rename_plan(str(plan), [RenameRow(tmp, "old.txt", "new.txt")])
                    original_plan = plan.read_bytes()
                    occupied = output / f"plan_results{extension}"
                    occupied.write_bytes(b"Do not overwrite this copy")
                    result_path = write_copy_results(str(plan), str(output), rows)
                    self.assertNotEqual(result_path, occupied)
                    self.assertEqual(occupied.read_bytes(), b"Do not overwrite this copy")
                    self.assertEqual(plan.read_bytes(), original_plan)
                    self.assertEqual(load_rename_plan(str(result_path)), rows)


if __name__ == "__main__":
    unittest.main()
