"""Build the Microsoft Store package (.msix) from the PyInstaller output.

Run on Windows after `pyinstaller` has produced dist/ModTender:
    python installer/make_msix.py
The package is left unsigned: Partner Center signs it when it's submitted to the Store."""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist" / "ModTender"
LAYOUT = ROOT / "dist" / "msix-layout"

IDENTITY = "DirtyMikeProductions.ModTender"
PUBLISHER = "CN=DF6C1A86-9433-4FFB-B581-C4A9165DA7B2"
PUBLISHER_NAME = "DirtyMikeProductions"
DESCRIPTION = "Find, fix and back up mods for your games"

MANIFEST = """<?xml version="1.0" encoding="utf-8"?>
<Package
  xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
  xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10"
  xmlns:rescap="http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities"
  xmlns:desktop6="http://schemas.microsoft.com/appx/manifest/desktop/windows10/6"
  IgnorableNamespaces="uap rescap desktop6">
  <Identity Name="{identity}" Publisher="{publisher}" Version="{version}" ProcessorArchitecture="x64" />
  <Properties>
    <DisplayName>ModTender</DisplayName>
    <PublisherDisplayName>{publisher_name}</PublisherDisplayName>
    <Logo>Assets\\StoreLogo.png</Logo>
    <!-- Mods live in other programs' folders, including AppData (Minecraft, Baldur's Gate 3).
         Without this, files ModTender puts there would be hidden from the games. -->
    <desktop6:FileSystemWriteVirtualization>disabled</desktop6:FileSystemWriteVirtualization>
  </Properties>
  <Dependencies>
    <TargetDeviceFamily Name="Windows.Desktop" MinVersion="10.0.19041.0" MaxVersionTested="10.0.26100.0" />
  </Dependencies>
  <Resources>
    <Resource Language="en-us" />
  </Resources>
  <Applications>
    <Application Id="ModTender" Executable="ModTender\\ModTender.exe" EntryPoint="Windows.FullTrustApplication">
      <uap:VisualElements DisplayName="ModTender" Description="{description}" BackgroundColor="transparent"
        Square150x150Logo="Assets\\Square150x150Logo.png" Square44x44Logo="Assets\\Square44x44Logo.png">
        <uap:DefaultTile Wide310x150Logo="Assets\\Wide310x150Logo.png" />
      </uap:VisualElements>
    </Application>
  </Applications>
  <Capabilities>
    <rescap:Capability Name="runFullTrust" />
    <rescap:Capability Name="unvirtualizedResources" />
  </Capabilities>
</Package>
"""

LOGOS = {"StoreLogo.png": (50, 50), "Square44x44Logo.png": (44, 44), "Square150x150Logo.png": (150, 150),
         "Wide310x150Logo.png": (310, 150), "Square44x44Logo.targetsize-256_altform-unplated.png": (256, 256)}


def version() -> str:
    text = (ROOT / "modtender" / "__init__.py").read_text(encoding="utf-8")
    v = re.search(r'__version__\s*=\s*"(\d+)\.(\d+)\.(\d+)', text)
    return f"{v.group(1)}.{v.group(2)}.{v.group(3)}.0"  # the Store needs four parts, the last one 0


def logos(assets: Path) -> None:
    from PIL import Image
    icon = Image.open(ROOT / "modtender" / "assets" / "icon_256.png").convert("RGBA")
    assets.mkdir(parents=True, exist_ok=True)
    for name, (w, h) in LOGOS.items():
        side = min(w, h) if w == h else int(h * 0.8)
        tile = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        img = icon.resize((side, side), Image.LANCZOS)
        tile.paste(img, ((w - side) // 2, (h - side) // 2), img)
        tile.save(assets / name)


def makeappx() -> Path:
    kits = Path(r"C:\Program Files (x86)\Windows Kits\10\bin")
    found = sorted(kits.glob("10.*/x64/makeappx.exe"))
    if not found:
        sys.exit("makeappx.exe not found (install the Windows 10/11 SDK)")
    return found[-1]


def main() -> None:
    if not (DIST / "ModTender.exe").is_file():
        sys.exit(f"Build the app first: {DIST / 'ModTender.exe'} is missing")
    shutil.rmtree(LAYOUT, ignore_errors=True)
    shutil.copytree(DIST, LAYOUT / "ModTender")
    (LAYOUT / "ModTender" / "_internal" / "store_build.flag").write_text("Microsoft Store build\n", encoding="utf-8")
    logos(LAYOUT / "Assets")
    v = version()
    (LAYOUT / "AppxManifest.xml").write_text(MANIFEST.format(identity=IDENTITY, publisher=PUBLISHER, version=v,
                                                            publisher_name=PUBLISHER_NAME, description=DESCRIPTION),
                                             encoding="utf-8")
    out = ROOT / "dist" / f"ModTender-{v[:-2]}-store.msix"
    out.unlink(missing_ok=True)
    subprocess.run([str(makeappx()), "pack", "/d", str(LAYOUT), "/p", str(out), "/o"], check=True)
    print(f"Built {out} ({out.stat().st_size // 1_000_000} MB), version {v}")


if __name__ == "__main__":
    main()
