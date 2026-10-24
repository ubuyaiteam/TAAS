"""Download and safely replace the running Windows executable."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import requests

from .errors import NetworkError, UpdateError
from .updates import UpdateInfo

POWERSHELL_UPDATER = r"""
param(
    [Parameter(Mandatory=$true)][string]$TargetPath,
    [Parameter(Mandatory=$true)][string]$UpdatePath,
    [Parameter(Mandatory=$true)][int]$WaitPid
)
$ErrorActionPreference = "Stop"
$replacePath = "$TargetPath.update"
$backupPath = "$TargetPath.$([guid]::NewGuid().ToString('N')).previous"
$scriptPath = $PSCommandPath
$workingDirectory = Split-Path -Parent $TargetPath
try {
    try {
        Wait-Process -Id $WaitPid -Timeout 120 -ErrorAction Stop
    } catch {
        if (Get-Process -Id $WaitPid -ErrorAction SilentlyContinue) {
            throw
        }
    }
    Copy-Item -LiteralPath $UpdatePath -Destination $replacePath -Force
    if (Test-Path -LiteralPath $TargetPath) {
        Move-Item -LiteralPath $TargetPath -Destination $backupPath -Force
    }
    Move-Item -LiteralPath $replacePath -Destination $TargetPath -Force
    Start-Process -FilePath $TargetPath -WorkingDirectory $workingDirectory
    if (Test-Path -LiteralPath $backupPath) {
        Remove-Item -LiteralPath $backupPath -Force -ErrorAction SilentlyContinue
    }
} catch {
    $updateError = $_.Exception.Message
    $rollbackError = ""
    if (Test-Path -LiteralPath $backupPath) {
        try {
            Copy-Item -LiteralPath $backupPath -Destination $TargetPath -Force
            Start-Process -FilePath $TargetPath -WorkingDirectory $workingDirectory
            Remove-Item -LiteralPath $backupPath -Force -ErrorAction SilentlyContinue
        } catch {
            $rollbackError = "`nRollback failed: $($_.Exception.Message)"
        }
    } elseif ((Test-Path -LiteralPath $TargetPath) -and
              -not (Get-Process -Id $WaitPid -ErrorAction SilentlyContinue)) {
        try {
            Start-Process -FilePath $TargetPath -WorkingDirectory $workingDirectory
        } catch {
            $rollbackError = "`nThe existing TAAS executable could not be restarted: $($_.Exception.Message)"
        }
    }
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show(
        "TAAS could not finish installing the update. The previous version was restored when possible.`n`n$updateError$rollbackError",
        "TAAS update failed",
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Error
    ) | Out-Null
} finally {
    Remove-Item -LiteralPath $replacePath -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $UpdatePath -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $scriptPath -Force -ErrorAction SilentlyContinue
}
"""

MAX_UPDATE_BYTES = 200 * 1024 * 1024


def install_update(info: UpdateInfo, token="", executable_path=None, http=None, popen=None, *,
                   platform=None, frozen=None, powershell=None, process_id=None):
    """Download, verify and start the Windows updater helper."""
    platform = sys.platform if platform is None else platform
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    if platform != "win32" or not frozen:
        raise UpdateError(
            "Automatic updates are available only in the installed Windows TAAS.exe. "
            "Download the new executable from the release page."
        )
    if not info.newer:
        raise UpdateError("There is no newer TAAS version to install.")
    parsed_url = urlparse(info.download_url)
    if (parsed_url.scheme != "https" or parsed_url.hostname != "github.com"
            or not parsed_url.path.casefold().endswith("/taas.exe")):
        raise UpdateError("GitHub did not provide a valid TAAS.exe download for this release.")
    digest_match = re.fullmatch(r"sha256:([0-9a-fA-F]{64})", info.digest)
    if not digest_match:
        raise UpdateError("GitHub did not provide a SHA-256 checksum for TAAS.exe. The update was not installed.")

    target = Path(executable_path or sys.executable).resolve()
    if not target.is_file():
        raise UpdateError(f"Could not find the running TAAS executable: {target}")
    powershell = powershell or shutil.which("powershell.exe")
    if not powershell:
        raise UpdateError("Windows PowerShell was not found, so TAAS could not install the update.")

    http = http or requests
    popen = popen or subprocess.Popen
    process_id = os.getpid() if process_id is None else process_id
    update_dir = Path(tempfile.mkdtemp(prefix="taas-update-"))
    update_path = update_dir / "TAAS.exe"
    script_path = update_dir / "install-update.ps1"
    response = None
    try:
        headers = {"Accept": "application/octet-stream", "User-Agent": "TAAS-updater"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            response = http.get(
                info.download_url,
                headers=headers,
                stream=True,
                timeout=(10, 60),
            )
        except (requests.ConnectionError, requests.Timeout):
            raise NetworkError("Could not download the TAAS update. Check the internet connection.")
        except requests.RequestException:
            raise UpdateError("The TAAS update download failed.")

        if response.status_code >= 400:
            raise UpdateError(f"GitHub could not provide the update (HTTP {response.status_code}).")
        digest = hashlib.sha256()
        size = 0
        try:
            with update_path.open("wb") as downloaded:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        downloaded.write(chunk)
                        digest.update(chunk)
                        size += len(chunk)
                        if size > MAX_UPDATE_BYTES:
                            raise UpdateError("The TAAS update is unexpectedly large. The update was not installed.")
        except (requests.RequestException, OSError):
            raise NetworkError("The TAAS update could not be downloaded completely.")
        if size == 0:
            raise UpdateError("GitHub returned an empty TAAS.exe. The update was not installed.")
        if digest.hexdigest().casefold() != digest_match.group(1).casefold():
            raise UpdateError("The TAAS.exe checksum did not match GitHub's release. The update was not installed.")

        script_path.write_text(POWERSHELL_UPDATER, encoding="utf-8")
        command = [
            powershell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
            "-File", str(script_path), "-TargetPath", str(target),
            "-UpdatePath", str(update_path), "-WaitPid", str(process_id),
        ]
        startupinfo = None
        if hasattr(subprocess, "STARTUPINFO"):
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        creationflags = (
            getattr(subprocess, "CREATE_NO_WINDOW", 0)
            | getattr(subprocess, "DETACHED_PROCESS", 0)
        )
        popen(
            command,
            cwd=str(target.parent),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            startupinfo=startupinfo,
            creationflags=creationflags,
        )
    except (OSError, requests.RequestException) as error:
        shutil.rmtree(update_dir, ignore_errors=True)
        raise UpdateError(f"Could not start the TAAS update: {error}")
    except Exception:
        shutil.rmtree(update_dir, ignore_errors=True)
        raise
    finally:
        if response is not None:
            response.close()
