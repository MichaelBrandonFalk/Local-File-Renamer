from __future__ import annotations

import hashlib
import json
import platform
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
VERSION_NAME = VERSION.replace(".", "_")
DOWNLOADS = ROOT / "downloads"


def run(*arguments: str) -> None:
    subprocess.run(list(arguments), cwd=ROOT, check=True, timeout=900)


def verify(executable: Path, system: str) -> None:
    report = ROOT / "build" / f"package-check-{system}.json"
    report.unlink(missing_ok=True)
    process = subprocess.run([str(executable), "--self-test", str(report)], cwd=ROOT, timeout=90)
    result = json.loads(report.read_text(encoding="utf-8"))
    print(json.dumps(result, indent=2))
    process.check_returncode()
    if not result.get("success") or result.get("version") != VERSION:
        raise RuntimeError(f"Packaged app verification failed: {result}")


def package_linux(bundle: Path) -> list[Path]:
    package_name = f"Local_File_Renamer_v{VERSION_NAME}_Linux_x64"
    portable = DOWNLOADS / f"{package_name}.tar.gz"
    with tarfile.open(portable, "w:gz") as archive:
        archive.add(bundle, arcname=package_name)
        for name in ("README.md", "LICENSE"):
            archive.add(ROOT / name, arcname=f"{package_name}/{name}")

    stage = ROOT / "build" / "linux-deb-stage"
    if stage.exists():
        shutil.rmtree(stage)
    installed = stage / "opt" / "local-file-renamer"
    shutil.copytree(bundle, installed, symlinks=True)
    control = stage / "DEBIAN"
    control.mkdir()
    installed_size = sum(path.stat().st_size for path in installed.rglob("*") if path.is_file()) // 1024
    (control / "control").write_text(
        f"Package: local-file-renamer\nVersion: {VERSION}\nArchitecture: amd64\n"
        "Maintainer: Michael Brandon Falk\nSection: utils\nPriority: optional\n"
        f"Installed-Size: {installed_size}\n"
        "Depends: libc6 (>= 2.35), libx11-6, libxext6, libxrender1, libxft2, libfontconfig1, fonts-dejavu-core\n"
        "Homepage: https://michaelbrandonfalk.github.io/Local-File-Renamer/\n"
        "Description: Scan folders and rename files using CSV or Excel plans\n"
        " Includes a bundled Python and Tcl/Tk runtime, plus optional renamed copies.\n",
        encoding="utf-8",
    )
    applications = stage / "usr" / "share" / "applications"
    applications.mkdir(parents=True)
    (applications / "local-file-renamer.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=Local File Renamer\n"
        "Comment=Rename files from a CSV or spreadsheet plan\n"
        "Exec=/opt/local-file-renamer/local-file-renamer\nIcon=local-file-renamer\n"
        "Terminal=false\nCategories=Utility;FileTools;\nStartupWMClass=LocalFileRenamer\n",
        encoding="utf-8",
    )
    icons = stage / "usr" / "share" / "icons" / "hicolor" / "512x512" / "apps"
    icons.mkdir(parents=True)
    shutil.copy2(ROOT / "docs" / "assets" / "local_file_renamer_icon.png", icons / "local-file-renamer.png")
    documentation = stage / "usr" / "share" / "doc" / "local-file-renamer"
    documentation.mkdir(parents=True)
    shutil.copy2(ROOT / "LICENSE", documentation / "copyright")
    command = stage / "usr" / "bin"
    command.mkdir(parents=True)
    (command / "local-file-renamer").symlink_to("/opt/local-file-renamer/local-file-renamer")
    deb = DOWNLOADS / f"Local_File_Renamer_v{VERSION_NAME}_Linux_Mint_amd64.deb"
    run("dpkg-deb", "--root-owner-group", "--build", str(stage), str(deb))
    return [portable, deb]


def main() -> None:
    system = platform.system()
    if system not in {"Windows", "Linux"} or platform.machine().lower() not in {"amd64", "x86_64"}:
        raise SystemExit("Run this builder on 64-bit Windows or Linux. Use build_mac_silicon.sh for macOS.")
    DOWNLOADS.mkdir(exist_ok=True)
    arguments = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--name", "local-file-renamer", "--hidden-import", "tkinter",
        "--add-data", f"{ROOT / 'assets' / 'local_file_renamer_icon.png'}:assets",
        "--add-data", f"{ROOT / 'assets' / 'neb-default-profile.json'}:assets",
    ]
    if system == "Windows":
        arguments.extend(["--onefile", "--windowed", "--icon", str(ROOT / "assets" / "local_file_renamer_icon.png")])
    else:
        arguments.append("--onedir")
    run(*arguments, str(ROOT / "local_file_renamer_app.py"))
    if system == "Windows":
        executable = ROOT / "dist" / "local-file-renamer.exe"
        verify(executable, system)
        release = DOWNLOADS / f"Local_File_Renamer_v{VERSION_NAME}_Windows_x64.exe"
        shutil.copy2(executable, release)
        artifacts = [release]
    else:
        bundle = ROOT / "dist" / "local-file-renamer"
        verify(bundle / "local-file-renamer", system)
        artifacts = package_linux(bundle)
    checksums = []
    for path in artifacts:
        with path.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        checksums.append(f"{digest}  {path.name}\n")
        print(f"Ready: {path}")
    (DOWNLOADS / f"SHA256SUMS-{system}.txt").write_text("".join(checksums), encoding="utf-8")


if __name__ == "__main__":
    main()
