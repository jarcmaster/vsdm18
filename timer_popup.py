# -*- coding: utf-8 -*-
"""
Ventana de aviso del Timer (categoria Practical).

Proceso independiente que el servidor lanza cuando un timer llega a 0.
Muestra el titulo del timer y un boton "Dismiss". Al cerrarla (Dismiss o la X),
el proceso termina; el servidor detecta que termino y detiene el parpadeo y el
sonido, devolviendo la tecla a su aspecto normal.

Uso:  python timer_popup.py "Titulo del timer"
Empaquetado:  StreamDockM18.exe --timer-popup "Titulo del timer"
"""

import sys


def run_popup(title: str = "Timer") -> None:
    import tkinter as tk

    root = tk.Tk()
    root.title("Stream Dock M18 — Timer")
    root.configure(bg="#14161c")
    root.attributes("-topmost", True)
    try:
        root.attributes("-toolwindow", True)
    except Exception:
        pass

    W, H = 360, 200
    root.update_idletasks()
    sw = root.winfo_screenwidth(); sh = root.winfo_screenheight()
    x = (sw - W) // 2; y = (sh - H) // 3
    root.geometry(f"{W}x{H}+{x}+{y}")
    root.resizable(False, False)

    tk.Label(root, text="⏰", bg="#14161c", fg="#ffcc33",
             font=("Segoe UI Emoji", 40)).pack(pady=(18, 4))
    tk.Label(root, text=(title or "Timer")[:40], bg="#14161c", fg="#ffffff",
             font=("Segoe UI", 14, "bold")).pack()
    tk.Label(root, text="Time's up!", bg="#14161c", fg="#9fb4d6",
             font=("Segoe UI", 11)).pack(pady=(2, 10))

    def dismiss(*_a):
        try:
            root.destroy()
        except Exception:
            pass

    btn = tk.Button(root, text="Dismiss", command=dismiss,
                    bg="#2d6cdf", fg="white", activebackground="#2559b8",
                    activeforeground="white", relief="flat",
                    font=("Segoe UI", 12, "bold"), width=14, height=1, cursor="hand2")
    btn.pack(pady=4)

    root.protocol("WM_DELETE_WINDOW", dismiss)
    root.bind("<Escape>", dismiss)
    root.bind("<Return>", dismiss)
    try:
        root.lift(); root.focus_force(); btn.focus_set()
        root.bell()
    except Exception:
        pass
    root.mainloop()


def main(argv) -> None:
    # el titulo es el ultimo argumento que no sea una bandera (--timer-popup)
    args = [a for a in argv[1:] if not a.startswith("--")]
    title = args[-1] if args else "Timer"
    run_popup(title)


if __name__ == "__main__":
    main(sys.argv)
