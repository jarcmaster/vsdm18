"""
Acciones para asignar a las teclas.

Dos familias:

1) Acciones "normales": funciones que reciben el KeyEvent y hacen algo
   (lanzar app, abrir URL, atajo de teclado, funcion tuya...).

2) Navegacion de paginas: devuelven un objeto PageNav que la app reconoce
   para cambiar de pagina (no es una funcion normal).

Ademas, `from_spec()` convierte un descriptor serializable (dict) en la accion
correspondiente. Eso permite guardar la configuracion en JSON desde la app de
configuracion y reconstruirla al ejecutar.
"""

from __future__ import annotations

import subprocess
import time
import webbrowser
from typing import Callable

# Una accion normal recibe el KeyEvent y no devuelve nada.
Action = Callable[[object], None]


# --- envio de teclas por SCANCODE (para que DCS World las reciba) ------------
# DCS lee el teclado por DirectInput/scancode e IGNORA las teclas que pyautogui
# inyecta con scancode 0. Aqui enviamos con SendInput + KEYEVENTF_SCANCODE para
# que juegos como DCS las registren. Si algo falla, se usa pyautogui como respaldo.
import ctypes as _ct
from ctypes import wintypes as _wt

_user32 = _ct.WinDLL("user32", use_last_error=True)
_ULONG_PTR = _ct.c_ulonglong if _ct.sizeof(_ct.c_void_p) == 8 else _ct.c_ulong

class _MOUSEINPUT(_ct.Structure):
    _fields_ = [("dx", _wt.LONG), ("dy", _wt.LONG), ("mouseData", _wt.DWORD),
                ("dwFlags", _wt.DWORD), ("time", _wt.DWORD), ("dwExtraInfo", _ULONG_PTR)]
class _KEYBDINPUT(_ct.Structure):
    _fields_ = [("wVk", _wt.WORD), ("wScan", _wt.WORD), ("dwFlags", _wt.DWORD),
                ("time", _wt.DWORD), ("dwExtraInfo", _ULONG_PTR)]
class _HARDWAREINPUT(_ct.Structure):
    _fields_ = [("uMsg", _wt.DWORD), ("wParamL", _wt.WORD), ("wParamH", _wt.WORD)]
class _INUNION(_ct.Union):
    _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT), ("hi", _HARDWAREINPUT)]
class _INPUT(_ct.Structure):
    _fields_ = [("type", _wt.DWORD), ("u", _INUNION)]

_INPUT_KEYBOARD = 1
_KEYEVENTF_EXTENDEDKEY = 0x0001
_KEYEVENTF_KEYUP = 0x0002
_KEYEVENTF_SCANCODE = 0x0008
_KEYEVENTF_UNICODE = 0x0004

# nombre de tecla (estilo pyautogui) -> (codigo VK de Windows, es_tecla_extendida)
_VK = {
    "shiftleft": (0xA0, False), "shiftright": (0xA1, False),
    "ctrlleft": (0xA2, False), "ctrlright": (0xA3, True),
    "altleft": (0xA4, False), "altright": (0xA5, True),
    "winleft": (0x5B, True), "winright": (0x5C, True),
    "ctrl": (0x11, False), "shift": (0x10, False), "alt": (0x12, False), "win": (0x5B, True),
    "space": (0x20, False), "enter": (0x0D, False), "return": (0x0D, False),
    "tab": (0x09, False), "backspace": (0x08, False), "esc": (0x1B, False), "escape": (0x1B, False),
    "left": (0x25, True), "up": (0x26, True), "right": (0x27, True), "down": (0x28, True),
    "home": (0x24, True), "end": (0x23, True), "pageup": (0x21, True), "pagedown": (0x22, True),
    "insert": (0x2D, True), "delete": (0x2E, True), "del": (0x2E, True),
    "pause": (0x13, False), "capslock": (0x14, False), "printscreen": (0x2C, True),
    "add": (0x6B, False), "subtract": (0x6D, False), "multiply": (0x6A, False),
    "divide": (0x6F, True), "decimal": (0x6E, False),
}

def _vk_ext(name):
    """Devuelve (vk, extended) para un nombre de tecla, o None si no se reconoce."""
    import re
    n = (name or "").lower()
    if n in _VK:
        return _VK[n]
    m = re.fullmatch(r"f(\d{1,2})", n)
    if m:
        i = int(m.group(1))
        if 1 <= i <= 24:
            return (0x70 + i - 1, False)
    if n.startswith("num") and n[3:].isdigit():
        return (0x60 + int(n[3:]), False)
    if len(name) == 1:
        res = _user32.VkKeyScanW(ord(name))
        if res != -1:
            return (res & 0xFF, False)
    return None

def _type_unicode(text, char_delay_ms=3):
    """Teclea texto LITERAL como caracteres Unicode (SendInput), donde este el
    cursor, sin tocar el portapapeles. `char_delay_ms` = pausa entre letras
    (efecto maquina de escribir). Funciona con acentos/enies. '\\n' = Enter."""
    d = max(0, int(char_delay_ms)) / 1000.0
    for ch in (text or ""):
        if ch in "\r\n":
            vk, ext = _VK["enter"]
            _sc_event(vk, False, ext); _sc_event(vk, True, ext)
            time.sleep(d)
            continue
        for up in (False, True):
            flags = _KEYEVENTF_UNICODE | (_KEYEVENTF_KEYUP if up else 0)
            inp = _INPUT(type=_INPUT_KEYBOARD,
                         u=_INUNION(ki=_KEYBDINPUT(wVk=0, wScan=ord(ch), dwFlags=flags,
                                                   time=0, dwExtraInfo=0)))
            _user32.SendInput(1, _ct.byref(inp), _ct.sizeof(_INPUT))
        time.sleep(d)


def _sc_event(vk, keyup, extended):
    scan = _user32.MapVirtualKeyW(vk, 0) & 0xFF
    flags = _KEYEVENTF_SCANCODE
    if extended:
        flags |= _KEYEVENTF_EXTENDEDKEY
    if keyup:
        flags |= _KEYEVENTF_KEYUP
    inp = _INPUT(type=_INPUT_KEYBOARD,
                 u=_INUNION(ki=_KEYBDINPUT(wVk=0, wScan=scan, dwFlags=flags,
                                           time=0, dwExtraInfo=0)))
    _user32.SendInput(1, _ct.byref(inp), _ct.sizeof(_INPUT))


# --- raton por Win32 directo (reproduccion EXACTA de macros) ----------------
_INPUT_MOUSE = 0
_MOUSE_FLAGS = {
    ("l", True): 0x0002, ("l", False): 0x0004,   # LEFTDOWN / LEFTUP
    ("r", True): 0x0008, ("r", False): 0x0010,   # RIGHTDOWN / RIGHTUP
    ("m", True): 0x0020, ("m", False): 0x0040,   # MIDDLEDOWN / MIDDLEUP
}

def _mouse_setpos(x, y) -> bool:
    """Coloca el cursor en coords FISICAS exactas (DPI-aware, igual que GetCursorPos)."""
    try:
        _user32.SetCursorPos(int(x), int(y))
        return True
    except Exception:
        return False

def _mouse_button(btn, down) -> bool:
    """Pulsa/suelta un boton del raton en la posicion ACTUAL (SendInput)."""
    try:
        flags = _MOUSE_FLAGS[(btn, down)]
        inp = _INPUT(type=_INPUT_MOUSE,
                     u=_INUNION(mi=_MOUSEINPUT(dx=0, dy=0, mouseData=0, dwFlags=flags,
                                               time=0, dwExtraInfo=0)))
        _user32.SendInput(1, _ct.byref(inp), _ct.sizeof(_INPUT))
        return True
    except Exception:
        return False


def send_combo_scancode(keys, hold=0.05) -> bool:
    """Pulsa una combinacion por scancode (modificadores primero). True si pudo.

    Mete una pausa corta entre cada tecla para que el juego asiente los
    modificadores antes de la tecla principal (DCS lo necesita).
    """
    resolved = [_vk_ext(k) for k in keys]
    if not resolved or any(r is None for r in resolved):
        return False
    try:
        for vk, ext in resolved:
            _sc_event(vk, False, ext)
            time.sleep(0.015)
        time.sleep(hold)
        for vk, ext in reversed(resolved):
            _sc_event(vk, True, ext)
            time.sleep(0.008)
        return True
    except Exception as e:
        print("[scancode]", e)
        return False


# --- navegacion de paginas --------------------------------------------------
class PageNav:
    """Marcador de navegacion de pagina. target: 'next', 'prev' o indice int."""
    def __init__(self, target):
        self.target = target

    def __repr__(self):
        return f"PageNav({self.target!r})"


def next_page() -> PageNav:
    return PageNav("next")


def prev_page() -> PageNav:
    return PageNav("prev")


def goto_page(n: int) -> PageNav:
    return PageNav(int(n))


def home() -> PageNav:
    """Va a la pagina marcada como 'por defecto'."""
    return PageNav("home")


def scene_next() -> PageNav:
    """Cambia a la siguiente escena (rota entre todas)."""
    return PageNav("scene_next")


def goto_scene(n: int) -> PageNav:
    return PageNav(("scene", int(n)))


# --- comandos que necesitan el dispositivo (los maneja la app) --------------
class DeviceCommand:
    """Marcador de accion que actua sobre el dispositivo (ej. brillo)."""
    def __init__(self, kind, value=None):
        self.kind = kind
        self.value = value

    def __repr__(self):
        return f"DeviceCommand({self.kind!r}, {self.value!r})"


def brightness(value: int) -> DeviceCommand:
    """Fija el brillo de las pantallas (0-100)."""
    return DeviceCommand("brightness", int(value))


# --- Timer (categoria Practical) --------------------------------------------
class TimerCommand:
    """
    Marcador de accion Timer. La app (servidor) lo maneja: cuenta regresiva en
    la propia tecla, al terminar notifica + parpadea; la pulsacion para/descarta.
    `cfg` lleva: seconds, notify, sound, blink (dos colores RGB).
    """
    def __init__(self, cfg: dict):
        self.cfg = cfg or {}

    def __repr__(self):
        return f"TimerCommand({self.cfg!r})"


class CalendarCommand:
    """
    Marcador de accion Calendar Notes. La app (servidor) lo maneja: pinta la
    fecha de hoy en la tecla y, al pulsar, abre la ventana de notas.
    """
    def __init__(self, cfg: dict):
        self.cfg = cfg or {}

    def __repr__(self):
        return f"CalendarCommand({self.cfg!r})"


class AlarmCommand:
    """
    Marcador de accion Alarm. La app (servidor) lo maneja: programa la alarma por
    hora/dia, al dispararse notifica/suena/parpadea (opcional accion asociada y
    escalada), y mantiene el aviso hasta reconocerlo. Pulsar la tecla pospone.
    `cfg`: time, note, repeat, days, interval_min, notify, sound, snooze_min,
    snooze_max, priority, escalate, exec.
    """
    def __init__(self, cfg: dict):
        self.cfg = cfg or {}

    def __repr__(self):
        return f"AlarmCommand({self.cfg!r})"


class RecorderCommand:
    """
    Marcador de accion "Hold and Record". La app lo maneja con press Y release:
    mantener presionado graba audio del microfono; al soltar guarda. Un clic
    corto (<~0.4s) abre la ventana con la lista de grabaciones.
    `cfg`: device, format, quality, samplerate, channels.
    """
    def __init__(self, cfg: dict):
        self.cfg = cfg or {}

    def __repr__(self):
        return f"RecorderCommand({self.cfg!r})"


class RecorderToggleCommand:
    """
    Marcador de accion "Long Recorder". A diferencia de Hold and Record, aqui un
    clic corto ALTERNA la grabacion: el primer clic empieza a grabar (la tecla
    muestra un boton rojo "REC") y el siguiente clic la detiene y guarda. Una
    pulsacion larga (long press) abre la ventana con las grabaciones y los
    ajustes. Pensado para grabaciones largas/continuas.
    `cfg`: device, format, quality, samplerate, channels.
    """
    def __init__(self, cfg: dict):
        self.cfg = cfg or {}

    def __repr__(self):
        return f"RecorderToggleCommand({self.cfg!r})"


class ReminderCommand:
    """
    Marcador de accion Reminder (indicador global). La app muestra en la tecla el
    PROXIMO aviso + un badge con los pendientes; al pulsar abre la ventana de
    recordatorios (crear/gestionar). Los recordatorios viven en reminders.json.
    """
    def __init__(self, cfg: dict):
        self.cfg = cfg or {}

    def __repr__(self):
        return f"ReminderCommand({self.cfg!r})"


class TodoCommand:
    """
    Marcador de accion To-Do (indicador global). La app muestra en la tecla la
    PROXIMA tarea + un badge con las pendientes; al pulsar abre la ventana de
    tareas (crear/gestionar). Las tareas viven en todos.json.
    """
    def __init__(self, cfg: dict):
        self.cfg = cfg or {}

    def __repr__(self):
        return f"TodoCommand({self.cfg!r})"


class SeqRepeatCommand:
    """
    Marcador de accion "Sequence Repeat" (grabador de macro raton+teclado). La
    app lo maneja: PULSACION LARGA empieza a grabar (el tile muestra REC); volver
    a pulsar detiene y guarda; PULSACION CORTA reproduce la ultima grabacion (el
    tile muestra PLAY). `cfg`: repeat, speed, record_keys, stop.
    """
    def __init__(self, cfg: dict):
        self.cfg = cfg or {}

    def __repr__(self):
        return f"SeqRepeatCommand({self.cfg!r})"


class CalcCommand:
    """
    Marcador de accion Calculadora. La app mantiene el estado (numero en curso,
    acumulador y operador) y pinta el display en la tecla con role 'enter' (=).
    `cfg`: {role, value}. roles: digit (value 0-9), dot, add (long=*), sub
    (long=/), enter (=), back (corto=borrar un digito; largo=limpiar todo).
    """
    def __init__(self, cfg: dict):
        self.cfg = cfg or {}

    def __repr__(self):
        return f"CalcCommand({self.cfg!r})"


# --- acciones normales ------------------------------------------------------
def func(fn: Callable[[], None]) -> Action:
    """Envuelve una funcion tuya sin argumentos como accion."""
    def action(event):
        fn()
    return action


def run(*command: str, shell: bool = False) -> Action:
    """Lanza un programa o comando. Ej: actions.run('notepad.exe')"""
    def action(event):
        subprocess.Popen(command if not shell else " ".join(command), shell=shell)
    return action


def open_path(path: str, args=None, display: bool = False) -> Action:
    """Abre un archivo o programa. Con `args` lo lanza; si no, lo abre con su app."""
    def action(event):
        import os
        if not (path or "").strip():
            return
        if args and not display:
            subprocess.Popen([path] + list(args))
        else:
            try:
                os.startfile(path)      # abrir/mostrar con la app por defecto
            except Exception:
                subprocess.Popen([path] + list(args or []))
    return action


def open_app(path: str) -> Action:
    """Lanza una app instalada (ruta a .lnk o .exe)."""
    def action(event):
        import os
        if not (path or "").strip():
            return
        try:
            os.startfile(path)
        except Exception:
            subprocess.Popen(f'start "" "{path}"', shell=True)
    return action


def multimedia(command: str) -> Action:
    """
    Tecla multimedia: playpause | nexttrack | prevtrack | stop |
    volumeup | volumedown | volumemute. Requiere pyautogui.
    """
    def action(event):
        import pyautogui
        pyautogui.press(command)
    return action


def close_window(app: str = "", force: bool = False) -> Action:
    """
    Cierra una aplicacion. Si `app` esta vacio, cierra la VENTANA ACTIVA (Alt+F4).
    Si `app` es un nombre o ruta de .exe, cierra ese proceso con taskkill:
      - normal: envia cierre a sus ventanas (taskkill /im)
      - force:  lo mata junto a sus procesos hijos (taskkill /f /t /im)
    """
    def action(event):
        t = (app or "").strip()
        if not t:
            import pyautogui
            pyautogui.hotkey("alt", "f4")
            return
        import os
        name = os.path.basename(t) if ("\\" in t or "/" in t) else t
        if not name.lower().endswith(".exe"):
            name += ".exe"
        args = ["taskkill"]
        if force:
            args += ["/f", "/t"]
        args += ["/im", name]
        try:
            subprocess.run(args, creationflags=0x08000000,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            print("[close]", e)
    return action


def ensure_dpi_aware():
    """
    Hace el proceso consciente del DPI (Per-Monitor v2 si se puede). Debe
    llamarse ANTES de leer/mover el cursor o enumerar monitores, para que
    grabacion y reproduccion usen el mismo espacio de coordenadas (fisico) y
    no se desfasen por el escalado de pantalla. Idempotente.
    """
    import ctypes
    # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
    for fn in (
        lambda: ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)),
        lambda: ctypes.windll.shcore.SetProcessDpiAwareness(2),
        lambda: ctypes.windll.user32.SetProcessDPIAware(),
    ):
        try:
            fn()
            return True   # no lanzo = API disponible y aplicada (o ya estaba)
        except Exception:
            continue
    return False


# forzar consciencia de DPI al cargar el modulo (antes de pyautogui)
try:
    ensure_dpi_aware()
except Exception:
    pass


def list_monitors():
    """
    Lista los monitores instalados (Windows) ordenados por posicion.
    Devuelve dicts: {index, x, y, width, height, primary, name}.
    x/y son la esquina superior-izquierda en el escritorio virtual.
    """
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32

    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    class MONITORINFOEXW(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", RECT),
                    ("rcWork", RECT), ("dwFlags", wintypes.DWORD),
                    ("szDevice", ctypes.c_wchar * 32)]

    found = []
    MONENUM = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p,
                                 ctypes.POINTER(RECT), ctypes.c_longlong)

    def _cb(hmon, hdc, lprect, lparam):
        mi = MONITORINFOEXW()
        mi.cbSize = ctypes.sizeof(MONITORINFOEXW)
        if user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            r = mi.rcMonitor
            found.append({"x": int(r.left), "y": int(r.top),
                          "width": int(r.right - r.left),
                          "height": int(r.bottom - r.top),
                          "primary": bool(mi.dwFlags & 1), "name": mi.szDevice})
        return 1

    try:
        user32.EnumDisplayMonitors(0, 0, MONENUM(_cb), 0)
    except Exception:
        pass
    if not found:  # fallback: escritorio virtual completo
        w = int(user32.GetSystemMetrics(0)); h = int(user32.GetSystemMetrics(1))
        found = [{"x": 0, "y": 0, "width": w, "height": h,
                  "primary": True, "name": "PRIMARY"}]
    found.sort(key=lambda m: (m["x"], m["y"]))
    for i, m in enumerate(found):
        m["index"] = i
    return found


def monitor_at(x, y, mons=None):
    """Indice del monitor que contiene (x, y), o None si ninguno."""
    mons = mons if mons is not None else list_monitors()
    for m in mons:
        if m["x"] <= x < m["x"] + m["width"] and m["y"] <= y < m["y"] + m["height"]:
            return m["index"]
    return None


def _resolve_xy(x, y, monitor):
    """x,y relativas al monitor indicado -> coords absolutas. monitor=None => absolutas."""
    if x is None or y is None:
        return None
    if monitor is None:
        return int(x), int(y)
    mons = list_monitors()
    if 0 <= monitor < len(mons):
        m = mons[monitor]
        return int(m["x"] + x), int(m["y"] + y)
    return int(x), int(y)


def mouse_event(spec_or_ev) -> Action:
    """
    Evento de raton. Admite:
      - str: left | right | double | middle | scroll_up | scroll_down | move
      - dict: {"event":..., "x":, "y":, "monitor":}
    Si x/y estan definidas, mueve el cursor antes de actuar (relativas al
    monitor si se indica; si no, absolutas). Si solo se indica monitor, va al
    centro de ese monitor. 'move' solo mueve el cursor. Requiere pyautogui.
    """
    if isinstance(spec_or_ev, dict):
        ev = spec_or_ev.get("event", "left")
        x = spec_or_ev.get("x"); y = spec_or_ev.get("y")
        monitor = spec_or_ev.get("monitor")
    else:
        ev = spec_or_ev or "left"
        x = y = monitor = None

    def action(event):
        import pyautogui
        tx = ty = None
        if x is not None and y is not None:
            res = _resolve_xy(x, y, monitor)
            if res:
                tx, ty = res
        elif monitor is not None:
            mons = list_monitors()
            if 0 <= monitor < len(mons):
                m = mons[monitor]
                tx = m["x"] + m["width"] // 2
                ty = m["y"] + m["height"] // 2
        if tx is not None:
            pyautogui.moveTo(tx, ty)
        if ev == "move":
            return
        elif ev == "left":
            pyautogui.click()
        elif ev == "right":
            pyautogui.rightClick()
        elif ev == "double":
            pyautogui.doubleClick()
        elif ev == "middle":
            pyautogui.middleClick()
        elif ev == "scroll_up":
            pyautogui.scroll(400)
        elif ev == "scroll_down":
            pyautogui.scroll(-400)
    return action


# --- hotkeys de parada (grabacion / reproduccion) ---------------------------
# nombre -> lista de VK que deben estar pulsados a la vez.
STOP_HOTKEYS = {
    "ESC": [0x1B],
    "F8": [0x77],
    "F9": [0x78],
    "F10": [0x79],
    "F12": [0x7B],
    "Ctrl+Alt+S": [0x11, 0x12, 0x53],
    "Ctrl+Shift+Q": [0x11, 0x10, 0x51],
}


def _hotkey_down(vks) -> bool:
    """True si TODOS los VK indicados estan pulsados ahora mismo (Windows)."""
    try:
        import ctypes
        u = ctypes.windll.user32
        return bool(vks) and all(u.GetAsyncKeyState(v) & 0x8000 for v in vks)
    except Exception:
        return False


# --- mapa VK -> nombre de tecla de pyautogui --------------------------------
_VK_NAMES = {
    0x08: "backspace", 0x09: "tab", 0x0D: "enter", 0x13: "pause",
    0x14: "capslock", 0x1B: "esc", 0x20: "space", 0x21: "pageup",
    0x22: "pagedown", 0x23: "end", 0x24: "home", 0x25: "left", 0x26: "up",
    0x27: "right", 0x28: "down", 0x2C: "printscreen", 0x2D: "insert",
    0x2E: "delete", 0x10: "shift", 0x11: "ctrl", 0x12: "alt",
    0xA0: "shift", 0xA1: "shift", 0xA2: "ctrl", 0xA3: "ctrl",
    0xA4: "alt", 0xA5: "alt", 0x5B: "win", 0x5C: "win",
    0x90: "numlock", 0x91: "scrolllock",
    0xBA: ";", 0xBB: "=", 0xBC: ",", 0xBD: "-", 0xBE: ".", 0xBF: "/",
    0xC0: "`", 0xDB: "[", 0xDC: "\\", 0xDD: "]", 0xDE: "'",
    0x6A: "multiply", 0x6B: "add", 0x6D: "subtract", 0x6E: "decimal", 0x6F: "divide",
}
for _i in range(24):
    _VK_NAMES[0x70 + _i] = "f" + str(_i + 1)
for _i in range(10):
    _VK_NAMES[0x60 + _i] = str(_i)   # numpad -> digito


def _vk_to_key(vk):
    """Convierte un codigo VK de Windows en nombre de tecla de pyautogui (o None)."""
    if 0x30 <= vk <= 0x39:
        return chr(vk)
    if 0x41 <= vk <= 0x5A:
        return chr(vk).lower()
    return _VK_NAMES.get(vk)


# --- aviso flotante (overlay) -----------------------------------------------
_OVERLAY = {"proc": None, "flag": None}


def show_overlay(text: str, color: str = "#c0392b", mode: str = "banner", subtitle: str = ""):
    """
    Muestra (o actualiza) un aviso flotante topmost.
    mode: 'banner' (esquina) o 'count' (cuenta regresiva grande y centrada).
    subtitle: texto bajo el numero en modo 'count' (ej. 'Preparando grabacion...').
    """
    import os
    import sys
    import tempfile
    import subprocess
    try:
        if not _OVERLAY["flag"]:
            _OVERLAY["flag"] = os.path.join(tempfile.gettempdir(), "m18_mouse_overlay.txt")
        with open(_OVERLAY["flag"], "w", encoding="utf-8") as f:
            f.write(f"{mode}|{color}|{subtitle}\n{text}")
        proc = _OVERLAY["proc"]
        if proc is None or proc.poll() is not None:
            flags = 0x08000000  # CREATE_NO_WINDOW
            if getattr(sys, "frozen", False):
                # empaquetado: el mismo exe en modo overlay (main.py despacha)
                args = [sys.executable, "--mouse-overlay", _OVERLAY["flag"]]
            else:
                script = os.path.join(os.path.dirname(os.path.dirname(__file__)), "mouse_overlay.py")
                args = [sys.executable, script, _OVERLAY["flag"]]
            _OVERLAY["proc"] = subprocess.Popen(args, creationflags=flags)
    except Exception as e:
        print("[overlay]", e)


def close_overlay():
    """Cierra el aviso flotante (borra el flag; el proceso sale solo)."""
    import os
    try:
        if _OVERLAY["flag"] and os.path.exists(_OVERLAY["flag"]):
            os.remove(_OVERLAY["flag"])
    except Exception:
        pass
    _OVERLAY["proc"] = None


def record_macro_loop(should_stop, rec_keys: bool = True, stop_hotkey: str = "ESC",
                      max_frames: int = 8000):
    """
    Graba raton (+ teclado si rec_keys) por POLLING hasta que should_stop()
    devuelva True o se pulse el hotkey de parada. Devuelve (frames, rec_monitors)
    con el mismo esquema que usa mouse_macro. Pensado para correr en un hilo.
    """
    import ctypes
    user32 = ctypes.windll.user32

    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
    pt = POINT()

    def down(vk):
        return bool(user32.GetAsyncKeyState(vk) & 0x8000)

    stop_vks = STOP_HOTKEYS.get(stop_hotkey, [0x1B])
    key_vks = []
    if rec_keys:
        for vk in range(0x08, 0xFF):
            if vk in (0x01, 0x02, 0x04, 0x05, 0x06):
                continue
            if vk in stop_vks:
                continue
            if _vk_to_key(vk):
                key_vks.append(vk)
    mons_rec = list_monitors()
    rec_monitors = [{"index": mm["index"], "width": mm["width"], "height": mm["height"]}
                    for mm in mons_rec]
    frames = []
    t0 = time.perf_counter()
    last_pos = None
    last_btn = (False, False, False)
    prev_keys = set()
    while not should_stop():
        if stop_vks and all(down(v) for v in stop_vks):
            break
        user32.GetCursorPos(ctypes.byref(pt))
        l, r, m = down(0x01), down(0x02), down(0x04)
        cur_keys = set(v for v in key_vks if down(v)) if rec_keys else set()
        moved = (last_pos is None or abs(pt.x - last_pos[0]) >= 2
                 or abs(pt.y - last_pos[1]) >= 2)
        btn_chg = (l, r, m) != last_btn
        kd = sorted(cur_keys - prev_keys)
        ku = sorted(prev_keys - cur_keys)
        if moved or btn_chg or kd or ku:
            ms = int((time.perf_counter() - t0) * 1000)
            fr = {"t": ms, "x": int(pt.x), "y": int(pt.y), "l": l, "r": r, "m": m}
            mi = monitor_at(pt.x, pt.y, mons_rec)
            if mi is not None:
                fr["mon"] = mi
                fr["rx"] = int(pt.x) - mons_rec[mi]["x"]
                fr["ry"] = int(pt.y) - mons_rec[mi]["y"]
            if kd:
                fr["kd"] = kd
            if ku:
                fr["ku"] = ku
            frames.append(fr)
            last_pos = (pt.x, pt.y)
            last_btn = (l, r, m)
            prev_keys = cur_keys
            if len(frames) >= max_frames:
                break
        time.sleep(0.012)
    return frames, rec_monitors


def mouse_macro(steps, repeat: int = 1, stop: str = "ESC", overlay: bool = True,
                speed: float = 1.0, rec_monitors=None, overlay_text: str = "") -> Action:
    """
    Reproduce una rutina grabada de movimientos/clics (y opcionalmente teclado).
    steps: frames {"t": ms, "x":, "y":, "l":, "r":, "m":, "kd":[vk...], "ku":[vk...],
    "mon":, "rx":, "ry":}. Si el frame trae mon/rx/ry se resuelve relativo a ese
    monitor y se reescala a su resolucion actual (exacto aunque cambie el DPI /
    la disposicion); si no, usa x/y absolutas. Respeta los tiempos / `speed`.
    `stop` aborta en cualquier momento (ver STOP_HOTKEYS). Requiere pyautogui.
    """
    steps = list(steps or [])
    stop_vks = STOP_HOTKEYS.get(stop, [0x1B])
    rec_mons = rec_monitors or []
    try:
        speed = max(1.0, float(speed or 1.0))
    except (TypeError, ValueError):
        speed = 1.0

    def action(event):
        import pyautogui
        old_pause = getattr(pyautogui, "PAUSE", 0.0)
        old_fs = getattr(pyautogui, "FAILSAFE", True)
        pyautogui.PAUSE = 0
        pyautogui.FAILSAFE = False   # coords en esquinas no deben abortar
        cur_mons = list_monitors()

        def resolve(f):
            mon = f.get("mon")
            if (mon is not None and 0 <= mon < len(rec_mons) and mon < len(cur_mons)):
                rm = rec_mons[mon]; cm = cur_mons[mon]
                rw = rm.get("width") or cm["width"] or 1
                rh = rm.get("height") or cm["height"] or 1
                ax = cm["x"] + int(round((f.get("rx", 0) or 0) * cm["width"] / rw))
                ay = cm["y"] + int(round((f.get("ry", 0) or 0) * cm["height"] / rh))
                return ax, ay
            return int(f.get("x", 0)), int(f.get("y", 0))

        if overlay:
            txt = overlay_text or f"PLAYING routine  —  press {stop} to stop"
            show_overlay(txt, "#1f7a4d")
        held_btn = {"l": False, "r": False, "m": False}
        held_keys = set()

        def _release_all():
            for key, name in (("l", "left"), ("r", "right"), ("m", "middle")):
                if held_btn[key]:
                    if not _mouse_button(key, False):
                        try:
                            pyautogui.mouseUp(button=name)
                        except Exception:
                            pass
                    held_btn[key] = False
            for k in list(held_keys):
                try:
                    pyautogui.keyUp(k)
                except Exception:
                    pass
            held_keys.clear()

        aborted = False
        try:
            for _ in range(max(1, int(repeat or 1))):
                if aborted:
                    break
                for key in held_btn:
                    held_btn[key] = False
                t0 = time.perf_counter()
                for f in steps:
                    target = ((f.get("t", 0) or 0) / 1000.0) / speed
                    end = t0 + target
                    while time.perf_counter() < end:
                        if _hotkey_down(stop_vks):
                            aborted = True
                            break
                        time.sleep(0.015)
                    if aborted:
                        break
                    try:
                        ax, ay = resolve(f)
                        if not _mouse_setpos(ax, ay):   # exacto (SetCursorPos); respaldo pyautogui
                            pyautogui.moveTo(ax, ay, _pause=False)
                    except Exception:
                        pass
                    for key, name in (("l", "left"), ("r", "right"), ("m", "middle")):
                        cur = bool(f.get(key))
                        if cur != held_btn[key]:
                            if not _mouse_button(key, cur):   # clic exacto en la posicion actual
                                (pyautogui.mouseDown if cur else pyautogui.mouseUp)(button=name)
                            held_btn[key] = cur
                    for vk in f.get("kd", []) or []:
                        name = _vk_to_key(vk)
                        if name:
                            try:
                                pyautogui.keyDown(name); held_keys.add(name)
                            except Exception:
                                pass
                    for vk in f.get("ku", []) or []:
                        name = _vk_to_key(vk)
                        if name:
                            try:
                                pyautogui.keyUp(name)
                            except Exception:
                                pass
                            held_keys.discard(name)
                _release_all()
        finally:
            _release_all()
            pyautogui.PAUSE = old_pause
            pyautogui.FAILSAFE = old_fs
            if overlay:
                close_overlay()
    return action


def devsleep() -> DeviceCommand:
    """Apaga/duerme las pantallas del equipo (brillo 0)."""
    return DeviceCommand("sleep")


def hotkey_switch(a_keys, b_keys) -> Action:
    """Alterna entre dos atajos en pulsaciones sucesivas. Requiere pyautogui."""
    st = {"on": False}

    def action(event):
        keys = b_keys if st["on"] else a_keys
        st["on"] = not st["on"]
        if not keys:
            return
        if send_combo_scancode(list(keys)):
            return
        import pyautogui
        pyautogui.hotkey(*keys)
    return action


def super_hotkeys(script: str, default_delay: int = 100,
                  text_mode: str = "type", text_delay: int = 500) -> Action:
    """
    Cada linea puede ser:
      * un COMBO de teclas:  'ctrl+c'  (retardo opcional 'ctrl+v:500')
      * una PAUSA:           '1000'  o  'wait 1000' / 'delay 1000'
      * TEXTO literal:       'text hola mundo'  o  'type ...'  (tambien una
        linea con espacios que no sea combo/pausa) -> se teclea donde este el
        cursor (con acentos, sin usar el portapapeles).
    Entre pasos espera `default_delay` ms (retardo GLOBAL). Corre en un hilo.
    """
    try:
        default_delay = int(default_delay)
    except (TypeError, ValueError):
        default_delay = 100
    try:
        text_delay = int(text_delay)
    except (TypeError, ValueError):
        text_delay = 500
    paste_mode = str(text_mode).lower() == "paste"
    steps = []   # (keys, delay, text)  -- text != None => teclear literal
    for raw in (script or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        # 1) PAUSA: un numero suelto ('1000') o 'wait/delay/sleep 1000'.
        low = line.lower().replace("ms", "").strip()
        pause = None
        if low.isdigit():
            pause = int(low)
        else:
            for _kw in ("wait", "delay", "sleep", "pause"):
                if low.startswith(_kw):
                    rest = low[len(_kw):].strip(" :\t")
                    if rest.isdigit():
                        pause = int(rest)
                    break
        if pause is not None:
            steps.append(([], pause, None))
            continue
        # 2) TEXTO literal: prefijo 'text '/'type ', o una linea con espacios
        #    que no es una combinacion (los combos usan '+').
        if line.lower().startswith(("text ", "type ")):
            steps.append(([], default_delay, line.split(None, 1)[1]))
            continue
        if " " in line and "+" not in line:
            steps.append(([], default_delay, line))
            continue
        # 3) COMBO de teclas (con retardo opcional ':ms').
        combo, delay = line, default_delay
        if ":" in line:
            combo, d = line.rsplit(":", 1)
            try:
                delay = int(d)
            except ValueError:
                delay = default_delay
        keys = [k.strip() for k in combo.replace(",", "+").split("+") if k.strip()]
        steps.append((keys, delay, None))

    def action(event):
        def run():
            for keys, delay, text in steps:
                try:
                    if text is not None:
                        if paste_mode:
                            _type_text(text)          # copiar/pegar (instantaneo)
                        else:
                            _type_unicode(text, text_delay)   # maquina de escribir
                    elif keys and not send_combo_scancode(keys):
                        import pyautogui
                        pyautogui.hotkey(*keys)
                except Exception as e:   # una linea mala NO corta la secuencia
                    print("[super_hotkeys]", keys or text, e)
                time.sleep(max(0, delay) / 1000.0)
        import threading as _th
        _th.Thread(target=run, daemon=True).start()
    return action


def _parse_subaction(line: str):
    """Convierte 'tipo parametro' en un spec de accion (para flows)."""
    line = line.strip()
    if not line:
        return None
    parts = line.split(None, 1)
    t = parts[0].lower()
    p = parts[1] if len(parts) > 1 else ""
    if t == "hotkey":
        return {"type": "hotkey", "keys": [k.strip() for k in p.replace(",", "+").split("+") if k.strip()]}
    if t == "run":
        return {"type": "run", "args": p.split()}
    if t == "open":
        return {"type": "open", "path": p}
    if t == "open_url":
        return {"type": "open_url", "url": p}
    if t == "write_text":
        return {"type": "write_text", "text": p}
    if t == "multimedia":
        return {"type": "multimedia", "command": p or "playpause"}
    if t == "mouse":
        return {"type": "mouse", "event": p or "left"}
    if t == "close":
        return {"type": "close", "app": p} if p else {"type": "close"}
    return None


def action_flow(script: str) -> Action:
    """Ejecuta varias acciones en secuencia (una 'tipo parametro' por linea)."""
    specs = [s for s in (_parse_subaction(l) for l in (script or "").splitlines()) if s]

    def action(event):
        for s in specs:
            a = from_spec(s)
            if callable(a):
                try:
                    a(event)
                except Exception as e:
                    print("[action_flow]", e)
            time.sleep(0.08)
    return action


def carousel(script: str) -> Action:
    """En cada pulsacion ejecuta la siguiente accion de la lista (rota)."""
    specs = [s for s in (_parse_subaction(l) for l in (script or "").splitlines()) if s]
    idx = {"i": 0}

    def action(event):
        if not specs:
            return
        s = specs[idx["i"] % len(specs)]
        idx["i"] += 1
        a = from_spec(s)
        if callable(a):
            a(event)
    return action


def action_toggle(a_spec, b_spec) -> Action:
    """Alterna entre dos acciones en pulsaciones sucesivas."""
    st = {"on": False}

    def action(event):
        s = b_spec if st["on"] else a_spec
        st["on"] = not st["on"]
        a = from_spec(s)
        if callable(a):
            a(event)
    return action


def open_url(url: str, browser: str = "default") -> Action:
    """
    Abre una URL. `browser`: default | edge | chrome | iexplore | firefox.
    Si el navegador indicado falla, cae al navegador por defecto.
    """
    def action(event):
        b = (browser or "default").lower()
        if b in ("default", ""):
            webbrowser.open(url)
            return
        name = {"edge": "msedge", "chrome": "chrome",
                "iexplore": "iexplore", "firefox": "firefox"}.get(b)
        try:
            # 'start "" <navegador> "<url>"' resuelve el navegador por el registro
            subprocess.Popen(f'start "" {name} "{url}"', shell=True)
        except Exception:
            webbrowser.open(url)
    return action


def hotkey(*keys: str) -> Action:
    """Combinacion de teclas, ej: hotkey('ctrl','shift','o').

    Envia por SCANCODE (SendInput) para que juegos como DCS la reciban; si alguna
    tecla no se reconoce, recurre a pyautogui.
    """
    def action(event):
        if send_combo_scancode(list(keys)):
            return
        import pyautogui
        pyautogui.hotkey(*keys)
    return action


def write_text(text: str, enter: bool = False, paste: bool = False) -> Action:
    """
    Escribe un texto (hasta ~5000 chars). Si `paste`, lo pega con Ctrl+V
    (mas rapido/fiable); si no, lo teclea. `enter` pulsa Enter al final.
    Requiere pyautogui.
    """
    def action(event):
        import pyautogui
        if paste and _set_clipboard(text):
            pyautogui.hotkey("ctrl", "v")
        else:
            pyautogui.typewrite(text)
        if enter:
            pyautogui.press("enter")
    return action


def _set_clipboard(text: str) -> bool:
    """Copia texto al portapapeles de Windows (sin dependencias)."""
    try:
        import ctypes
        from ctypes import c_void_p, c_size_t
        u32 = ctypes.windll.user32
        k32 = ctypes.windll.kernel32
        k32.GlobalAlloc.restype = c_void_p
        k32.GlobalAlloc.argtypes = [ctypes.c_uint, c_size_t]
        k32.GlobalLock.restype = c_void_p
        k32.GlobalLock.argtypes = [c_void_p]
        k32.GlobalUnlock.argtypes = [c_void_p]
        u32.SetClipboardData.restype = c_void_p
        u32.SetClipboardData.argtypes = [ctypes.c_uint, c_void_p]
        data = text.encode("utf-16-le") + b"\x00\x00"
        if not u32.OpenClipboard(0):
            return False
        try:
            u32.EmptyClipboard()
            h = k32.GlobalAlloc(0x0002, len(data))   # GMEM_MOVEABLE
            p = k32.GlobalLock(h)
            ctypes.memmove(p, data, len(data))
            k32.GlobalUnlock(h)
            u32.SetClipboardData(13, h)               # CF_UNICODETEXT
        finally:
            u32.CloseClipboard()
        return True
    except Exception:
        return False


def _get_clipboard():
    """Devuelve el texto del portapapeles (CF_UNICODETEXT) o None."""
    try:
        import ctypes
        from ctypes import c_void_p
        u32 = ctypes.windll.user32
        k32 = ctypes.windll.kernel32
        k32.GlobalLock.restype = c_void_p
        k32.GlobalLock.argtypes = [c_void_p]
        k32.GlobalUnlock.argtypes = [c_void_p]
        u32.GetClipboardData.restype = c_void_p
        u32.GetClipboardData.argtypes = [ctypes.c_uint]
        if not u32.OpenClipboard(0):
            return None
        try:
            h = u32.GetClipboardData(13)   # CF_UNICODETEXT
            if not h:
                return None
            p = k32.GlobalLock(h)
            if not p:
                return None
            try:
                return ctypes.c_wchar_p(p).value
            finally:
                k32.GlobalUnlock(h)
        finally:
            u32.CloseClipboard()
    except Exception:
        return None


def _type_text(text):
    """Escribe texto LITERAL donde este el cursor pegandolo (fiable e instantaneo,
    sin corromper caracteres). Restaura el portapapeles previo. Respaldo: Unicode."""
    prev = _get_clipboard()
    try:
        if _set_clipboard(text):
            if not send_combo_scancode(["ctrl", "v"]):
                import pyautogui
                pyautogui.hotkey("ctrl", "v")
            time.sleep(0.12)   # que la app lea el portapapeles antes de restaurar
        else:
            _type_unicode(text)
    finally:
        if prev is not None:
            _set_clipboard(prev)


def password(text: str, enter: bool = False, paste: bool = True) -> Action:
    """
    Escribe una contrasena en el control enfocado. Si `paste`, la copia al
    portapapeles y pega con Ctrl+V; si no, la teclea. `enter` pulsa Enter al
    final. Requiere pyautogui.
    """
    def action(event):
        import pyautogui
        if paste and _set_clipboard(text):
            pyautogui.hotkey("ctrl", "v")
        else:
            pyautogui.typewrite(text)
        if enter:
            pyautogui.press("enter")
    return action


def sequence(*actions_list) -> Action:
    """Ejecuta varias acciones en orden al pulsar una tecla."""
    def action(event):
        for a in actions_list:
            if isinstance(a, PageNav):
                continue  # la navegacion no tiene sentido dentro de una secuencia
            a(event)
    return action


# --- descriptor serializable (dict) -> accion -------------------------------
# Tipos admitidos en la config JSON:
#   {"type": "run", "args": ["notepad.exe"]}
#   {"type": "open_url", "url": "https://..."}
#   {"type": "hotkey", "keys": ["ctrl", "c"]}
#   {"type": "write_text", "text": "hola"}
#   {"type": "next_page"} / {"type": "prev_page"} / {"type": "goto_page", "page": 2}
#   {"type": "none"} o None  -> sin accion
ACTION_TYPES = [
    "none", "run", "open", "open_app", "open_url", "hotkey", "write_text",
    "password", "multimedia", "brightness", "close", "mouse", "devsleep",
    "scene_shift", "goto_scene", "page_indicator", "hotkey_switch", "super_hotkeys",
    "action_flow", "carousel", "action_toggle",
    "play_audio", "stop_audio", "timer", "timer_exec", "routine", "calendar", "alarm", "recorder",
    "recorder_toggle", "reminder", "todo",
    "next_page", "prev_page", "goto_page", "home",
]

# configuracion global de OBS (host/port/password), la fija la app al arrancar
_OBS_CFG = None


def set_obs_config(cfg):
    global _OBS_CFG
    _OBS_CFG = cfg or None


def get_obs_config():
    return _OBS_CFG or {"host": "127.0.0.1", "port": 4455, "password": ""}


# rutinas grabadas con nombre (categoria Practical "Rutinas"); la app las fija
_ROUTINES = {}


def set_routines(routines):
    """Registra las rutinas por nombre. `routines`: lista de dicts {name, steps,...}."""
    global _ROUTINES
    _ROUTINES = {r["name"]: r for r in (routines or []) if r.get("name")}


def get_routine(name):
    return _ROUTINES.get(name)


def routine_action(name):
    """Accion que reproduce una rutina grabada por su nombre (o nada si no existe)."""
    r = _ROUTINES.get(name)
    if not r:
        def _missing(event):
            print(f"[rutina] no encontrada: {name!r}")
        return _missing
    return mouse_macro(r.get("steps", []), r.get("repeat", 1), r.get("stop", "ESC"),
                       speed=r.get("speed", 1), rec_monitors=r.get("rec_monitors"),
                       overlay_text=r.get("overlay_text", ""))


def screen_capture(clipboard: bool = True, save_dir: str = "", ask_name: bool = False):
    """Accion: captura un area de pantalla con el selector `region_capture.py`
    (otro proceso) y, segun la config, la copia al portapapeles y/o la guarda en
    una carpeta (pidiendo el nombre o con uno aleatorio). Fire-and-forget: no
    bloquea el bucle de eventos del equipo."""
    import os
    import sys
    import subprocess

    def action(_ev=None):
        try:
            flags = 0x08000000  # CREATE_NO_WINDOW
            if getattr(sys, "frozen", False):
                args = [sys.executable, "--region-capture"]
            else:
                script = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                      "region_capture.py")
                args = [sys.executable, script]
            if clipboard:
                args.append("--clipboard")
            if save_dir:
                args += ["--save-dir", save_dir]
                if ask_name:
                    args.append("--ask-name")
            subprocess.Popen(args, creationflags=flags)
        except Exception as e:
            print("[screen_capture]", e)
    return action


def from_spec(spec: dict | None):
    """Construye una accion (o PageNav, o None) a partir de un descriptor dict."""
    if not spec:
        return None
    t = spec.get("type")
    if t in (None, "none"):
        return None
    if t == "run":
        return run(*spec.get("args", []))
    if t == "open_url":
        return open_url(spec.get("url", ""), spec.get("browser", "default"))
    if t == "hotkey":
        return hotkey(*spec.get("keys", []))
    if t == "write_text":
        return write_text(spec.get("text", ""), spec.get("enter", False),
                          spec.get("paste", False))
    if t == "password":
        return password(spec.get("text", ""), spec.get("enter", False),
                        spec.get("paste", True))
    if t == "open":
        return open_path(spec.get("path", ""), spec.get("args"),
                         spec.get("display", False))
    if t == "open_app":
        return open_app(spec.get("path", ""))
    if t == "multimedia":
        return multimedia(spec.get("command", "playpause"))
    if t == "brightness":
        return brightness(int(spec.get("value", 80)))
    if t == "close":
        return close_window(spec.get("app", ""), spec.get("force", False))
    if t == "screen_capture":
        return screen_capture(bool(spec.get("clipboard", True)),
                              spec.get("save_dir", ""),
                              bool(spec.get("ask_name", False)))
    if t == "mouse":
        if spec.get("event") == "macro" or spec.get("steps"):
            return mouse_macro(spec.get("steps", []), spec.get("repeat", 1),
                               spec.get("stop", "ESC"), speed=spec.get("speed", 1),
                               rec_monitors=spec.get("rec_monitors"),
                               overlay_text=spec.get("overlay_text", ""))
        return mouse_event(spec)
    if t == "devsleep":
        return devsleep()
    if t == "scene_shift":
        tg = spec.get("target", "next")
        if tg == "prev":
            return PageNav("scene_prev")
        if tg == "home":
            return PageNav("scene_home")   # ir a la escena por defecto
        if isinstance(tg, int) or (isinstance(tg, str) and tg.lstrip("-").isdigit()):
            return goto_scene(int(tg))
        return scene_next()
    if t == "goto_scene":
        return goto_scene(int(spec.get("scene", 0)))
    if t == "page_indicator":
        return None
    if t == "hotkey_switch":
        return hotkey_switch(spec.get("a", []), spec.get("b", []))
    if t == "super_hotkeys":
        return super_hotkeys(spec.get("script", ""), spec.get("delay", 100),
                             spec.get("text_mode", "type"), spec.get("text_delay", 500))
    if t == "action_flow":
        return action_flow(spec.get("script", ""))
    if t == "carousel":
        return carousel(spec.get("script", ""))
    if t == "action_toggle":
        return action_toggle(spec.get("a", {}), spec.get("b", {}))
    if t in ("timer", "timer_exec"):
        return TimerCommand(spec)
    if t == "calendar":
        return CalendarCommand(spec)
    if t == "alarm":
        return AlarmCommand(spec)
    if t == "recorder":
        return RecorderCommand(spec)
    if t == "recorder_toggle":
        return RecorderToggleCommand(spec)
    if t == "reminder":
        return ReminderCommand(spec)
    if t == "todo":
        return TodoCommand(spec)
    if t == "calc":
        return CalcCommand(spec)
    if t == "seq_repeat":
        return SeqRepeatCommand(spec)
    if t == "routine":
        return routine_action(spec.get("name", ""))
    if t in ("play_audio", "stop_audio"):
        from . import audio as _audio
        return _audio.action_from_spec(spec)
    if t.startswith("obs_"):
        from . import obs as _obs
        return _obs.action_from_spec(spec)
    if t == "next_page":
        return next_page()
    if t == "prev_page":
        return prev_page()
    if t == "goto_page":
        return goto_page(int(spec.get("page", 0)))
    if t == "home":
        return home()
    # tipos aun no implementados (p.ej. "todo") o desconocidos: no romper el
    # runtime, simplemente no hacen nada (se avisa por consola).
    print(f"[actions] accion no implementada: {t!r} (se ignora)")
    return None
