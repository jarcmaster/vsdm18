# -*- coding: utf-8 -*-
"""
Aviso rapido al arrancar: una burbuja llamativa (sin bordes) que aparece encima
del reloj de la bandeja, con una flecha apuntando al System Tray, y desaparece
sola a los 5 segundos. Se lanza como proceso aparte desde tray_app.

Uso:  tray_toast.py   |   StreamDockM18.exe --tray-toast
"""

import ctypes
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# --- textos localizados (titulo de marca fijo) ------------------------------
TITLE = "Stream Dock M18"
MSG = {
    "en": ("Running in the System Tray", "Click the tray icon to open the configurator"),
    "es": ("La aplicación está en la bandeja del sistema", "Haz clic en el icono para abrir el configurador"),
    "pt": ("Em execução na bandeja do sistema", "Clique no ícone para abrir o configurador"),
    "fr": ("En cours dans la barre d'état système", "Cliquez sur l'icône pour ouvrir le configurateur"),
    "de": ("Läuft im System-Tray", "Klicke auf das Symbol, um den Konfigurator zu öffnen"),
    "it": ("In esecuzione nella barra di sistema", "Clicca sull'icona per aprire il configuratore"),
    "ru": ("Работает в системном трее", "Нажмите на значок, чтобы открыть конфигуратор"),
    "zh": ("正在系统托盘中运行", "点击托盘图标打开配置器"),
    "ja": ("システムトレイで実行中", "トレイアイコンをクリックで設定を開く"),
    "ko": ("시스템 트레이에서 실행 중", "트레이 아이콘을 클릭해 설정 열기"),
    "ar": ("يعمل في علبة النظام", "انقر على الأيقونة لفتح المُهيّئ"),
}


def _lang():
    try:
        import m18_paths
        cfgp = m18_paths.config_path()
    except Exception:
        cfgp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    try:
        with open(cfgp, "r", encoding="utf-8") as f:
            return (json.load(f).get("lang") or "en").lower()
    except Exception:
        return "en"


def _target():
    """Punto (x, y) donde apuntar la flecha (el icono del tray), pasado por argv."""
    ints = []
    for a in sys.argv[1:]:
        try:
            ints.append(int(a))
        except (TypeError, ValueError):
            continue
        if len(ints) == 2:
            return ints[0], ints[1]
    return None, None


def _work_area():
    """Area de trabajo del monitor principal (sin la barra de tareas), en px fisicos."""
    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]
    r = RECT()
    try:
        if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(r), 0):
            return r.left, r.top, r.right, r.bottom
    except Exception:
        pass
    return None


def _lerp(c1, c2, t):
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


def run():
    import tkinter as tk

    try:   # posicionar en px fisicos aunque haya escalado de pantalla
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    lang = _lang()
    head, sub = MSG.get(lang, MSG["en"])

    KEY = "#010203"          # color "transparente" (para las esquinas / fuera de la burbuja)
    TOP = (58, 160, 255)     # azul brillante
    BOT = (142, 45, 226)     # morado
    W, BODY_H, ARROW_H = 330, 104, 20
    H = BODY_H + ARROW_H
    ARROW_HW = 15

    tx, ty = _target()       # icono del tray al que apuntar (o None)

    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    try:
        root.attributes("-transparentcolor", KEY)
    except Exception:
        pass
    root.configure(bg=KEY)

    # posicion: la flecha apunta al icono del tray (tx); el globo queda encima de la barra
    wa = _work_area()
    if wa:
        wl, _wt, wr, wb = wa
    else:
        wl = 0
        wr = root.winfo_screenwidth()
        wb = root.winfo_screenheight() - 48
    if tx is not None:
        x = tx - (W - 34)                       # globo hacia la izquierda del icono
        x = max(wl + 6, min(x, wr - W - 6))     # pero sin salirse de la pantalla
        y = wb - H + 10                         # la punta asoma hacia la barra (al icono)
        arrow_cx = max(18, min(tx - x, W - 18)) # la punta se alinea exactamente con el icono
    else:
        x = wr - W - 12
        y = wb - H - 6
        arrow_cx = W - 34
    root.geometry(f"{W}x{H}+{max(0, x)}+{max(0, y)}")

    cv = tk.Canvas(root, width=W, height=H, bg=KEY, highlightthickness=0, bd=0)
    cv.pack()

    # cuerpo con degradado vertical (azul -> morado)
    for i in range(BODY_H):
        col = "#%02x%02x%02x" % _lerp(TOP, BOT, i / max(1, BODY_H - 1))
        cv.create_line(0, i, W, i, fill=col)
    # borde sutil
    cv.create_rectangle(1, 1, W - 1, BODY_H - 1, outline="#ffffff", width=1)
    # flecha apuntando hacia abajo (al tray), del color inferior del degradado
    bot_hex = "#%02x%02x%02x" % BOT
    cv.create_polygon(arrow_cx - ARROW_HW, BODY_H - 1, arrow_cx + ARROW_HW, BODY_H - 1,
                      arrow_cx, H - 1, fill=bot_hex, outline=bot_hex)

    # contenido
    cv.create_text(22, 24, text="📌", anchor="w", font=("Segoe UI Emoji", 18), fill="white")
    cv.create_text(52, 22, text=TITLE, anchor="w", font=("Segoe UI", 12, "bold"), fill="white")
    cv.create_text(22, 56, text=head, anchor="w", font=("Segoe UI", 10, "bold"), fill="white",
                   width=W - 40)
    cv.create_text(22, 82, text=sub, anchor="w", font=("Segoe UI", 8), fill="#e8ecff",
                   width=W - 40)

    state = {"closing": False}

    def close():
        if state["closing"]:
            return
        state["closing"] = True
        _fade_out()

    def _fade_out(a=0.97):
        if a <= 0.05:
            try:
                root.destroy()
            except Exception:
                pass
            return
        try:
            root.attributes("-alpha", a)
        except Exception:
            pass
        root.after(30, lambda: _fade_out(a - 0.12))

    def _fade_in(a=0.0):
        try:
            root.attributes("-alpha", a)
        except Exception:
            pass
        if a < 0.97:
            root.after(16, lambda: _fade_in(a + 0.12))

    cv.bind("<Button-1>", lambda e: close())
    root.bind("<Button-1>", lambda e: close())
    _fade_in()
    root.after(4500, close)          # empieza a desvanecerse a los 4.5 s
    root.after(6000, root.destroy)   # salvaguarda: cerrar a los 6 s pase lo que pase

    try:
        root.lift()
    except Exception:
        pass
    root.mainloop()


def main(argv=None):
    try:
        run()
    except Exception as e:
        print("[toast]", e)


if __name__ == "__main__":
    main(sys.argv)
