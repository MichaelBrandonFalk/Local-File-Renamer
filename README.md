# Local File Renamer

Local File Renamer is a small macOS app for building a CSV rename plan from a local folder and then applying that plan to real files on your computer.

## Download

Download the latest Apple Silicon build from the public releases page:

- [Local File Renamer v1.0 for macOS Apple Silicon](https://github.com/MichaelBrandonFalk/Local-File-Renamer/releases/download/v1.0/Local_File_Renamer_v1_0_macOS_Apple_Silicon.zip)

## Compatibility

The macOS download is a self-contained Apple Silicon app bundle. Users do not need Python, Tkinter, Homebrew, PyInstaller, or any command-line tools installed.

- Architecture: Apple Silicon / `arm64`
- Minimum macOS target: macOS 11 Big Sur
- Bundled runtime: Python 3.13 plus Tcl/Tk UI libraries

This public build is ad-hoc signed. For the smoothest double-click launch experience after downloading from the web, the app should also be signed with an Apple Developer ID certificate and notarized by Apple.

## What It Does

- Scans a selected local folder.
- Writes a CSV with `folder_location`, `current_name`, `desired_name`, and `status`.
- Lets you load an edited CSV rename plan.
- Lets you add a single rename row directly in the app.
- Renames actual files after you click `Run Renames` and confirm.
- Writes status results back to the CSV when a CSV is loaded.

## CSV Format

```csv
folder_location,current_name,desired_name,status
/Users/me/Desktop/files,old-name.txt,new-name.txt,
```

`desired_name` must be a file name only, not a path. Existing files are not overwritten unless you enable the overwrite option in the app.

## Build Locally

```bash
python3 -m unittest discover -s tests
./build_mac_silicon.sh
```

The build creates:

- `dist/Local File Renamer V1_0.app`
- `downloads/Local_File_Renamer_v1_0_macOS_Apple_Silicon.zip`

## Notarized Public Release

For a public build that opens normally on downloaded Macs, sign and notarize with an Apple Developer ID certificate:

```bash
export CODESIGN_IDENTITY="Developer ID Application: Your Name (TEAMID)"
export NOTARY_PROFILE="your-notarytool-profile"
./notarize_mac_release.sh
```

## Versioning

Each update should increment `VERSION`, add a `CHANGELOG.md` entry, build a new versioned app name, and publish a new GitHub release.
