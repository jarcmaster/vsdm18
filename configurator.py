"""
App de configuracion para el Stream Dock M18 (GUI, Tkinter).

Permite:
  - Crear / borrar / renombrar paginas y REORDENARLAS (subir/bajar).
  - Editar las 15 teclas de cada pagina: texto, color de letra/fondo, icono
    (imagen) y accion (lanzar app, URL, atajo, teclear, o navegar paginas).
  - Configurar los 3 botones laterales (left/mid/right).
  - Guardar / cargar la configuracion en JSON.
  - Previsualizar la pagina seleccionada en el dispositivo real.

Ejecuta:  python configurator.py
Luego, para usar la config:  python run_config.py config.json
"""

import json
import os
import tkinter as tk
from tkinter import ttk, filedialog, colorchooser, messagebox, simpledialog

from streamdock_m18 import default_config, build_app_from_config, StreamDockM18
from streamdock_m18 import obs as sd_obs
from streamdock_m18.actions import ACTION_TYPES

_APPS_CACHE = None


def get_installed_apps(reload=False):
    """Devuelve {nombre: ruta_lnk} de los accesos directos del menu Inicio."""
    global _APPS_CACHE
    if _APPS_CACHE is not None and not reload:
        return _APPS_CACHE
    apps = {}
    dirs = [
        os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"),
                     "Microsoft", "Windows", "Start Menu", "Programs"),
        os.path.join(os.environ.get("APPDATA", ""),
                     "Microsoft", "Windows", "Start Menu", "Programs"),
    ]
    for base in dirs:
        if not os.path.isdir(base):
            continue
        for root, _, files in os.walk(base):
            for fn in files:
                if fn.lower().endswith(".lnk"):
                    apps.setdefault(os.path.splitext(fn)[0], os.path.join(root, fn))
    _APPS_CACHE = dict(sorted(apps.items(), key=lambda kv: kv[0].lower()))
    return _APPS_CACHE

import io
try:
    from PIL import Image, ImageTk, ImageDraw
    _HAS_IMGTK = True
except Exception:
    _HAS_IMGTK = False

from streamdock_m18 import device as sd_device

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
ICONS_DIR = os.path.join(os.path.dirname(__file__), "icons")
DEVICE_IMG = os.path.join(os.path.dirname(__file__), "assets", "device.png")
_IMG_EXT = (".png", ".jpg", ".jpeg", ".gif", ".bmp")

# Geometria de la imagen del equipo (fracciones del ancho/alto de la imagen),
# detectada automaticamente sobre assets/device.png (472x414).
DEV_COLX = [0.180, 0.335, 0.489, 0.644, 0.799]   # centros X de las 5 columnas
DEV_ROWY = [0.223, 0.401, 0.580]                 # centros Y de las 3 filas
DEV_KEY_N = 0.112                                # lado de tecla (fraccion del ancho)
DEV_AUXX = [0.34, 0.49, 0.655]                   # centros X de los 3 botones fisicos
DEV_AUXY = 0.800                                 # centro Y de los botones fisicos
DEV_AUX_H = 0.095                                # diametro del circulo (fraccion del ALTO)

# Navegadores para la accion Website (open_url)
BROWSERS = [("Default Browser", "default"), ("Microsoft Edge", "edge"),
            ("Google Chrome", "chrome"), ("Internet Explorer", "iexplore"),
            ("Mozilla Firefox", "firefox")]


_FONTS_CACHE = None


def get_system_fonts():
    """Devuelve {nombre_familia: ruta_ttf} de las fuentes instaladas (Windows)."""
    global _FONTS_CACHE
    if _FONTS_CACHE is not None:
        return _FONTS_CACHE
    fonts = {}
    try:
        import winreg
        fonts_dir = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
        for hive, sub in ((winreg.HKEY_LOCAL_MACHINE,
                           r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"),
                          (winreg.HKEY_CURRENT_USER,
                           r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts")):
            try:
                k = winreg.OpenKey(hive, sub)
            except OSError:
                continue
            i = 0
            while True:
                try:
                    name, val, _ = winreg.EnumValue(k, i); i += 1
                except OSError:
                    break
                if not str(val).lower().endswith((".ttf", ".ttc", ".otf")):
                    continue
                # nombre: "Arial (TrueType)" -> "Arial"
                disp = name.rsplit("(", 1)[0].strip()
                path = val if os.path.isabs(val) else os.path.join(fonts_dir, val)
                if os.path.exists(path):
                    fonts[disp] = path
    except Exception:
        pass
    _FONTS_CACHE = dict(sorted(fonts.items(), key=lambda kv: kv[0].lower()))
    return _FONTS_CACHE


def read_config_file(path):
    """Lee un config.json y rellena los campos que falten."""
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    cfg.setdefault("pages", [{"name": "Pagina 1", "keys": {}}])
    cfg.setdefault("aux", {})
    cfg.setdefault("default_page", 0)
    cfg.setdefault("brightness", 80)
    return cfg


def load_thumb(path, size):
    """Carga una imagen y devuelve un ImageTk.PhotoImage reducido a `size` px."""
    img = Image.open(path).convert("RGBA")
    img.thumbnail((size, size))
    return ImageTk.PhotoImage(img)


def make_trash_icon(size=22):
    """Dibuja un icono de papelera (rojo) y lo devuelve como ImageTk.PhotoImage."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    w = size
    col = (225, 80, 80, 255)
    dark = (120, 30, 30, 255)
    d.rectangle([w*0.40, w*0.12, w*0.60, w*0.20], fill=col)              # asa
    d.rectangle([w*0.16, w*0.20, w*0.84, w*0.28], fill=col)             # tapa
    d.polygon([(w*0.24, w*0.28), (w*0.76, w*0.28),
               (w*0.70, w*0.86), (w*0.30, w*0.86)], fill=col)          # cuerpo
    lw = max(1, int(w*0.045))
    for fx in (0.40, 0.50, 0.60):
        d.line([(w*fx, w*0.36), (w*fx, w*0.78)], fill=dark, width=lw)   # ranuras
    return ImageTk.PhotoImage(img)


def render_key_photo(spec, size, pos=None):
    """
    Devuelve un ImageTk.PhotoImage que muestra la tecla EXACTAMENTE como la
    pinta el dispositivo: genera el mismo 64x64 que se envia (icono reescalado
    o texto renderizado) y lo escala a `size` px para llenar el boton.
    Las teclas vacias salen en negro (como fisicamente) con su numero en gris.
    """
    base = None
    try:
        img_path = (spec or {}).get("image")
        text = (spec or {}).get("text")
        if (img_path and os.path.exists(img_path)) or text:
            # mismo compositor que el dispositivo: imagen + texto (hasta 3 lineas)
            base = sd_device.compose_key_image(
                text=text,
                image=img_path if (img_path and os.path.exists(img_path)) else None,
                fg=tuple(spec.get("fg", [255, 255, 255])),
                bg=tuple(spec.get("bg", [0, 0, 0])),
                font=spec.get("font"))
    except Exception:
        base = None
    if base is None:
        # sin texto ni imagen: mostrar el color de fondo (refleja el color elegido)
        bgc = tuple((spec or {}).get("bg", [0, 0, 0]))
        base = Image.new("RGB", (64, 64), bgc)
        if pos is not None:
            ImageDraw.Draw(base).text((3, 2), str(pos), fill=(120, 120, 120))
    disp = base.resize((size, size), Image.LANCZOS)
    return ImageTk.PhotoImage(disp)


# Librería de acciones (estilo software oficial). Cada entrada: (nombre, action_id).
# action_id "todo:" = aun sin implementar (a la espera de especificaciones).
ACTION_LIBRARY = [
    ("Stream Dock", [
        ("Create Folder", "create_folder"),
        ("Scene Shift", "todo:scene_shift"),
        ("Previous Page", "prev_page"),
        ("Next Page", "next_page"),
        ("Go to Page", "goto_page"),
        ("Page Indicator", "todo:page_indicator"),
        ("Brightness", "brightness"),
        ("devsleep", "todo:devsleep"),
    ]),
    ("Toolbox", [
        ("Website", "open_url"),
        ("Hotkey", "hotkey"),
        ("HotkeySwitch", "todo:hotkey_switch"),
        ("Super Hotkeys", "todo:super_hotkeys"),
        ("Mouse event", "todo:mouse_event"),
        ("Open", "open"),
        ("Open an app", "open_app"),
        ("Close", "todo:close_app"),
        ("Text", "write_text"),
        ("Password", "password"),
        ("Multimedia", "multimedia"),
    ]),
    ("Audio Player", [
        ("Play Audio", "todo:play_audio"),
        ("Stop Audio", "todo:stop_audio"),
    ]),
    ("Operation Flow", [
        ("Action flow", "todo:action_flow"),
        ("Carousel", "todo:carousel"),
        ("Action Toggle", "todo:action_toggle"),
    ]),
    ("OBS Studio", [
        ("Record", "obs_record"),
        ("Stream", "obs_stream"),
        ("Virtual camera", "obs_vcam"),
        ("Scene", "obs_scene"),
        ("Source Visibility", "obs_source"),
        ("Audio Mixer", "obs_audio"),
        ("Studio Mode", "obs_studio_mode"),
        ("Screenshot", "obs_screenshot"),
        ("Transition", "obs_transition"),
        ("Green background image UP", "obs_green_up"),
        ("Green background image DN", "obs_green_dn"),
    ]),
]


def center_on_current_monitor(win):
    """Centra la ventana en el monitor donde esta (Windows: via ctypes)."""
    win.update_idletasks()
    w, h = win.winfo_width(), win.winfo_height()
    try:
        import ctypes
        from ctypes import wintypes

        class RECT(ctypes.Structure):
            _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                        ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

        class MONITORINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", RECT),
                        ("rcWork", RECT), ("dwFlags", wintypes.DWORD)]

        user32 = ctypes.windll.user32
        hwnd = win.winfo_id()
        mon = user32.MonitorFromWindow(hwnd, 2)  # MONITOR_DEFAULTTONEAREST
        mi = MONITORINFO(); mi.cbSize = ctypes.sizeof(MONITORINFO)
        user32.GetMonitorInfoW(mon, ctypes.byref(mi))
        mx, my = mi.rcWork.left, mi.rcWork.top
        mw = mi.rcWork.right - mi.rcWork.left
        mh = mi.rcWork.bottom - mi.rcWork.top
        x, y = mx + (mw - w) // 2, my + (mh - h) // 2
    except Exception:
        x = (win.winfo_screenwidth() - w) // 2
        y = (win.winfo_screenheight() - h) // 2
    win.geometry(f"+{max(x, 0)}+{max(y, 0)}")

# Disposicion de las 15 teclas LCD (posicion logica -> fila, columna)
GRID = [(r, c) for r in range(3) for c in range(5)]  # pos 0..14


def rgb_to_hex(rgb):
    r, g, b = rgb
    return f"#{r:02x}{g:02x}{b:02x}"


class IconPicker(tk.Toplevel):
    """Galeria: navega icons/<categoria>/<subcarpeta> y elige un icono."""

    def __init__(self, master, icons_dir):
        super().__init__(master)
        self.title("Galeria de iconos")
        self.geometry("660x580")
        self.icons_dir = icons_dir
        self.result = None
        self._thumbs = []  # mantener referencias para que no las borre el GC

        top = ttk.Frame(self); top.pack(fill="x", padx=8, pady=6)
        ttk.Label(top, text="Categoria:").pack(side="left")
        self.cat_var = tk.StringVar()
        cats = [d for d in sorted(os.listdir(icons_dir))
                if os.path.isdir(os.path.join(icons_dir, d))]
        self.cat_cb = ttk.Combobox(top, textvariable=self.cat_var, values=cats,
                                   state="readonly", width=18)
        self.cat_cb.pack(side="left", padx=4)
        self.cat_cb.bind("<<ComboboxSelected>>", lambda e: self._on_cat())

        ttk.Label(top, text="Subcarpeta:").pack(side="left", padx=(10, 0))
        self.sub_var = tk.StringVar()
        self.sub_cb = ttk.Combobox(top, textvariable=self.sub_var, values=[],
                                   state="readonly", width=20)
        self.sub_cb.pack(side="left", padx=4)
        self.sub_cb.bind("<<ComboboxSelected>>", lambda e: self._populate())

        srch = ttk.Frame(self); srch.pack(fill="x", padx=8)
        ttk.Label(srch, text="Buscar:").pack(side="left")
        self.search_var = tk.StringVar()
        ent = ttk.Entry(srch, textvariable=self.search_var)
        ent.pack(side="left", fill="x", expand=True, padx=4)
        ent.bind("<KeyRelease>", lambda e: self._populate())

        mid = ttk.Frame(self); mid.pack(fill="both", expand=True, padx=8, pady=6)
        self.canvas = tk.Canvas(mid, highlightthickness=0)
        sb = ttk.Scrollbar(mid, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        self.inner.bind("<Configure>",
                        lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=sb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.canvas.bind_all("<MouseWheel>",
                             lambda e: self.canvas.yview_scroll(int(-e.delta / 120), "units"))

        self.transient(master); self.grab_set()
        if cats:
            self.cat_var.set(cats[0]); self._on_cat()
        center_on_current_monitor(self)

    def _current_folder(self):
        cat, sub = self.cat_var.get(), self.sub_var.get()
        if not cat:
            return None
        base = os.path.join(self.icons_dir, cat)
        if sub and sub != "(raiz)":
            return os.path.join(base, sub)
        return base

    def _on_cat(self):
        base = os.path.join(self.icons_dir, self.cat_var.get())
        subs = [d for d in sorted(os.listdir(base))
                if os.path.isdir(os.path.join(base, d))]
        has_imgs = any(f.lower().endswith(_IMG_EXT) for f in os.listdir(base))
        values = (["(raiz)"] if has_imgs else []) + subs
        self.sub_cb.config(values=values)
        self.sub_var.set(values[0] if values else "")
        self._populate()

    def _populate(self):
        for w in self.inner.winfo_children():
            w.destroy()
        self._thumbs.clear()
        folder = self._current_folder()
        if not folder or not os.path.isdir(folder):
            return
        q = self.search_var.get().lower().strip()
        files = [f for f in sorted(os.listdir(folder))
                 if f.lower().endswith(_IMG_EXT) and q in f.lower()]
        cols = 5
        for i, fn in enumerate(files):
            path = os.path.join(folder, fn)
            try:
                thumb = load_thumb(path, 72)
            except Exception:
                continue
            self._thumbs.append(thumb)
            name = os.path.splitext(fn)[0]
            b = tk.Button(self.inner, image=thumb, text=name, compound="top",
                          width=92, wraplength=88, font=("", 7),
                          command=lambda p=path: self._choose(p))
            b.grid(row=i // cols, column=i % cols, padx=4, pady=4, sticky="n")

    def _choose(self, path):
        self.result = path
        self.destroy()


class HotkeyCaptureDialog(tk.Toplevel):
    """Captura una combinacion de teclas (o una sola) y la devuelve en result."""

    def __init__(self, master):
        super().__init__(master)
        self.title("Capturar atajo")
        self.resizable(False, False)
        self.result = None
        ttk.Label(self, text="Pulsa la combinacion de teclas\n(Esc para cancelar)",
                  justify="center").pack(padx=24, pady=(16, 6))
        self.info = ttk.Label(self, text="...", font=("", 13, "bold"))
        self.info.pack(pady=(0, 16))
        self.bind("<KeyPress>", self._on_key)
        self.transient(master); self.grab_set()
        self.focus_force()
        center_on_current_monitor(self)

    @staticmethod
    def _norm(keysym):
        m = {"Return": "enter", "Escape": "esc", "space": "space", "Tab": "tab",
             "BackSpace": "backspace", "Delete": "delete", "Prior": "pageup",
             "Next": "pagedown", "Up": "up", "Down": "down", "Left": "left",
             "Right": "right", "Home": "home", "End": "end"}
        if keysym in m:
            return m[keysym]
        return keysym.lower()

    def _on_key(self, e):
        if e.keysym == "Escape":
            self.result = None; self.destroy(); return
        mods = []
        if e.state & 0x4:
            mods.append("ctrl")
        if (e.state & 0x20000) or (e.state & 0x8):
            mods.append("alt")
        if e.state & 0x1:
            mods.append("shift")
        if e.keysym in ("Control_L", "Control_R", "Alt_L", "Alt_R", "Shift_L",
                        "Shift_R", "Win_L", "Win_R", "Super_L", "Super_R"):
            self.info.config(text=("+".join(mods) + "+..." if mods else "..."))
            return
        combo = "+".join(mods + [self._norm(e.keysym)])
        self.result = combo
        self.info.config(text=combo)
        self.after(300, self.destroy)


class KeyEditor(tk.Toplevel):
    """Dialogo para editar una tecla (o un boton lateral si is_aux=True)."""

    def __init__(self, master, spec: dict, title: str, is_aux: bool = False,
                 preset_type: str | None = None):
        super().__init__(master)
        self.title(title)
        self.resizable(False, False)
        self.result = None
        self.is_aux = is_aux
        spec = dict(spec or {})
        self.fg = list(spec.get("fg", [255, 255, 255]))
        self.bg = list(spec.get("bg", [0, 0, 0]))
        self.font_path = spec.get("font")

        row = 0
        # cabecera: icono papelera (vaciar la tecla) arriba a la derecha
        hdr = ttk.Frame(self)
        hdr.grid(row=row, column=0, columnspan=2, sticky="ew", padx=8, pady=(6, 0))
        self._trash_img = make_trash_icon(22) if _HAS_IMGTK else None
        tb = tk.Button(hdr, bd=0, relief="flat", cursor="hand2", command=self._clear)
        if self._trash_img:
            tb.config(image=self._trash_img)
        else:
            tb.config(text="Vaciar")
        tb.pack(side="right")
        row += 1

        if not is_aux:
            ttk.Label(self, text="Texto (hasta\n3 lineas, Enter):").grid(
                row=row, column=0, sticky="e", padx=6, pady=4)
            self.text_box = tk.Text(self, width=24, height=3, font=("", 10), wrap="word")
            self.text_box.insert("1.0", spec.get("text") or "")
            self.text_box.grid(row=row, column=1, padx=6, pady=4, sticky="w")
            self.text_box.bind("<KeyRelease>", lambda e: self._update_preview())
            self.text_box.bind("<Return>", self._limit_lines)
            row += 1

            ttk.Label(self, text="Fuente:").grid(row=row, column=0, sticky="e", padx=6)
            self._fonts = get_system_fonts()
            names = list(self._fonts.keys())
            cur_name = next((n for n, p in self._fonts.items() if p == self.font_path),
                            "Arial" if "Arial" in self._fonts else (names[0] if names else ""))
            self.font_var = tk.StringVar(value=cur_name)
            fcb = ttk.Combobox(self, textvariable=self.font_var, values=names,
                               state="readonly", width=22)
            fcb.grid(row=row, column=1, sticky="w", padx=6, pady=2)
            fcb.bind("<<ComboboxSelected>>", lambda e: self._on_font())
            self.font_path = self._fonts.get(cur_name, self.font_path)
            row += 1

            ttk.Label(self, text="Color letra:").grid(row=row, column=0, sticky="e", padx=6)
            self.fg_btn = tk.Button(self, text="  ", bg=rgb_to_hex(self.fg), width=4,
                                    command=self._pick_fg)
            self.fg_btn.grid(row=row, column=1, sticky="w", padx=6, pady=2)
            row += 1

            ttk.Label(self, text="Color fondo:").grid(row=row, column=0, sticky="e", padx=6)
            self.bg_btn = tk.Button(self, text="  ", bg=rgb_to_hex(self.bg), width=4,
                                    command=self._pick_bg)
            self.bg_btn.grid(row=row, column=1, sticky="w", padx=6, pady=2)
            row += 1

            ttk.Label(self, text="Icono:").grid(row=row, column=0, sticky="e", padx=6)
            self.img_var = tk.StringVar(value=spec.get("image") or "")
            f = ttk.Frame(self); f.grid(row=row, column=1, sticky="w", padx=6, pady=2)
            ttk.Entry(f, textvariable=self.img_var, width=16).pack(side="left")
            ttk.Button(f, text="...", width=3, command=self._pick_img).pack(side="left", padx=2)
            ttk.Button(f, text="Galeria", command=self._open_gallery).pack(side="left")
            row += 1
            ttk.Label(self, text="Vista previa:").grid(row=row, column=0, sticky="e", padx=6)
            self.preview_lbl = tk.Label(self, relief="groove", bd=2)
            self.preview_lbl.grid(row=row, column=1, sticky="w", padx=6, pady=2)
            row += 1
            ttk.Button(self, text="Quitar icono",
                       command=self._clear_icon).grid(row=row, column=1, sticky="w", padx=6)
            row += 1

        # --- accion ---
        ttk.Separator(self, orient="horizontal").grid(row=row, column=0, columnspan=2, sticky="ew", pady=6)
        row += 1
        ttk.Label(self, text="Accion:").grid(row=row, column=0, sticky="e", padx=6)
        action = spec.get("action") or {"type": "none"}
        self.type_var = tk.StringVar(value=action.get("type", "none"))
        cb = ttk.Combobox(self, textvariable=self.type_var, values=ACTION_TYPES,
                          state="readonly", width=20)
        cb.grid(row=row, column=1, padx=6, pady=2, sticky="w")
        cb.bind("<<ComboboxSelected>>", lambda e: self._refresh_param())
        row += 1

        ttk.Label(self, text="Parametro:").grid(row=row, column=0, sticky="e", padx=6)
        self.param_var = tk.StringVar(value=self._param_from_action(action))
        pf = ttk.Frame(self); pf.grid(row=row, column=1, padx=6, pady=2, sticky="w")
        self.param_entry = ttk.Entry(pf, textvariable=self.param_var, width=22)
        self.param_entry.pack(side="left")
        self.capture_btn = ttk.Button(pf, text="Capturar", command=self._capture_hotkey)
        row += 1
        # navegador (solo para open_url)
        self.browser_lbl = ttk.Label(self, text="Navegador:")
        self.browser_var = tk.StringVar()
        self.browser_cb = ttk.Combobox(self, textvariable=self.browser_var,
                                        values=[n for n, _ in BROWSERS], state="readonly", width=20)
        cur_browser = action.get("browser", "default") if action.get("type") == "open_url" else "default"
        self.browser_cb.set(dict((v, n) for n, v in BROWSERS).get(cur_browser, "Default Browser"))
        self._browser_row = row
        row += 1
        self.hint = ttk.Label(self, text="", foreground="#888")
        self.hint.grid(row=row, column=0, columnspan=2, padx=6)
        row += 1
        if preset_type and action.get("type", "none") == "none":
            self.type_var.set(preset_type)
        self._refresh_param()

        # --- botones ---
        bar = ttk.Frame(self); bar.grid(row=row, column=0, columnspan=2, pady=8)
        ttk.Button(bar, text="Aceptar", command=self._ok).pack(side="left", padx=4)
        ttk.Button(bar, text="Vaciar tecla", command=self._clear).pack(side="left", padx=4)
        ttk.Button(bar, text="Cancelar", command=self.destroy).pack(side="left", padx=4)

        if not self.is_aux:
            self._update_preview()
        self.transient(master)
        self.grab_set()
        center_on_current_monitor(self)

    def _text(self):
        return self.text_box.get("1.0", "end-1c")

    def _limit_lines(self, event):
        # bloquear Enter si ya hay 3 lineas (2 saltos)
        if self.text_box.get("1.0", "end-1c").count("\n") >= 2:
            return "break"

    def _on_font(self):
        self.font_path = self._fonts.get(self.font_var.get())
        self._update_preview()

    def _param_from_action(self, action):
        t = action.get("type")
        if t == "run":
            return " ".join(action.get("args", []))
        if t == "open_url":
            return action.get("url", "")
        if t == "hotkey":
            return "+".join(action.get("keys", []))
        if t == "write_text":
            return action.get("text", "")
        if t == "goto_page":
            return str(action.get("page", 0))
        return ""

    def _refresh_param(self):
        t = self.type_var.get()
        hints = {
            "run": "programa y argumentos, p.ej.:  notepad.exe",
            "open_url": "URL, p.ej.:  https://google.com",
            "hotkey": "teclas separadas por +, p.ej.:  ctrl+shift+o",
            "write_text": "texto a teclear",
            "goto_page": "indice de pagina (0, 1, 2...)",
            "next_page": "(sin parametro)",
            "prev_page": "(sin parametro)",
            "none": "(sin accion)",
        }
        self.hint.config(text=hints.get(t, ""))
        state = "normal" if t in ("run", "open_url", "hotkey", "write_text", "goto_page") else "disabled"
        self.param_entry.config(state=state)
        # boton Capturar solo para hotkey
        if t == "hotkey":
            self.capture_btn.pack(side="left", padx=4)
        else:
            self.capture_btn.pack_forget()
        # fila Navegador solo para open_url
        if t == "open_url":
            self.browser_lbl.grid(row=self._browser_row, column=0, sticky="e", padx=6)
            self.browser_cb.grid(row=self._browser_row, column=1, sticky="w", padx=6, pady=2)
        else:
            self.browser_lbl.grid_remove()
            self.browser_cb.grid_remove()

    def _capture_hotkey(self):
        dlg = HotkeyCaptureDialog(self)
        self.wait_window(dlg)
        if dlg.result:
            self.param_var.set(dlg.result)

    def _build_action(self):
        t = self.type_var.get()
        p = self.param_var.get().strip()
        if t == "none":
            return None
        if t == "run":
            return {"type": "run", "args": p.split()}
        if t == "open_url":
            browser = dict(BROWSERS).get(self.browser_var.get(), "default")
            url = p
            if url and "://" not in url:
                url = "https://" + url
            return {"type": "open_url", "url": url, "browser": browser}
        if t == "hotkey":
            return {"type": "hotkey", "keys": [k.strip() for k in p.replace(",", "+").split("+") if k.strip()]}
        if t == "write_text":
            return {"type": "write_text", "text": p}
        if t == "goto_page":
            return {"type": "goto_page", "page": int(p or 0)}
        if t in ("next_page", "prev_page"):
            return {"type": t}
        return None

    def _pick_fg(self):
        c = colorchooser.askcolor(color=rgb_to_hex(self.fg))[0]
        if c:
            self.fg = [int(x) for x in c]; self.fg_btn.config(bg=rgb_to_hex(self.fg))
            self._update_preview()

    def _pick_bg(self):
        c = colorchooser.askcolor(color=rgb_to_hex(self.bg))[0]
        if c:
            self.bg = [int(x) for x in c]; self.bg_btn.config(bg=rgb_to_hex(self.bg))
            self._update_preview()

    def _pick_img(self):
        path = filedialog.askopenfilename(
            initialdir=ICONS_DIR if os.path.isdir(ICONS_DIR) else os.path.dirname(__file__),
            filetypes=[("Imagenes", "*.png *.jpg *.jpeg *.gif *.bmp"), ("Todos", "*.*")])
        if path:
            self.img_var.set(path)
            self._update_preview()

    def _open_gallery(self):
        if not _HAS_IMGTK:
            messagebox.showinfo("Info", "Necesitas Pillow para la galeria (pip install Pillow)."); return
        if not os.path.isdir(ICONS_DIR):
            messagebox.showinfo("Info", f"No existe la carpeta de iconos:\n{ICONS_DIR}"); return
        picker = IconPicker(self, ICONS_DIR)
        self.wait_window(picker)
        if picker.result:
            self.img_var.set(picker.result)
            self._update_preview()

    def _clear_icon(self):
        self.img_var.set("")
        self._update_preview()

    def _current_spec(self):
        return {"text": self._text(), "image": self.img_var.get(),
                "fg": self.fg, "bg": self.bg, "font": self.font_path}

    def _update_preview(self):
        if not hasattr(self, "preview_lbl"):
            return
        if _HAS_IMGTK:
            # vista previa IDENTICA a como se vera en el dispositivo (64x64 -> 80px)
            self._thumb = render_key_photo(self._current_spec(), 80)
            self.preview_lbl.config(image=self._thumb, text="")
        else:
            self.preview_lbl.config(text=os.path.basename(self.img_var.get()) or "(sin icono)")

    def _ok(self):
        spec = {}
        if not self.is_aux:
            txt = "\n".join(self._text().split("\n")[:3])   # maximo 3 lineas
            if txt.strip():
                spec["text"] = txt
            if self.img_var.get():
                spec["image"] = self.img_var.get()
            spec["fg"] = self.fg
            spec["bg"] = self.bg
            if self.font_path:
                spec["font"] = self.font_path
        act = self._build_action()
        if act:
            spec["action"] = act
        self.result = spec
        self.destroy()

    def _clear(self):
        self.result = {}   # tecla vacia
        self.destroy()


class CreateFolderDialog(tk.Toplevel):
    """
    'Create Folder' (estilo Stream Dock): crea una carpeta = pagina nueva,
    enlaza la tecla seleccionada para abrirla (goto_page) y le pone titulo/icono.
    Anade automaticamente en la carpeta una tecla 'Back' que vuelve a la pagina
    de origen.
    """

    def __init__(self, app, key_pos):
        super().__init__(app)
        self.app = app          # Configurator
        self.key_pos = key_pos
        self.title("Stream Dock: Create Folder")
        self.resizable(False, False)
        self.img_path = ""

        head = ttk.Frame(self); head.pack(fill="x", padx=12, pady=(10, 4))
        ttk.Label(head, text="Crear carpeta", font=("", 11, "bold")).pack(side="left")

        body = ttk.Frame(self); body.pack(fill="both", expand=True, padx=12, pady=6)

        # preview (icono de la carpeta / titulo)
        self.preview_lbl = tk.Label(body, relief="groove", bd=2)
        self.preview_lbl.grid(row=0, column=0, rowspan=3, padx=(0, 12), pady=4)

        ttk.Label(body, text="Titulo:").grid(row=0, column=1, sticky="e", pady=4)
        self.title_var = tk.StringVar(value="Carpeta")
        ent = ttk.Entry(body, textvariable=self.title_var, width=26)
        ent.grid(row=0, column=2, sticky="w", pady=4)
        self.title_var.trace_add("write", lambda *a: self._update_preview())

        ttk.Label(body, text="Icono:").grid(row=1, column=1, sticky="e", pady=4)
        iconf = ttk.Frame(body); iconf.grid(row=1, column=2, sticky="w", pady=4)
        ttk.Button(iconf, text="Galeria", command=self._gallery).pack(side="left")
        ttk.Button(iconf, text="...", width=3, command=self._browse).pack(side="left", padx=2)
        ttk.Button(iconf, text="Quitar", command=self._clear_icon).pack(side="left")

        self.include_var = tk.StringVar(value="Incluye: 0 teclas (se configuran luego)")
        ttk.Label(body, textvariable=self.include_var, foreground="#888").grid(
            row=2, column=1, columnspan=2, sticky="w", pady=4)

        self.open_after = tk.BooleanVar(value=True)
        ttk.Checkbutton(body, text="Abrir la carpeta para configurarla al crear",
                        variable=self.open_after).grid(row=3, column=1, columnspan=2, sticky="w", pady=6)

        bar = ttk.Frame(self); bar.pack(pady=10)
        ttk.Button(bar, text="Crear", command=self._create).pack(side="left", padx=4)
        ttk.Button(bar, text="Cancelar", command=self.destroy).pack(side="left", padx=4)

        self._update_preview()
        self.transient(app); self.grab_set()
        center_on_current_monitor(self)

    def _spec(self):
        return {"text": self.title_var.get(), "image": self.img_path,
                "fg": [255, 255, 255], "bg": [40, 40, 60]}

    def _update_preview(self):
        if _HAS_IMGTK:
            self._thumb = render_key_photo(self._spec(), 80)
            self.preview_lbl.config(image=self._thumb, text="")

    def _gallery(self):
        if not (_HAS_IMGTK and os.path.isdir(ICONS_DIR)):
            messagebox.showinfo("Info", "Galeria no disponible."); return
        p = IconPicker(self, ICONS_DIR); self.wait_window(p)
        if p.result:
            self.img_path = p.result; self._update_preview()

    def _browse(self):
        p = filedialog.askopenfilename(
            initialdir=ICONS_DIR if os.path.isdir(ICONS_DIR) else os.path.dirname(__file__),
            filetypes=[("Imagenes", "*.png *.jpg *.jpeg *.gif *.bmp"), ("Todos", "*.*")])
        if p:
            self.img_path = p; self._update_preview()

    def _clear_icon(self):
        self.img_path = ""; self._update_preview()

    def _create(self):
        title = self.title_var.get().strip() or "Carpeta"
        cfg = self.app.cfg
        parent = self.app.sel_page
        # crear la pagina-carpeta con una tecla 'Back' a la pagina de origen
        cfg["pages"].append({
            "name": title,
            "keys": {"14": {"text": "Back", "bg": [60, 0, 0],
                            "action": {"type": "goto_page", "page": parent}}},
        })
        new_index = len(cfg["pages"]) - 1
        # enlazar la tecla seleccionada para abrir la carpeta
        spec = {"action": {"type": "goto_page", "page": new_index}, "bg": [40, 40, 60]}
        if self.img_path:
            spec["image"] = self.img_path
        if title and (not self.img_path or self.title_var.get().strip()):
            spec["text"] = title           # titulo tambien sobre el icono
        cfg["pages"][parent].setdefault("keys", {})[str(self.key_pos)] = spec

        if self.open_after.get():
            self.app.sel_page = new_index
        self.app._refresh_pages()
        self.app._refresh_grid()
        self.destroy()


class WebsiteDialog(tk.Toplevel):
    """'Website' (Toolbox): abre una URL en el navegador elegido."""

    BROWSERS = [("Default Browser", "default"), ("Microsoft Edge", "edge"),
                ("Google Chrome", "chrome"), ("Internet Explorer", "iexplore"),
                ("Mozilla Firefox", "firefox")]

    def __init__(self, app, key_pos):
        super().__init__(app)
        self.app = app
        self.key_pos = key_pos
        self.title("Toolbox: Website")
        self.resizable(False, False)
        cur = app.cfg["pages"][app.sel_page].get("keys", {}).get(str(key_pos), {})
        act = cur.get("action", {}) if cur.get("action", {}).get("type") == "open_url" else {}
        self.img_path = cur.get("image", "")

        ttk.Label(self, text="Website", font=("", 11, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", padx=12, pady=(10, 6))

        self.preview_lbl = tk.Label(self, relief="groove", bd=2)
        self.preview_lbl.grid(row=1, column=0, rowspan=4, padx=12, pady=4)

        ttk.Label(self, text="Title (3 lineas):").grid(row=1, column=1, sticky="e", pady=4)
        self.title_box = tk.Text(self, width=30, height=3, font=("", 10), wrap="word")
        self.title_box.insert("1.0", cur.get("text", "") or "")
        self.title_box.grid(row=1, column=2, sticky="w", padx=6)
        self.title_box.bind("<KeyRelease>", lambda e: self._update_preview())
        self.title_box.bind("<Return>", lambda e: "break"
                            if self.title_box.get("1.0", "end-1c").count("\n") >= 2 else None)

        ttk.Label(self, text="URL:").grid(row=2, column=1, sticky="e", pady=4)
        self.url_var = tk.StringVar(value=act.get("url", ""))
        ttk.Entry(self, textvariable=self.url_var, width=30).grid(row=2, column=2, sticky="w", padx=6)

        ttk.Label(self, text="Open Mode:").grid(row=3, column=1, sticky="e", pady=4)
        self.mode_var = tk.StringVar()
        names = [n for n, _ in self.BROWSERS]
        cb = ttk.Combobox(self, textvariable=self.mode_var, values=names,
                          state="readonly", width=28)
        cb.grid(row=3, column=2, sticky="w", padx=6)
        cur_val = act.get("browser", "default")
        cb.current([v for _, v in self.BROWSERS].index(cur_val) if cur_val in dict(
            (v, n) for n, v in self.BROWSERS) else 0)

        iconf = ttk.Frame(self); iconf.grid(row=4, column=1, columnspan=2, sticky="w", padx=6, pady=4)
        ttk.Label(iconf, text="Icono:").pack(side="left")
        ttk.Button(iconf, text="Galeria", command=self._gallery).pack(side="left", padx=4)
        ttk.Button(iconf, text="...", width=3, command=self._browse).pack(side="left")
        ttk.Button(iconf, text="Quitar", command=self._clear_icon).pack(side="left", padx=4)

        bar = ttk.Frame(self); bar.grid(row=5, column=0, columnspan=3, pady=10)
        ttk.Button(bar, text="Aceptar", command=self._ok).pack(side="left", padx=4)
        ttk.Button(bar, text="Vaciar tecla", command=self._delete).pack(side="left", padx=4)
        ttk.Button(bar, text="Cancelar", command=self.destroy).pack(side="left", padx=4)

        self._update_preview()
        self.transient(app); self.grab_set()
        center_on_current_monitor(self)

    def _title(self):
        return self.title_box.get("1.0", "end-1c")

    def _spec_preview(self):
        return {"text": self._title(), "image": self.img_path,
                "fg": [255, 255, 255], "bg": [20, 70, 40]}

    def _update_preview(self):
        if _HAS_IMGTK:
            self._thumb = render_key_photo(self._spec_preview(), 80)
            self.preview_lbl.config(image=self._thumb, text="")

    def _gallery(self):
        if not (_HAS_IMGTK and os.path.isdir(ICONS_DIR)):
            messagebox.showinfo("Info", "Galeria no disponible."); return
        p = IconPicker(self, ICONS_DIR); self.wait_window(p)
        if p.result:
            self.img_path = p.result; self._update_preview()

    def _browse(self):
        p = filedialog.askopenfilename(
            initialdir=ICONS_DIR if os.path.isdir(ICONS_DIR) else os.path.dirname(__file__),
            filetypes=[("Imagenes", "*.png *.jpg *.jpeg *.gif *.bmp"), ("Todos", "*.*")])
        if p:
            self.img_path = p; self._update_preview()

    def _clear_icon(self):
        self.img_path = ""; self._update_preview()

    def _ok(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showinfo("Info", "Escribe una URL."); return
        if "://" not in url:
            url = "https://" + url
        browser = dict(self.BROWSERS)[self.mode_var.get()] if self.mode_var.get() in dict(self.BROWSERS) else "default"
        spec = {"action": {"type": "open_url", "url": url, "browser": browser},
                "bg": [20, 70, 40]}
        title = "\n".join(self._title().split("\n")[:3])
        if self.img_path:
            spec["image"] = self.img_path
        if title.strip():
            spec["text"] = title           # se muestra tambien sobre la imagen
        elif not self.img_path:
            spec["text"] = "Web"
        self.app.cfg["pages"][self.app.sel_page].setdefault("keys", {})[str(self.key_pos)] = spec
        self.app._refresh_grid()
        self.destroy()

    def _delete(self):
        self.app.cfg["pages"][self.app.sel_page].get("keys", {}).pop(str(self.key_pos), None)
        self.app._refresh_grid()
        self.destroy()


class PasswordDialog(tk.Toplevel):
    """'Password' (Toolbox): escribe/pega una contrasena en el control enfocado."""

    def __init__(self, app, key_pos):
        super().__init__(app)
        self.app = app
        self.key_pos = key_pos
        self.title("Toolbox: Password")
        self.resizable(False, False)
        cur = app.cfg["pages"][app.sel_page].get("keys", {}).get(str(key_pos), {})
        act = cur.get("action", {}) if cur.get("action", {}).get("type") == "password" else {}
        self.img_path = cur.get("image", "")
        self._shown = False

        ttk.Label(self, text="Password", font=("", 11, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(10, 6))
        self._trash_img = make_trash_icon(20) if _HAS_IMGTK else None
        tb = tk.Button(self, bd=0, relief="flat", cursor="hand2", command=self._delete)
        tb.config(image=self._trash_img) if self._trash_img else tb.config(text="Vaciar")
        tb.grid(row=0, column=2, sticky="e", padx=8)

        self.preview_lbl = tk.Label(self, relief="groove", bd=2)
        self.preview_lbl.grid(row=1, column=0, rowspan=5, padx=12, pady=4)

        ttk.Label(self, text="Title:").grid(row=1, column=1, sticky="e", pady=4)
        self.title_box = tk.Text(self, width=28, height=3, font=("", 10), wrap="word")
        self.title_box.insert("1.0", cur.get("text", "") or "")
        self.title_box.grid(row=1, column=2, sticky="w", padx=6)
        self.title_box.bind("<KeyRelease>", lambda e: self._update_preview())
        self.title_box.bind("<Return>", lambda e: "break"
                            if self.title_box.get("1.0", "end-1c").count("\n") >= 2 else None)

        ttk.Label(self, text="Password:").grid(row=2, column=1, sticky="e", pady=4)
        pf = ttk.Frame(self); pf.grid(row=2, column=2, sticky="w", padx=6)
        self.pwd_var = tk.StringVar(value=act.get("text", ""))
        self.pwd_entry = ttk.Entry(pf, textvariable=self.pwd_var, width=24, show="*")
        self.pwd_entry.pack(side="left")
        self.eye_btn = ttk.Button(pf, text="Ver", width=7, command=self._toggle_show)
        self.eye_btn.pack(side="left", padx=2)

        self.enter_var = tk.BooleanVar(value=act.get("enter", False))
        ttk.Checkbutton(self, text='Pulsar "Enter" automaticamente al final',
                        variable=self.enter_var).grid(row=3, column=2, sticky="w", padx=6)
        self.paste_var = tk.BooleanVar(value=act.get("paste", True))
        ttk.Checkbutton(self, text="Usar copiar-y-pegar (clipboard)",
                        variable=self.paste_var).grid(row=4, column=2, sticky="w", padx=6)

        iconf = ttk.Frame(self); iconf.grid(row=5, column=2, sticky="w", padx=6, pady=4)
        ttk.Label(iconf, text="Icono:").pack(side="left")
        ttk.Button(iconf, text="Galeria", command=self._gallery).pack(side="left", padx=4)
        ttk.Button(iconf, text="...", width=3, command=self._browse).pack(side="left")
        ttk.Button(iconf, text="Quitar", command=self._clear_icon).pack(side="left", padx=4)

        ttk.Label(self, text="La contrasena se guarda en texto plano en config.json",
                  foreground="#b06").grid(row=6, column=0, columnspan=3, padx=12, pady=(2, 0))

        bar = ttk.Frame(self); bar.grid(row=7, column=0, columnspan=3, pady=10)
        ttk.Button(bar, text="Aceptar", command=self._ok).pack(side="left", padx=4)
        ttk.Button(bar, text="Vaciar tecla", command=self._delete).pack(side="left", padx=4)
        ttk.Button(bar, text="Cancelar", command=self.destroy).pack(side="left", padx=4)

        self._update_preview()
        self.transient(app); self.grab_set()
        center_on_current_monitor(self)

    def _toggle_show(self):
        self._shown = not self._shown
        self.pwd_entry.config(show="" if self._shown else "*")
        self.eye_btn.config(text="Ocultar" if self._shown else "Ver")

    def _title(self):
        return self.title_box.get("1.0", "end-1c")

    def _spec_preview(self):
        return {"text": self._title(), "image": self.img_path,
                "fg": [255, 255, 255], "bg": [30, 60, 120]}

    def _update_preview(self):
        if _HAS_IMGTK:
            self._thumb = render_key_photo(self._spec_preview(), 80)
            self.preview_lbl.config(image=self._thumb, text="")

    def _gallery(self):
        if not (_HAS_IMGTK and os.path.isdir(ICONS_DIR)):
            messagebox.showinfo("Info", "Galeria no disponible."); return
        p = IconPicker(self, ICONS_DIR); self.wait_window(p)
        if p.result:
            self.img_path = p.result; self._update_preview()

    def _browse(self):
        p = filedialog.askopenfilename(
            initialdir=ICONS_DIR if os.path.isdir(ICONS_DIR) else os.path.dirname(__file__),
            filetypes=[("Imagenes", "*.png *.jpg *.jpeg *.gif *.bmp"), ("Todos", "*.*")])
        if p:
            self.img_path = p; self._update_preview()

    def _clear_icon(self):
        self.img_path = ""; self._update_preview()

    def _ok(self):
        spec = {"action": {"type": "password", "text": self.pwd_var.get(),
                           "enter": bool(self.enter_var.get()),
                           "paste": bool(self.paste_var.get())},
                "bg": [30, 60, 120]}
        title = "\n".join(self._title().split("\n")[:3])
        if self.img_path:
            spec["image"] = self.img_path
        if title.strip():
            spec["text"] = title
        elif not self.img_path:
            spec["text"] = "PWD"
        self.app.cfg["pages"][self.app.sel_page].setdefault("keys", {})[str(self.key_pos)] = spec
        self.app._refresh_grid()
        self.destroy()

    def _delete(self):
        self.app.cfg["pages"][self.app.sel_page].get("keys", {}).pop(str(self.key_pos), None)
        self.app._refresh_grid()
        self.destroy()


class _KeyDialogBase(tk.Toplevel):
    """Base para dialogos de accion: Title + icono + preview + papelera."""
    HEADER = "Accion"
    DEFAULT_LABEL = "Btn"
    PREVIEW_BG = [40, 40, 40]

    def __init__(self, app, key_pos):
        super().__init__(app)
        self.app = app
        self.key_pos = key_pos
        self.title(self.HEADER)
        self.resizable(False, False)
        self.cur = app.cfg["pages"][app.sel_page].get("keys", {}).get(str(key_pos), {})
        self.act = self.cur.get("action", {}) or {}
        self.img_path = self.cur.get("image", "")

        top = ttk.Frame(self); top.pack(fill="x", padx=12, pady=(10, 4))
        ttk.Label(top, text=self.HEADER, font=("", 11, "bold")).pack(side="left")
        self._trash_img = make_trash_icon(20) if _HAS_IMGTK else None
        tb = tk.Button(top, bd=0, relief="flat", cursor="hand2", command=self._delete)
        tb.config(image=self._trash_img) if self._trash_img else tb.config(text="Vaciar")
        tb.pack(side="right")

        body = ttk.Frame(self); body.pack(fill="both", expand=True, padx=12, pady=6)
        self.preview_lbl = tk.Label(body, relief="groove", bd=2)
        self.preview_lbl.grid(row=0, column=0, rowspan=30, padx=(0, 12), pady=4, sticky="n")
        self.form = ttk.Frame(body); self.form.grid(row=0, column=1, sticky="nw")
        self._r = 0
        self._add_title_row()
        self._build_body(self.form)
        self._add_icon_row()

        bar = ttk.Frame(self); bar.pack(pady=10)
        ttk.Button(bar, text="Aceptar", command=self._ok).pack(side="left", padx=4)
        ttk.Button(bar, text="Vaciar tecla", command=self._delete).pack(side="left", padx=4)
        ttk.Button(bar, text="Cancelar", command=self.destroy).pack(side="left", padx=4)

        self._update_preview()
        self.transient(app); self.grab_set()
        center_on_current_monitor(self)

    def _row(self):
        r = self._r; self._r += 1; return r

    def _add_title_row(self):
        r = self._row()
        ttk.Label(self.form, text="Title:").grid(row=r, column=0, sticky="e", padx=4, pady=4)
        self.title_box = tk.Text(self.form, width=30, height=3, font=("", 10), wrap="word")
        self.title_box.insert("1.0", self.cur.get("text", "") or "")
        self.title_box.grid(row=r, column=1, sticky="w", pady=4)
        self.title_box.bind("<KeyRelease>", lambda e: self._update_preview())
        self.title_box.bind("<Return>", lambda e: "break"
                            if self.title_box.get("1.0", "end-1c").count("\n") >= 2 else None)

    def _add_icon_row(self):
        r = self._row()
        ttk.Label(self.form, text="Icono:").grid(row=r, column=0, sticky="e", padx=4)
        f = ttk.Frame(self.form); f.grid(row=r, column=1, sticky="w", pady=4)
        ttk.Button(f, text="Galeria", command=self._gallery).pack(side="left")
        ttk.Button(f, text="...", width=3, command=self._browse).pack(side="left", padx=2)
        ttk.Button(f, text="Quitar", command=self._clear_icon).pack(side="left")

    # --- a sobreescribir ---
    def _build_body(self, form):
        pass

    def _action_spec(self):
        return None

    # --- comunes ---
    def _title(self):
        return self.title_box.get("1.0", "end-1c")

    def _spec_preview(self):
        return {"text": self._title(), "image": self.img_path,
                "fg": [255, 255, 255], "bg": self.PREVIEW_BG}

    def _update_preview(self):
        if _HAS_IMGTK:
            self._thumb = render_key_photo(self._spec_preview(), 80)
            self.preview_lbl.config(image=self._thumb, text="")

    def _gallery(self):
        if not (_HAS_IMGTK and os.path.isdir(ICONS_DIR)):
            messagebox.showinfo("Info", "Galeria no disponible."); return
        p = IconPicker(self, ICONS_DIR); self.wait_window(p)
        if p.result:
            self.img_path = p.result; self._update_preview()

    def _browse(self):
        p = filedialog.askopenfilename(
            initialdir=ICONS_DIR if os.path.isdir(ICONS_DIR) else os.path.dirname(__file__),
            filetypes=[("Imagenes", "*.png *.jpg *.jpeg *.gif *.bmp"), ("Todos", "*.*")])
        if p:
            self.img_path = p; self._update_preview()

    def _clear_icon(self):
        self.img_path = ""; self._update_preview()

    def _ok(self):
        spec = {"bg": list(self.PREVIEW_BG)}
        act = self._action_spec()
        if act:
            spec["action"] = act
        title = "\n".join(self._title().split("\n")[:3])
        if self.img_path:
            spec["image"] = self.img_path
        if title.strip():
            spec["text"] = title
        elif not self.img_path:
            spec["text"] = self.DEFAULT_LABEL
        self.app.cfg["pages"][self.app.sel_page].setdefault("keys", {})[str(self.key_pos)] = spec
        self.app._refresh_grid()
        self.destroy()

    def _delete(self):
        self.app.cfg["pages"][self.app.sel_page].get("keys", {}).pop(str(self.key_pos), None)
        self.app._refresh_grid()
        self.destroy()


class OpenDialog(_KeyDialogBase):
    HEADER = "Toolbox: Open"; DEFAULT_LABEL = "Open"; PREVIEW_BG = [20, 70, 40]

    def _build_body(self, form):
        r = self._row()
        ttk.Label(form, text="App/File:").grid(row=r, column=0, sticky="e", padx=4, pady=4)
        f = ttk.Frame(form); f.grid(row=r, column=1, sticky="w")
        self.path_var = tk.StringVar(value=self.act.get("path", ""))
        ttk.Entry(f, textvariable=self.path_var, width=28).pack(side="left")
        ttk.Button(f, text="Archivo", command=self._pick_file).pack(side="left", padx=2)
        ttk.Button(f, text="Carpeta", command=self._pick_folder).pack(side="left")
        r = self._row()
        ttk.Label(form, text="arguments:").grid(row=r, column=0, sticky="e", padx=4)
        self.args_var = tk.StringVar(value=" ".join(self.act.get("args", []) or []))
        ttk.Entry(form, textvariable=self.args_var, width=34).grid(row=r, column=1, sticky="w", pady=4)
        r = self._row()
        self.display_var = tk.BooleanVar(value=self.act.get("display", False))
        ttk.Checkbutton(form, text="Open/Display (abrir con la app por defecto)",
                        variable=self.display_var).grid(row=r, column=1, sticky="w")

    def _pick_file(self):
        p = filedialog.askopenfilename()
        if p:
            self.path_var.set(p)

    def _pick_folder(self):
        p = filedialog.askdirectory()
        if p:
            self.path_var.set(p)

    def _action_spec(self):
        return {"type": "open", "path": self.path_var.get().strip(),
                "args": self.args_var.get().split(), "display": bool(self.display_var.get())}


class OpenAppDialog(_KeyDialogBase):
    HEADER = "Toolbox: Open an app"; DEFAULT_LABEL = "App"; PREVIEW_BG = [25, 25, 25]

    def _build_body(self, form):
        self._apps = get_installed_apps()
        r = self._row()
        ttk.Label(form, text="AppName:").grid(row=r, column=0, sticky="e", padx=4, pady=4)
        self.app_var = tk.StringVar()
        self.app_cb = ttk.Combobox(form, textvariable=self.app_var,
                                   values=list(self._apps.keys()), width=32, state="readonly")
        self.app_cb.grid(row=r, column=1, sticky="w", pady=4)
        # preseleccionar si ya habia
        cur_path = self.act.get("path", "")
        cur_name = next((n for n, p in self._apps.items() if p == cur_path), "")
        if cur_name:
            self.app_var.set(cur_name)
        r = self._row()
        ttk.Button(form, text="Reload App", command=self._reload).grid(row=r, column=1, sticky="w", pady=4)

    def _reload(self):
        self._apps = get_installed_apps(reload=True)
        self.app_cb.config(values=list(self._apps.keys()))

    def _action_spec(self):
        return {"type": "open_app", "path": self._apps.get(self.app_var.get(), "")}


class MultimediaDialog(_KeyDialogBase):
    HEADER = "Toolbox: Multimedia"; DEFAULT_LABEL = "Media"; PREVIEW_BG = [40, 30, 50]
    CMDS = [("Play / Pausa", "playpause"), ("Siguiente", "nexttrack"),
            ("Anterior", "prevtrack"), ("Stop", "stop"),
            ("Subir volumen", "volumeup"), ("Bajar volumen", "volumedown"),
            ("Silenciar", "volumemute")]

    def _build_body(self, form):
        r = self._row()
        ttk.Label(form, text="Comando:").grid(row=r, column=0, sticky="e", padx=4, pady=4)
        self.cmd_var = tk.StringVar()
        cb = ttk.Combobox(form, textvariable=self.cmd_var, values=[n for n, _ in self.CMDS],
                          state="readonly", width=24)
        cb.grid(row=r, column=1, sticky="w", pady=4)
        cur = self.act.get("command", "playpause")
        cb.set(dict((v, n) for n, v in self.CMDS).get(cur, "Play / Pausa"))

    def _action_spec(self):
        return {"type": "multimedia", "command": dict(self.CMDS).get(self.cmd_var.get(), "playpause")}


class BrightnessDialog(_KeyDialogBase):
    HEADER = "Stream Dock: Brightness"; DEFAULT_LABEL = "Bright"; PREVIEW_BG = [50, 50, 20]

    def _build_body(self, form):
        r = self._row()
        ttk.Label(form, text="Brillo:").grid(row=r, column=0, sticky="e", padx=4, pady=4)
        self.val_var = tk.IntVar(value=int(self.act.get("value", 80)))
        f = ttk.Frame(form); f.grid(row=r, column=1, sticky="w", pady=4)
        ttk.Scale(f, from_=0, to=100, variable=self.val_var, length=180,
                  orient="horizontal").pack(side="left")
        ttk.Label(f, textvariable=self.val_var, width=4).pack(side="left", padx=4)

    def _action_spec(self):
        return {"type": "brightness", "value": int(self.val_var.get())}


class ObsSettingsDialog(tk.Toplevel):
    """Configuracion de conexion a OBS (obs-websocket v5)."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("OBS Studio Plugin")
        self.resizable(False, False)
        obs = app.cfg.setdefault("obs", {"host": "127.0.0.1", "port": 4455, "password": ""})
        self.host_var = tk.StringVar(value=obs.get("host", "127.0.0.1"))
        self.port_var = tk.StringVar(value=str(obs.get("port", 4455)))
        self.pwd_var = tk.StringVar(value=obs.get("password", ""))

        g = ttk.Frame(self); g.pack(padx=16, pady=12)
        ttk.Label(g, text="Server IP").grid(row=0, column=0, sticky="e", pady=4, padx=4)
        ttk.Entry(g, textvariable=self.host_var, width=26).grid(row=0, column=1, pady=4)
        ttk.Label(g, text="Server Port").grid(row=1, column=0, sticky="e", pady=4, padx=4)
        ttk.Entry(g, textvariable=self.port_var, width=26).grid(row=1, column=1, pady=4)
        ttk.Label(g, text="Server Password").grid(row=2, column=0, sticky="e", pady=4, padx=4)
        ttk.Entry(g, textvariable=self.pwd_var, width=26, show="*").grid(row=2, column=1, pady=4)

        bar = ttk.Frame(self); bar.pack(pady=(0, 12))
        ttk.Button(bar, text="Connect", command=self._connect).pack(pady=2)
        ttk.Button(bar, text="Reset Connection", command=self._reset).pack(pady=2)

        self.transient(app); self.grab_set()
        center_on_current_monitor(self)

    def _store(self):
        self.app.cfg["obs"] = {"host": self.host_var.get().strip() or "127.0.0.1",
                               "port": int(self.port_var.get() or 4455),
                               "password": self.pwd_var.get()}
        return self.app.cfg["obs"]

    def _connect(self):
        cfg = self._store()
        try:
            ver = sd_obs.test_connection(cfg)
            messagebox.showinfo("OBS", f"Conectado. OBS version {ver}")
        except Exception as e:
            messagebox.showerror("OBS", f"No se pudo conectar:\n{e}")

    def _reset(self):
        self.host_var.set("127.0.0.1"); self.port_var.set("4455"); self.pwd_var.set("")
        self._store()


class ObsActionDialog(_KeyDialogBase):
    """Dialogo generico para las 11 acciones de OBS Studio."""
    _HEADERS = {
        "obs_record": "OBS: Record", "obs_stream": "OBS: Stream",
        "obs_vcam": "OBS: Virtual Camera", "obs_scene": "OBS: Scene",
        "obs_source": "OBS: Source Visibility", "obs_audio": "OBS: Audio Mixer",
        "obs_studio_mode": "OBS: Studio Mode", "obs_screenshot": "OBS: Screenshot",
        "obs_transition": "OBS: Transition", "obs_green_up": "OBS: Green image UP",
        "obs_green_dn": "OBS: Green image DN"}
    _LABELS = {
        "obs_record": "REC", "obs_stream": "LIVE", "obs_vcam": "VCAM",
        "obs_scene": "SCENE", "obs_source": "SRC", "obs_audio": "MUTE",
        "obs_studio_mode": "STUDIO", "obs_screenshot": "SHOT",
        "obs_transition": "TRANS", "obs_green_up": "GRN+", "obs_green_dn": "GRN-"}

    def __init__(self, app, key_pos, obs_type):
        self.obs_type = obs_type
        self.HEADER = self._HEADERS.get(obs_type, "OBS Studio")
        self.DEFAULT_LABEL = self._LABELS.get(obs_type, "OBS")
        self.PREVIEW_BG = [40, 20, 60]
        super().__init__(app, key_pos)

    def _obs_cfg(self):
        return self.app.cfg.get("obs", {"host": "127.0.0.1", "port": 4455, "password": ""})

    def _build_body(self, form):
        t = self.obs_type
        r = self._row()
        ttk.Button(form, text="Conexion OBS...",
                   command=lambda: ObsSettingsDialog(self.app)).grid(row=r, column=1, sticky="w", pady=2)

        self.scene_cb = self.source_cb = self.input_cb = self.mode_var = None
        if t in ("obs_scene", "obs_source", "obs_green_up", "obs_green_dn"):
            r = self._row()
            ttk.Label(form, text="Escena:").grid(row=r, column=0, sticky="e", padx=4)
            self.scene_var = tk.StringVar(value=self.act.get("scene", ""))
            self.scene_cb = ttk.Combobox(form, textvariable=self.scene_var, width=26)
            self.scene_cb.grid(row=r, column=1, sticky="w", pady=2)
            ttk.Button(form, text="OBS", width=4,
                       command=self._fetch_scenes).grid(row=r, column=2, padx=2)
        if t in ("obs_source", "obs_green_up", "obs_green_dn"):
            r = self._row()
            ttk.Label(form, text="Fuente:").grid(row=r, column=0, sticky="e", padx=4)
            self.source_var = tk.StringVar(value=self.act.get("source", ""))
            self.source_cb = ttk.Combobox(form, textvariable=self.source_var, width=26)
            self.source_cb.grid(row=r, column=1, sticky="w", pady=2)
            ttk.Button(form, text="OBS", width=4,
                       command=self._fetch_sources).grid(row=r, column=2, padx=2)
        if t == "obs_source":
            r = self._row()
            ttk.Label(form, text="Modo:").grid(row=r, column=0, sticky="e", padx=4)
            self.mode_var = tk.StringVar(value=self.act.get("mode", "toggle"))
            ttk.Combobox(form, textvariable=self.mode_var, state="readonly",
                         values=["toggle", "show", "hide"], width=24).grid(row=r, column=1, sticky="w", pady=2)
        if t == "obs_audio":
            r = self._row()
            ttk.Label(form, text="Entrada:").grid(row=r, column=0, sticky="e", padx=4)
            self.input_var = tk.StringVar(value=self.act.get("input", ""))
            self.input_cb = ttk.Combobox(form, textvariable=self.input_var, width=26)
            self.input_cb.grid(row=r, column=1, sticky="w", pady=2)
            ttk.Button(form, text="OBS", width=4,
                       command=self._fetch_inputs).grid(row=r, column=2, padx=2)
            r = self._row()
            ttk.Label(form, text="Modo:").grid(row=r, column=0, sticky="e", padx=4)
            self.mode_var = tk.StringVar(value=self.act.get("mode", "toggle"))
            ttk.Combobox(form, textvariable=self.mode_var, state="readonly",
                         values=["toggle", "mute", "unmute"], width=24).grid(row=r, column=1, sticky="w", pady=2)
        if t == "obs_screenshot":
            r = self._row()
            ttk.Label(form, text="Carpeta:").grid(row=r, column=0, sticky="e", padx=4)
            self.folder_var = tk.StringVar(value=self.act.get("folder", ""))
            f = ttk.Frame(form); f.grid(row=r, column=1, sticky="w", pady=2)
            ttk.Entry(f, textvariable=self.folder_var, width=24).pack(side="left")
            ttk.Button(f, text="...", width=3,
                       command=lambda: self.folder_var.set(filedialog.askdirectory() or self.folder_var.get())).pack(side="left")

    def _fetch_scenes(self):
        try:
            self.scene_cb.config(values=sd_obs.get_scenes(self._obs_cfg()))
        except Exception as e:
            messagebox.showerror("OBS", str(e))

    def _fetch_sources(self):
        try:
            self.source_cb.config(values=sd_obs.get_sources(self._obs_cfg(), self.scene_var.get()))
        except Exception as e:
            messagebox.showerror("OBS", str(e))

    def _fetch_inputs(self):
        try:
            self.input_cb.config(values=sd_obs.get_inputs(self._obs_cfg()))
        except Exception as e:
            messagebox.showerror("OBS", str(e))

    def _action_spec(self):
        t = self.obs_type
        spec = {"type": t}
        if t in ("obs_scene", "obs_source", "obs_green_up", "obs_green_dn"):
            spec["scene"] = self.scene_var.get()
        if t in ("obs_source", "obs_green_up", "obs_green_dn"):
            spec["source"] = self.source_var.get()
        if t == "obs_source":
            spec["mode"] = self.mode_var.get()
        if t == "obs_audio":
            spec["input"] = self.input_var.get()
            spec["mode"] = self.mode_var.get()
        if t == "obs_screenshot" and self.folder_var.get().strip():
            spec["folder"] = self.folder_var.get().strip()
        return spec


class Configurator(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Stream Dock M18 - Configurador")
        self.geometry("1060x560")
        # al arrancar carga config.json si existe; si no, config de ejemplo
        if os.path.exists(CONFIG_PATH):
            try:
                self.cfg = read_config_file(CONFIG_PATH)
                self.title(f"Stream Dock M18 - Configurador  [{os.path.basename(CONFIG_PATH)}]")
            except Exception as e:
                print(f"No se pudo leer {CONFIG_PATH}: {e}")
                self.cfg = default_config()
        else:
            self.cfg = default_config()
        self.sel_page = 0
        self.selected_key = None     # tecla seleccionada para la libreria de acciones
        self._drag = None            # estado de arrastre (drag&drop)
        self._ghost = None           # etiqueta flotante durante el arrastre
        self._last_layout = None     # (ox,oy,dw,dh,cell) para el glow
        self.dev = None
        self._grid_thumbs = {}   # refs de miniaturas del grid (evita que las borre el GC)
        self._build_ui()
        self._refresh_pages()
        self._refresh_grid()
        self.after(5000, self._keepalive_tick)
        self.after(60, lambda: center_on_current_monitor(self))

    # --- UI -----------------------------------------------------------------
    def _build_ui(self):
        top = ttk.Frame(self); top.pack(fill="x", padx=8, pady=6)
        ttk.Button(top, text="Cargar", command=self.load).pack(side="left")
        ttk.Button(top, text="Guardar", command=self.save).pack(side="left", padx=4)
        ttk.Separator(top, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Label(top, text="Brillo:").pack(side="left")
        self.bright_var = tk.IntVar(value=self.cfg.get("brightness", 80))
        ttk.Spinbox(top, from_=0, to=100, width=5, textvariable=self.bright_var,
                    command=self._on_bright).pack(side="left", padx=4)
        ttk.Separator(top, orient="vertical").pack(side="left", fill="y", padx=8)
        self.conn_btn = ttk.Button(top, text="Conectar", command=self.toggle_device)
        self.conn_btn.pack(side="left")
        ttk.Button(top, text="Previsualizar pagina", command=self.preview).pack(side="left", padx=4)
        ttk.Button(top, text="OBS...", command=lambda: ObsSettingsDialog(self)).pack(side="left", padx=4)

        body = ttk.Frame(self); body.pack(fill="both", expand=True, padx=8, pady=6)

        # panel de paginas
        left = ttk.LabelFrame(body, text="Paginas")
        left.pack(side="left", fill="y")
        self.pages_list = tk.Listbox(left, width=20, height=14, exportselection=False)
        self.pages_list.pack(padx=6, pady=6)
        self.pages_list.bind("<<ListboxSelect>>", self._on_page_select)
        pb = ttk.Frame(left); pb.pack(pady=4)
        ttk.Button(pb, text="Nueva", width=7, command=self.new_page).grid(row=0, column=0, padx=2)
        ttk.Button(pb, text="Borrar", width=7, command=self.del_page).grid(row=0, column=1, padx=2)
        ttk.Button(pb, text="Renombrar", width=16, command=self.rename_page).grid(row=1, column=0, columnspan=2, pady=2)
        ttk.Button(pb, text="▲ Subir", width=7, command=lambda: self.move_page(-1)).grid(row=2, column=0, padx=2)
        ttk.Button(pb, text="▼ Bajar", width=7, command=lambda: self.move_page(1)).grid(row=2, column=1, padx=2)
        ttk.Button(pb, text="★ Marcar por defecto", width=16,
                   command=self.set_default).grid(row=3, column=0, columnspan=2, pady=2)

        # libreria de acciones (panel derecho, acordeon)
        self._build_library(body)

        # vista del equipo: imagen de fondo + botones encima, en un canvas
        right = ttk.Frame(body); right.pack(side="left", fill="both", expand=True, padx=(10, 0))
        ttk.Label(right, text="1 clic = seleccionar · doble clic = editar",
                  foreground="#888").pack(anchor="w")
        self.device_canvas = tk.Canvas(right, highlightthickness=0, bg="#15151a")
        self.device_canvas.pack(fill="both", expand=True)
        self.device_canvas.bind("<Configure>", lambda e: self._layout_device())

        self._bg_src = None
        if _HAS_IMGTK and os.path.exists(DEVICE_IMG):
            try:
                self._bg_src = Image.open(DEVICE_IMG).convert("RGBA")
            except Exception:
                self._bg_src = None

        # botones de tecla (hijos del canvas; se colocan en _layout_device)
        self.key_btns = []
        self._key_win = [None] * 15
        for pos in range(15):
            b = tk.Button(self.device_canvas, bd=0, relief="flat", highlightthickness=0,
                          cursor="hand2", command=lambda p=pos: self.select_key(p))
            b.bind("<Double-Button-1>", lambda e, p=pos: self.edit_key(p))
            self.key_btns.append(b)

        # botones fisicos laterales: se dibujan como texto transparente sobre los
        # circulos de la imagen (ver _layout_device). El area del circulo es
        # clicable via tag.
        self._aux_imgs = []   # refs de imagenes transparentes (hit area)
        for name in ("left", "mid", "right"):
            self.device_canvas.tag_bind(f"aux_{name}", "<Button-1>",
                                        lambda e, n=name: self.edit_aux(n))

    def _aux_label(self, name):
        """Texto corto para el boton lateral segun su accion."""
        spec = self.cfg.get("aux", {}).get(name)
        act = spec.get("action", {}).get("type") if spec and spec.get("action") else None
        m = {"prev_page": "PREV", "next_page": "NEXT", "home": "HOME",
             "goto_page": "GOTO"}
        if act in m:
            return m[act]
        if act:
            return act.upper()[:5]
        return name.upper()[:4]

    # --- vista del equipo (fondo + botones) ---------------------------------
    def _layout_device(self):
        c = self.device_canvas
        if self._bg_src is None:
            return
        cw, ch = c.winfo_width(), c.winfo_height()
        if cw < 20 or ch < 20:
            return
        bw, bh = self._bg_src.width, self._bg_src.height
        scale = min(cw / bw, ch / bh)
        dw, dh = max(1, int(bw * scale)), max(1, int(bh * scale))
        ox, oy = (cw - dw) // 2, (ch - dh) // 2
        # fondo
        self._bg_photo = ImageTk.PhotoImage(self._bg_src.resize((dw, dh), Image.LANCZOS))
        c.delete("bg")
        c.create_image(ox, oy, anchor="nw", image=self._bg_photo, tags="bg")
        c.tag_lower("bg")
        # teclas
        keys = self.cfg["pages"][self.sel_page].get("keys", {}) if self.cfg["pages"] else {}
        cell = max(16, int(DEV_KEY_N * dw))
        self._dev_photos = []
        for pos in range(15):
            r, col = divmod(pos, 5)
            cx = ox + DEV_COLX[col] * dw
            cy = oy + DEV_ROWY[r] * dh
            spec = keys.get(str(pos))
            photo = render_key_photo(spec, cell, pos=pos)
            self._dev_photos.append(photo)
            b = self.key_btns[pos]
            sel = (pos == self.selected_key)
            b.config(image=photo, width=cell, height=cell,
                     bd=(3 if sel else 0), relief="solid" if sel else "flat",
                     highlightthickness=0)
            if self._key_win[pos] is None:
                self._key_win[pos] = c.create_window(cx, cy, window=b, anchor="center")
            else:
                c.coords(self._key_win[pos], cx, cy)
        # botones fisicos: circulo transparente clicable + texto PREV/HOME/NEXT
        d = max(20, int(DEV_AUX_H * dh))
        fsize = max(6, int(d * 0.20))
        self._aux_imgs = []
        for i, name in enumerate(("left", "mid", "right")):
            bx = ox + DEV_AUXX[i] * dw
            by = oy + DEV_AUXY * dh
            label = self._aux_label(name)
            c.delete(f"aux_{name}")
            # area clicable transparente (del tamano del circulo)
            timg = ImageTk.PhotoImage(Image.new("RGBA", (d, d), (0, 0, 0, 0)))
            self._aux_imgs.append(timg)
            c.create_image(bx, by, image=timg, tags=(f"aux_{name}",))
            # texto con contorno para legibilidad (fondo transparente)
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                c.create_text(bx + dx, by + dy, text=label, fill="black",
                              font=("", fsize, "bold"), tags=(f"aux_{name}",))
            c.create_text(bx, by, text=label, fill="white",
                          font=("", fsize, "bold"), tags=(f"aux_{name}",))
        # guardar geometria para el glow de seleccion
        self._last_layout = (ox, oy, dw, dh, cell)
        self._draw_selection_glow()

    def _draw_selection_glow(self):
        """Dibuja un resplandor cian alrededor de la tecla seleccionada."""
        c = self.device_canvas
        c.delete("glow")
        if self.selected_key is None or not getattr(self, "_last_layout", None):
            return
        ox, oy, dw, dh, cell = self._last_layout
        r, col = divmod(self.selected_key, 5)
        cx = ox + DEV_COLX[col] * dw
        cy = oy + DEV_ROWY[r] * dh
        half = cell / 2
        # capas de glow (fuera -> dentro), de tenue a brillante
        for extra, color, w in ((7, "#0b4651", 3), (5, "#1699b5", 3),
                                (3, "#4fe3ff", 2), (1, "#c7f8ff", 2)):
            h = half + extra
            c.create_rectangle(cx - h, cy - h, cx + h, cy + h,
                               outline=color, width=w, tags="glow")

    # --- libreria de acciones (acordeon) ------------------------------------
    def _build_library(self, body):
        lib = ttk.LabelFrame(body, text="Libreria de acciones")
        lib.pack(side="right", fill="y")
        hint = ttk.Label(lib, text="Selecciona una tecla y luego una accion",
                         foreground="#888", wraplength=210)
        hint.pack(fill="x", padx=6, pady=(4, 2))

        # area scrollable
        wrap = ttk.Frame(lib); wrap.pack(fill="both", expand=True)
        canvas = tk.Canvas(wrap, width=230, highlightthickness=0)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        canvas.bind_all("<MouseWheel>",
                        lambda e: canvas.yview_scroll(int(-e.delta / 120), "units"))

        self._cat_bodies = {}
        for cat, items in ACTION_LIBRARY:
            header = tk.Button(inner, text=f"▶  {cat}", anchor="w", relief="flat",
                               font=("", 9, "bold"), bg="#2b2b2b", fg="white",
                               activebackground="#3a3a3a", activeforeground="white",
                               command=lambda c=cat: self._toggle_cat(c))
            header.pack(fill="x", pady=(4, 0))
            cbody = ttk.Frame(inner)   # contraido por defecto (no se hace pack)
            for name, aid in items:
                eb = tk.Button(cbody, text=f"    {name}", anchor="w", relief="flat")
                eb.bind("<ButtonPress-1>", lambda e, a=aid, n=name: self._drag_start(e, a, n))
                eb.bind("<B1-Motion>", self._drag_motion)
                eb.bind("<ButtonRelease-1>", self._drag_release)
                eb.pack(fill="x")
            self._cat_bodies[cat] = (header, cbody)

    def _toggle_cat(self, cat):
        header, cbody = self._cat_bodies[cat]
        if cbody.winfo_ismapped():
            cbody.pack_forget()
            header.config(text=f"▶  {cat}")
        else:
            cbody.pack(fill="x", after=header)
            header.config(text=f"▼  {cat}")

    def select_key(self, pos):
        self.selected_key = pos
        self._apply_selection_highlight()
        self._draw_selection_glow()

    # --- drag & drop de la libreria a las teclas ----------------------------
    def _drag_start(self, e, aid, name):
        self._drag = {"aid": aid, "name": name, "active": False,
                      "x0": e.x_root, "y0": e.y_root}

    def _drag_motion(self, e):
        if not self._drag:
            return
        if not self._drag["active"]:
            if abs(e.x_root - self._drag["x0"]) + abs(e.y_root - self._drag["y0"]) > 6:
                self._drag["active"] = True
                self._make_ghost(self._drag["name"])
        if self._drag["active"] and self._ghost is not None:
            self._ghost.geometry(f"+{e.x_root + 12}+{e.y_root + 10}")

    def _make_ghost(self, text):
        self._destroy_ghost()
        g = tk.Toplevel(self)
        g.overrideredirect(True)
        try:
            g.attributes("-topmost", True)
        except Exception:
            pass
        tk.Label(g, text=text, bg="#2d6cdf", fg="white", bd=1, relief="solid",
                 padx=8, pady=2).pack()
        self._ghost = g

    def _destroy_ghost(self):
        if self._ghost is not None:
            self._ghost.destroy()
            self._ghost = None

    def _drag_release(self, e):
        drag = self._drag
        self._drag = None
        self._destroy_ghost()
        if not drag:
            return
        if not drag["active"]:
            # fue un clic normal: asignar a la tecla ya seleccionada
            self.assign_action(drag["aid"], drag["name"])
            return
        pos = self._key_at(e.x_root, e.y_root)
        if pos is not None:
            self._drop_action(drag["aid"], drag["name"], pos)

    def _key_at(self, xr, yr):
        for pos, b in enumerate(self.key_btns):
            try:
                x0, y0 = b.winfo_rootx(), b.winfo_rooty()
                if x0 <= xr <= x0 + b.winfo_width() and y0 <= yr <= y0 + b.winfo_height():
                    return pos
            except Exception:
                pass
        return None

    def _drop_action(self, aid, name, pos):
        keys = self.cfg["pages"][self.sel_page].get("keys", {})
        if keys.get(str(pos)):   # tecla no vacia -> preguntar
            if not messagebox.askyesno(
                    "Reemplazar",
                    f"La tecla {pos} no esta vacia.\n¿Reemplazar su contenido?"):
                return
        self.select_key(pos)
        self.assign_action(aid, name)

    def _apply_selection_highlight(self):
        for i, b in enumerate(self.key_btns):
            sel = (i == self.selected_key)
            b.config(relief="solid" if sel else "raised", bd=3 if sel else 2)

    def _set_key_action(self, pos, action, default_text=None, bg=None):
        keys = self.cfg["pages"][self.sel_page].setdefault("keys", {})
        spec = dict(keys.get(str(pos), {}))
        spec["action"] = action
        if default_text and not spec.get("text") and not spec.get("image"):
            spec["text"] = default_text
        if bg:
            spec["bg"] = bg
        keys[str(pos)] = spec
        self._refresh_grid()

    def _open_action_dialog(self, pos, aid):
        """Abre el dialogo dedicado de la accion. Devuelve True si lo gestiono."""
        dialogs = {"password": PasswordDialog, "open": OpenDialog,
                   "open_app": OpenAppDialog, "multimedia": MultimediaDialog,
                   "brightness": BrightnessDialog}
        if aid in dialogs:
            dialogs[aid](self, pos); return True
        if aid and aid.startswith("obs_"):
            ObsActionDialog(self, pos, aid); return True
        return False

    def assign_action(self, aid, name):
        if self.selected_key is None:
            messagebox.showinfo("Info", "Selecciona primero una tecla (1 clic en el grid).")
            return
        pos = self.selected_key
        if aid == "open_url":
            self.edit_key(pos, preset_type="open_url"); return
        if aid == "hotkey":
            self.edit_key(pos, preset_type="hotkey"); return
        if self._open_action_dialog(pos, aid):
            return
        if aid == "create_folder":
            CreateFolderDialog(self, pos); return
        if aid == "prev_page":
            self._set_key_action(pos, {"type": "prev_page"}, "◀ Prev"); return
        if aid == "next_page":
            self._set_key_action(pos, {"type": "next_page"}, "Next ▶"); return
        if aid == "goto_page":
            n = simpledialog.askinteger("Go to Page", "Indice de pagina (0,1,2...):",
                                        parent=self, minvalue=0)
            if n is not None:
                self._set_key_action(pos, {"type": "goto_page", "page": n}, f"Pag {n}")
            return
        if aid == "run":
            path = filedialog.askopenfilename(title="Elegir app/programa",
                                              filetypes=[("Programas", "*.exe"), ("Todos", "*.*")])
            if path:
                self._set_key_action(pos, {"type": "run", "args": [path]},
                                     os.path.splitext(os.path.basename(path))[0])
            return
        if aid == "write_text":
            txt = simpledialog.askstring("Text", "Texto a teclear:", parent=self)
            if txt is not None:
                self._set_key_action(pos, {"type": "write_text", "text": txt}, "Text")
            return
        if aid.startswith("todo:"):
            self._set_key_action(pos, {"type": "todo", "name": name}, name)
            messagebox.showinfo("En construccion",
                f"La accion '{name}' aun no esta implementada.\n\n"
                "Pasame sus opciones/comportamiento y la implemento.")
            return

    # --- paginas ------------------------------------------------------------
    def _refresh_pages(self):
        self.pages_list.delete(0, "end")
        default = self.cfg.get("default_page", 0)
        for i, p in enumerate(self.cfg["pages"]):
            star = " ★" if i == default else ""
            self.pages_list.insert("end", f"{i}: {p.get('name', 'pagina')}{star}")
        if self.cfg["pages"]:
            self.sel_page = min(self.sel_page, len(self.cfg["pages"]) - 1)
            self.pages_list.selection_set(self.sel_page)

    def _on_page_select(self, _evt):
        sel = self.pages_list.curselection()
        if sel:
            self.sel_page = sel[0]
            self._refresh_grid()

    def new_page(self):
        name = simpledialog.askstring("Nueva pagina", "Nombre:", parent=self) or "pagina"
        self.cfg["pages"].append({"name": name, "keys": {}})
        self.sel_page = len(self.cfg["pages"]) - 1
        self._refresh_pages(); self._refresh_grid()

    def del_page(self):
        if len(self.cfg["pages"]) <= 1:
            messagebox.showinfo("Info", "Debe quedar al menos una pagina."); return
        i = self.sel_page
        del self.cfg["pages"][i]
        # mantener valido el indice de pagina por defecto
        d = self.cfg.get("default_page", 0)
        if d == i:
            self.cfg["default_page"] = 0
        elif d > i:
            self.cfg["default_page"] = d - 1
        self.sel_page = max(0, i - 1)
        self._refresh_pages(); self._refresh_grid()

    def set_default(self):
        """Marca la pagina seleccionada como por defecto y pone el boton central en 'home'."""
        self.cfg["default_page"] = self.sel_page
        self.cfg.setdefault("aux", {})["mid"] = {"action": {"type": "home"}}
        self._refresh_pages(); self._refresh_grid()
        messagebox.showinfo(
            "Pagina por defecto",
            f"Pagina {self.sel_page} marcada como por defecto (★).\n"
            "El boton CENTRAL cargara esta pagina al pulsarlo.")

    def rename_page(self):
        p = self.cfg["pages"][self.sel_page]
        name = simpledialog.askstring("Renombrar", "Nombre:", initialvalue=p.get("name", ""), parent=self)
        if name:
            p["name"] = name; self._refresh_pages()

    def move_page(self, delta):
        i, j = self.sel_page, self.sel_page + delta
        pages = self.cfg["pages"]
        if 0 <= j < len(pages):
            pages[i], pages[j] = pages[j], pages[i]
            # que el ★ por defecto siga a su pagina al reordenar
            d = self.cfg.get("default_page", 0)
            if d == i:
                self.cfg["default_page"] = j
            elif d == j:
                self.cfg["default_page"] = i
            self.sel_page = j
            self._refresh_pages(); self._refresh_grid()

    # --- teclas -------------------------------------------------------------
    def _refresh_grid(self):
        # la vista del equipo (fondo + botones) se re-renderiza entera
        self._layout_device()

    def edit_key(self, pos, preset_type=None):
        keys = self.cfg["pages"][self.sel_page].setdefault("keys", {})
        # las acciones con ventana propia se editan con su dialogo
        atype = keys.get(str(pos), {}).get("action", {}).get("type")
        if preset_type is None and self._open_action_dialog(pos, atype):
            return
        ed = KeyEditor(self, keys.get(str(pos), {}), f"Tecla {pos}", preset_type=preset_type)
        self.wait_window(ed)
        if ed.result is not None:
            if ed.result == {}:
                keys.pop(str(pos), None)
            else:
                keys[str(pos)] = ed.result
            self._refresh_grid()

    def edit_aux(self, name):
        aux = self.cfg.setdefault("aux", {})
        ed = KeyEditor(self, aux.get(name, {}), f"Boton lateral: {name}", is_aux=True)
        self.wait_window(ed)
        if ed.result is not None:
            if ed.result == {}:
                aux.pop(name, None)
            else:
                aux[name] = ed.result
            self._refresh_grid()

    # --- dispositivo --------------------------------------------------------
    def _on_bright(self):
        self.cfg["brightness"] = int(self.bright_var.get())

    def toggle_device(self):
        if self.dev is None:
            try:
                self.dev = StreamDockM18(); self.dev.open()
                self.conn_btn.config(text="Desconectar")
            except Exception as e:
                self.dev = None
                messagebox.showerror("Error al conectar", str(e))
        else:
            try:
                self.dev.close()
            finally:
                self.dev = None
                self.conn_btn.config(text="Conectar")

    def preview(self):
        if self.dev is None:
            messagebox.showinfo("Info", "Pulsa 'Conectar' primero."); return
        try:
            self.cfg["brightness"] = int(self.bright_var.get())
            app = build_app_from_config(self.cfg, device=self.dev)
            self.dev.set_brightness(self.cfg["brightness"])
            app.goto_page(self.sel_page)   # limpia y pinta la pagina seleccionada
        except Exception as e:
            messagebox.showerror("Error al previsualizar", str(e))

    def _keepalive_tick(self):
        if self.dev is not None:
            try:
                self.dev.keepalive()
            except Exception:
                pass
        self.after(5000, self._keepalive_tick)

    # --- guardar / cargar ---------------------------------------------------
    def save(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".json", initialfile="config.json",
            initialdir=os.path.dirname(__file__),
            filetypes=[("JSON", "*.json")])
        if not path:
            return
        self.cfg["brightness"] = int(self.bright_var.get())
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.cfg, f, indent=2, ensure_ascii=False)
        messagebox.showinfo("Guardado", f"Config guardada en:\n{path}\n\n"
                            f"Ejecutala con:  python run_config.py \"{path}\"")

    def load(self):
        path = filedialog.askopenfilename(
            initialdir=os.path.dirname(__file__), filetypes=[("JSON", "*.json")])
        if not path:
            return
        self.cfg = read_config_file(path)
        self.bright_var.set(self.cfg.get("brightness", 80))
        self.sel_page = 0
        self._refresh_pages(); self._refresh_grid()


if __name__ == "__main__":
    Configurator().mainloop()
