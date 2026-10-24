"""Makes assets\\taas.ico (the icon of TAAS.exe and the installer) from the logo drawing.

Run it after changing taas/ui/logo.py:   python make_icon.py
build_exe.bat and the GitHub release workflow run it for you before building.
"""

from pathlib import Path  # file paths

from taas.ui.logo import write_ico  # the logo drawing

TARGET = Path(__file__).resolve().parent / "assets" / "taas.ico"

if __name__ == "__main__":
    TARGET.parent.mkdir(exist_ok=True)
    write_ico(TARGET)
    print(f"Wrote {TARGET}")
