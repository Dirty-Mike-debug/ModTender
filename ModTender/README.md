# ModTender 0.25

A mod manager and safety tool for Windows. It finds your games, checks every mod for problems, explains how to fix them, and keeps backups you can restore at any time.

## Updating from an older version

Use **Check for updates → Update now** inside the app (installed app: from 0.6; script version: from 0.5). For older versions, extract the new zip **into your existing ModTender folder** and choose *Replace the files*. Your settings, backups and disabled mods are stored separately and stay untouched.

## Install

Download **ModTender-Setup-<version>.exe** from [Releases](https://github.com/Dirty-Mike-debug/ModTender/releases/latest) and run it. ModTender installs for your Windows user only (no admin prompt) and adds Start menu and desktop shortcuts. Uninstall it from Windows Settings → Apps. Uninstalling leaves your settings, backups and disabled mods in `%LOCALAPPDATA%\ModTender`.

Windows SmartScreen may warn about an unrecognized app the first time, because the installer isn't code-signed yet. Click **More info → Run anyway**.

### Script version (for development)

Install Python 3.10+ (tick "Add python.exe to PATH"), then double-click `run.bat`. The first launch sets up a private Python environment. To build the .exe and installer yourself, run `build.bat` (needs [Inno Setup 6](https://jrsoftware.org/isinfo.php) for the installer step).

## What it does

- **Finds your games automatically.** It checks Steam libraries (on any drive), your real Documents folder (even when OneDrive moved it), AppData, and every CurseForge Minecraft instance. For anything else, use **Add game** and pick the mods folder.
- **Steam Workshop**: Workshop mods are scanned alongside local ones, and every Steam game you have Workshop mods for appears in the game list. ModTender never moves Workshop files; the Workshop page button takes you to Steam to unsubscribe.
- **Get mods**: trusted download sites per game (official sites, community sites, required mod loaders) plus safety tips. The list lives in `modtender/assets/mod_sources.json` and the app fetches the latest copy from GitHub.
- **Dashboard**: a health score, mod count, number of issues and your last backup, all in one place.
- **Mods**: search, sort and filter your mods, with versions read from the mods themselves (Farming Simulator `modDesc.xml`, Fabric/Quilt/Forge, Stardew SMAPI). **Disable** moves a mod out of the game's folder; **Enable** moves it back. Nothing is deleted.
- **Issues** detected:
  - damaged or incomplete downloads
  - the same mod installed twice, and several versions of one mod
  - mods that contain programs or scripts (`.exe`, `.bat`, `.ps1`…), as a safety warning
  - Farming Simulator 22/25: file names the game silently ignores, missing `modDesc.xml`, and mod packs that need unzipping
  - The Witcher 3: mod folders the game ignores, script conflicts between mods, and Script Merger results that are out of date
  - Skyrim SE / Fallout 4: missing or turned-off masters, masters in the wrong order, damaged plugins, plugin limits
  - Cyberpunk 2077: archive mods that overwrite each other's files, and which one wins
  - Minecraft: mods built for a different mod loader or Minecraft version
  - Deadlock: gameinfo.gi reset by an update, .vpk files with names the game won't load, mods overriding each other
  - Arma 3: two mods shipping the same addon, mods without signing keys; Arma Reforger: missing dependencies and unfinished downloads
  - Crash logs: names the mod most likely behind a crash (Minecraft, Stardew Valley, Valheim, Farming Simulator)
  - Baldur's Gate 3: mods not in the mod list, and listed mods whose file is missing
  - files the game can't use (`.rar`, readmes, unfinished downloads)
- **Space saver** (Dashboard → More): stores identical mod files once across all your games and packs, with Undo.
- **Play** (Dashboard): checks for problems that would stop the game starting, launches it through Steam, and watches for a crash, naming the likely mod the moment it happens.
- **Find the broken mod** (Dashboard): turns mods off in halves while you test the game, and narrows a crash or bug down to the one mod causing it. Handles mods that need other mods, saves progress, and always puts everything back.
- **Match mods** (Dashboard): compare your mods with a Farming Simulator server or savegame, a friend's shared mod list, a Modrinth modpack or a pasted list, then turn on, download or find what's missing. **Share my mod list** saves a file friends can match.
- **Virus scan**: new mods, updates and downloads are checked with your antivirus (Microsoft Defender, or whichever antivirus you have) before they're installed. **Scan for viruses** checks everything you already have, and the Mods page shows a Clean / Flagged badge for each mod.
- **Game update warnings**: when Steam patches a game, the Issues page says what usually breaks for that game and which of your mods are most at risk. It also warns when an update is waiting, so you can back up first.
- **Install mods**: drag downloaded mods onto the window (or **Install mod** on the Mods page). ModTender copies or unpacks them into the right place for the game, and moves any older copy to quarantine instead of overwriting it.
- **Mod updates** (Minecraft): checks Modrinth for newer versions that match your loader and Minecraft version, verifies each download, and keeps the old version in disabled mods.
- **Crash logs**: after a crash, the Issues page names the mod most likely to blame. **Read crash log** opens any log by hand.
- **Fix / Fix all**: most issues can be repaired with one click. Fix all applies every safe fix in the right order and can back up your mods first. Nothing is ever deleted: removed files go to ModTender's disabled or quarantine folder (Backups → Quarantine).
- **Missing mods**: flags mods that need another mod you don't have installed or have disabled (Farming Simulator and Stardew Valley).
- **Backups**: snapshots of the whole mods folder where each mod file is stored only once, so repeat backups take little space. Automatic backups (daily, weekly, and/or when mods change), "What changed since?" for any backup, and "Mark as working" + "Roll back to working setup". Restoring never deletes anything: your current folder is renamed to `mods.before-restore-…` first. The oldest backups are cleaned up automatically (10 per game by default, working setups are always kept).
- **Appearance**: four built-in themes (Midnight, Graphite, Nord, Daylight), eight one-click accent colors, and a color picker for the background, sidebar, cards, borders and text. Settings → Appearance.
- **Updates**: *Check for updates* (bottom of the sidebar, or Settings → Updates) finds new versions on GitHub Releases. *Update now* downloads and installs it, then restarts ModTender. The previous version is kept in `.modtender-update\previous` and restored automatically if an install fails.
- **Users**: each person on the PC gets their own settings, theme and games, with an optional PIN.
- **Personalize**: profile picture or colored initial, Dashboard greeting, favorite games pinned to the top, start page, text size and compact layout. Online accounts are planned alongside Free vs Pro.
- **Report a problem** (sidebar): saves a zip with your description, the log and scan, and opens a pre-filled GitHub report. Nothing is sent automatically.
- **Export report**: a plain-text summary to paste when asking for help on a forum or Discord.

## Supported games out of the box

Farming Simulator 25 & 22, Minecraft Java (plus CurseForge instances), Stardew Valley, The Sims 4, Skyrim SE, Fallout 4, The Witcher 3, Cyberpunk 2077, Baldur's Gate 3, Valheim (BepInEx), RimWorld, Euro Truck Simulator 2, American Truck Simulator, Cities: Skylines II, SnowRunner, Arma 3, Arma Reforger, Deadlock. Any other game works through **Add game**, and every Steam game you have Workshop mods for is listed automatically.

To add a game permanently, add a `GameDef` entry to `modtender/core/games.py`.

## Where files go

| What | Where |
|---|---|
| Users | `%LOCALAPPDATA%\ModTender\users.json` (PINs stored as salted hashes) |
| Each user's settings | `%LOCALAPPDATA%\ModTender\users\<user>\settings.json` |
| Scan cache, logs | `%LOCALAPPDATA%\ModTender\` |
| Disabled mods | `%LOCALAPPDATA%\ModTender\disabled\<game>\` |
| Files moved by Fix | `%LOCALAPPDATA%\ModTender\quarantine\<game>\` |
| Backups (default, can be changed in Settings) | `%LOCALAPPDATA%\ModTender\backups\<game>\` |

## Project layout

```
main.py                 entry point
installer/ModTender.iss Inno Setup installer script
build.bat               build the .exe + installer locally
modtender/core/         no UI code; can be tested on its own
  games.py              game list + Steam/CurseForge detection
  scanner.py            reads mods, metadata, hashes (cached)
  issues.py             problem detection, health score, fix plans
  fixer.py              applies fixes (always reversible)
  backups.py            create / list / restore / prune
  manager.py            enable / disable
  report.py             text report
  settings.py           JSON settings (per user)
  users.py              local users and PINs
  sources.py            'Get mods' database (bundled + refreshed from GitHub)
  updates.py            GitHub Releases update check
  self_update.py        in-app download + install
modtender/ui/           PySide6 interface (theme, pages, main window)
```

## Roadmap

1. ~~Professional UI / dashboard~~ (this version)
2. ~~Auto game/mod-folder detection~~ (first pass done; more games to add)
3. Deeper conflict detection: ~~dependency checks~~, ~~Witcher 3 script conflicts~~; next: other games' file overrides
4. ~~Scheduled backups and recovery~~ (0.11)
5. ~~Local users~~ (0.9), then online accounts + Free vs Pro split
6. ~~Windows installer~~ (done in 0.6), code signing, then Steam
