# Changelog

## 1.5 - 2026-10-06

- Added optional Rename copies mode to keep source files in place.
- Default the copy destination to a new folder in Downloads, with an editable path and Browse control.
- Copy files under their desired names and report destination paths and per-file results.
- Keep the original rename plan intact in copy mode and save a separate results plan in the output folder.
- Protect source folders and skip existing output names unless overwrite is enabled.

## 1.4 - 2026-10-05

- Scan the selected folder before choosing where to save a CSV or spreadsheet.
- Report file access and subfolder permission errors instead of silently omitting files.
- Offer to include subfolders when no files are found directly in the selected folder.
- Prevent empty scans from creating or replacing a rename plan with a header-only export.

## 1.3 - 2026-07-13

- Replaced the app icon with the updated pomegranate tile artwork.
- Regenerated the full macOS `.icns` icon set.
- Updated the public download page icon asset.

## 1.2 - 2026-07-10

- Added a custom pomegranate tile app icon.
- Generated and applied a full macOS `.icns` icon set.
- Added the icon to the public download page.

## 1.1 - 2026-06-30

- Refreshed the desktop app with a soft purple and grey layout.
- Removed the single rename row workflow.
- Added CSV and `.xlsx` spreadsheet export options.
- Added plan browsing and loading for both CSV and `.xlsx` spreadsheets.
- Updated the public download page with the same visual direction.

## 1.0 - 2026-06-29

- Initial Apple Silicon macOS app.
- Added folder scanning to CSV.
- Added CSV loading and manual rename row input.
- Added confirmed local file rename execution.
- Added versioned PyInstaller build and zip packaging.
