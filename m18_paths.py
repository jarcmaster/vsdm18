r"""
Rutas compartidas por el configurador y la bandeja.

- En desarrollo (ejecutando .py desde el repo): todo vive en la carpeta del repo.
- Empaquetado (.exe de PyInstaller/Flet): la config y los iconos del usuario van a
  %APPDATA%\Stream Dock M18 by JARCMASTER (escribibles y compartidos entre los dos
  ejecutables), y los recursos de solo-lectura (device.png, banderas, app.ico) se
  leen de la carpeta empaquetada (_MEIPASS).
"""

import os
import sys

APP_DIRNAME = "Stream Dock M18 by JARCMASTER"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _repo_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def data_dir() -> str:
    """Carpeta escribible y compartida para config.json e icons/ del usuario."""
    if is_frozen():
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        d = os.path.join(base, APP_DIRNAME)
    else:
        d = _repo_dir()
    os.makedirs(d, exist_ok=True)
    return d


def resource_dir() -> str:
    """Carpeta de recursos de solo-lectura (empaquetados o del repo)."""
    if is_frozen():
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return _repo_dir()


def config_path() -> str:
    return os.path.join(data_dir(), "config.json")


def icons_dir() -> str:
    return os.path.join(data_dir(), "icons")


def assets_dir() -> str:
    return os.path.join(resource_dir(), "assets")


# --- primera ejecucion: copiar datos empaquetados a %APPDATA% ---------------
def ensure_user_data() -> None:
    """Copia config.json e icons/ empaquetados a data_dir si faltan (1a vez)."""
    import shutil
    if not is_frozen():
        return
    dd = data_dir()
    cfg = os.path.join(dd, "config.json")
    if not os.path.exists(cfg):
        src = os.path.join(resource_dir(), "config.json")
        if os.path.exists(src):
            try:
                shutil.copy(src, cfg)
            except Exception:
                pass
    idir = os.path.join(dd, "icons")
    if not os.path.isdir(idir) or not os.listdir(idir):
        src = os.path.join(resource_dir(), "icons")
        if os.path.isdir(src):
            try:
                shutil.copytree(src, idir, dirs_exist_ok=True)
            except Exception:
                pass


# --- inicio automatico con Windows (clave HKCU\...\Run) ----------------------
RUN_NAME = "StreamDockM18_JARCMASTER"
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def startup_command() -> str:
    """Comando que arranca el server (exe unificado sin args, o tray_app.py en dev)."""
    if is_frozen():
        return f'"{sys.executable}"'
    tray = os.path.join(_repo_dir(), "tray_app.py")
    pyw = sys.executable
    cand = os.path.join(os.path.dirname(pyw), "pythonw.exe")
    if os.path.exists(cand):
        pyw = cand
    return f'"{pyw}" "{tray}"'


def is_autostart() -> bool:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
            winreg.QueryValueEx(k, RUN_NAME)
            return True
    except OSError:
        return False


def set_autostart(enable: bool) -> None:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if enable:
                winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ, startup_command())
            else:
                try:
                    winreg.DeleteValue(k, RUN_NAME)
                except FileNotFoundError:
                    pass
    except OSError as e:
        print("[autostart]", e)
