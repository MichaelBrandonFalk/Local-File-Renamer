from __future__ import annotations

import csv
import os
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List
from xml.etree import ElementTree as ET


APP_NAME = "Local File Renamer"
APP_VERSION = "1.1"
CSV_HEADERS = ["folder_location", "current_name", "desired_name", "status"]
PLAN_EXTENSIONS = (".csv", ".xlsx")
XML_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
XML_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
XML_PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


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


def write_scan_plan(folder_location: str, plan_path: str, recursive: bool = False) -> List[RenameRow]:
    rows = scan_folder(folder_location, recursive=recursive)
    write_rename_plan(plan_path, rows)
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


def load_rename_plan(plan_path: str) -> List[RenameRow]:
    path = Path(plan_path).expanduser()
    suffix = path.suffix.lower()

    if suffix == ".csv":
        return load_rename_csv(str(path))
    if suffix == ".xlsx":
        return load_rename_xlsx(str(path))

    raise RenameError("Rename plan must be a .csv or .xlsx file.")


def write_rename_csv(csv_path: str, rows: Iterable[RenameRow]) -> None:
    path = Path(csv_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_HEADERS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.to_csv_row())


def write_rename_plan(plan_path: str, rows: Iterable[RenameRow]) -> None:
    path = Path(plan_path).expanduser()
    suffix = path.suffix.lower()

    if suffix == ".csv":
        write_rename_csv(str(path), rows)
        return
    if suffix == ".xlsx":
        write_rename_xlsx(str(path), rows)
        return

    raise RenameError("Rename plan must be saved as .csv or .xlsx.")


def load_rename_xlsx(xlsx_path: str) -> List[RenameRow]:
    path = Path(xlsx_path).expanduser()
    if not path.exists():
        raise RenameError(f"Spreadsheet does not exist: {path}")

    try:
        with zipfile.ZipFile(path, "r") as archive:
            sheet_path = _first_worksheet_path(archive)
            shared_strings = _read_shared_strings(archive)
            worksheet = ET.fromstring(archive.read(sheet_path))
    except (KeyError, ET.ParseError, zipfile.BadZipFile) as exc:
        raise RenameError(f"Could not read spreadsheet: {exc}") from exc

    table = _worksheet_to_table(worksheet, shared_strings)
    if not table:
        return []

    headers = [cell.strip() for cell in table[0]]
    missing = [header for header in CSV_HEADERS[:3] if header not in headers]
    if missing:
        raise RenameError(f"Spreadsheet is missing required column(s): {', '.join(missing)}")

    rows: List[RenameRow] = []
    for values in table[1:]:
        mapping = {header: values[index] if index < len(values) else "" for index, header in enumerate(headers)}
        if any((mapping.get(header) or "").strip() for header in CSV_HEADERS):
            rows.append(RenameRow.from_mapping(mapping))

    return rows


def write_rename_xlsx(xlsx_path: str, rows: Iterable[RenameRow]) -> None:
    path = Path(xlsx_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)

    row_values = [CSV_HEADERS]
    row_values.extend([[row.folder_location, row.current_name, row.desired_name, row.status] for row in rows])

    ET.register_namespace("", XML_MAIN_NS)
    ET.register_namespace("r", XML_REL_NS)

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _xlsx_content_types_xml())
        archive.writestr("_rels/.rels", _xlsx_root_rels_xml())
        archive.writestr("docProps/app.xml", _xlsx_app_xml())
        archive.writestr("docProps/core.xml", _xlsx_core_xml())
        archive.writestr("xl/workbook.xml", _xlsx_workbook_xml())
        archive.writestr("xl/_rels/workbook.xml.rels", _xlsx_workbook_rels_xml())
        archive.writestr("xl/styles.xml", _xlsx_styles_xml())
        archive.writestr("xl/worksheets/sheet1.xml", _xlsx_sheet_xml(row_values))


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


def _first_worksheet_path(archive: zipfile.ZipFile) -> str:
    try:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    except KeyError:
        return "xl/worksheets/sheet1.xml"

    sheet = workbook.find(f".//{{{XML_MAIN_NS}}}sheet")
    if sheet is None:
        return "xl/worksheets/sheet1.xml"

    rel_id = sheet.attrib.get(f"{{{XML_REL_NS}}}id")
    if not rel_id:
        return "xl/worksheets/sheet1.xml"

    for rel in rels.findall(f"{{{XML_PACKAGE_REL_NS}}}Relationship"):
        if rel.attrib.get("Id") == rel_id:
            target = rel.attrib.get("Target", "worksheets/sheet1.xml")
            if target.startswith("/"):
                return target.lstrip("/")
            return "xl/" + target.lstrip("/")

    return "xl/worksheets/sheet1.xml"


def _read_shared_strings(archive: zipfile.ZipFile) -> List[str]:
    try:
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []

    strings: List[str] = []
    for item in root.findall(f"{{{XML_MAIN_NS}}}si"):
        strings.append("".join(text.text or "" for text in item.findall(f".//{{{XML_MAIN_NS}}}t")))
    return strings


def _worksheet_to_table(root: ET.Element, shared_strings: List[str]) -> List[List[str]]:
    table: List[List[str]] = []

    for row in root.findall(f".//{{{XML_MAIN_NS}}}row"):
        values: List[str] = []
        for cell in row.findall(f"{{{XML_MAIN_NS}}}c"):
            cell_ref = cell.attrib.get("r", "")
            index = _cell_column_index(cell_ref)
            while len(values) < index:
                values.append("")
            values.append(_xlsx_cell_value(cell, shared_strings))
        table.append(values)

    return table


def _xlsx_cell_value(cell: ET.Element, shared_strings: List[str]) -> str:
    cell_type = cell.attrib.get("t")

    if cell_type == "inlineStr":
        return "".join(text.text or "" for text in cell.findall(f".//{{{XML_MAIN_NS}}}t")).strip()

    value = cell.find(f"{{{XML_MAIN_NS}}}v")
    raw = value.text if value is not None and value.text is not None else ""

    if cell_type == "s":
        try:
            return shared_strings[int(raw)].strip()
        except (ValueError, IndexError):
            return ""

    return raw.strip()


def _cell_column_index(cell_ref: str) -> int:
    letters = "".join(char for char in cell_ref if char.isalpha()).upper()
    if not letters:
        return 0

    index = 0
    for char in letters:
        index = index * 26 + (ord(char) - ord("A") + 1)
    return index - 1


def _column_name(index: int) -> str:
    name = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(ord("A") + remainder) + name
    return name


def _xlsx_sheet_xml(rows: List[List[str]]) -> str:
    root = ET.Element(f"{{{XML_MAIN_NS}}}worksheet")
    sheet_data = ET.SubElement(root, f"{{{XML_MAIN_NS}}}sheetData")

    for row_index, row_values in enumerate(rows, start=1):
        row_el = ET.SubElement(sheet_data, f"{{{XML_MAIN_NS}}}row", {"r": str(row_index)})
        for col_index, value in enumerate(row_values):
            cell_ref = f"{_column_name(col_index)}{row_index}"
            cell_el = ET.SubElement(row_el, f"{{{XML_MAIN_NS}}}c", {"r": cell_ref, "t": "inlineStr"})
            inline = ET.SubElement(cell_el, f"{{{XML_MAIN_NS}}}is")
            text = ET.SubElement(inline, f"{{{XML_MAIN_NS}}}t")
            text.text = str(value)

    return _xml_bytes(root)


def _xlsx_content_types_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>"""


def _xlsx_root_rels_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>"""


def _xlsx_workbook_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Rename Plan" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>"""


def _xlsx_workbook_rels_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""


def _xlsx_styles_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="1"><font><sz val="11"/><name val="Aptos"/></font></fonts>
  <fills count="1"><fill><patternFill patternType="none"/></fill></fills>
  <borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>
</styleSheet>"""


def _xlsx_app_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Local File Renamer</Application>
</Properties>"""


def _xlsx_core_xml() -> str:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:creator>Local File Renamer</dc:creator>
  <cp:lastModifiedBy>Local File Renamer</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified>
</cp:coreProperties>"""


def _xml_bytes(root: ET.Element) -> str:
    return ET.tostring(root, encoding="utf-8", xml_declaration=True).decode("utf-8")
