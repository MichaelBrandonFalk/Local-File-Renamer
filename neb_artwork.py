from __future__ import annotations

import hashlib
import json
import os
import re
import ssl
import sys
import unicodedata
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from local_file_renamer_core import APP_VERSION, RenameError, RenameRow, copy_rows, scan_folder


PROFILE_URL = "https://michaelbrandonfalk.github.io/NameEverythingBetter/default-profile.json"
SNAPSHOT = Path(__file__).parent / "assets" / "neb-default-profile.json"
COMBINED_TYPE = "Series + Season"
INFORMATIONAL = ("Excluded:", "Missing:", "Conflict:", "Needs input:")


class NEBError(RenameError):
    pass


def title_slug(value: str, rules: dict) -> str:
    text = value.strip()
    if rules["titleCase"] == "lower":
        text = text.lower()
    elif rules["titleCase"] == "upper":
        text = text.upper()
    text = re.sub("['\u2019]", "" if rules["apostrophes"] == "remove" else " ", text)
    if rules["plus"] == "context":
        text = re.sub(r"\s+\+\s+", " and ", text)
        text = text.replace("+", " plus ")
    else:
        text = text.replace("+", f" {rules['plus']} ")
    text = text.replace("&", f" {rules['ampersand']} ").replace("@", f" {rules['at']} ")
    text = re.sub(r"([a-zA-Z0-9])\.\.\.(?=[a-zA-Z0-9])", r"\1 ", text)
    text = re.sub("[\u00b7*!.\u00a0]", "", text)
    if rules["stripAccents"]:
        text = re.sub("[\u0300-\u036f]", "", unicodedata.normalize("NFKD", text))
    return re.sub(r"[^a-zA-Z0-9]+", rules["separator"], text).strip(rules["separator"])


@dataclass
class NEBProfile:
    document: dict
    fetched_at: str = ""

    def __post_init__(self):
        document = self.document
        if not isinstance(document, dict):
            raise NEBError("NEB returned an invalid profile document.")
        if document.get("schemaVersion") != 1 or document.get("normalization", {}).get("titleCharacterSet") != "ascii":
            raise NEBError("NEB's profile format has changed. Update Local File Renamer before building artwork.")
        self.profile = document.get("profile", {})
        if self.profile.get("id") != "neb-standard":
            raise NEBError("The downloaded profile is not NEB Standard.")
        self.rules = self.profile.get("rules", {})
        if self.rules.get("separator") not in {"_", "-"} or self.rules.get("titleCase") not in {"lower", "upper", "preserve"}:
            raise NEBError("NEB's title rules are not supported by this app version.")
        self.types = {item["name"]: item for item in self.profile.get("types", []) if item.get("domain") == "art"}
        self.extensions = document.get("artExtensions", {})
        self.extra_codes = document.get("extraUsageCodes", {})
        if not self.types or not self.extensions:
            raise NEBError("NEB's current profile has no artwork definitions.")
        if not document.get("titleExamples") or {item.get("type") for item in document.get("artExamples", [])} != set(self.types):
            raise NEBError("NEB's profile is missing its engine verification examples.")
        self.fingerprint = hashlib.sha256(json.dumps({
            "profile": self.profile, "extensions": self.extensions, "normalization": document["normalization"], "extraCodes": self.extra_codes,
        }, sort_keys=True).encode()).hexdigest()
        for example in document.get("titleExamples", []):
            if title_slug(example["input"], self.rules) != example["output"]:
                raise NEBError("NEB's title normalization has changed. Update this app; no files have been changed.")
        for example in document.get("artExamples", []):
            actual = [self.filename(example["type"], example["values"], variant) for variant in self.types[example["type"]]["variants"]]
            if actual != example["filenames"]:
                raise NEBError(f"NEB's {example['type']} naming rules have changed in a way this app cannot interpret.")

    @property
    def revision(self) -> str:
        return self.document.get("source", {}).get("revision", "unknown")

    def fields(self, selected: str) -> list[dict]:
        fields = {}
        for name in self.type_names(selected):
            for item in self.types[name]["fields"]:
                if item["key"] not in {"art_tag", "aspect_ratio", "dimensions"}:
                    fields.setdefault(item["key"], item)
        return list(fields.values())

    def type_names(self, selected: str) -> list[str]:
        names = ["Series", "Season Placeholder"] if selected == COMBINED_TYPE else [selected]
        if any(name not in self.types for name in names):
            raise NEBError("Choose an artwork type from the current NEB profile.")
        return names

    def filename(self, type_name: str, values: dict, variant: dict) -> str:
        item = self.types[type_name]
        language = values.get("language", "English")
        tokens = {"art_tag": variant["artTag"], "aspect_ratio": variant["aspectRatio"], "dimensions": variant["dimensions"]}
        tokens["extension"] = self.extensions[variant["artTag"]]
        for definition in item["fields"]:
            key = definition["key"]
            if key in tokens:
                continue
            value = str(values.get(key, "")).strip()
            if not value:
                raise NEBError(f"{definition['label']} is required.")
            if definition["type"] == "select" and value not in definition.get("options", []):
                raise NEBError(f"Choose an allowed {definition['label']}.")
            if key == "language":
                value = self.rules["spanishArt"] if value == "Spanish" else self.rules["englishArt"]
            elif key in {"season", "episode"}:
                numeric = re.sub(r"^[se]", "", value, flags=re.I)
                if not re.fullmatch(r"[0-9]{1,3}", numeric) or not 1 <= int(numeric) <= 999:
                    raise NEBError(f"{definition['label']} must be between 1 and 999.")
                value = f"{key[0]}{int(numeric):02d}"
            elif key == "year":
                if not re.fullmatch(r"[0-9]{4}", value):
                    raise NEBError("Year must have four digits.")
            elif definition["type"] != "select":
                value = title_slug(value, self.rules)
                if not value:
                    raise NEBError(f"{definition['label']} needs letters or numbers.")
            tokens[key] = value
        if "extra_usage" in tokens:
            tokens["extra"] = self.extra_codes.get(values.get("extra_usage"), "")
        recipe = item["templates"].get(language, {}).get("filename", "")
        if not recipe:
            raise NEBError(f"No {language} artwork recipe is configured for {type_name}.")
        try:
            result = re.sub(r"\{([a-z][a-z0-9_]*)\}", lambda match: tokens[match[1]], recipe)
        except KeyError as exc:
            raise NEBError(f"NEB's recipe needs a value for {exc.args[0]}.") from exc
        result = re.sub(r"_+", self.rules["separator"], result)
        if not result or len(result) > 240 or re.search(r'[{}\\/:*?"<>|\x00-\x1f]', result) or result.endswith((".", " ")):
            raise NEBError("NEB's recipe produced an invalid destination filename.")
        return result


def profile_cache_path() -> Path:
    if sys.platform == "win32":
        root = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Caches"
    else:
        root = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return root / "local-file-renamer" / "neb-default-profile.json"


def read_profile(path: Path = SNAPSHOT) -> NEBProfile:
    try:
        return NEBProfile(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise NEBError(f"Could not read the NEB profile: {exc}") from exc


def fetch_current_profile(cache_path: Path | None = None) -> NEBProfile:
    import certifi

    request = Request(f"{PROFILE_URL}?check={datetime.now(timezone.utc).timestamp()}", headers={
        "User-Agent": f"Local-File-Renamer/{APP_VERSION}", "Cache-Control": "no-cache", "Accept": "application/json",
    })
    try:
        with urlopen(request, context=ssl.create_default_context(cafile=certifi.where()), timeout=15) as response:
            data = response.read(2_000_001)
        if len(data) > 2_000_000:
            raise NEBError("NEB's profile response was unexpectedly large.")
        profile = NEBProfile(json.loads(data))
        profile.fetched_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    except NEBError:
        raise
    except (URLError, OSError, ValueError, KeyError, TypeError) as exc:
        raise NEBError(f"Could not verify the current NEB defaults. Check your connection and retry.\n\n{exc}") from exc
    try:
        path = cache_path or profile_cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    except OSError:
        pass
    return profile


def episode_selection(value: str) -> set[int]:
    result = set()
    for part in re.split(r"[,\s]+", value.strip()):
        if not part:
            continue
        match = re.fullmatch(r"[eE]?([0-9]{1,3})(?:-[eE]?([0-9]{1,3}))?", part)
        if not match:
            raise NEBError("Episode selection must use numbers or ranges, such as 1-12, 15.")
        first, last = int(match[1]), int(match[2] or match[1])
        if not 1 <= first <= last <= 999:
            raise NEBError("Episode numbers must be between 1 and 999, in ascending ranges.")
        result.update(range(first, last + 1))
    return result


@dataclass
class ArtFile:
    row: RenameRow
    values: dict
    tag: str
    ratio: str
    dimensions: str
    extension: str


def parse_art_file(row: RenameRow, profile: NEBProfile) -> ArtFile | None:
    tags = "|".join(re.escape(tag) for tag in profile.extensions)
    languages = "|".join(re.escape(code) for code in sorted({profile.rules["englishArt"], profile.rules["spanishArt"], "eng", "las"}, key=len, reverse=True))
    match = re.fullmatch(
        rf"(?P<head>.*?)(?P<language>{languages})_(?P<tag>{tags})_(?P<ratio>[0-9]+x[0-9]+)_(?P<dimensions>[0-9]+x[0-9]+)(?:[_ -]+v[0-9]+| ?\([0-9]+\))?\.(?P<extension>jpg|jpeg|png)",
        row.current_name, flags=re.I,
    )
    if not match:
        return None
    head = match["head"].rstrip("_ .-")
    values = {"language": "Spanish" if match["language"].casefold() in {profile.rules["spanishArt"].casefold(), "las"} else "English"}
    values["source_prefix"] = head
    episode = re.search(r"(?:s([0-9]{1,4})[_ .-]*)?(?:e|episode[_ .-]*)([0-9]{1,3})$", head, flags=re.I)
    season = re.search(r"(?:^|[_ .-])s([0-9]{1,4})$", head, flags=re.I)
    if episode:
        if episode[1]:
            values["year" if len(episode[1]) == 4 else "season"] = str(int(episode[1]))
        values["episode"] = str(int(episode[2]))
        head = head[:episode.start()].rstrip("_ .-")
    elif season:
        values["year" if len(season[1]) == 4 else "season"] = str(int(season[1]))
        head = head[:season.start()].rstrip("_ .-")
    if "season" not in values:
        for parent in (Path(row.folder_location), *Path(row.folder_location).parents):
            directory = re.fullmatch(r"(?:s|season[ _-]*)([0-9]{1,3})", parent.name, flags=re.I)
            if directory:
                values["season"] = str(int(directory[1]))
                values["season_from_directory"] = True
                break
    values["title"] = head
    return ArtFile(row, values, match["tag"].lower(), match["ratio"].lower(), match["dimensions"].lower(), match["extension"].lower())


def profile_source_values(source: ArtFile, profile: NEBProfile, type_name: str) -> dict:
    values = dict(source.values)
    recipe = profile.types[type_name]["templates"][values["language"]]["filename"]
    if "_{language}_" not in recipe:
        return values
    prefix = recipe.split("_{language}_", 1)[0]
    pattern = re.escape(prefix)
    keys = re.findall(r"\{([a-z][a-z0-9_]*)\}", prefix)
    patterns = {
        "season": r"s[0-9]{1,3}", "episode": r"e[0-9]{1,3}", "year": r"[0-9]{4}",
        "extra": "(?:" + "|".join(re.escape(code) for code in profile.extra_codes.values()) + ")",
    }
    for key in keys:
        token = patterns.get(key, r".+?")
        pattern = pattern.replace(re.escape("{" + key + "}"), f"(?P<{key}>{token})")
    match = re.fullmatch(pattern, values["source_prefix"], flags=re.I)
    if match:
        for key, value in match.groupdict().items():
            if key == "extra":
                for label, code in profile.extra_codes.items():
                    if code == value:
                        values["extra_usage"] = label
            else:
                values[key] = str(int(value[1:])) if key in {"season", "episode"} else value
        if match.groupdict().get("season"):
            values.pop("season_from_directory", None)
    return values


@dataclass
class Requirement:
    filename: str
    destination: str
    label: str
    rows: list[RenameRow] = field(default_factory=list)


@dataclass
class ArtworkPlan:
    profile: NEBProfile
    rows: list[RenameRow]
    requirements: list[Requirement]
    source_folder: str

    def summary(self) -> str:
        ready = sum(bool(row.desired_name) for row in self.rows)
        missing = sum(not item.rows for item in self.requirements)
        conflicts = sum(len(item.rows) > 1 and not any(row.desired_name for row in item.rows) for item in self.requirements)
        return f"{ready} ready; {missing} missing; {conflicts} conflicting requirements"

    def choose_match(self, selected: RenameRow) -> bool:
        for requirement in self.requirements:
            if len(requirement.rows) > 1 and any(row is selected for row in requirement.rows):
                for row in requirement.rows:
                    row.desired_name = requirement.filename if row is selected else ""
                    row.status = f"Ready: {requirement.label}" if row is selected else "Excluded: alternative source"
                return True
        return False


def build_artwork_plan(folder: str, profile: NEBProfile, selected_type: str, values: dict, *, recursive: bool = True, required_only: bool = True, group_output: bool = True) -> ArtworkPlan:
    types = profile.type_names(selected_type)
    raw_rows = scan_folder(folder, recursive)
    files = [parsed for row in raw_rows if (parsed := parse_art_file(row, profile)) is not None]
    if not files:
        raise NEBError("No supported artwork filenames were found in the source folder.")
    wanted_episodes = episode_selection(values.get("episode", ""))
    requirements = []
    plan_rows = []
    consumed = set()
    problems = {}
    for type_name in types:
        definition = profile.types[type_name]
        keys = {item["key"] for item in profile.fields(type_name)}
        subjects = {}
        for raw_source in files:
            source = replace(raw_source, values=profile_source_values(raw_source, profile, type_name))
            subject = {key: str(values.get(key, "")).strip() for key in keys}
            subject["language"] = values.get("language", "English")
            if source.values["language"] != subject["language"]:
                continue
            if any(
                definition["type"] == "select" and source.values.get(definition["key"])
                and subject.get(definition["key"]) and source.values[definition["key"]] != subject[definition["key"]]
                for definition in profile.fields(type_name)
            ):
                continue
            for key in ("season", "episode", "year"):
                original = source.values.get(key, "")
                if key == "season" and subject.get(key) and source.values.get("season_from_directory"):
                    original = ""
                if key not in keys:
                    continue
                if key == "episode":
                    if wanted_episodes and original and int(original) not in wanted_episodes:
                        subject = None
                        break
                    subject[key] = original or (str(next(iter(wanted_episodes))) if len(wanted_episodes) == 1 else "")
                elif original:
                    if subject[key] and subject[key].lstrip("sS").isdigit() and int(subject[key].lstrip("sS")) != int(original):
                        subject = None
                        break
                    subject[key] = original
            if subject is None:
                continue
            for key in keys - {"title", "language", "season", "episode", "year"}:
                if not subject[key] and source.values.get(key):
                    subject[key] = source.values[key]
            if "title" in keys and not subject["title"]:
                subject["title"] = source.values["title"]
                if title_slug(subject["title"], profile.rules) in {"title", "placeholder", "untitled"}:
                    problems[id(source.row)] = "Needs input: enter the correct title for the placeholder"
                    continue
            if "title" in subject:
                subject["title"] = title_slug(subject["title"], profile.rules)
            try:
                first = definition["variants"][0] if definition["variants"] else definition["sizes"][0]
                profile.filename(type_name, subject, first)
            except (NEBError, IndexError) as exc:
                problems[id(source.row)] = f"Needs input: {exc}"
                continue
            signature = tuple(sorted(subject.items()))
            subjects.setdefault(signature, {"values": subject, "files": []})["files"].append(source)
        if not subjects and problems:
            raise NEBError(next(iter(problems.values())))
        # Explicit episode ranges also expose requirements for episodes absent from the download.
        if "episode" in keys and wanted_episodes and subjects:
            for subject in list(subjects.values()):
                for episode in wanted_episodes:
                    fields = {**subject["values"], "episode": str(episode)}
                    subjects.setdefault(tuple(sorted(fields.items())), {"values": fields, "files": []})
        for subject in subjects.values():
            fields, candidates = subject["values"], subject["files"]
            if group_output and len(types) > 1:
                destination = "Series" if type_name == "Series" else f"Season {int(fields['season']):02d}"
            elif group_output and "episode" in keys:
                season = f"s{int(fields['season']):02d}_" if fields.get("season") else f"s{fields['year']}_" if fields.get("year") else ""
                destination = f"{season}e{int(fields['episode']):02d}"
            else:
                destination = ""
            variants = definition["variants"] if required_only else definition["sizes"]
            if not required_only:
                variants = [variant for variant in variants if any((source.tag, source.ratio, source.dimensions) == (variant["artTag"], variant["aspectRatio"], variant["dimensions"]) for source in candidates)]
            for variant in variants:
                filename = profile.filename(type_name, fields, variant)
                requirement = Requirement(filename, destination, type_name)
                expected_extension = profile.extensions[variant["artTag"]]
                for source in candidates:
                    if (source.tag, source.ratio, source.dimensions) != (variant["artTag"], variant["aspectRatio"], variant["dimensions"]):
                        continue
                    if source.extension != expected_extension and not (expected_extension == "jpg" and source.extension == "jpeg"):
                        continue
                    row = RenameRow(source.row.folder_location, source.row.current_name, filename, f"Ready: {type_name}")
                    requirement.rows.append(row)
                    consumed.add(id(source.row))
                if len(requirement.rows) > 1:
                    for row in requirement.rows:
                        row.desired_name = ""
                        row.status = f"Conflict: multiple sources for {filename}"
                if not requirement.rows:
                    plan_rows.append(RenameRow(folder, "", "", f"Missing: {destination + '/' if destination else ''}{filename}"))
                plan_rows.extend(requirement.rows)
                requirements.append(requirement)
    for row in raw_rows:
        if id(row) not in consumed:
            row.status = problems.get(id(row), "Excluded: not required for the selected type, language, or episodes")
            plan_rows.append(row)
    targets = {}
    for requirement in requirements:
        targets.setdefault((requirement.destination.casefold(), requirement.filename.casefold()), []).append(requirement)
    for duplicates in targets.values():
        if len(duplicates) > 1:
            for requirement in duplicates:
                for row in requirement.rows:
                    row.desired_name = ""
                    row.status = "Conflict: multiple requirements use the same output filename"
    if not requirements and files:
        issues = next(iter(problems.values()), "No files match the selected type, language, and field filters.")
        raise NEBError(issues)
    return ArtworkPlan(profile, plan_rows, requirements, folder)


def copy_artwork_plan(plan: ArtworkPlan, selected_rows: list[RenameRow], output_folder: str, allow_overwrite: bool = False) -> list[RenameRow]:
    output = Path(output_folder).expanduser().resolve()
    if not output_folder.strip() or any(output == Path(row.folder_location).expanduser().resolve() for row in selected_rows if row.current_name):
        raise NEBError("Choose an output folder different from the original artwork folder.")
    included = {id(row) for row in selected_rows}
    sources = {Path(row.folder_location).expanduser().resolve() for row in selected_rows if row.current_name}
    for requirement in plan.requirements:
        destination = (output / requirement.destination).resolve()
        if not destination.is_relative_to(output) or destination in sources:
            raise NEBError("An output subfolder points outside the destination or back to the originals. Choose a new output folder.")
    destinations = {}
    for requirement in plan.requirements:
        for row in requirement.rows:
            if id(row) in included and row.desired_name:
                key = (requirement.destination.casefold(), row.desired_name.casefold())
                destinations.setdefault(key, []).append(row)
    for requirement in plan.requirements:
        ready = []
        for row in requirement.rows:
            if id(row) not in included or not row.desired_name:
                continue
            if len(destinations[(requirement.destination.casefold(), row.desired_name.casefold())]) > 1:
                row.status = "Conflict: multiple requirements use the same output filename"
                continue
            ready.append(row)
        if ready:
            result = copy_rows(ready, str(output / requirement.destination), allow_overwrite)
            for original, copied in zip(ready, result):
                original.status = copied.status
    return selected_rows
