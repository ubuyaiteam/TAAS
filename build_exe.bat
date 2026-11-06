@echo off
setlocal
cd /d "%~dp0"

set "PYTHON=venv\Scripts\python.exe"
set "PYINSTALLER=venv\Scripts\pyinstaller.exe"
set "ISCC_PATH="

if not exist "client_secret.json" (
  echo Required installer input client_secret.json was not found.
  goto :error
)

if not exist "%PYTHON%" (
  py -3 -m venv venv
  if errorlevel 1 goto :error
)

"%PYTHON%" -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto :error

"%PYTHON%" -m unittest discover -s tests -t .
if errorlevel 1 goto :error

"%PYINSTALLER%" --noconfirm --clean TAAS.spec
if errorlevel 1 goto :error

for /f "delims=" %%V in ('venv\Scripts\python.exe -c "from taas import __version__; print(__version__)"') do set "APP_VERSION=%%V"
if not defined APP_VERSION goto :error

if not exist release mkdir release
copy /y "USER_GUIDE.md" "release\USER_GUIDE.md" >nul
if errorlevel 1 goto :error

if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" (
  set "ISCC_PATH=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
) else if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
  set "ISCC_PATH=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
) else if exist "C:\Program Files\Inno Setup 6\ISCC.exe" (
  set "ISCC_PATH=C:\Program Files\Inno Setup 6\ISCC.exe"
)

if not defined ISCC_PATH (
  echo Inno Setup 6 was not found. Install it to create the Windows installer.
  goto :error
)

"%ISCC_PATH%" /DMyAppVersion=%APP_VERSION% "taas_setup.iss"
if errorlevel 1 goto :error

echo Installer created in installer_output.
exit /b 0

:error
echo Build stopped. Review the error above and check the build prerequisites.
exit /b 1
