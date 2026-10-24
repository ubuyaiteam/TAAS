@echo off
rem ============================================================
rem  Builds TAAS.exe on Windows. Needs Python 3.10 or newer.
rem  Run this file by double-clicking it, or from a Command Prompt.
rem  Result: the "release" folder with TAAS.exe and the guide.
rem ============================================================
cd /d "%~dp0"
rem make Python read and write files as UTF-8, so letters outside English do not cause errors
set PYTHONUTF8=1

rem is Python installed?
py --version >nul 2>&1
if errorlevel 1 (
  echo Python was not found. Install Python 3.10 or newer from python.org and tick "Add python.exe to PATH".
  goto :error
)

echo [1/5] Making a clean Python environment...
rem an old environment from an earlier try is removed, so the libraries are installed fresh
if exist .venv rmdir /s /q .venv
py -m venv .venv
if errorlevel 1 goto :error
call .venv\Scripts\activate.bat

echo [2/5] Installing the libraries...
python -m pip install --upgrade pip
pip install -r requirements.txt pyinstaller
if errorlevel 1 goto :error

echo [3/5] Running the tests...
python -m unittest discover -s tests -t .
if errorlevel 1 goto :error

echo [4/5] Making the icon and building TAAS.exe (this takes a few minutes)...
rem assets\taas.ico is drawn from the logo code, so it always matches the app
python make_icon.py
if errorlevel 1 goto :error
rem --onefile = one .exe file, --windowed = no black console window
rem --collect-all customtkinter = include the screen toolkit's theme files
pyinstaller --noconfirm --clean --onefile --windowed --name TAAS --icon assets\taas.ico --collect-all customtkinter run_taas.py
if errorlevel 1 goto :error

echo [5/5] Making the release folder...
if exist release rmdir /s /q release
mkdir release
copy /y dist\TAAS.exe release\TAAS.exe >nul
copy /y USER_GUIDE.md release\USER_GUIDE.md >nul
rem the Google client file ships next to the .exe, if you put it in this folder
if exist client_secret.json copy /y client_secret.json release\client_secret.json >nul
if not exist client_secret.json echo NOTE: client_secret.json was not found here, so it is not in the release folder. See GOOGLE_SETUP.md.

echo.
echo Done. Open the "release" folder.
pause
exit /b 0

:error
echo.
echo The build stopped because of an error. Read the lines above this message.
echo If you ask for help, send a picture of the lines just above this message.
pause
exit /b 1
