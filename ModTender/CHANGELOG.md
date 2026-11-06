# Changelog

## 0.5.1
- **Fixed:** Minecraft (Forge/NeoForge) mods could be mistaken for "older versions" of the mods they depend on, so Fix all disabled them (for example Ad Astra, EnderDrives and CC: Tweaked in All the Mods 10). ModTender now reads only the mod's own id.
- Fix all is more careful: when versions are matched by file name only (not by the id inside the mod), that fix is left for you to apply by hand. Farming Simulator is unaffected.
- New log file at `%LOCALAPPDATA%\ModTender\logs\modtender.log` recording scans, fixes, enables/disables, backups, updates and errors. Settings → Updates → Open log folder.

## 0.5.0
- **Updates install from inside the app.** Check for updates → Update now downloads the new version, installs it and restarts ModTender. No browser needed. Your settings, backups and mods aren't touched, and the previous version is kept in case anything goes wrong.

## 0.4.0
- New **Fix** and **Fix all** buttons: ModTender can now repair most issues for you, and offers to back up your mods first
  - Damaged mods and stray files are moved to a quarantine folder
  - Extra copies and older versions of a mod are disabled, keeping the best one
  - Farming Simulator mod packs are unpacked, mods zipped one folder too deep are rebuilt, and bad file names are fixed
- Missing-dependency check: flags mods that need another mod you don't have (with a search link) or have disabled (one-click enable). Works for Farming Simulator and Stardew Valley.
- Quarantine button on the Backups page

## 0.3.0
- Redesigned interface: icons, a health gauge, cleaner tables and spacing
- Customizable colors: Midnight, Graphite, Nord and Daylight themes, eight accent colors, and a picker for every main color (Settings → Appearance)
- Check for updates button (sidebar and Settings → Updates)

## 0.2.0
- First release of ModTender
- Finds Steam, CurseForge and common game mod folders automatically
- Dashboard with health score, mod list with enable/disable, issue checker, backups with safe restore, text reports
