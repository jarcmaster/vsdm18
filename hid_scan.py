# -*- coding: utf-8 -*-
"""
Diagnostico HID: lista TODOS los dispositivos HID conectados (VID:PID, nombre,
interfaz, usage_page) y resalta cualquier Stream Dock (VID 0x5548). Sirve para
saber por que el app no reconoce el M18 en un equipo nuevo:

  * si NO aparece ningun 5548:xxxx  -> cable de solo carga / puerto / driver.
  * si aparece 5548:1000            -> el equipo ES compatible; si aun asi el
                                       app no lo abre, lo retiene el software
                                       oficial (cierralo) o es un problema de
                                       permisos/driver.
  * si aparece 5548:<otro PID>      -> es un rebrand con PID distinto; hay que
                                       anadir ese PID al app para soportarlo.

Escribe el resultado en %APPDATA%\\Stream Dock M18 by JARCMASTER\\hid_scan.txt y
en el Escritorio, y lo muestra en una ventana.

Uso:  hid_scan.py   |   StreamDockM18.exe --hid-scan
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

M18_VID = 0x5548
M18_PID = 0x1000


def collect():
    lines = []
    try:
        import hid
    except Exception as e:
        return [f"ERROR: no se pudo cargar hidapi: {e!r}"], []
    try:
        devs = list(hid.enumerate())
    except Exception as e:
        return [f"ERROR: hid.enumerate fallo: {e!r}"], []

    sd = [d for d in devs if d.get("vendor_id") == M18_VID]
    lines.append(f"Dispositivos HID totales: {len(devs)}")
    if sd:
        lines.append("")
        lines.append(">>> Stream Dock detectado(s) (VID 0x5548):")
        for d in sd:
            lines.append("    " + _fmt(d))
        pids = {d.get("product_id") for d in sd}
        if M18_PID in pids:
            lines.append("")
            lines.append("    => Es COMPATIBLE (5548:1000). Si el app no lo abre,")
            lines.append("       cierra el software oficial de VSD/Mirabox.")
        else:
            lines.append("")
            lines.append(f"    => PID distinto de 0x1000 ({', '.join(f'{p:#06x}' for p in pids)}).")
            lines.append("       Es un rebrand; hay que anadir ese PID al app.")
    else:
        lines.append("")
        lines.append(">>> NO se encontro ningun Stream Dock (VID 0x5548).")
        lines.append("    Causas: cable USB-C de SOLO CARGA, puerto/hub, o driver.")
        lines.append("    Prueba otro cable de DATOS y un puerto directo del equipo.")

    lines.append("")
    lines.append("--- Todos los dispositivos HID ---")
    for d in sorted(devs, key=lambda x: (x.get("vendor_id") or 0, x.get("product_id") or 0)):
        lines.append(_fmt(d))
    return lines, sd


def _fmt(d):
    vid = d.get("vendor_id") or 0
    pid = d.get("product_id") or 0
    prod = (d.get("product_string") or "").strip()
    manu = (d.get("manufacturer_string") or "").strip()
    up = d.get("usage_page")
    iface = d.get("interface_number")
    up_s = f"{up:#06x}" if isinstance(up, int) else str(up)
    return f"{vid:#06x}:{pid:#06x}  if={iface}  usage_page={up_s}  {manu} {prod}".rstrip()


def _save(text):
    paths = []
    try:
        import m18_paths
        paths.append(os.path.join(m18_paths.data_dir(), "hid_scan.txt"))
    except Exception:
        pass
    try:
        paths.append(os.path.join(os.path.join(os.path.expanduser("~"), "Desktop"), "hid_scan.txt"))
    except Exception:
        pass
    saved = []
    for p in paths:
        try:
            with open(p, "w", encoding="utf-8") as f:
                f.write(text)
            saved.append(p)
        except Exception:
            pass
    return saved


def run():
    lines, sd = collect()
    text = "\n".join(lines)
    saved = _save(text)
    print(text)
    try:
        import tkinter as tk
        BG = "#14161c"; FG = "#e6e6e6"; OK = "#6fcf97"; WARN = "#e6b800"
        root = tk.Tk(); root.title("Stream Dock M18 — Diagnostico HID")
        root.configure(bg=BG); root.attributes("-topmost", True)
        root.geometry("760x560")
        head = (">>> Stream Dock DETECTADO" if sd else ">>> Stream Dock NO detectado")
        tk.Label(root, text=head, bg=BG, fg=(OK if sd else WARN),
                 font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=12, pady=(10, 2))
        wrap = tk.Frame(root, bg=BG); wrap.pack(fill="both", expand=True, padx=12, pady=(0, 6))
        sb = tk.Scrollbar(wrap, orient="vertical")
        txt = tk.Text(wrap, bg="#1b1e26", fg=FG, relief="flat", wrap="none",
                      font=("Consolas", 9), borderwidth=0, highlightthickness=0,
                      yscrollcommand=sb.set)
        sb.config(command=txt.yview); sb.pack(side="right", fill="y")
        txt.pack(side="left", fill="both", expand=True)
        txt.insert("1.0", text); txt.config(state="disabled")
        if saved:
            tk.Label(root, text="Guardado en:  " + "   |   ".join(saved), bg=BG, fg="#9fb4d6",
                     font=("Segoe UI", 8), wraplength=740, justify="left").pack(anchor="w", padx=12)
        tk.Button(root, text="Cerrar", command=root.destroy, bg="#2a2f3a", fg=FG, relief="flat",
                  font=("Segoe UI", 10, "bold"), cursor="hand2").pack(pady=8)
        root.mainloop()
    except Exception as e:
        print("[hid-scan] ui:", e)


def main(argv=None):
    run()


if __name__ == "__main__":
    main(sys.argv)
