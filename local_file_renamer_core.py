from __future__ import annotations

import csv
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List


APP_NAME = "Local File Renamer"
APP_VERSION = "1.0"
CSV_HEADERS = ["folder_location", "current_name", "desired_name", "status"]


class RenameError(ValueError):
    """Raised when a rename plan has invalid user input."""


@dataclass
class RenameRow:
    folder_location: str
    current_name: str
    desired_name: str = ""
    status: str = ""

    @classmethod
    def from_mapping(cls, row: dict[str, str]) -> "RenameRow":
        return cls(
            folder_location=(row.get("folder_location") or "").strip(),
            current_name=(row.get("current_name") or "").strip(),
            desired_name=(row.get("desired_name") or "").strip(),
            status=(row.get("status") or "").strip(),
        )

    def to_csv_row(self) -> dict[str, str]:
        return {
            "folder_location": self.folder_location,
            "current_name": self.current_name,
            "desired_name": self.desired_name,
            "status": self.status,
        }


def normalize_folder(folder_location: str) -> Path:
    folder = Path(folder_location).expanduser()
    if not folder.exists():
        raise RenameError(f"Folder does not exist: {folder}")
    if not folder.is_dir():
        raise RenameError(f"Not a folder: {folder}")
    return folder


def validate_file_name(file_name: str, field_label: str) -> str:
    clean = file_name.strip()
    if not clean:
        raise RenameError(f"{field_label} is required.")
    if clean in {".", ".."}:
        raise RenameError(f"{field_label} cannot be {clean!r}.")
    if "\x00" in clean:
        raise RenameError(f"{field_label} cannot contain null characters.")
    if "/" in clean or (os.altsep and os.altsep in clean):
        raise RenameError(f"{field_label} must be a file name only, not a path.")
    return clean


def scan_folder(folder_location: str, recursive: bool = False) -> List[RenameRow]:
    folder = normalize_folder(folder_location)
    iterator = folder.rglob("*") if recursive else folder.iterdir()
    files = sorted((path for path in iterator if path.is_file()), key=lambda p: str(p).lower())

    return [
        RenameRow(
            folder_location=str(path.parent),
            current_name=path.name,
            desired_name="",
            status="",
        )
        for path in files
    ]


def write_scan_csv(folder_location: str, csv_path: str, recursive: bool = False) -> List[RenameRow]:
    rows = scan_folder(folder_location, recursive=recursive)
    write_rename_csv(csv_path, rows)
    return rows


def load_rename_csv(csv_path: str) -> List[RenameRow]:
    path = Path(csv_path).expanduser()
    if not path.exists():
        raise RenameError(f"CSV does not exist: {path}")

    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = [header for header in CSV_HEADERS[:3] if header not in (reader.fieldnames or [])]
        if missing:
            raise RenameError(f"CSV is missing required column(s): {', '.join(missing)}")
        return [RenameRow.from_mapping(row) for row in reader]


def write_rename_csv(csv_path: str, rows: Iterable[RenameRow]) -> None:
    path = Path(csv_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_HEADERS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.to_csv_row())


def rename_rows(rows: Iterable[RenameRow], allow_overwrite: bool = False) -> List[RenameRow]:
    results: List[RenameRow] = []

    for row in rows:
        result = RenameRow(
            folder_location=row.folder_location,
            current_name=row.current_name,
            desired_name=row.desired_name,
            status="",
        )

        try:
            if not result.desired_name.strip():
                result.status = "Skipped: desired_name is blank"
            else:
                result.status = rename_one(
                    result.folder_location,
                    result.current_name,
                    result.desired_name,
                    allow_overwrite=allow_overwrite,
                )
                if result.status.startswith("Renamed"):
                    result.current_name = result.desired_name
                    result.desired_name = ""
        except Exception as exc:
            result.status = f"Error: {exc}"

        results.append(result)

    return results


def rename_one(
    folder_location: str,
    current_name: str,
    desired_name: str,
    allow_overwrite: bool = False,
) -> str:
    folder = normalize_folder(folder_location)
    current = validate_file_name(current_name, "current_name")
    desired = validate_file_name(desired_name, "desired_name")

    source = folder / current
    target = folder / desired

    if current == desired:
        return "Skipped: current_name already matches desired_name"
    if not source.exists():
        return "Not found"
    if not source.is_file():
        return "Skipped: source is not a file"

    if target.exists():
        if _is_same_file(source, target):
            _rename_case_only(source, target)
            return f"Renamed: {current} -> {desired}"
        if not allow_overwrite:
            return "Skipped: desired_name already exists"
        target.unlink()

    source.rename(target)
    return f"Renamed: {current} -> {desired}"


def _is_same_file(left: Path, right: Path) -> bool:
    try:
        return left.samefile(right)
    except OSError:
        return False


def _rename_case_only(source: Path, target: Path) -> None:
    if source.name == target.name:
        return

    temp_name = f".rename_tmp_{uuid.uuid4().hex}_{source.name}"
    temp = source.with_name(temp_name)
    source.rename(temp)
    temp.rename(target)
