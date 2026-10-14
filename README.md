# Local File Renamer

Local File Renamer is a desktop app for Windows, Linux Mint, and macOS. Build a CSV or spreadsheet rename plan from a local folder, then rename the files in place or save renamed copies in a separate folder.

## Download

Download v1.6 from the public releases page:

- [Windows x64 executable](https://github.com/MichaelBrandonFalk/Local-File-Renamer/releases/download/v1.6/Local_File_Renamer_v1_6_Windows_x64.exe)
- [Linux Mint amd64 installer](https://github.com/MichaelBrandonFalk/Local-File-Renamer/releases/download/v1.6/Local_File_Renamer_v1_6_Linux_Mint_amd64.deb)
- [Linux x64 portable archive](https://github.com/MichaelBrandonFalk/Local-File-Renamer/releases/download/v1.6/Local_File_Renamer_v1_6_Linux_x64.tar.gz)
- [macOS Apple Silicon ZIP](https://github.com/MichaelBrandonFalk/Local-File-Renamer/releases/download/v1.6/Local_File_Renamer_v1_6_macOS_Apple_Silicon.zip)

## Compatibility

The downloads bundle Python and Tcl/Tk. Users do not need Python, pip, Homebrew, PyInstaller, or development tools installed.

| Download | Supported System | Opening the App |
| --- | --- | --- |
| Windows `.exe` | Windows 10/11, x64 | Open the downloaded executable. No installer or administrator access needed. |
| Mint `.deb` | Linux Mint 21.x/22.x, amd64 | Open in Mint's package installer, install, then launch Local File Renamer from the application menu. |
| Linux `.tar.gz` | Mint 21.x/22.x and compatible desktop Linux with glibc 2.35+, x64 | Extract the full archive and open `local-file-renamer` inside it. Keep `_internal` beside the executable. |
| macOS `.zip` | macOS 11 Big Sur or newer, Apple Silicon | Extract the ZIP and open the `.app`. |

The Mint installer declares the standard desktop library dependencies and includes an application-menu launcher and icon. Windows and Linux ARM builds are not included. The macOS public build remains ad-hoc signed; Developer ID signing and notarization require an Apple developer certificate.

## What It Does

- Scans a selected local folder.
- Offers to scan subfolders when the selected folder has no files directly inside it.
- Reports permission errors and prevents empty scans from saving a blank export.
- Writes a CSV or `.xlsx` spreadsheet with `folder_location`, `current_name`, `desired_name`, and `status`.
- Lets you browse to and load an edited CSV or spreadsheet rename plan.
- Renames actual files after you click `Run Renames` and confirm.
- Optionally copies files under their desired names to a separate output folder, leaving originals in place.
- Writes status results back to the loaded plan for in-place renames, or to a separate output report in copy mode.
- Uses a custom pomegranate tile app icon.

## CSV Format

```csv
folder_location,current_name,desired_name,status
/Users/me/Desktop/files,old-name.txt,new-name.txt,
```

The `.xlsx` spreadsheet uses the same columns. `desired_name` must be a file name only, not a path. Existing files are not overwritten unless you enable the overwrite option in the app.

Exports populate `folder_location` and `current_name` for each file found. The `desired_name` and `status` columns start blank. Enable `Include subfolders` to list files inside nested folders. If macOS blocks access, choose the folder with `Browse` and grant the app access in System Settings > Privacy & Security > Files and Folders.

## Rename Copies

Select `Rename copies` after loading an edited plan. The output defaults to a new `Renamed Files` folder in Downloads. Edit `Output folder` or use `Browse` to choose a different destination, then click `Copy & Rename` and confirm. The folder is created when the run starts.

Windows uses the system Downloads location, including redirected folders. Linux uses the configured XDG Downloads folder, including localized names. The displayed output path remains selected between runs; choose a different empty folder for a fresh set of copies.

Rows with a blank `desired_name` are skipped. Copies from all source folders go directly into the selected output folder. Duplicate output names are skipped unless `Allow overwrite existing files` is enabled. An output folder cannot also be a source folder.

The original files and input plan stay in place. A separate results plan is saved in the output folder, in the same CSV or XLSX format as the input. Copy results retain the source names and desired names, with the destination recorded in `status`. Existing copies and reports are not replaced unless file overwrite is explicitly enabled; reports always receive a unique name.

## Build Locally

Builders require Python 3.13 or newer with Tkinter. On Windows or Linux:

```bash
python -m pip install -r requirements-build.txt
python -m unittest discover -s tests -v
python build_release.py
```

On Linux, build on Ubuntu 22.04 or Linux Mint 21 for the oldest supported glibc baseline. A graphical session is required for package checks; CI uses `xvfb-run -a python build_release.py`. The Linux builder also requires `dpkg-deb`.

On an Apple Silicon Mac:

```bash
python3 -m unittest discover -s tests
./build_mac_silicon.sh
```

Builds place versioned release packages and SHA-256 checksums in `downloads/`. Windows and Linux builds run the packaged application through CSV/XLSX export, plan loading, copying, results reporting, renaming, and window-layout checks before packaging completes.

GitHub Actions builds on native Windows and Linux runners, then verifies both the portable archive and installed DEB in Linux Mint 21.3 and 22 containers. Containers verify the application and its desktop libraries with a virtual display; they do not simulate the full Cinnamon, MATE, or Xfce desktop.

## Notarized Public Release

For a public build that opens normally on downloaded Macs, sign and notarize with an Apple Developer ID certificate:

```bash
export CODESIGN_IDENTITY="Developer ID Application: Your Name (TEAMID)"
export NOTARY_PROFILE="your-notarytool-profile"
./notarize_mac_release.sh
```

## Versioning

Each update should increment `VERSION`, add a `CHANGELOG.md` entry, build a new versioned app name, and publish a new GitHub release.
