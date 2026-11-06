# ModTender

A mod manager and safety tool for Windows. It finds your games, checks every mod for problems, explains how to fix them, and keeps backups you can restore at any time.

**Download:** grab the latest zip from [Releases](https://github.com/Dirty-Mike-debug/ModTender/releases/latest), extract it and double-click `run.bat`.

Full instructions are in [ModTender/README.md](ModTender/README.md). Version history is in [ModTender/CHANGELOG.md](ModTender/CHANGELOG.md).

## Releasing a new version

Bump `__version__` in `ModTender/modtender/__init__.py`, add a section for it to `ModTender/CHANGELOG.md`, and push to `main`. GitHub Actions builds the zip and publishes the Release automatically.
