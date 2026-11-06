@echo off
rem Build ModTender.exe and the installer on your own PC (GitHub does this automatically for releases).
rem Needs: Python 3.10+, and Inno Setup 6 (https://jrsoftware.org/isinfo.php) for the installer step.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" py -3 -m venv .venv
".venv\Scripts\python.exe" -m pip install -r requirements.txt pyinstaller || exit /b 1
".venv\Scripts\pyinstaller.exe" --noconfirm --clean --windowed --name ModTender ^
    --icon modtender\assets\modtender.ico --add-data "modtender\assets;modtender\assets" main.py || exit /b 1
for /f "tokens=2 delims==" %%v in ('findstr /b "__version__" modtender\__init__.py') do set VER=%%~v
set VER=%VER: =%
set VER=%VER:"=%
set ISCC="%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist %ISCC% (%ISCC% /DMyAppVersion=%VER% installer\ModTender.iss) else (echo Inno Setup not found: skipping the installer. The app is in dist\ModTender\)
echo.
echo Done. App: dist\ModTender\ModTender.exe
