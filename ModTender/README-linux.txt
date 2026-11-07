ModTender for Linux (test build)
================================

1. Extract this archive anywhere (for example ~/Apps/ModTender).
2. Open the ModTender folder and run ./ModTender (double-click it, or run it from a terminal).

ModTender finds:
- Steam games (native Steam, the Debian/Ubuntu package and the Flatpak version), including
  mod folders inside Proton prefixes for Windows games like Farming Simulator and Arma Reforger.
- Steam Workshop mods for every game.
- Minecraft in ~/.minecraft.
For anything else, use "Add game" and pick the mods folder.

Notes for this test build:
- Settings and backups live in ~/.local/share/ModTender.
- Virus scanning uses ClamAV if it's installed (sudo apt install clamav). Without it, mods aren't checked.
- "Check for updates" downloads and installs new versions by itself, then restarts ModTender.
- If it won't start, run it from a terminal and send the error to the developer, or use
  "Report a problem" in the sidebar.
