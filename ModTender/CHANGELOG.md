# Changelog

## 0.10.0
- **Personalize ModTender** (Settings → Personalize, saved per user):
  - Profile picture: pick any image (cropped to a circle), or keep your initial and choose its color
  - A greeting on the Dashboard ("Good evening, …")
  - Favorite games: star a game with ☆ next to the game list to pin it to the top
  - Choose which page ModTender opens on
  - Text size (Small to Extra large) and a compact layout that fits more rows on screen

## 0.9.0
- **User accounts on this PC.** Everyone can have their own ModTender settings, theme, games and backup folder. Pick who's using ModTender on the new sign-in screen, and switch users from the bottom of the sidebar.
  - Optional PIN per user (after 5 wrong tries the sign-in waits 30 seconds)
  - Settings → Users: change your name, set or remove your PIN, add users, delete your user
  - With a single user and no PIN, ModTender opens straight away as before. Tick "Always show the sign-in screen" to change that.
  - Your existing settings become your first user, named after your Windows account.

## 0.8.0
- **Script conflict detection for The Witcher 3.** When two mods change the same script file, only one of them works. ModTender now lists which mods clash, which files, and which mod's version is currently used, and points you to Script Merger.
- **Out-of-date merge warning:** if you update a script mod after running Script Merger, ModTender tells you to merge again.

## 0.7.1
- **The Witcher 3: Wild Hunt support.** Finds the game on Steam or GOG, scans its mods folder and Steam Workshop items, and flags mod folders the game ignores because their name doesn't start with "mod" (Fix renames them). Zipped mods left in the mods folder are flagged too.
- Witcher 3 added to the Get mods page: Nexus Mods, the Steam Workshop, Community Patch - Shared Imports, Script Merger and REDkit, plus install tips.

## 0.7.0
- **Steam Workshop mods are scanned too.** RimWorld and Euro/American Truck Simulator show their Workshop mods next to local ones, and every other Steam game you have Workshop mods for gets its own entry in the game list.
  - Workshop items show their real names (RimWorld About.xml, SCS manifest.sii) and a Workshop page button
  - Catches empty or broken Workshop downloads, Workshop items with programs inside, and a local copy of a mod you're also subscribed to (Fix keeps the Workshop one)
  - Missing RimWorld dependencies link straight to a Workshop search
  - ModTender never moves Workshop files, since Steam would just re-download them
- **New Get mods page:** trusted places to download mods for each supported game, which ones are official, the mod loaders you need first, game-specific tips and safety advice. The list updates itself from GitHub, without needing a new ModTender version.

## 0.6.0
- **ModTender is now a real Windows app.** Install it with **ModTender-Setup.exe**: no Python needed, Start menu and desktop shortcuts, and an uninstaller in Windows Settings → Apps. It installs just for you, so no administrator prompt.
- **New logo:** a cog with an M in the middle. The sidebar version follows your accent color.
- In-app updates now download and run the installer silently, then reopen ModTender.
- "Updated to …" message after every update.
- The script version (run.bat) still works and still updates itself.

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
