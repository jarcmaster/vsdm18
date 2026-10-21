# -*- coding: utf-8 -*-
"""
Ventana de Recordatorios (categoria Practical "Reminder").

Dos modos:
  * ring   : aviso cuando vence un recordatorio. Botones Complete (exit 0),
             Snooze (exit 10), Dismiss (exit 20).
  * manage : gestor completo (lista, crear/editar, completar, posponer,
             borrar, historial, recordatorios rapidos).

Uso:  reminders_popup.py <mode> [id title note due priority]
"""

import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from streamdock_m18 import reminders as RM
except Exception as e:  # noqa
    RM = None
    _imp_err = e

BG = "#14161c"; PANEL = "#1b1e26"; FG = "#e6e6e6"; MUT = "#9fb4d6"; ACC = "#2d6cdf"
PRIO = [("Normal", "normal"), ("Urgent", "urgent"), ("Work", "work"),
        ("Break", "break"), ("Stream", "stream"), ("Personal", "personal")]
REPEATS = [("Once", "once"), ("Daily", "daily"), ("Weekly", "weekly"),
           ("Monthly", "monthly"), ("Custom days", "days")]
NOTIFY = [("Sound + visual", "both"), ("Sound", "sound"), ("Visual", "visual")]
PRIO_HEX = {"urgent": "#e62828", "work": "#d2963c", "break": "#3cb478",
            "stream": "#aa46d2", "personal": "#3c8cff", "normal": "#7f8aa0"}
_EVENT = {"fired": ("🔔", "#e67800"), "completed": ("✔", "#6fcf97"),
          "snoozed": ("💤", "#9fb4d6"), "dismissed": ("✖", "#c77"), "missed": ("⚠", "#e6b800")}


def run_ring(title, note, due, priority):
    import tkinter as tk
    accent = PRIO_HEX.get(priority, "#e67800")
    res = {"code": 0}
    root = tk.Tk(); root.title("Stream Dock M18 — Reminder"); root.configure(bg=BG)
    root.attributes("-topmost", True)
    W, H = 380, 250
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f"{W}x{H}+{(sw-W)//2}+{(sh-H)//4}"); root.resizable(False, False)
    tk.Label(root, text="REMINDER", bg=accent, fg="white", font=("Segoe UI", 10, "bold")).pack(fill="x", ipady=3)
    tk.Label(root, text="🔔", bg=BG, fg=accent, font=("Segoe UI Emoji", 30)).pack(pady=(10, 0))
    tk.Label(root, text=(title or "Reminder")[:48], bg=BG, fg="#fff", font=("Segoe UI", 14, "bold"),
             wraplength=350).pack()
    if note:
        tk.Label(root, text=note[:80], bg=BG, fg=MUT, font=("Segoe UI", 10), wraplength=350).pack(pady=(1, 2))
    d = RM.parse_due(due) if RM else None
    if d:
        tk.Label(root, text=d.strftime("%a %Y-%m-%d  %H:%M"), bg=BG, fg="#9fb4d6",
                 font=("Segoe UI", 10)).pack(pady=(0, 6))

    def finish(c):
        res["code"] = c
        try:
            root.destroy()
        except Exception:
            pass
    row = tk.Frame(root, bg=BG); row.pack(pady=6)
    tk.Button(row, text="✔ Complete", command=lambda: finish(0), bg="#2a6b4a", fg="white", relief="flat",
              font=("Segoe UI", 10, "bold"), width=11, cursor="hand2").pack(side="left", padx=4)
    tk.Button(row, text="💤 Snooze", command=lambda: finish(10), bg="#2a2f3a", fg="#dfe6f2", relief="flat",
              font=("Segoe UI", 10, "bold"), width=10, cursor="hand2").pack(side="left", padx=4)
    tk.Button(row, text="✖ Dismiss", command=lambda: finish(20), bg=accent, fg="white", relief="flat",
              font=("Segoe UI", 10, "bold"), width=10, cursor="hand2").pack(side="left", padx=4)
    root.protocol("WM_DELETE_WINDOW", lambda: finish(20))
    try:
        root.lift(); root.focus_force(); root.bell()
    except Exception:
        pass
    root.mainloop()
    sys.exit(res["code"])


def confirm_dialog(parent, title, message, ok_text="Delete", cancel_text="Cancel", danger=True):
    """Dialogo de confirmacion con el tema oscuro. Devuelve True/False."""
    import tkinter as tk
    res = {"ok": False}
    dlg = tk.Toplevel(parent); dlg.title(title); dlg.configure(bg=BG)
    dlg.attributes("-topmost", True); dlg.resizable(False, False)
    dlg.transient(parent)
    W, H = 370, 180
    try:
        parent.update_idletasks()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        x, y = px + (pw - W) // 2, py + (ph - H) // 2
    except Exception:
        x = y = 200
    dlg.geometry(f"{W}x{H}+{max(0, x)}+{max(0, y)}")
    tk.Label(dlg, text="⚠", bg=BG, fg="#e6b800", font=("Segoe UI Emoji", 24)).pack(pady=(16, 0))
    tk.Label(dlg, text=title, bg=BG, fg="#fff", font=("Segoe UI", 13, "bold")).pack(pady=(2, 4))
    tk.Label(dlg, text=message, bg=BG, fg=MUT, font=("Segoe UI", 10), justify="center").pack(pady=(0, 12))
    row = tk.Frame(dlg, bg=BG); row.pack()

    def done(v):
        res["ok"] = v
        try:
            dlg.destroy()
        except Exception:
            pass
    tk.Button(row, text=cancel_text, command=lambda: done(False), bg="#2a2f3a", fg="#dfe6f2",
              relief="flat", font=("Segoe UI", 10, "bold"), width=10, cursor="hand2",
              activebackground="#3a3f4a", activeforeground="white").pack(side="left", padx=6)
    tk.Button(row, text=ok_text, command=lambda: done(True), bg=("#b23a48" if danger else ACC), fg="white",
              relief="flat", font=("Segoe UI", 10, "bold"), width=10, cursor="hand2",
              activebackground=("#c7495a" if danger else "#3f7ce8"), activeforeground="white").pack(side="left", padx=6)
    dlg.bind("<Escape>", lambda e: done(False))
    dlg.bind("<Return>", lambda e: done(True))
    dlg.protocol("WM_DELETE_WINDOW", lambda: done(False))
    try:
        dlg.grab_set(); dlg.lift(); dlg.focus_force()
    except Exception:
        pass
    parent.wait_window(dlg)
    return res["ok"]


def run_manage():
    import tkinter as tk
    from tkinter import ttk, messagebox

    store = RM.load_store()
    root = tk.Tk(); root.title("Stream Dock M18 — Reminders"); root.configure(bg=BG)
    root.attributes("-topmost", True)
    W, H = 760, 640
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f"{W}x{H}+{(sw-W)//2}+{max(10,(sh-H)//6)}"); root.minsize(700, 580)
    from tkinter import font as tkfont
    tv_font = tkfont.Font(family="Segoe UI", size=10)
    row_h = tv_font.metrics("linespace") + 8   # escala con la DPI (evita filas encimadas)
    try:
        st = ttk.Style(); st.theme_use("clam")
        st.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=FG, rowheight=row_h, borderwidth=0, font=tv_font)
        st.configure("Treeview.Heading", background="#232733", foreground=MUT, borderwidth=0)
        st.map("Treeview", background=[("selected", ACC)], foreground=[("selected", "white")])
    except Exception:
        pass
    sel = {"id": None}

    # --- lista (izquierda) ---
    left = tk.Frame(root, bg=BG); left.pack(side="left", fill="both", expand=True, padx=(10, 5), pady=10)
    tk.Label(left, text="Reminders", bg=BG, fg=MUT, font=("Segoe UI", 10, "bold")).pack(anchor="w")
    cols = ("due", "rep", "st")
    tree = ttk.Treeview(left, columns=cols, show="tree headings", height=14, selectmode="browse")
    tree.heading("#0", text="Title"); tree.column("#0", width=150)
    tree.heading("due", text="Due"); tree.column("due", width=120, anchor="center")
    tree.heading("rep", text="Repeat"); tree.column("rep", width=70, anchor="center")
    tree.heading("st", text="Status"); tree.column("st", width=70, anchor="center")
    tree.pack(fill="both", expand=True, pady=(2, 4))
    pend_lbl = tk.Label(left, text="", bg=BG, fg=MUT, font=("Segoe UI", 9)); pend_lbl.pack(anchor="w")

    # --- formulario (derecha) ---
    right = tk.Frame(root, bg=BG, width=300); right.pack(side="left", fill="y", padx=(5, 10), pady=10)
    right.pack_propagate(False)

    def _lab(txt):
        tk.Label(right, text=txt, bg=BG, fg=MUT, font=("Segoe UI", 9)).pack(anchor="w", pady=(4, 0))

    _lab("Title")
    e_title = tk.Entry(right, bg=PANEL, fg=FG, insertbackground=FG, relief="flat", font=("Segoe UI", 11))
    e_title.pack(fill="x", ipady=3)
    _lab("Note")
    e_note = tk.Entry(right, bg=PANEL, fg=FG, insertbackground=FG, relief="flat", font=("Segoe UI", 10))
    e_note.pack(fill="x", ipady=3)

    _lab("Date & time")
    dtrow = tk.Frame(right, bg=BG); dtrow.pack(fill="x", pady=(0, 2))
    now = dt.datetime.now()
    cb_m = ttk.Combobox(dtrow, width=3, state="readonly", values=[f"{i:02d}" for i in range(1, 13)])
    cb_d = ttk.Combobox(dtrow, width=3, state="readonly", values=[f"{i:02d}" for i in range(1, 32)])
    cb_y = ttk.Combobox(dtrow, width=5, state="readonly", values=[str(now.year + i) for i in range(0, 3)])
    cb_h = ttk.Combobox(dtrow, width=3, state="readonly", values=[str(i) for i in range(1, 13)])
    cb_min = ttk.Combobox(dtrow, width=3, state="readonly", values=[f"{i:02d}" for i in range(60)])
    cb_ap = ttk.Combobox(dtrow, width=3, state="readonly", values=["AM", "PM"])
    for w in (cb_m, cb_d, cb_y, cb_h, cb_min, cb_ap):
        w.pack(side="left", padx=1)

    _lab("Repeat")
    cb_rep = ttk.Combobox(right, state="readonly", values=[d for d, _v in REPEATS]); cb_rep.pack(fill="x")
    DAYS = [("S", 6), ("M", 0), ("T", 1), ("W", 2), ("T", 3), ("F", 4), ("S", 5)]
    dayrow = tk.Frame(right, bg=BG); dayrow.pack(fill="x", pady=(2, 0))
    daysel = set(); daybtns = []

    def _day_restyle():
        for i, (_l, wd) in enumerate(DAYS):
            daybtns[i].config(bg="#3c6cff" if wd in daysel else "#262b36",
                              fg="white" if wd in daysel else "#9aa3b2")

    def _day_toggle(i):
        wd = DAYS[i][1]
        daysel.discard(wd) if wd in daysel else daysel.add(wd)
        _day_restyle()
    for i, (lbl, _wd) in enumerate(DAYS):
        b = tk.Button(dayrow, text=lbl, width=2, relief="flat", font=("Segoe UI", 9, "bold"),
                      command=lambda i=i: _day_toggle(i))
        b.grid(row=0, column=i, padx=2, ipady=1); daybtns.append(b)

    row2 = tk.Frame(right, bg=BG); row2.pack(fill="x", pady=(4, 0))
    tk.Label(row2, text="Snooze", bg=BG, fg=MUT, font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w")
    cb_sn = ttk.Combobox(row2, width=5, state="readonly", values=["5", "10", "15", "30"]); cb_sn.grid(row=1, column=0, padx=(0, 8))
    tk.Label(row2, text="Notify", bg=BG, fg=MUT, font=("Segoe UI", 9)).grid(row=0, column=1, sticky="w")
    cb_nt = ttk.Combobox(row2, width=14, state="readonly", values=[d for d, _v in NOTIFY]); cb_nt.grid(row=1, column=1)

    _lab("Priority / category")
    cb_pr = ttk.Combobox(right, state="readonly", values=[d for d, _v in PRIO]); cb_pr.pack(fill="x")
    v_conf = tk.BooleanVar()
    tk.Checkbutton(right, text="Repeat until confirmed", variable=v_conf, bg=BG, fg=FG,
                   selectcolor=PANEL, activebackground=BG, activeforeground=FG,
                   font=("Segoe UI", 9)).pack(anchor="w", pady=(4, 0))

    _lab("On due, run")
    exrow = tk.Frame(right, bg=BG); exrow.pack(fill="x")
    cb_ex = ttk.Combobox(exrow, width=7, state="readonly", values=["none", "app", "key"]); cb_ex.pack(side="left")
    e_ex = tk.Entry(exrow, bg=PANEL, fg=FG, insertbackground=FG, relief="flat", font=("Segoe UI", 9))
    e_ex.pack(side="left", fill="x", expand=True, padx=(4, 0), ipady=2)

    def set_dt(d):
        cb_m.set(f"{d.month:02d}"); cb_d.set(f"{d.day:02d}"); cb_y.set(str(d.year))
        h = d.hour % 12 or 12
        cb_h.set(str(h)); cb_min.set(f"{d.minute:02d}"); cb_ap.set("PM" if d.hour >= 12 else "AM")

    def get_dt():
        try:
            h = int(cb_h.get())
            if cb_ap.get() == "PM" and h != 12:
                h += 12
            if cb_ap.get() == "AM" and h == 12:
                h = 0
            return dt.datetime(int(cb_y.get()), int(cb_m.get()), int(cb_d.get()), h, int(cb_min.get()))
        except Exception:
            return dt.datetime.now() + dt.timedelta(minutes=10)

    def clear_form(due=None):
        sel["id"] = None
        e_title.delete(0, "end"); e_note.delete(0, "end"); e_ex.delete(0, "end")
        set_dt(due or (dt.datetime.now() + dt.timedelta(minutes=10)))
        cb_rep.set("Once"); cb_sn.set("10"); cb_nt.set("Sound + visual"); cb_pr.set("Normal")
        cb_ex.set("none"); v_conf.set(False); daysel.clear(); _day_restyle()

    def load_form(r):
        sel["id"] = r.get("id")
        e_title.delete(0, "end"); e_title.insert(0, r.get("title", ""))
        e_note.delete(0, "end"); e_note.insert(0, r.get("note", ""))
        d = RM.parse_due(r.get("due", "")) or dt.datetime.now()
        set_dt(d)
        cb_rep.set(next((dd for dd, v in REPEATS if v == r.get("repeat", "once")), "Once"))
        cb_sn.set(str(r.get("snooze_min", 10)))
        cb_nt.set(next((dd for dd, v in NOTIFY if v == r.get("notify", "both")), "Sound + visual"))
        cb_pr.set(next((dd for dd, v in PRIO if v == r.get("priority", "normal")), "Normal"))
        v_conf.set(bool(r.get("repeat_until_confirm")))
        daysel.clear(); daysel.update(int(x) for x in r.get("days", [])); _day_restyle()
        ex = r.get("exec") or {}
        k = ex.get("kind", "none"); cb_ex.set(k if k in ("none", "app", "key") else "none")
        e_ex.delete(0, "end")
        if k == "app":
            e_ex.insert(0, ex.get("path", ""))
        elif k == "key":
            e_ex.insert(0, "+".join(ex.get("keys", [])))

    def refresh():
        nonlocal store
        store = RM.load_store()
        tree.delete(*tree.get_children())
        rems = sorted(store.get("reminders", []),
                      key=lambda r: (r.get("status") != "pending", r.get("due", "")))
        for r in rems:
            d = RM.parse_due(r.get("due", ""))
            tree.insert("", "end", iid=r.get("id"), text=(r.get("title") or "")[:22],
                        values=(d.strftime("%m/%d %H:%M") if d else "",
                                r.get("repeat", "once"),
                                "✔ done" if r.get("status") == "completed" else "pending"))
        pend_lbl.config(text=f"{RM.pending_count(store)} pending")

    def _cur():
        return next((r for r in store.get("reminders", []) if r.get("id") == sel["id"]), None)

    def on_select(_e=None):
        s = tree.selection()
        if s:
            r = next((x for x in store.get("reminders", []) if x.get("id") == s[0]), None)
            if r:
                load_form(r)
    tree.bind("<<TreeviewSelect>>", on_select)

    def save():
        rep = next((v for d, v in REPEATS if d == cb_rep.get()), "once")
        notify = next((v for d, v in NOTIFY if d == cb_nt.get()), "both")
        prio = next((v for d, v in PRIO if d == cb_pr.get()), "normal")
        k = cb_ex.get() or "none"
        if k == "app":
            ex = {"kind": "app", "path": e_ex.get().strip()}
        elif k == "key":
            ex = {"kind": "key", "keys": [x.strip() for x in e_ex.get().replace(",", "+").split("+") if x.strip()]}
        else:
            ex = {"kind": "none"}
        r = _cur()
        if r is None:
            r = {"id": RM.new_id(), "status": "pending", "snooze_count": 0, "last_fired": None}
            store.setdefault("reminders", []).append(r)
        r.update({"title": e_title.get().strip() or "Reminder", "note": e_note.get().strip(),
                  "due": get_dt().isoformat(), "repeat": rep, "days": sorted(daysel),
                  "snooze_min": int(cb_sn.get() or 10), "notify": notify, "priority": prio,
                  "repeat_until_confirm": bool(v_conf.get()), "exec": ex, "status": "pending"})
        RM.save_store(store); refresh(); clear_form()

    def complete():
        r = _cur()
        if not r:
            return
        RM.append_history(store, r.get("title"), "completed")
        if r.get("repeat", "once") == "once":
            r["status"] = "completed"
        else:
            nxt = RM.advance_due(RM.parse_due(r.get("due", "")) or dt.datetime.now(), r.get("repeat"), r.get("days"))
            r["due"] = nxt.isoformat() if nxt else r.get("due")
            if not nxt:
                r["status"] = "completed"
        RM.save_store(store); refresh()

    def delete():
        r = _cur()
        if not r:
            return
        if messagebox.askyesno("Delete", f"Delete “{r.get('title')}”?", parent=root, icon="warning", default="no"):
            store["reminders"] = [x for x in store.get("reminders", []) if x.get("id") != r.get("id")]
            RM.save_store(store); refresh(); clear_form()

    # --- quick add ---
    def quick(delta=None, tomorrow9=False):
        clear_form()
        if tomorrow9:
            d = (dt.datetime.now() + dt.timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
        else:
            d = dt.datetime.now() + delta
        set_dt(d); e_title.focus_set()

    qrow = tk.Frame(right, bg=BG); qrow.pack(fill="x", pady=(8, 2))
    tk.Label(qrow, text="Quick:", bg=BG, fg=MUT, font=("Segoe UI", 9)).pack(side="left")
    for txt, fn in (("+10m", lambda: quick(dt.timedelta(minutes=10))),
                    ("+30m", lambda: quick(dt.timedelta(minutes=30))),
                    ("+1h", lambda: quick(dt.timedelta(hours=1))),
                    ("Tmrw 9", lambda: quick(tomorrow9=True))):
        tk.Button(qrow, text=txt, command=fn, bg="#2a2f3a", fg=FG, relief="flat",
                  font=("Segoe UI", 9), cursor="hand2").pack(side="left", padx=2)

    brow = tk.Frame(right, bg=BG); brow.pack(fill="x", pady=(6, 2))
    tk.Button(brow, text="New", command=lambda: clear_form(), bg="#2a2f3a", fg=FG, relief="flat",
              font=("Segoe UI", 10, "bold"), cursor="hand2").pack(side="left", padx=2)
    tk.Button(brow, text="Save", command=save, bg=ACC, fg="white", relief="flat",
              font=("Segoe UI", 10, "bold"), cursor="hand2").pack(side="left", padx=2)
    tk.Button(brow, text="Complete", command=complete, bg="#2a6b4a", fg="white", relief="flat",
              font=("Segoe UI", 10, "bold"), cursor="hand2").pack(side="left", padx=2)
    tk.Button(brow, text="Delete", command=delete, bg="#5a2a36", fg="white", relief="flat",
              font=("Segoe UI", 10, "bold"), cursor="hand2").pack(side="left", padx=2)

    # --- historial (con scroll + limpiar) ---
    histhdr = tk.Frame(left, bg=BG); histhdr.pack(fill="x", pady=(6, 0))
    tk.Label(histhdr, text="History", bg=BG, fg=MUT, font=("Segoe UI", 9, "bold")).pack(side="left")
    clear_btn = tk.Button(histhdr, text="🗑 Clear", bg="#2a2f3a", fg="#dfe6f2", relief="flat",
                          font=("Segoe UI", 8, "bold"), cursor="hand2", padx=8,
                          activebackground="#3a3f4a", activeforeground="white")
    clear_btn.pack(side="right")

    histwrap = tk.Frame(left, bg=PANEL); histwrap.pack(fill="x", pady=(2, 0))
    hist_sb = ttk.Scrollbar(histwrap, orient="vertical")
    hist_txt = tk.Text(histwrap, bg=PANEL, fg=FG, relief="flat", height=7, wrap="none",
                       font=("Segoe UI", 9), borderwidth=0, highlightthickness=0,
                       padx=6, pady=2, yscrollcommand=hist_sb.set, cursor="arrow")
    hist_sb.config(command=hist_txt.yview)
    hist_sb.pack(side="right", fill="y")
    hist_txt.pack(side="left", fill="both", expand=True)
    for _evk, (_ic, _col) in _EVENT.items():
        hist_txt.tag_configure(_evk, foreground=_col)
    hist_txt.tag_configure("_mut", foreground=MUT)
    # permitir rueda del raton aunque el widget este deshabilitado
    hist_txt.bind("<MouseWheel>", lambda e: (hist_txt.yview_scroll(int(-e.delta / 120), "units"), "break")[1])

    def refresh_hist():
        hist_txt.config(state="normal")
        hist_txt.delete("1.0", "end")
        history = store.get("history", [])
        for ev in history:
            icon, _col = _EVENT.get(ev.get("event", ""), ("•", MUT))
            line = f"{icon} {ev.get('t','')}  {ev.get('title','')} ({ev.get('event','')})\n"
            tag = ev.get("event", "") if ev.get("event", "") in _EVENT else "_mut"
            hist_txt.insert("end", line, tag)
        if not history:
            hist_txt.insert("end", "No history yet\n", "_mut")
        hist_txt.config(state="disabled")

    def clear_history():
        if not store.get("history"):
            return
        if confirm_dialog(root, "Clear history", "Delete all reminder history?\nThis cannot be undone.",
                          ok_text="Clear"):
            store["history"] = []
            RM.save_store(store); refresh_hist()
    clear_btn.config(command=clear_history)

    _orig_refresh = refresh

    def refresh():  # noqa
        _orig_refresh(); refresh_hist()

    clear_form(); refresh()
    try:
        root.lift(); root.focus_force()
    except Exception:
        pass
    root.mainloop()


def main(argv=None):
    argv = argv if argv is not None else sys.argv
    args = [a for a in argv[1:] if not a.startswith("--")]
    mode = args[0] if args else "manage"
    if RM is None:
        import tkinter as tk
        r = tk.Tk(); r.configure(bg=BG)
        tk.Label(r, text="reminders module not available", bg=BG, fg="#ff8a8a").pack(padx=20, pady=20)
        r.mainloop(); return
    if mode == "ring":
        title = args[2] if len(args) > 2 else "Reminder"
        note = args[3] if len(args) > 3 else ""
        due = args[4] if len(args) > 4 else ""
        prio = args[5] if len(args) > 5 else "normal"
        run_ring(title, note, due, prio)
    else:
        run_manage()


if __name__ == "__main__":
    main(sys.argv)
