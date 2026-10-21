"""
Aviso flotante (topmost, click-through) para grabacion/reproduccion de rutinas
del raton. Dos modos:

  * "count"  -> cuenta regresiva grande y centrada, con anillo animado.
  * "banner" -> aviso compacto en la esquina (parpadea).

El proceso principal escribe en <flagfile>:
    <modo>|<color-hex>\n<texto>
(si no hay '|', se asume modo banner y la 1a linea es el color). Cuando el
archivo desaparece o queda vacio, el aviso se cierra solo.

Uso:  python mouse_overlay.py <flagfile>
"""

import os
import sys
import time
import tkinter as tk


def _click_through(root):
    """Transparente a los clics (no roba foco ni bloquea)."""
    try:
        import ctypes
        hwnd = root.winfo_id()
        GWL_EXSTYLE = -20
        WS_EX_LAYERED = 0x00080000
        WS_EX_TRANSPARENT = 0x00000020
        WS_EX_NOACTIVATE = 0x08000000
        u = ctypes.windll.user32
        style = u.GetWindowLongW(hwnd, GWL_EXSTYLE)
        u.SetWindowLongW(hwnd, GWL_EXSTYLE,
                         style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE)
        # Al tocar WS_EX_LAYERED hay que re-aplicar los atributos de capa o GDI
        # deja de pintar (se ve un recuadro blanco). LWA_ALPHA = 0x02.
        u.SetLayeredWindowAttributes(hwnd, 0, 235, 0x02)
    except Exception:
        pass


def _parse(flag):
    if not flag or not os.path.exists(flag):
        return None
    try:
        with open(flag, "r", encoding="utf-8") as f:
            data = f.read()
    except Exception:
        return ("banner", "#c0392b", "")   # error transitorio: mantener
    if not data.strip():
        return None
    head, _, body = data.partition("\n")
    head = head.strip()
    subtitle = ""
    if "|" in head:
        parts = head.split("|")
        mode = (parts[0].strip() or "banner")
        color = (parts[1].strip() or "#c0392b") if len(parts) > 1 else "#c0392b"
        subtitle = parts[2].strip() if len(parts) > 2 else ""
    else:
        mode, color = "banner", (head or "#c0392b")
    return (mode, color, body, subtitle)


def main():
    # el flagfile es el ultimo argumento que no sea una bandera (--mouse-overlay)
    _args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flag = _args[-1] if _args else ""
    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    try:
        root.attributes("-alpha", 0.93)
    except Exception:
        pass

    st = {"mode": None, "widget": None, "num": None, "change": 0.0, "blink": True}
    root.after(90, lambda: _click_through(root))

    def set_mode(mode):
        if st["mode"] == mode:
            return
        st["mode"] = mode
        if st["widget"] is not None:
            st["widget"].destroy()
        if mode == "count":
            st["widget"] = tk.Canvas(root, width=250, height=250,
                                     highlightthickness=0, bd=0, bg="#15151b")
        else:
            st["widget"] = tk.Label(root, font=("Segoe UI", 13, "bold"),
                                    fg="#ffffff", justify="left", padx=18, pady=12)
        st["widget"].pack()
        _click_through(root)

    def draw_count(color, body, subtitle):
        num = body.strip()
        if num != st["num"]:
            st["num"] = num
            st["change"] = time.monotonic()
        c = st["widget"]
        W = H = 250
        bg = "#15151b"
        root.configure(bg=bg); c.configure(bg=bg)
        sw = root.winfo_screenwidth(); sh = root.winfo_screenheight()
        root.geometry(f"{W}x{H}+{(sw - W) // 2}+{(sh - H) // 3}")
        cx, cy, R = W // 2, H // 2, 95
        frac = min(1.0, (time.monotonic() - st["change"]) / 1.0)
        c.delete("all")
        c.create_oval(cx - R, cy - R, cx + R, cy + R, outline="#333842", width=12)
        extent = -359.999 * (1.0 - frac)           # anillo que se vacia
        if extent <= -0.2:
            c.create_arc(cx - R, cy - R, cx + R, cy + R, start=90, extent=extent,
                         style="arc", outline=color, width=12)
        pop = 1.22 - 0.22 * min(1.0, frac * 2.2)    # "pop" al cambiar de numero
        c.create_text(cx, cy - 6, text=num, fill="#ffffff",
                      font=("Segoe UI", int(104 * pop), "bold"))
        if subtitle:
            c.create_text(cx, cy + R + 26, text=subtitle,
                          fill="#cfcfcf", font=("Segoe UI", 11))

    def draw_banner(color, body):
        st["num"] = None
        c = st["widget"]
        mark = "●" if st["blink"] else "○"
        st["blink"] = not st["blink"]
        c.configure(text=f"{mark}  {body}", bg=color)
        root.configure(bg=color)
        root.update_idletasks()
        w = c.winfo_reqwidth(); h = c.winfo_reqheight()
        sw = root.winfo_screenwidth()
        root.geometry(f"{w}x{h}+{max(0, sw - w - 24)}+28")

    def tick():
        p = _parse(flag)
        if p is None:
            root.destroy(); return
        mode, color, body, subtitle = p
        try:
            set_mode(mode)
            if mode == "count":
                draw_count(color, body, subtitle)
            else:
                draw_banner(color, body)
        except Exception:
            pass
        root.after(40 if mode == "count" else 450, tick)

    root.after(60, tick)
    root.mainloop()


if __name__ == "__main__":
    main()
