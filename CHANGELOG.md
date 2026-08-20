# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/) once it
reaches 1.0.

## [0.2.4] - 2026-08-20

### Added

- A 30-second cooldown on manual Refresh clicks, shown as a "Wait Ns"
  countdown in place of the link. Anthropic's usage endpoint isn't a public
  API and is known to lock out hard — and not recover for the rest of the
  session — if polled too aggressively, so this stops click-spam before it
  can trigger that.

### Changed

- Clearer message when Anthropic does rate-limit a usage check: explains
  what happened and that it clears on its own, instead of a bare "rate
  limited" line.

### Fixed

- Tray tooltip crash when an error message was long enough to exceed
  Windows' 128-character `Shell_NotifyIcon` tooltip limit (hit for real by
  the friendlier rate-limit message above). Titles now truncate safely
  before being handed to the OS.

## [0.2.3] - 2026-08-20

### Added

- Hover states for the dashboard's Close/Refresh/Quit controls: a pill-shaped
  highlight, a brighter text color, a hand cursor, and a bigger hit box than
  the raw text glyphs.
- A small rotating spinner in place of the "Refresh" label while a
  manually-triggered fetch is in flight, cleared automatically once new data
  (or an error) arrives. Scoped to manual clicks — the silent 5-minute
  background auto-refresh doesn't spin.

## [0.2.2] - 2026-08-20

### Fixed

- Blurry/pixelated dashboard on scaled Windows displays (e.g. 150%, 200%).
  Tkinter isn't DPI-aware by default, so Windows rendered the popup at 96 DPI
  and stretched the bitmap to fit — the app now declares itself DPI-aware
  before any window is created, and the dashboard scales all of its own
  layout math (card size, margins, padding, bar height) to the real DPI.

### Added

- Dashboard screenshot in the README.

## [0.2.1] - 2026-08-20

### Changed

- The dashboard now opens on **any** click — left or right — instead of
  right-click showing a plain native popup menu you had to click "Open
  dashboard" inside of. Win32 tray context menus can't be styled at all, so
  Refresh and Quit moved fully into the dashboard itself as links.

## [0.2.0] - 2026-08-20

### Added

- A custom always-on-top Tk "flyout" dashboard, shown near the tray icon on
  click: a dark rounded card with colored progress bars for session (5h) and
  weekly (7d) usage, percent used, and reset countdowns — replacing the plain
  native tray menu, which can't be styled.

## [0.1.0] - 2026-08-20

### Added

- Initial release: a Windows system tray icon showing Claude plan usage.
- Reads the OAuth token Claude Code caches at `~/.claude/.credentials.json`
  and polls Anthropic's (unofficial) `/api/oauth/usage` endpoint on a
  5-minute background timer.
- Ring-gauge tray icon, color-coded green/yellow/red by usage level.
- Native right-click menu with session/weekly usage, reset times, manual
  refresh, and quit.
- MIT license, `pyproject.toml` packaging with a `claude-usage-tray`
  GUI entry point, and a Windows Startup shortcut installer script.
