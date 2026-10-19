# Changelog

## 1.2.0 - 2026-10-19

- SpaceHound is now branded **by Veneficus** (app, installer, Apps & features, exe details, reports)
- New "Midnight Desert" design: warm lamp-lit dark theme with drifting dust and dunes, amber JetBrains Mono
  readouts, wide Archivo headings, numbered sections, a terminal-style scan screen and a sand-toned light theme
- Recoloured logo: a sand hound with amber sonar waves on an espresso tile
- Warmer category, age and chart colours; HTML report restyled to match
- About section links to the GitHub project

## 1.1.0 - 2026-10-19

- New logo: a hound sniffing out "sonar" waves (icon, sidebar, scan screen)
- Built-in installer: `SpaceHound.exe --install` (or the Install button) adds SpaceHound to the
  Start menu / Windows search and to Apps & features; `--uninstall` removes it again
- "Update installed copy" and "Open installed app" when running a newer portable download
- CI uses current GitHub Actions versions

## 1.0.0 - 2026-10-18

First release.

- Parallel drive/folder scanner with low memory use, junction-safe and OneDrive-aware
- Overview with automatic "why is my disk full?" insights and drive composition bar
- Explorer, interactive treemap & sunburst (colour by type, age or folder)
- Largest files, file types, old files & forgotten folders, global search
- Smart cleanup with ~45 cache/temp rules and explained-only system items
- Duplicate finder (size → partial hash → BLAKE2), hard-link aware, auto-select, hard-link replacement
- Dev junk finder for node_modules, Gradle/Android, Rust, Python, .NET, Flutter, Unity, Unreal, CMake
- Empty folders, move to another drive, rescan folder, CSV/HTML export
- Scan snapshots with "what grew" comparison
- Installed apps with measured sizes and side-by-side old version detection
- Recycle Bin by default, protected paths, activity log
- Dark & light theme, single-file portable .exe
- "Deep space" design: aurora background, glass panels, Space Grotesk headings
- Disk Health score (0-100) with gradient gauge and one-click fixes
- Live sonar scan screen, Bubbles map mode, Ctrl+K command palette, animated counters and confetti
