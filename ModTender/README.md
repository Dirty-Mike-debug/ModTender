# ModTender 0.3

A mod manager and safety tool for Windows. It finds your games, checks every mod for problems, explains how to fix them, and keeps backups you can restore at any time.

## Updating from an older version

Extract the new zip **into your existing ModTender folder** and choose *Replace the files*. Your settings, backups and disabled mods are stored separately and stay untouched.

## Run it

1. Install **Python 3.10 or newer** from [python.org](https://www.python.org/downloads/). During setup, tick **"Add python.exe to PATH"**.
2. Double-click **`run.bat`**.

The first launch sets up a private Python environment and downloads PySide6 (about 1–2 minutes). After that, it opens straight away.

To run it by hand instead: `pip install -r requirements.txt` then `python main.py`.

## What it does

- **Finds your games automatically.** It checks Steam libraries (on any drive), your real Documents folder (even when OneDrive moved it), AppData, and every CurseForge Minecraft instance. For anything else, use **+ Add game** and pick the mods folder.
- **Dashboard**: a health score, mod count, number of issues and your last backup, all in one place.
- **Mods**: search, sort and filter your mods, with versions read from the mods themselves (Farming Simulator `modDesc.xml`, Fabric/Quilt/Forge, Stardew SMAPI). **Disable** moves a mod out of the game's folder; **Enable** moves it back. Nothing is deleted.
- **Issues** detected:
  - damaged or incomplete downloads
  - the same mod installed twice, and several versions of one mod
  - mods that contain programs or scripts (`.exe`, `.bat`, `.ps1`…), as a safety warning
  - Farming Simulator 22/25: file names the game silently ignores, missing `modDesc.xml`, and mod packs that need unzipping
  - files the game can't use (`.rar`, readmes, unfinished downloads)
- **Backups**: a one-click snapshot of the whole mods folder. Restoring never deletes anything: your current folder is renamed to `mods.before-restore-…` first. The oldest backups are cleaned up automatically (10 per game by default).
- **Appearance**: four built-in themes (Midnight, Graphite, Nord, Daylight), eight one-click accent colors, and a color picker for the background, sidebar, cards, borders and text. Settings → Appearance.
- **Check for updates**: the button at the bottom of the sidebar (or Settings → Updates) checks the project's GitHub Releases page for a newer version. Set `UPDATE_REPO` in `modtender/__init__.py`, or enter the repository in Settings, once a repo exists.
- **Export report**: a plain-text summary to paste when asking for help on a forum or Discord.

## Supported games out of the box

Farming Simulator 25 & 22, Minecraft Java (plus CurseForge instances), Stardew Valley, Skyrim SE, Fallout 4, Cyberpunk 2077, Baldur's Gate 3, Valheim (BepInEx), RimWorld, Euro Truck Simulator 2, American Truck Simulator, Cities: Skylines II, SnowRunner. Any other game works through **+ Add game**.

To add a game permanently, add a `GameDef` entry to `modtender/core/games.py`.

## Where files go

| What | Where |
|---|---|
| Settings, scan cache | `%LOCALAPPDATA%\ModTender\` |
| Disabled mods | `%LOCALAPPDATA%\ModTender\disabled\<game>\` |
| Backups (default, can be changed in Settings) | `%LOCALAPPDATA%\ModTender\backups\<game>\` |

## Project layout

```
main.py                 entry point
modtender/core/         no UI code; can be tested on its own
  games.py              game list + Steam/CurseForge detection
  scanner.py            reads mods, metadata, hashes (cached)
  issues.py             problem detection + health score
  backups.py            create / list / restore / prune
  manager.py            enable / disable
  report.py             text report
  settings.py           JSON settings
  updates.py            GitHub Releases update check
modtender/ui/           PySide6 interface (theme, pages, main window)
```

## Roadmap

1. ~~Professional UI / dashboard~~ (this version)
2. ~~Auto game/mod-folder detection~~ (first pass done; more games to add)
3. Deeper conflict detection: files that overwrite each other, dependency checks
4. Scheduled backups and automatic recovery
5. Free vs Pro split
6. Windows installer (PyInstaller + Inno Setup), then Steam
