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
            script = os.path.join(os.path.dirname(os.path.dirname(__file__)), "mouse_overlay.py")
            flags = 0x08000000  # CREATE_NO_WINDOW
            _OVERLAY["proc"] = subprocess.Popen([sys.executable, script, _OVERLAY["flag"]],
                                                creationflags=flags)
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
                        pyautogui.moveTo(ax, ay, _pause=False)
                    except Exception:
                        pass
                    for key, name in (("l", "left"), ("r", "right"), ("m", "middle")):
                        cur = bool(f.get(key))
                        if cur != held_btn[key]:
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
        import pyautogui
        keys = b_keys if st["on"] else a_keys
        st["on"] = not st["on"]
        if keys:
            pyautogui.hotkey(*keys)
    return action


def super_hotkeys(script: str) -> Action:
    """
    Secuencia de atajos: una combinacion por linea, con retardo opcional
    'combo:ms' (ej. 'ctrl+c', 'ctrl+v:500', 'enter'). Requiere pyautogui.
    """
    steps = []
    for line in (script or "").splitlines():
        line = line.strip()
        if not line:
            continue
        combo, delay = line, 100
        if ":" in line:
            combo, d = line.rsplit(":", 1)
            try:
                delay = int(d)
            except ValueError:
                delay = 100
        keys = [k.strip() for k in combo.replace(",", "+").split("+") if k.strip()]
        steps.append((keys, delay))

    def action(event):
        import pyautogui
        for keys, delay in steps:
            if keys:
                pyautogui.hotkey(*keys)
            time.sleep(max(0, delay) / 1000.0)
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
    """Combinacion de teclas, ej: hotkey('ctrl','shift','o'). Requiere pyautogui."""
    def action(event):
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
    "next_page", "prev_page", "goto_page", "home",
]

# configuracion global de OBS (host/port/password), la fija la app al arrancar
_OBS_CFG = None


def set_obs_config(cfg):
    global _OBS_CFG
    _OBS_CFG = cfg or None


def get_obs_config():
    return _OBS_CFG or {"host": "127.0.0.1", "port": 4455, "password": ""}


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
        return super_hotkeys(spec.get("script", ""))
    if t == "action_flow":
        return action_flow(spec.get("script", ""))
    if t == "carousel":
        return carousel(spec.get("script", ""))
    if t == "action_toggle":
        return action_toggle(spec.get("a", {}), spec.get("b", {}))
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
