"""
Selector de area de pantalla (estilo "recorte").

Dos usos:
  * Imagen de Tile (icono):   --out <ruta.png>   -> guarda el recorte ahi.
  * Accion "Screen Capture":  --clipboard         -> copia el recorte al portapapeles
                              --save-dir <dir>     -> guarda el recorte en esa carpeta
                              --ask-name           -> pide el nombre antes de guardar
                                                      (si no, usa un nombre aleatorio)

Cubre TODO el escritorio virtual (todos los monitores) con una captura congelada
y atenuada. El usuario arrastra un rectangulo; al soltar, se recorta esa zona de
la captura original (brillante). El recorte se entrega a resolucion completa (el
compositor de teclas ya lo redimensiona a 64x64 cuando se usa como icono).

Uso:  python region_capture.py --out <ruta.png>
      python region_capture.py --clipboard --save-dir <dir> [--ask-name]
Codigos de salida:  0 = ok,  1 = cancelado / nada que hacer.
"""

import os
import re
import sys
import tkinter as tk

from PIL import Image, ImageTk

# Reutiliza DPI-awareness y enumeracion de monitores del backend (import ligero:
# pyautogui se importa de forma perezosa alli, no al cargar el modulo).
try:
    from streamdock_m18 import actions as sd_actions
except Exception:
    sd_actions = None

_LANG = None


def _lang():
    """Idioma configurado (config.json -> 'lang'); 'en' por defecto."""
    try:
        import json
        import m18_paths
        with open(m18_paths.config_path(), encoding="utf-8") as f:
            return (json.load(f) or {}).get("lang", "en") or "en"
    except Exception:
        return "en"


def _t(key):
    """Traduce una clave de i18n_extra al idioma configurado (fallback a 'en')."""
    global _LANG
    if _LANG is None:
        _LANG = _lang()
    try:
        from i18n_extra import EXTRA
        d = EXTRA.get(key, {})
        return d.get(_LANG) or d.get("en") or key
    except Exception:
        return key


def _virtual_bounds():
    """(x, y, w, h) del escritorio virtual completo en coords fisicas."""
    mons = sd_actions.list_monitors() if sd_actions else []
    if not mons:
        # Fallback: solo el monitor primario via GetSystemMetrics.
        import ctypes
        u = ctypes.windll.user32
        return 0, 0, int(u.GetSystemMetrics(0)), int(u.GetSystemMetrics(1))
    vx = min(m["x"] for m in mons)
    vy = min(m["y"] for m in mons)
    vr = max(m["x"] + m["width"] for m in mons)
    vb = max(m["y"] + m["height"] for m in mons)
    return vx, vy, vr - vx, vb - vy


def _arg(argv, name):
    """Valor de --name <val> o --name=val, o None."""
    for i, a in enumerate(argv):
        if a == name and i + 1 < len(argv):
            return argv[i + 1]
        if a.startswith(name + "="):
            return a.split("=", 1)[1]
    return None


def _safe_name(name):
    """Sanea un nombre de archivo y asegura extension .png."""
    name = (name or "").strip()
    name = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", name).strip(" .")
    if not name:
        return ""
    if not name.lower().endswith(".png"):
        name += ".png"
    return name


def _random_name():
    import random
    import time
    return f"capture_{time.strftime('%Y%m%d_%H%M%S')}_{random.randint(0, 999):03d}.png"


def _ask_name(default):
    """Pide el nombre de la imagen en un dialogo (topmost). None si se cancela."""
    import tkinter as tk
    from tkinter import simpledialog
    r = tk.Tk()
    r.withdraw()
    try:
        r.attributes("-topmost", True)
    except Exception:
        pass
    try:
        val = simpledialog.askstring(_t("rc_save_title"), _t("rc_name_label"),
                                     initialvalue=default, parent=r)
    except Exception:
        val = None
    try:
        r.destroy()
    except Exception:
        pass
    return val


def _copy_to_clipboard(img):
    """Copia un PIL.Image al portapapeles de Windows como CF_DIB."""
    import ctypes
    import io
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "BMP")
    data = buf.getvalue()[14:]   # quitar la cabecera BMP de 14 bytes -> DIB
    buf.close()
    u = ctypes.windll.user32
    k = ctypes.windll.kernel32
    # restype/argtypes correctos para no truncar handles en 64 bits.
    k.GlobalAlloc.restype = ctypes.c_void_p
    k.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    k.GlobalLock.restype = ctypes.c_void_p
    k.GlobalLock.argtypes = [ctypes.c_void_p]
    k.GlobalUnlock.argtypes = [ctypes.c_void_p]
    u.SetClipboardData.restype = ctypes.c_void_p
    u.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
    GMEM_MOVEABLE = 0x0002
    CF_DIB = 8
    if not u.OpenClipboard(0):
        return False
    try:
        u.EmptyClipboard()
        h = k.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not h:
            return False
        p = k.GlobalLock(h)
        ctypes.memmove(p, data, len(data))
        k.GlobalUnlock(h)
        u.SetClipboardData(CF_DIB, h)   # el sistema toma posesion de la memoria
    finally:
        u.CloseClipboard()
    return True


def _select_region():
    """Muestra el overlay y devuelve el PIL.Image recortado, o None si se cancela."""
    if sd_actions:
        try:
            sd_actions.ensure_dpi_aware()
        except Exception:
            pass

    vx, vy, vw, vh = _virtual_bounds()

    # Pequena pausa para que la ventana que nos lanzo termine de minimizarse y
    # NO salga en la captura (el proceso ya tardo en arrancar, esto es margen).
    import time
    time.sleep(0.25)

    from PIL import ImageGrab
    try:
        full = ImageGrab.grab(bbox=(vx, vy, vx + vw, vy + vh), all_screens=True)
    except TypeError:
        full = ImageGrab.grab()
        vx, vy = 0, 0
        vw, vh = full.size
    full = full.convert("RGB")

    dim = Image.blend(full, Image.new("RGB", full.size, (0, 0, 0)), 0.55)

    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.geometry(f"{vw}x{vh}+{vx}+{vy}")
    root.configure(bg="#000000")

    canvas = tk.Canvas(root, width=vw, height=vh, highlightthickness=0, bd=0,
                       bg="#000000", cursor="crosshair")
    canvas.pack(fill="both", expand=True)

    photo = ImageTk.PhotoImage(dim)
    canvas.create_image(0, 0, anchor="nw", image=photo)
    canvas.create_text(vw // 2, 28, text=_t("rc_hint"),
                       fill="#ffffff", font=("Segoe UI", 13, "bold"))

    st = {"x0": None, "y0": None, "rect": None, "dims": None, "result": None}

    def on_press(e):
        st["x0"], st["y0"] = e.x, e.y
        for key in ("rect", "dims"):
            if st[key] is not None:
                canvas.delete(st[key]); st[key] = None

    def on_motion(e):
        if st["x0"] is None:
            return
        x0, y0, x1, y1 = st["x0"], st["y0"], e.x, e.y
        if st["rect"] is None:
            st["rect"] = canvas.create_rectangle(x0, y0, x1, y1,
                                                 outline="#4fe3ff", width=2)
        else:
            canvas.coords(st["rect"], x0, y0, x1, y1)
        w, h = abs(x1 - x0), abs(y1 - y0)
        label = f"{w} x {h}"
        tx, ty = max(x0, x1), min(y0, y1) - 12
        if st["dims"] is None:
            st["dims"] = canvas.create_text(tx, ty, text=label, anchor="se",
                                            fill="#4fe3ff", font=("Segoe UI", 11, "bold"))
        else:
            canvas.coords(st["dims"], tx, ty)
            canvas.itemconfigure(st["dims"], text=label)

    def _close():
        if st.get("closed"):
            return
        st["closed"] = True
        try:
            root.destroy()
        except Exception:
            pass

    def on_release(e):
        if st["x0"] is None:
            return
        l, r = sorted((st["x0"], e.x))
        t, b = sorted((st["y0"], e.y))
        l = max(0, min(l, vw)); r = max(0, min(r, vw))
        t = max(0, min(t, vh)); b = max(0, min(b, vh))
        if (r - l) >= 2 and (b - t) >= 2:
            st["result"] = full.crop((l, t, r, b))
        _close()

    def on_cancel(_e=None):
        st["result"] = None
        _close()

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_motion)
    canvas.bind("<ButtonRelease-1>", on_release)
    root.bind_all("<Escape>", on_cancel)
    root.bind_all("<Button-3>", on_cancel)

    def _grab_focus():
        try:
            root.focus_force()
            canvas.focus_set()
            root.grab_set()
        except Exception:
            pass

    # Una ventana overrideredirect lanzada desde un subproceso NO consigue el foco
    # de teclado de forma fiable en Windows, asi que bind("<Escape>") puede no
    # llegar nunca. Sondeamos el estado GLOBAL de ESC con Win32 GetAsyncKeyState
    # (no depende del foco). Tambien cancela por combinaciones del raton.
    def _poll_cancel():
        if st.get("closed"):
            return
        try:
            import ctypes
            # bit alto (0x8000) = tecla actualmente presionada. 0x1B = VK_ESCAPE.
            if ctypes.windll.user32.GetAsyncKeyState(0x1B) & 0x8000:
                on_cancel()
                return
        except Exception:
            pass
        try:
            root.after(40, _poll_cancel)
        except Exception:
            pass

    root.update_idletasks()
    _grab_focus()
    root.after(60, _grab_focus)
    # arranca el sondeo con un pequeno margen para no capturar un ESC previo.
    root.after(250, _poll_cancel)

    root.mainloop()
    return st["result"]


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    out_path = _arg(argv, "--out")
    save_dir = _arg(argv, "--save-dir")
    want_clip = "--clipboard" in argv
    ask_name = "--ask-name" in argv

    if not (out_path or save_dir or want_clip):
        print("[region_capture] nada que hacer (usa --out / --clipboard / --save-dir)",
              file=sys.stderr)
        return 1

    img = _select_region()
    if img is None:
        return 1   # cancelado

    did = False

    # 1) Portapapeles.
    if want_clip:
        try:
            if _copy_to_clipboard(img):
                did = True
        except Exception as e:
            print("[region_capture] portapapeles:", e, file=sys.stderr)

    # 2) Ruta exacta (flujo del icono).
    if out_path:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
            img.save(out_path, "PNG")
            print(out_path)
            did = True
        except Exception as e:
            print("[region_capture] no se pudo guardar:", e, file=sys.stderr)

    # 3) Carpeta de guardado (flujo de la accion), con nombre pedido o aleatorio.
    if save_dir:
        name = ""
        if ask_name:
            name = _safe_name(_ask_name(_random_name()))
        if not name:
            name = _random_name()
        try:
            os.makedirs(save_dir, exist_ok=True)
            dest = os.path.join(save_dir, name)
            img.save(dest, "PNG")
            print(dest)
            did = True
        except Exception as e:
            print("[region_capture] no se pudo guardar en carpeta:", e, file=sys.stderr)

    return 0 if did else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
