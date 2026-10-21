# -*- coding: utf-8 -*-
"""
Ventana de Alarma (categoria Practical). Dos modos:

  * ring : suena una alarma. Botones Snooze (exit 10) / Dismiss (exit 0).
  * info : al pulsar la tecla. Muestra proxima alarma + historial, y un
           formulario rapido para re-armar/crear la alarma en ESE boton
           (hora, repeticion, nota) que se guarda en config.json.

Uso:  alarm_popup.py <nota> <cuando> <prioridad> <modo> [state.json] [config.json] [scene] [page] [pos]
Empaquetado:  StreamDockM18.exe --alarm-popup ...
"""

import json
import os
import sys

_PRIORITY = {
    "urgent": ("#e62828", "URGENT"), "reminder": ("#3c8cff", "REMINDER"),
    "break": ("#3cb478", "BREAK"), "work": ("#d2963c", "WORK"),
    "stream": ("#aa46d2", "STREAM"), "normal": ("#e67800", "ALARM"),
}
_EVENT_LABEL = {"rang": ("🔔", "#e67800"), "dismissed": ("✔", "#6fcf97"),
                "snoozed": ("💤", "#9fb4d6"), "missed": ("⚠", "#e6b800")}
_REPEATS = [("Once", "once"), ("Every day", "daily"), ("Weekdays (Mon-Fri)", "weekdays")]


def _load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _key_action(cfg, scene, page, pos):
    try:
        return cfg["scenes"][scene]["pages"][page]["keys"][str(pos)]["action"]
    except Exception:
        return None


def _save_alarm(config_path, scene, page, pos, time24, repeat, note, days=None):
    cfg = _load_json(config_path)
    if not isinstance(cfg, dict):
        return False
    try:
        keys = cfg["scenes"][scene]["pages"][page].setdefault("keys", {})
        slot = keys.setdefault(str(pos), {})
        action = slot.get("action")
        if not isinstance(action, dict) or action.get("type") != "alarm":
            action = {"type": "alarm", "notify": True, "sound": True, "snooze_min": 5,
                      "snooze_max": 3, "priority": "normal", "escalate": False,
                      "days": [], "interval_min": 60, "exec": {"kind": "none"}}
            slot["action"] = action
        action["time"] = time24
        action["repeat"] = repeat
        action["note"] = note
        action["days"] = list(days or [])
        tmp = config_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        os.replace(tmp, config_path)
        return True
    except Exception as e:
        print("[alarm] save cfg:", e)
        return False


def run_popup(note="Alarm", when="", priority="normal", mode="ring", history=None,
              config_path="", scene=0, page=0, pos=0):
    import tkinter as tk
    from tkinter import ttk

    accent, label = _PRIORITY.get(priority, _PRIORITY["normal"])
    result = {"code": 0}
    is_info = (mode == "info")
    can_edit = is_info and bool(config_path) and os.path.exists(config_path)

    # cfg actual de la alarma (para prerellenar el formulario)
    cur = {}
    if can_edit:
        c = _load_json(config_path)
        a = _key_action(c, scene, page, pos) if c else None
        if isinstance(a, dict) and a.get("type") == "alarm":
            cur = a

    root = tk.Tk()
    root.title("Stream Dock M18 — Alarm")
    root.configure(bg="#14161c")
    root.attributes("-topmost", True)
    W, H = (420, 610) if is_info else (380, 230)
    sw = root.winfo_screenwidth(); sh = root.winfo_screenheight()
    root.geometry(f"{W}x{H}+{(sw - W) // 2}+{(sh - H) // 4}")
    root.resizable(False, False)

    tk.Label(root, text=label, bg=accent, fg="white",
             font=("Segoe UI", 10, "bold")).pack(fill="x", ipady=3)
    tk.Label(root, text=("🗓" if is_info else "⏰"), bg="#14161c", fg=accent,
             font=("Segoe UI Emoji", 26 if is_info else 34)).pack(pady=(8, 0))
    tk.Label(root, text=(note or "Alarm")[:48], bg="#14161c", fg="#ffffff",
             font=("Segoe UI", 13, "bold"), wraplength=380).pack()
    if when:
        tk.Label(root, text=when, bg="#14161c", fg="#9fb4d6",
                 font=("Segoe UI", 10)).pack(pady=(1, 4))

    def finish(code):
        result["code"] = code
        try:
            root.destroy()
        except Exception:
            pass

    if can_edit:
        # --- formulario rapido: re-armar / crear en este boton ---
        tk.Label(root, text="Set / re-arm this alarm", bg="#14161c", fg="#7f8aa0",
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=16, pady=(6, 0))
        form = tk.Frame(root, bg="#14161c"); form.pack(fill="x", padx=14)

        # prerellenar hora
        hh, mm = 7, 0
        try:
            p = str(cur.get("time", "07:00")).replace(".", ":").split(":")
            hh = max(0, min(23, int(p[0]))); mm = max(0, min(59, int(p[1])))
        except Exception:
            pass
        ampm0 = "PM" if hh >= 12 else "AM"
        h12 = hh % 12 or 12
        hour_cb = ttk.Combobox(form, width=4, state="readonly",
                               values=[str(x) for x in range(1, 13)])
        hour_cb.set(str(h12))
        min_cb = ttk.Combobox(form, width=4, state="readonly",
                              values=[f"{x:02d}" for x in range(60)])
        min_cb.set(f"{mm:02d}")
        ampm_cb = ttk.Combobox(form, width=4, state="readonly", values=["AM", "PM"])
        ampm_cb.set(ampm0)
        hour_cb.grid(row=0, column=0, padx=2, pady=4)
        tk.Label(form, text=":", bg="#14161c", fg="#9fb4d6").grid(row=0, column=1)
        min_cb.grid(row=0, column=2, padx=2)
        ampm_cb.grid(row=0, column=3, padx=2)

        # --- selector de dias de la semana (S M T W T F S) ---
        # display -> weekday (Mon=0..Sun=6); la fila empieza en domingo
        DAYS = [("S", 6), ("M", 0), ("T", 1), ("W", 2), ("T", 3), ("F", 4), ("S", 5)]
        rep0 = cur.get("repeat", "once")
        if rep0 == "daily":
            selected = {0, 1, 2, 3, 4, 5, 6}
        elif rep0 == "weekdays":
            selected = {0, 1, 2, 3, 4}
        elif rep0 == "days":
            selected = set(int(d) for d in cur.get("days", []))
        else:
            selected = set()
        day_frame = tk.Frame(root, bg="#14161c")
        day_frame.pack(anchor="w", padx=14, pady=(4, 0))
        day_btns = []

        def _restyle():
            for i, (_lbl, wd) in enumerate(DAYS):
                on = wd in selected
                day_btns[i].config(bg="#3c6cff" if on else "#262b36",
                                   fg="white" if on else "#9aa3b2")

        def _toggle(i):
            wd = DAYS[i][1]
            selected.discard(wd) if wd in selected else selected.add(wd)
            _restyle()
        for i, (lbl, _wd) in enumerate(DAYS):
            b = tk.Button(day_frame, text=lbl, width=2, relief="flat", cursor="hand2",
                          font=("Segoe UI", 10, "bold"), borderwidth=0,
                          command=lambda i=i: _toggle(i))
            b.grid(row=0, column=i, padx=3, ipady=2)
            day_btns.append(b)
        _restyle()
        tk.Label(root, text="No days selected = once", bg="#14161c", fg="#6a7484",
                 font=("Segoe UI", 8)).pack(anchor="w", padx=16)

        tk.Label(root, text="Message", bg="#14161c", fg="#7f8aa0",
                 font=("Segoe UI", 9)).pack(anchor="w", padx=16, pady=(4, 0))
        note_entry = tk.Entry(root, bg="#1b1e26", fg="#e6e6e6", insertbackground="#e6e6e6",
                              borderwidth=0, font=("Segoe UI", 10))
        note_entry.insert(0, cur.get("note", ""))
        note_entry.pack(fill="x", padx=16, ipady=4, pady=(2, 2))

        status_lbl = tk.Label(root, text="", bg="#14161c", fg="#6fcf97", font=("Segoe UI", 9))
        status_lbl.pack(anchor="w", padx=16)

        def do_set():
            try:
                h = int(hour_cb.get()); m = int(min_cb.get())
            except (TypeError, ValueError):
                h, m = 7, 0
            if ampm_cb.get() == "PM" and h != 12:
                h += 12
            if ampm_cb.get() == "AM" and h == 12:
                h = 0
            sel = sorted(selected)
            days = []
            if not sel:
                rep = "once"
            elif len(sel) == 7:
                rep = "daily"
            elif set(sel) == {0, 1, 2, 3, 4}:
                rep = "weekdays"
            else:
                rep = "days"; days = sel
            ok = _save_alarm(config_path, scene, page, pos, f"{h:02d}:{m:02d}", rep,
                             note_entry.get(), days)
            if ok:
                status_lbl.config(text="Alarm set ✔  (applies in a moment)")
                root.after(1200, lambda: finish(0))
            else:
                status_lbl.config(text="Could not save", fg="#ff8a8a")

        tk.Button(root, text="Set alarm", command=do_set, bg=accent, fg="white",
                  activebackground=accent, activeforeground="white", relief="flat",
                  font=("Segoe UI", 10, "bold"), cursor="hand2").pack(padx=16, pady=(2, 6), anchor="e")

    if is_info:
        tk.Label(root, text="History", bg="#14161c", fg="#7f8aa0",
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=16)
        box = tk.Frame(root, bg="#1b1e26")
        box.pack(fill="both", expand=True, padx=12, pady=(2, 6))
        rows = (history or [])[:8]
        if not rows:
            tk.Label(box, text="— no events yet —", bg="#1b1e26", fg="#6a7484",
                     font=("Segoe UI", 10)).pack(anchor="w", padx=8, pady=8)
        for ev in rows:
            icon, col = _EVENT_LABEL.get(ev.get("event", ""), ("•", "#9fb4d6"))
            txt = f"{icon}  {ev.get('t', '')}   {ev.get('note', '')}   ({ev.get('event', '')})"
            tk.Label(box, text=txt[:56], bg="#1b1e26", fg=col, anchor="w",
                     font=("Segoe UI", 9)).pack(fill="x", padx=8, pady=1)

    row = tk.Frame(root, bg="#14161c")
    row.pack(pady=6)
    if is_info:
        tk.Button(row, text="Close", command=lambda: finish(0), bg="#2a2f3a", fg="#dfe6f2",
                  activebackground="#39414f", activeforeground="white", relief="flat",
                  font=("Segoe UI", 11, "bold"), width=14, height=1, cursor="hand2").pack()
    else:
        tk.Button(row, text="Snooze", command=lambda: finish(10), bg="#2a2f3a", fg="#dfe6f2",
                  activebackground="#39414f", activeforeground="white", relief="flat",
                  font=("Segoe UI", 11, "bold"), width=12, height=1, cursor="hand2").pack(side="left", padx=6)
        tk.Button(row, text="Dismiss", command=lambda: finish(0), bg=accent, fg="white",
                  activebackground=accent, activeforeground="white", relief="flat",
                  font=("Segoe UI", 11, "bold"), width=12, height=1, cursor="hand2").pack(side="left", padx=6)

    root.protocol("WM_DELETE_WINDOW", lambda: finish(0))
    root.bind("<Escape>", lambda e: finish(0))
    try:
        root.lift(); root.focus_force()
        if not is_info:
            root.bell()
    except Exception:
        pass
    root.mainloop()
    sys.exit(result["code"])


def main(argv=None):
    argv = argv if argv is not None else sys.argv
    args = [a for a in argv[1:] if not a.startswith("--")]

    def g(i, d=""):
        return args[i] if len(args) > i else d
    note = g(0, "Alarm"); when = g(1, ""); priority = g(2, "normal"); mode = g(3, "ring")
    state_path = g(4, ""); config_path = g(5, "")
    try:
        scene = int(g(6, "0")); page = int(g(7, "0")); pos = int(g(8, "0"))
    except (TypeError, ValueError):
        scene = page = pos = 0
    history = None
    if mode == "info" and state_path:
        d = _load_json(state_path)
        history = (d or {}).get("history", []) if isinstance(d, dict) else []
    run_popup(note, when, priority, mode, history, config_path, scene, page, pos)


if __name__ == "__main__":
    main(sys.argv)
