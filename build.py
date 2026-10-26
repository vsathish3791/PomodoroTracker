"""Build PomodoroTracker.exe and (if Inno Setup is installed) the Windows installer.

    .venv\\Scripts\\python build.py

Steps:
  1. Draw the app icon to assets/icon.ico
  2. PyInstaller -> dist/PomodoroTracker/PomodoroTracker.exe (+ its files)
  3. Inno Setup  -> installer_output/PomodoroTracker-Setup-<version>.exe
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
ICON = ASSETS / "icon.ico"

INNO_LOCATIONS = [
    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Inno Setup 6" / "ISCC.exe",
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Inno Setup 6" / "ISCC.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
]


def make_icon():
    from PySide6.QtGui import QGuiApplication, QImage
    from pomodoro.timer import Phase
    from pomodoro.ui.theme import PHASE_COLORS, make_icon as draw

    _app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    ASSETS.mkdir(exist_ok=True)
    image: QImage = draw(PHASE_COLORS[Phase.FOCUS], "25").pixmap(256, 256).toImage()
    if not image.save(str(ICON), "ICO"):
        sys.exit("Couldn't write assets/icon.ico")
    print(f"Icon:      {ICON}")


def build_exe():
    from pomodoro import __version__
    shutil.rmtree(ROOT / "build", ignore_errors=True)
    shutil.rmtree(ROOT / "dist", ignore_errors=True)
    subprocess.run([
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
        "--name", "PomodoroTracker", "--icon", str(ICON),
        # Only Core/Gui/Widgets/Network are used; leave the big unused Qt parts out.
        "--exclude-module", "PySide6.QtWebEngineCore", "--exclude-module", "PySide6.QtQml",
        "--exclude-module", "PySide6.QtQuick", "--exclude-module", "PySide6.Qt3DCore",
        "--exclude-module", "PySide6.QtCharts", "--exclude-module", "PySide6.QtMultimedia",
        "--exclude-module", "tkinter",
        str(ROOT / "main.py"),
    ], check=True, cwd=ROOT)
    exe = ROOT / "dist" / "PomodoroTracker" / "PomodoroTracker.exe"
    print(f"App:       {exe}  (version {__version__})")


def build_installer():
    from pomodoro import __version__
    iscc = next((p for p in INNO_LOCATIONS if p.exists()), None)
    if iscc is None:
        print("Installer: skipped - Inno Setup 6 is not installed "
              "(https://jrsoftware.org/isinfo.php, or: winget install JRSoftware.InnoSetup)")
        return
    subprocess.run([str(iscc), f"/DAppVersion={__version__}",
                    str(ROOT / "installer" / "PomodoroTracker.iss")], check=True, cwd=ROOT)
    print(f"Installer: {ROOT / 'installer_output' / f'PomodoroTracker-Setup-{__version__}.exe'}")


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    make_icon()
    build_exe()
    build_installer()
