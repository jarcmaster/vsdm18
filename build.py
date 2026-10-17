"""
Construye UN solo ejecutable de "Stream Dock M18 by JARCMASTER".

Genera  dist/StreamDockM18.exe  que hace de server+bandeja (sin args) y de
configurador (con --config). Al ejecutarlo la 1a vez se auto-registra para
iniciar con Windows y copia los iconos/config a %APPDATA%.

Requisitos:  pip install pyinstaller flet
Uso:         python build.py
Instalador (opcional):  iscc installer.iss   (requiere Inno Setup 6)
"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ICON = os.path.join(HERE, "assets", "app.ico")
SEP = ";"   # separador de --add-data en Windows
FLET = os.path.join(os.path.dirname(sys.executable), "Scripts", "flet.exe")


def _kill_running():
    subprocess.run(["taskkill", "/F", "/IM", "StreamDockM18.exe"], capture_output=True)


def build():
    flet = FLET if os.path.exists(FLET) else "flet"
    cmd = [flet, "pack", "main.py",
           "--name", "StreamDockM18", "--icon", ICON,
           "--add-data", f"assets{SEP}assets",
           "--add-data", f"icons{SEP}icons",
           "--add-data", f"config.json{SEP}.",
           "--add-data", f"i18n_extra.py{SEP}.",
           "--add-data", f"m18_paths.py{SEP}.",
           "--add-data", f"configurator_flet.py{SEP}.",
           "--add-data", f"tray_app.py{SEP}.",
           "--add-data", f"mouse_overlay.py{SEP}.",
           "--add-data", f"README.md{SEP}.",
           "--add-data", f"streamdock_m18{SEP}streamdock_m18",
           "--hidden-import", "hid",
           # Audio Player (import perezoso en streamdock_m18/audio.py): forzamos
           # su inclusion para que los hooks de PyInstaller empaqueten las DLLs
           # nativas (PortAudio de sounddevice, libsndfile de soundfile).
           "--hidden-import", "sounddevice",
           "--hidden-import", "soundfile",
           "--hidden-import", "numpy",
           "--hidden-import", "cffi",
           "--hidden-import", "_cffi_backend",
           "-y"]
    print(">>", " ".join(cmd))
    subprocess.check_call(cmd, cwd=HERE)
    print("\nListo:  dist\\StreamDockM18.exe")
    print("Ejecutalo una vez (se auto-instala el arranque con Windows y arranca el server).")


if __name__ == "__main__":
    _kill_running()
    build()
