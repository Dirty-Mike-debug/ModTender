"""In-app updating: download the release zip, then swap the files in after ModTender closes.

Flow:
1. download_update()  - fetch the zip, check it, unpack it into <app>/.modtender-update/new
2. launch_installer() - start a small helper process, then the app quits
3. the helper waits for ModTender to exit, copies the new files over the old ones
   (keeping .venv), reinstalls requirements if they changed, and starts ModTender again.
The previous version's files are kept in .modtender-update/previous in case anything goes wrong.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from .. import __version__
from .log import log
from .updates import UpdateError, UpdateInfo

APP_DIR = Path(__file__).resolve().parents[2]  # folder holding main.py
STAGE = APP_DIR / ".modtender-update"


def can_self_update() -> bool:
    return (APP_DIR / "main.py").is_file() and (APP_DIR / "modtender" / "__init__.py").is_file()


def download_update(info: UpdateInfo, progress=None) -> Path:
    if not info.asset_url:
        raise UpdateError("This release has no download attached.")
    if STAGE.exists():
        shutil.rmtree(STAGE, ignore_errors=True)
    STAGE.mkdir(parents=True)
    zip_path = STAGE / "update.zip"
    req = urllib.request.Request(info.asset_url, headers={"User-Agent": f"ModTender/{__version__}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp, open(zip_path, "wb") as out:
            total = int(resp.headers.get("Content-Length") or info.asset_size or 0)
            done = 0
            while chunk := resp.read(256 * 1024):
                out.write(chunk)
                done += len(chunk)
                if progress and total:
                    progress(done * 90 / total, f"Downloading ModTender {info.latest}… {done // 1024} KB")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise UpdateError("The download failed. Check your internet connection and try again.") from exc

    if progress:
        progress(92, "Checking the download…")
    new = STAGE / "new"
    try:
        with zipfile.ZipFile(zip_path) as zf:
            if zf.testzip() is not None:
                raise UpdateError("The download is damaged. Please try again.")
            zf.extractall(new)
    except zipfile.BadZipFile as exc:
        raise UpdateError("The download is damaged. Please try again.") from exc

    # The zip holds a top-level ModTender/ folder; find the folder that contains main.py.
    root = next((p.parent for p in new.rglob("main.py") if (p.parent / "modtender" / "__init__.py").is_file()), None)
    if root is None:
        raise UpdateError("The download doesn't look like a ModTender release.")
    log.info("Update %s downloaded and unpacked to %s", info.latest, root)
    if progress:
        progress(100, "Update downloaded")
    return root


INSTALLER = r'''
import ctypes, os, shutil, subprocess, sys, time, traceback
from pathlib import Path

pid, src, dst = int(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
stage = dst / ".modtender-update"
log = open(stage / "update.log", "a", encoding="utf-8")

def say(msg):
    log.write(time.strftime("%H:%M:%S ") + msg + "\n")
    log.flush()

def wait_for_exit(pid, timeout=60):
    if os.name == "nt":
        SYNCHRONIZE = 0x00100000
        h = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, pid)
        if h:
            ctypes.windll.kernel32.WaitForSingleObject(h, timeout * 1000)
            ctypes.windll.kernel32.CloseHandle(h)
        time.sleep(0.5)
        return
    end = time.time() + timeout
    while time.time() < end:
        try:
            os.kill(pid, 0)
        except OSError:
            return
        time.sleep(0.2)

SKIP = {".venv", ".modtender-update", "__pycache__", ".git"}

def files(root):
    for p in root.rglob("*"):
        rel = p.relative_to(root)
        if p.is_file() and not (set(rel.parts) & SKIP):
            yield rel

try:
    say(f"waiting for ModTender (pid {pid}) to close")
    wait_for_exit(pid)
    old_req = (dst / "requirements.txt").read_text(encoding="utf-8") if (dst / "requirements.txt").exists() else ""

    prev = stage / "previous"
    for rel in files(dst):
        (prev / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(dst / rel, prev / rel)
    say("saved the previous version")

    new_files = set(files(src))
    for rel in new_files:
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        for attempt in range(20):  # a file can stay locked for a moment after the app exits
            try:
                shutil.copy2(src / rel, target)
                break
            except PermissionError:
                time.sleep(0.5)
        else:
            raise PermissionError(f"couldn't replace {rel}")
    # remove program files that no longer exist in the new version (only inside the package)
    for rel in list(files(dst / "modtender")):
        if Path("modtender", rel) not in new_files and rel.suffix == ".py":
            (dst / "modtender" / rel).unlink()
    say(f"installed {len(new_files)} files")

    new_req = (dst / "requirements.txt").read_text(encoding="utf-8") if (dst / "requirements.txt").exists() else ""
    py = Path(sys.executable)
    console_py = py.with_name("python.exe") if py.name.lower() == "pythonw.exe" else py
    if new_req != old_req:
        say("requirements changed, installing")
        flags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW
        subprocess.run([str(console_py), "-m", "pip", "install", "-r", str(dst / "requirements.txt")],
                       cwd=dst, creationflags=flags)
    shutil.rmtree(stage / "new", ignore_errors=True)
    (stage / "update.zip").unlink(missing_ok=True)
    say("update complete, restarting")
except Exception:
    say("UPDATE FAILED:\n" + traceback.format_exc())
    prev = stage / "previous"
    if prev.exists():
        for p in prev.rglob("*"):
            if p.is_file():
                rel = p.relative_to(prev)
                (dst / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, dst / rel)
        say("restored the previous version")
finally:
    gui = Path(sys.executable)
    if os.name == "nt" and gui.name.lower() == "python.exe" and gui.with_name("pythonw.exe").exists():
        gui = gui.with_name("pythonw.exe")
    subprocess.Popen([str(gui), str(dst / "main.py")], cwd=dst)
    log.close()
'''


def launch_installer(new_root: Path) -> None:
    """Start the helper that finishes the update once this process exits. Call, then quit the app."""
    log.info("Starting installer, ModTender will restart")
    script = STAGE / "install_update.py"
    script.write_text(INSTALLER, encoding="utf-8")
    flags = 0
    if os.name == "nt":
        flags = 0x00000008 | 0x00000200 | 0x08000000  # DETACHED_PROCESS | NEW_PROCESS_GROUP | NO_WINDOW
    subprocess.Popen([sys.executable, str(script), str(os.getpid()), str(new_root), str(APP_DIR)],
                     cwd=str(STAGE), creationflags=flags, close_fds=True)


def pop_update_log() -> str:
    """The log from the last update (if one just happened), removed once read."""
    log = STAGE / "update.log"
    try:
        text = log.read_text(encoding="utf-8")
        log.unlink()
        return text
    except OSError:
        return ""
