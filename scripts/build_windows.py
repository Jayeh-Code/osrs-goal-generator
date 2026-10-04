"""Build a Windows x64 folder distribution; run using the app's Python environment."""
from pathlib import Path
import subprocess
import sys
import shutil

root = Path(__file__).resolve().parent.parent
app = root / 'desktop_app'
subprocess.run([
    sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--windowed', '--onedir',
    '--icon', str(app/'assets/ui/app-icon.ico'),
    '--name', 'OSRS Goal Generator', '--paths', str(app/'src'),
    '--add-data', str(app/'assets') + ';assets',
    '--copy-metadata', 'PySide6', '--copy-metadata', 'PySide6_Essentials',
    '--copy-metadata', 'shiboken6',
    '--distpath', str(root/'dist'), '--workpath', str(root/'build'/'pyinstaller'),
    '--specpath', str(root/'build'), str(app/'run.py'),
], check=True)
shutil.copytree(root/'packaging'/'windows', root/'dist'/'OSRS Goal Generator', dirs_exist_ok=True)
