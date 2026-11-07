# ModTender privacy policy

_Last updated: November 7, 2026_

ModTender is a mod manager that runs on your PC. It has no accounts, no ads and no analytics, and it doesn't sell or share your data.

## What stays on your PC

Everything ModTender knows about you and your games is stored only on your computer:

- your settings, themes, local ModTender users and PINs (PINs are stored as one-way hashes),
- the list of your games and mods, scan results and virus-scan results,
- backups of your mods, and mods you turn off or quarantine,
- ModTender's log file.

On Windows this is in `%LOCALAPPDATA%\ModTender` (backups default to your Documents folder). On Linux it's in `~/.local/share/ModTender`. Uninstalling ModTender and deleting that folder removes all of it.

## When ModTender connects to the internet

ModTender only connects to the services below, and only for the reasons listed. None of them receive your name, email address or files.

| Service | Why | What is sent |
|---|---|---|
| GitHub (github.com) | Checking for ModTender updates and downloading them (not in the Microsoft Store version), and refreshing the list of where to get mods for each game | A normal web request |
| Modrinth (modrinth.com) | **Mod updates** and **Match mods** for Minecraft | The SHA-1 fingerprints of your Minecraft mod files, your mod loader and Minecraft version |
| Steam (steampowered.com) | Showing the names of Steam Workshop items and Steam games | The Workshop item and game ID numbers |
| A link you paste | **Match mods** with a Farming Simulator server stats link | A request to that link only |
| Modpack download links | **Download missing** in Match mods, from a Modrinth pack you opened | A request to the download links in that pack |

Virus scanning uses the antivirus already on your PC (Microsoft Defender, or another antivirus through Windows' scanning interface, or ClamAV on Linux). Files are checked on your computer and are not uploaded by ModTender.

## Problem reports

**Report a problem** saves a zip file on your Desktop with your description, ModTender's log, your mod list and basic system information. These can include folder paths on your PC, which usually contain your Windows user name. Nothing is sent automatically. ModTender can open a GitHub page where you may choose to attach the zip, and anything you post there is public under GitHub's own privacy policy.

## Children

ModTender doesn't collect personal information from anyone, including children.

## Changes and contact

If this policy changes, the new version will be posted here with a new date. Questions: open an issue at https://github.com/Dirty-Mike-debug/ModTender/issues
