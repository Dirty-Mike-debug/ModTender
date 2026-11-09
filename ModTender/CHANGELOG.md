# Changelog

## 0.29.1
- Crash log reader: Minecraft crashes like "Mod 'architectury' is not available!" while starting are a side effect of another mod failing to load first. ModTender no longer blames the mods in the stack trace for these; it reads latest.log to find the mod that actually failed, or says so plainly if it can't tell.
- Crash log reader: catches NeoForge's "Failed to create mod instance. ModID: …" lines and more mixin notes in stack traces.

## 0.29.0
- **Mod profiles** (Mods page → Profile). Save which mods are on as a named profile ("Multiplayer", "Solo heavy mods"…) and switch between them in one click. ModTender turns the profile's mods on and the rest off. Nothing is deleted, and the setup you had before is saved as "Before switching" so you can undo. The button shows which profile matches your mods right now. Free: 2 profiles per game; Pro: unlimited. Not available for games whose launcher or load order file decides what loads (Skyrim, Fallout 4, BG3, RimWorld, Arma, DayZ, Total War).
- **DayZ.** @mods in the game folder plus Workshop mods, a check for two mods shipping the same addon, crash log reading (.RPT), game update warnings and Play. Installing a zip puts it in an @folder automatically.
- **Total War: Warhammer III.** .pack mods in the data folder plus Workshop mods. Creative Assembly's own packs are recognized and protected. Flags packs made for older Total War games (they won't load), damaged packs, and the same mod both in the data folder and from the Workshop.
- **Planet Zoo.** Mod folders in win64\ovldata, with Frontier's own content protected. Flags mods unzipped one folder too deep (the most common reason a new species doesn't show up). Get mods lists ACSE, which most species mods need.

## 0.28.1
- **Tidy-up pass.**
- The mouse wheel no longer changes a drop-down (theme, game, text size…) when you're just scrolling a page past it. Click the box first if you want to use the wheel on it.
- Long game names in the sidebar now end with "…" instead of being cut off mid-word. Hover to see the full name.
- Steam library paths now show with their proper capitals (C:\Program Files (x86)\Steam…) instead of all lowercase.
- Get mods: a Steam Workshop game now shows under its own name instead of "Other games", without a second Steam Workshop card, and the tip names your game.
- Issues: when there's nothing wrong, the details panel says so and points to the crash log reader and Find broken mod.
- Backups: for games whose mods all come from the Workshop, the empty backup list and buttons are hidden and Back up now is greyed out.
- "Show in Explorer" is now "Show in folder", so it reads right on Linux too. Small code clean-ups.

## 0.28.0
- **Welcome tour.** The first time ModTender opens, a short five-screen tour shows which modded games it found and the four things worth knowing: scan and fix, Play and Find broken mod, backups, and staying safe. The last screen lets you pick a game and make a first backup in one click. See it again from Settings → Updates → Show welcome tour.

## 0.27.0
- **ModTender Pro is built in, ready for launch.** Everything that finds and fixes problems stays free. Pro (a one-time purchase through Gumroad, unlocked with the license key from the receipt) adds automatic backups and unlimited backup history, updating all Minecraft mods at once, one-click fixes in Match mods, the Space saver, custom colors, and a Pro badge. One key works on up to 5 PCs, and Pro keeps working offline.
- Pro isn't on sale yet, so nothing is locked in this version.

## 0.26.0
- **Getting ready for the Microsoft Store.** Each release now also builds a Microsoft Store package. The Store version is signed by Microsoft (no more "Windows protected your PC" warning) and gets its updates from the Store, so its own updater is switched off. The GitHub version keeps updating itself as before.
- Privacy policy published at github.com/Dirty-Mike-debug/ModTender/blob/main/PRIVACY.md.

## 0.25.0
- **Space saver** (Dashboard → More). Finds mod files stored more than once across all your games and packs (for example the same .jar in ATM10 and ATM11) and keeps just one copy on disk using hard links. Every pack still has its own normal file. Only byte-for-byte identical files on the same drive are shared; OneDrive folders and Steam Workshop items are never touched. When a launcher updates a mod later, that pack simply gets its own copy again. **Undo space saver** turns everything back into separate copies.

## 0.24.0
- **Play button** (Dashboard). ModTender checks your mods first and warns about anything that would stop the game starting (with "Show me" or "Play anyway"), then starts the game through Steam.
- **Crash watching.** While you play, ModTender watches the game's crash reports and logs. If the game crashes, ModTender pops up with the mod most likely to blame and a one-click "Turn off" (or Find broken mod when no single mod is named). The status bar shows "Watching … for crashes"; click it to stop.
- Minecraft packs are checked and watched too; start them from CurseForge or the Minecraft Launcher as usual.

## 0.23.0
- **Automatic updates on Linux.** Check for updates → Update now downloads the new Linux version, checks it, swaps it in and restarts ModTender, just like on Windows. If anything goes wrong, the previous version is put back. (Linux users on 0.21 or 0.22 need to update by hand once to get this.)

## 0.22.0
- **Deadlock support.** Finds your mods in Deadlock\game\citadel\addons and checks the three things that stop them working:
  - **gameinfo.gi not set up**: every Deadlock update puts the original file back, which switches all mods off. ModTender spots it and can add the line for you (keeping a backup), or you can use Deadlock Mod Manager's Launch Modded.
  - **Wrong file names**: Deadlock only loads pak01_dir.vpk to pak99_dir.vpk. Fix renames mods (and their _000 parts) to free numbers and remembers their original names, so the Mods page still shows "CoolHUD" instead of pak04_dir.vpk.
  - **Mods that change the same files**: ModTender reads inside each .vpk and tells you which mod wins (lower numbers win).
- Drag a .vpk or a GameBanana zip onto ModTender and it's named correctly and placed in addons automatically.
- Deadlock added to game update warnings and Get mods. Find broken mod works for Deadlock too.

## 0.21.0
- **Linux test build.** Download ModTender-<version>-linux-x64.tar.gz, extract it and run ModTender. It finds Steam (native, Debian/Ubuntu and Flatpak), Workshop mods, mod folders inside Proton for Windows games (Farming Simulator, Arma Reforger, The Sims 4...), and ~/.minecraft. Settings live in ~/.local/share/ModTender. Virus scanning uses ClamAV if it's installed.
- The script version now includes run.sh for Linux and macOS.

## 0.20.0
- **Arma 3 support.** Finds your Steam Workshop mods and local @mods in the game folder, with names read from each mod's meta.cpp / mod.cpp. Warns when two mods contain the same addon (.pbo), which usually means a library like CBA is loaded twice, and when mods have no signing key (.bikey), which gets you kicked from servers that verify signatures. Crash logs (.rpt) are read too, including "addon X requires addon Y" errors.
- **Arma Reforger support.** Finds your Workshop downloads in Documents\My Games\ArmaReforger\addons and reads each mod's name, version and dependencies from ServerData.json. Flags missing dependencies (with a link to the Reforger Workshop) and mods that didn't finish downloading. Reads Reforger's logs after a crash.
- **Match mods** now reads Arma 3 Launcher presets (.html exports and .preset2 files) and Arma Reforger server config.json files, matching by Workshop ID or mod ID, so you can see exactly what a group or server runs that you don't.
- Game update warnings for Arma 3 and Reforger, and both games added to Get mods.
- Mod info files are now found regardless of capital letters in their names.

## 0.19.0
- **Game update warnings.** ModTender notices when Steam updates one of your games and puts a warning on the Issues page: what usually breaks after a patch for that game (script extenders, BepInEx plugins, SMAPI, Cyberpunk's frameworks...), what to do about it, and which of your mods are most at risk. Dismiss it once you've checked.
- **Heads-up when Steam has an update waiting**, so you can back up your mods before it installs.

## 0.18.0
- **Virus scan for mods.** Every mod you install with ModTender, every Modrinth update and every modpack download is checked with your antivirus first; anything flagged is blocked and never reaches the game. Uses Microsoft Defender when it's on, and otherwise Windows' antimalware interface, which passes the file to whatever antivirus you have (Norton, Bitdefender and so on).
- **Scan for viruses** (Mods page, More menu) checks all your current mods. Results are remembered, so a mod is only checked again when it changes or after 30 days.
- New **Virus scan** column on the Mods page: Clean, Flagged, or not checked yet. Flagged mods show up on the Issues page as critical, with a one-click move to quarantine.
- Settings → Backups & scanning: turn the automatic check off if you need to.

## 0.17.0
- **Match mods with a server or friend.** New card on the Dashboard (also in the More menus). Open a friend's ModTender mod list, a Farming Simulator server's stats file or link, a savegame's careerSavegame.xml, a Modrinth modpack (.mrpack), or paste a list of names, and see which mods you're missing, have turned off, have a different version of, or have extra. One click turns on the ones you have but disabled, downloads missing mods from Modrinth packs (checked against the pack's checksums), turns off extras, or opens the missing ones on ModHub / Modrinth. **Copy as text** gives you the differences to paste into Discord.
- **Share my mod list** saves a small .modtender file listing your turned-on mods, for friends to match.

## 0.16.1
- Tidier pages: less-used buttons (open folder, save report, show in Explorer, Workshop page, read crash log, scan again) moved into a **More** menu on the Dashboard, Mods and Issues pages.
- **Find broken mod** now has its own card on the Dashboard, under the stats.

## 0.16.0
- **Find the broken mod.** New on the Dashboard. When something crashes or breaks and the logs don't say why, ModTender turns mods off in halves, you start the game and say whether the problem still happens, and it narrows down to the one mod causing it: about 11 rounds for 500 mods. The first round checks whether it's a mod at all, the last confirms the result. Mods that other mods need are turned off together, so you never get "missing dependency" errors along the way. Progress is saved, so you can close ModTender and carry on later, and Stop always puts everything back. Works for Minecraft, Farming Simulator, Stardew Valley, Valheim, Cyberpunk, Witcher 3, The Sims 4 and custom games. Not yet for Skyrim, Fallout 4, Baldur's Gate 3, RimWorld and the truck sims, because moving their mods would scramble their load order or mod list.
- Minecraft mods now record which other mods they need.

## 0.15.0
- **Install mods by drag and drop.** Drop downloaded mods anywhere on the window (or use **Install mod** on the Mods page) and ModTender puts them where the game expects: copies .jar/.zip/.package files, unpacks zips for games that use folders (Stardew, RimWorld, Witcher 3), puts Valheim Thunderstore packages into BepInEx/plugins, sends Cyberpunk files to the right game folders, and unpacks Skyrim/Fallout mods into Data. Older copies with the same name go to quarantine instead of being overwritten. Tells you plainly when something can't be installed (RAR/7z files, FOMOD installers).
- **Mod updates (Minecraft).** **Mod updates** on the Mods page checks Modrinth for newer versions that match your loader and Minecraft version. Pick which to install; downloads are checked against Modrinth's checksum, and old versions are kept in disabled mods so you can switch back. Warns before updating mods inside a CurseForge modpack.
- **Report a problem** in the sidebar: saves a zip with your description, ModTender's log, your scan and system info, and opens a pre-filled GitHub report. Nothing is sent automatically.

## 0.14.3
- Fixed: mods turned off by CurseForge (files ending in .jar.disabled) were reported as files the game can't use, and Fix all moved them out of the mods folder. They're now left alone.

## 0.14.2
- Fixed: Forge/NeoForge mods that list an older release of the same Minecraft line (for example "1.21 only" in a 1.21.1 pack) were wrongly reported as the wrong version. They load fine, so they're no longer flagged. Mods built for a different line (like 1.20 in a 1.21 pack) are still caught.

## 0.14.1
- Fixed: scanning a Minecraft instance could fail with "'list' object has no attribute 'values'" when a mod lists its dependencies in an unusual way
- A mod with unusual metadata can no longer stop a scan

## 0.14.0
- **Minecraft: wrong loader or wrong version.** ModTender reads which mod loader (Forge, NeoForge, Fabric, Quilt) and which Minecraft versions each mod is built for, and warns about mods that won't load in your instance. For CurseForge instances it knows the exact loader and version; for other folders it works out the loader from your other mods. Understands multi-loader mods, Sinytra Connector, and NeoForge 1.20.1 loading Forge mods.
- **Crash log reader.** After a crash, the Issues page tells you which mod is most likely to blame and offers to turn it off to test. Reads Minecraft crash reports and launch logs (missing dependencies, wrong versions, mixin errors), Stardew Valley's SMAPI log (skipped mods, errors), BepInEx logs for Valheim, and Farming Simulator's log.txt. Old crashes stop showing once you change your mods.
- **Read crash log** button on the Issues page: open any crash report or log by hand.

## 0.13.0
- **Cyberpunk 2077 archive conflicts:** ModTender reads the file list inside every .archive mod (including REDmods) and tells you when two mods replace the same game files, which one the game actually uses, and how many files are affected. Follows the game's real load order: modlist.txt if you have one, otherwise alphabetical, with REDmods last.
- Damaged or incomplete .archive files are reported
- Cyberpunk's modlist.txt is no longer flagged as a file the game can't use

## 0.12.0
- **Skyrim SE and Fallout 4 load-order checks:** plugins missing a required master (which crash the game on startup), masters that are installed but turned off, masters loading after the plugins that need them, damaged plugins, the 254 / 4096 plugin limits, and plugins installed but turned off. Reads plugins.txt and each plugin's header.
- **Baldur's Gate 3 mod list check:** mods installed but not in your mod list, and mods in the list whose file is missing (which can stop saves loading).
- **The Sims 4** is now supported: finds your Mods folder and checks it.
- **Get mods** now also covers The Sims 4, Elden Ring, Terraria, Lethal Company and Satisfactory.
- Base-game files (like Skyrim.esm) are never offered as "extra copies" to disable
- Huge base-game archives aren't fingerprinted, so first scans of Skyrim/Fallout are much faster
- Release notes in the update window show as plain text

## 0.11.0
- **Space-saving backups.** Each mod file is stored only once, so a new backup only takes space for mods that changed. Daily backups of a big mod folder cost almost nothing extra. Older backups still work.
- **Automatic backups** per game (Backups page): every day or every week, and optionally whenever ModTender notices your mods changed.
- **What changed since?** Pick any backup to see which mods were added, removed, updated, turned on or turned off since then, and restore it from the same window.
- **Mark as working + Roll back:** mark a backup from when the game ran fine, then return to it with one click if it starts crashing. Working setups are never deleted automatically.
- The Dashboard shows how many changes you've made since your last backup.
- Fixed: harmless shortcut files inside mods (like Style Colonies blueprints) were flagged as programs
- The Workshop page button only shows for games with Workshop mods

## 0.10.3
- Opening ModTender while it's already open now reliably brings its window to the front
- Steam games that only show as "Steam app 123456" get their real name (looked up once from the Steam store)
- For Workshop-only games the Dashboard says backups aren't needed, since Steam keeps those mods

## 0.10.2
- In-app updates now close any other open ModTender windows first, so they can't stall the update, and keep a setup log in case something goes wrong.

## 0.10.1
Fixes from a look at the app on a real PC:
- Dashboard cards no longer stretch to fill the window
- "Healthy", "Enabled" and "No problems" are always green, whatever your accent color
- Buttons never get their labels cut off, and long page descriptions wrap
- The ☆ favorite button and the game list are wider, and the full game name shows on hover
- Only one ModTender window: opening it again brings the open window to the front
- Steam Workshop items show their real names (looked up from Steam once and remembered)
- Get mods links the Steam Workshop for Workshop-only games like Counter-Strike 2
- A greyed-out Fix all looks disabled; color pickers in Settings are spaced properly

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
