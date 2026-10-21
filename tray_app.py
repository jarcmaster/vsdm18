"""
Aplicacion de bandeja (system tray) para el Stream Dock M18 by JARCMASTER.

- Mantiene el dispositivo funcionando en segundo plano (lee config.json).
- Recarga EN VIVO cuando config.json cambia (el configurador auto-guarda), asi
  cualquier edicion se refleja al instante en el hardware.
- Icono en la bandeja con menu:  Abrir Configurador  |  Salir.
- Al cerrar el configurador, la bandeja sigue viva; solo "Salir" cierra todo.

Uso:   pythonw tray_app.py     (o el .exe con  --tray)
"""

import json
import os
import subprocess
import sys
import threading
import time
import ctypes
from ctypes import wintypes

from streamdock_m18 import build_app_from_config, StreamDockM18
import m18_paths

HERE = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) \
    else os.path.dirname(os.path.abspath(__file__))
CONFIG = m18_paths.config_path()
ICON_PATH = os.path.join(m18_paths.assets_dir(), "app.ico")

_stop = threading.Event()
# Se activa cuando Windows reanuda de suspension; el runtime reconecta el HID.
_resume = threading.Event()


def resume_cb():
    """True una sola vez tras reanudar (consume la senal). Lo usa app.run()."""
    if _resume.is_set():
        _resume.clear()
        return True
    return False


def _read_cfg():
    with open(CONFIG, "r", encoding="utf-8") as f:
        return json.load(f)


# --- hilo que maneja el dispositivo y recarga en vivo -----------------------
def runtime_loop():
    while not _stop.is_set():
        try:
            cfg = _read_cfg()
        except Exception as e:
            print("[tray] config:", e)
            time.sleep(2)
            continue
        try:
            app = build_app_from_config(cfg, device=StreamDockM18())
        except Exception as e:
            print("[tray] build:", e)
            time.sleep(2)
            continue
        last = {"m": os.path.getmtime(CONFIG) if os.path.exists(CONFIG) else 0}

        def reload_cb():
            if _stop.is_set():
                return False
            try:
                m = os.path.getmtime(CONFIG)
            except OSError:
                return None
            if m != last["m"]:
                last["m"] = m
                try:
                    return _read_cfg()
                except Exception:
                    return None
            return None

        try:
            app.run(reload_cb=reload_cb, resume_cb=resume_cb)
        except Exception as e:
            print("[tray] run:", e)
        if _stop.is_set():
            break
        time.sleep(2)   # reintentar (p.ej. se reconecta el USB)


def launch_configurator():
    try:
        if getattr(sys, "frozen", False):
            # mismo exe unificado, en modo configurador
            subprocess.Popen([sys.executable, "--config"], close_fds=True)
        else:
            pyw = sys.executable
            subprocess.Popen([pyw, os.path.join(HERE, "configurator_flet.py")], close_fds=True)
    except Exception as e:
        print("[tray] launch config:", e)


def show_tray_toast(target=None):
    """Aviso rapido (burbuja) al arrancar: la app esta en la bandeja del sistema.
    `target`: (x, y) en px donde debe apuntar la flecha (el icono del tray)."""
    try:
        flags = 0x08000000   # CREATE_NO_WINDOW
        if getattr(sys, "frozen", False):
            args = [sys.executable, "--tray-toast"]
        else:
            args = [sys.executable, os.path.join(HERE, "tray_toast.py")]
        if target:
            args += [str(int(target[0])), str(int(target[1]))]
        subprocess.Popen(args, close_fds=True, creationflags=flags)
    except Exception as e:
        print("[tray] toast:", e)


# --- bandeja Win32 (ctypes, sin dependencias) -------------------------------
WM_APP = 0x8000
WM_TRAY = WM_APP + 1
WM_COMMAND = 0x0111
WM_DESTROY = 0x0002
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205
WM_NULL = 0x0000
# energia: reanudar de suspension -> reconectar el dispositivo
WM_POWERBROADCAST = 0x0218
PBT_APMRESUMESUSPEND = 0x0007
PBT_APMRESUMEAUTOMATIC = 0x0012
NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP = 1, 2, 4
IDI_APPLICATION = 32512
IMAGE_ICON = 1
LR_LOADFROMFILE, LR_DEFAULTSIZE = 0x0010, 0x0040
TPM_RIGHTBUTTON, TPM_RETURNCMD = 0x0002, 0x0100
MF_STRING, MF_SEPARATOR = 0x0000, 0x0800
CW_USEDEFAULT = 0x80000000
ID_OPEN, ID_EXIT = 1001, 1002

u32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32
k32 = ctypes.windll.kernel32

WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_longlong, wintypes.HWND, wintypes.UINT,
                             wintypes.WPARAM, wintypes.LPARAM)

# tipos de las APIs (imprescindible en 64 bits para no truncar handles/lparam)
u32.DefWindowProcW.restype = ctypes.c_longlong
u32.DefWindowProcW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
u32.CreateWindowExW.restype = wintypes.HWND
u32.CreateWindowExW.argtypes = (wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID)
u32.DestroyWindow.argtypes = (wintypes.HWND,)
u32.CreatePopupMenu.restype = wintypes.HMENU
u32.TrackPopupMenu.argtypes = (wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int,
                               ctypes.c_int, wintypes.HWND, wintypes.LPVOID)
u32.SetForegroundWindow.argtypes = (wintypes.HWND,)
u32.AppendMenuW.argtypes = (wintypes.HMENU, wintypes.UINT, ctypes.c_void_p, wintypes.LPCWSTR)
u32.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
u32.GetMessageW.argtypes = (ctypes.c_void_p, wintypes.HWND, wintypes.UINT, wintypes.UINT)
shell32.Shell_NotifyIconW.argtypes = (wintypes.DWORD, ctypes.c_void_p)
k32.GetModuleHandleW.restype = wintypes.HMODULE


class NOTIFYICONDATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uTimeoutOrVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", ctypes.c_byte * 16),
        ("hBalloonIcon", wintypes.HICON),
    ]


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD), ("Data4", ctypes.c_byte * 8)]


class NOTIFYICONIDENTIFIER(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND),
                ("uID", wintypes.UINT), ("guidItem", GUID)]


def _tray_icon_center(hwnd, uid=1):
    """Centro (x, y) en px del icono del tray (o del chevron si esta oculto)."""
    try:
        shell32.Shell_NotifyIconGetRect.restype = ctypes.c_long   # HRESULT
        shell32.Shell_NotifyIconGetRect.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
    except Exception:
        return None
    nii = NOTIFYICONIDENTIFIER()
    nii.cbSize = ctypes.sizeof(NOTIFYICONIDENTIFIER)
    nii.hWnd = hwnd
    nii.uID = uid
    rect = wintypes.RECT()
    for _ in range(12):   # el shell puede tardar un instante en colocar el icono
        try:
            hr = shell32.Shell_NotifyIconGetRect(ctypes.byref(nii), ctypes.byref(rect))
        except Exception as e:
            print("[tray] iconrect:", e)
            return None
        if hr == 0 and (rect.right > rect.left) and (rect.bottom > rect.top):
            return ((rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2)
        time.sleep(0.04)
    return None


class WNDCLASS(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


def _load_icon():
    u32.LoadImageW.restype = wintypes.HANDLE
    if os.path.exists(ICON_PATH):
        h = u32.LoadImageW(None, ICON_PATH, IMAGE_ICON, 0, 0,
                           LR_LOADFROMFILE | LR_DEFAULTSIZE)
        if h:
            return h
    u32.LoadIconW.restype = wintypes.HICON
    return u32.LoadIconW(None, wintypes.LPCWSTR(IDI_APPLICATION))


_MUTEX_NAME = "Global\\StreamDockM18_JARCMASTER_Tray"


def _already_running():
    k32.CreateMutexW.restype = wintypes.HANDLE
    h = k32.CreateMutexW(None, False, _MUTEX_NAME)
    return bool(h) and k32.GetLastError() == 183   # ERROR_ALREADY_EXISTS


def _first_run_setup():
    """Empaquetado: copiar datos y refrescar el arranque con Windows al exe actual."""
    if not getattr(sys, "frozen", False):
        return
    try:
        m18_paths.ensure_user_data()
        # preferencia del usuario (config); por defecto True
        pref = True
        try:
            with open(CONFIG, "r", encoding="utf-8") as f:
                pref = bool(json.load(f).get("autostart", True))
        except Exception:
            pass
        m18_paths.set_autostart(pref)   # SetValueEx siempre apunta al exe actual
    except Exception as e:
        print("[tray] setup:", e)


def run_tray():
    if _already_running():
        return   # ya hay una bandeja/server -> instancia unica
    _first_run_setup()
    hinst = k32.GetModuleHandleW(None)
    nid = NOTIFYICONDATA()

    def wndproc(hwnd, msg, wparam, lparam):
        if msg == WM_TRAY:
            low = lparam & 0xFFFF
            if low == WM_RBUTTONUP:              # clic derecho -> menu Abrir/Salir
                _show_menu(hwnd)
            elif low in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):   # clic izquierdo -> abrir app
                launch_configurator()
            return 0
        if msg == WM_COMMAND:
            cmd = wparam & 0xFFFF
            if cmd == ID_OPEN:
                launch_configurator()
            elif cmd == ID_EXIT:
                _stop.set()
                shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
                u32.DestroyWindow(hwnd)
            return 0
        if msg == WM_POWERBROADCAST:
            # el PC reanudo de suspension -> senalar reconexion del HID
            if wparam in (PBT_APMRESUMEAUTOMATIC, PBT_APMRESUMESUSPEND):
                _resume.set()
            return 1   # TRUE: mensaje atendido
        if msg == WM_DESTROY:
            u32.PostQuitMessage(0)
            return 0
        return u32.DefWindowProcW(hwnd, msg, wparam, lparam)

    proc = WNDPROC(wndproc)
    wc = WNDCLASS()
    wc.lpfnWndProc = proc
    wc.hInstance = hinst
    wc.lpszClassName = "M18TrayWindow"
    u32.RegisterClassW(ctypes.byref(wc))
    hwnd = u32.CreateWindowExW(0, "M18TrayWindow", "M18 Tray", 0,
                               0, 0, 0, 0, None, None, hinst, None)

    def _show_menu(hwnd):
        hmenu = u32.CreatePopupMenu()
        u32.AppendMenuW(hmenu, MF_STRING, ID_OPEN, "Open Configurator")
        u32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)
        u32.AppendMenuW(hmenu, MF_STRING, ID_EXIT, "Exit")
        pt = wintypes.POINT()
        u32.GetCursorPos(ctypes.byref(pt))
        u32.SetForegroundWindow(hwnd)
        u32.TrackPopupMenu(hmenu, TPM_RIGHTBUTTON, pt.x, pt.y, 0, hwnd, None)
        u32.PostMessageW(hwnd, WM_NULL, 0, 0)
        u32.DestroyMenu(hmenu)

    nid.cbSize = ctypes.sizeof(NOTIFYICONDATA)
    nid.hWnd = hwnd
    nid.uID = 1
    nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
    nid.uCallbackMessage = WM_TRAY
    nid.hIcon = _load_icon()
    nid.szTip = "Stream Dock M18 by JARCMASTER"
    shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))

    # aviso rapido: la app quedo en la bandeja (la flecha apunta al icono real)
    show_tray_toast(_tray_icon_center(hwnd, 1))

    threading.Thread(target=runtime_loop, daemon=True).start()

    msg = wintypes.MSG()
    while u32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        u32.TranslateMessage(ctypes.byref(msg))
        u32.DispatchMessageW(ctypes.byref(msg))
    _stop.set()


if __name__ == "__main__":
    run_tray()
