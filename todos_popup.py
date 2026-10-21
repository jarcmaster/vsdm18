# -*- coding: utf-8 -*-
"""
Ventana de To-Do (categoria Practical): gestor de tareas.

Vistas Hoy / Proximo / Todo / Completadas / Papelera, busqueda, lista de tareas,
editor con titulo/descripcion/fecha/prioridad/categoria/lista/estado/recurrencia
y subtareas, completar (recurrentes crean la siguiente), borrar a papelera y
restaurar.

Uso:  todos_popup.py   |   StreamDockM18.exe --todos-popup
"""

import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from streamdock_m18 import todos as TD
except Exception as e:  # noqa
    TD = None
    _imp_err = e

BG = "#14161c"; PANEL = "#1b1e26"; FG = "#e6e6e6"; MUT = "#9fb4d6"; ACC = "#2d6cdf"
PRIO = [("Normal", "normal"), ("Urgent", "urgent"), ("Work", "work"),
        ("Personal", "personal"), ("Stream", "stream")]
STATE = [("Pending", "pending"), ("In progress", "in_progress"),
         ("Completed", "completed"), ("Postponed", "postponed")]
RECUR = [("No repeat", "none"), ("Daily", "daily"), ("Weekly", "weekly"), ("Monthly", "monthly")]
PRIO_HEX = {"urgent": "#e62828", "work": "#d2963c", "personal": "#3c8cff",
            "stream": "#aa46d2", "normal": "#7f8aa0"}


def run():
    import tkinter as tk
    from tkinter import ttk, messagebox

    store = TD.load_store()
    view = {"name": "today"}
    sel = {"id": None}

    root = tk.Tk(); root.title("Stream Dock M18 — To-Do"); root.configure(bg=BG)
    root.attributes("-topmost", True)
    W, H = 970, 660
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f"{W}x{H}+{(sw-W)//2}+{max(10,(sh-H)//7)}"); root.minsize(910, 600)
    from tkinter import font as tkfont
    tv_font = tkfont.Font(family="Segoe UI", size=10)
    row_h = tv_font.metrics("linespace") + 10   # escala con la DPI (evita filas encimadas)
    try:
        s = ttk.Style(); s.theme_use("clam")
        s.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=FG, rowheight=row_h, borderwidth=0, font=tv_font)
        s.configure("Treeview.Heading", background="#232733", foreground=MUT, borderwidth=0)
        s.map("Treeview", background=[("selected", ACC)], foreground=[("selected", "white")])
    except Exception:
        pass

    # ================= IZQUIERDA =================
    left = tk.Frame(root, bg=BG); left.pack(side="left", fill="both", expand=True, padx=(10, 5), pady=10)

    # quick add
    qrow = tk.Frame(left, bg=BG); qrow.pack(fill="x")
    q_entry = tk.Entry(qrow, bg=PANEL, fg=FG, insertbackground=FG, relief="flat", font=("Segoe UI", 11))
    q_entry.pack(side="left", fill="x", expand=True, ipady=4)

    def quick_add(_e=None):
        txt = q_entry.get().strip()
        if not txt:
            return
        t = {"id": TD.new_id(), "title": txt, "desc": "", "due": None, "priority": "normal",
             "category": "", "list": "Inbox", "state": "pending", "recurring": "none",
             "subtasks": [], "created": dt.datetime.now().isoformat(), "completed_at": None}
        store.setdefault("tasks", []).append(t)
        TD.save_store(store); q_entry.delete(0, "end"); refresh()
    q_entry.bind("<Return>", quick_add)
    tk.Button(qrow, text="+ Add", command=quick_add, bg=ACC, fg="white", relief="flat",
              font=("Segoe UI", 10, "bold"), cursor="hand2").pack(side="left", padx=(4, 0))

    # vistas
    vrow = tk.Frame(left, bg=BG); vrow.pack(fill="x", pady=(6, 2))
    vbtns = {}

    def set_view(name):
        view["name"] = name
        for n, b in vbtns.items():
            b.config(bg=ACC if n == name else "#2a2f3a", fg="white" if n == name else MUT)
        refresh()
    for name, lbl in (("today", "Today"), ("upcoming", "Upcoming"), ("all", "All"),
                      ("completed", "Done"), ("trash", "Trash")):
        b = tk.Button(vrow, text=lbl, command=lambda n=name: set_view(n), bg="#2a2f3a", fg=MUT,
                      relief="flat", font=("Segoe UI", 9, "bold"), cursor="hand2")
        b.pack(side="left", padx=2); vbtns[name] = b

    # busqueda + lista-filtro
    frow = tk.Frame(left, bg=BG); frow.pack(fill="x", pady=(2, 2))
    search = tk.Entry(frow, bg=PANEL, fg=FG, insertbackground=FG, relief="flat", font=("Segoe UI", 10))
    search.pack(side="left", fill="x", expand=True, ipady=3)
    search.bind("<KeyRelease>", lambda e: refresh())
    list_cb = ttk.Combobox(frow, width=12, state="readonly")
    list_cb.pack(side="left", padx=(4, 0))
    list_cb.bind("<<ComboboxSelected>>", lambda e: refresh())

    # lista
    cols = ("due", "prio", "st")
    tree = ttk.Treeview(left, columns=cols, show="tree headings", selectmode="browse")
    tree.heading("#0", text="Task"); tree.column("#0", width=260)
    tree.heading("due", text="Due"); tree.column("due", width=110, anchor="center")
    tree.heading("prio", text="Priority"); tree.column("prio", width=70, anchor="center")
    tree.heading("st", text="State"); tree.column("st", width=90, anchor="center")
    tree.pack(fill="both", expand=True, pady=(4, 2))
    for v, hx in PRIO_HEX.items():
        tree.tag_configure(v, foreground=hx)
    count_lbl = tk.Label(left, text="", bg=BG, fg=MUT, font=("Segoe UI", 9)); count_lbl.pack(anchor="w")

    # ================= DERECHA (editor) =================
    right = tk.Frame(root, bg=BG, width=370); right.pack(side="left", fill="y", padx=(5, 10), pady=10)
    right.pack_propagate(False)

    def _lab(txt):
        tk.Label(right, text=txt, bg=BG, fg=MUT, font=("Segoe UI", 9)).pack(anchor="w", pady=(4, 0))

    _lab("Title")
    e_title = tk.Entry(right, bg=PANEL, fg=FG, insertbackground=FG, relief="flat", font=("Segoe UI", 11))
    e_title.pack(fill="x", ipady=3)
    _lab("Description")
    e_desc = tk.Text(right, bg=PANEL, fg=FG, insertbackground=FG, relief="flat", font=("Segoe UI", 10), height=3, wrap="word")
    e_desc.pack(fill="x")

    v_due = tk.BooleanVar()
    duehdr = tk.Frame(right, bg=BG); duehdr.pack(fill="x", pady=(4, 0))
    tk.Checkbutton(duehdr, text="Deadline", variable=v_due, bg=BG, fg=MUT, selectcolor=PANEL,
                   activebackground=BG, activeforeground=FG, font=("Segoe UI", 9),
                   command=lambda: _due_toggle()).pack(side="left")
    dtrow = tk.Frame(right, bg=BG); dtrow.pack(fill="x")
    now = dt.datetime.now()
    cb_m = ttk.Combobox(dtrow, width=3, state="readonly", values=[f"{i:02d}" for i in range(1, 13)])
    cb_d = ttk.Combobox(dtrow, width=3, state="readonly", values=[f"{i:02d}" for i in range(1, 32)])
    cb_y = ttk.Combobox(dtrow, width=5, state="readonly", values=[str(now.year + i) for i in range(0, 3)])
    cb_h = ttk.Combobox(dtrow, width=3, state="readonly", values=[str(i) for i in range(1, 13)])
    cb_min = ttk.Combobox(dtrow, width=3, state="readonly", values=[f"{i:02d}" for i in range(60)])
    cb_ap = ttk.Combobox(dtrow, width=3, state="readonly", values=["AM", "PM"])
    for w in (cb_m, cb_d, cb_y, cb_h, cb_min, cb_ap):
        w.pack(side="left", padx=1)

    def _due_toggle():
        st = "readonly" if v_due.get() else "disabled"
        for w in (cb_m, cb_d, cb_y, cb_h, cb_min, cb_ap):
            w.config(state=st)

    r1 = tk.Frame(right, bg=BG); r1.pack(fill="x", pady=(4, 0))
    tk.Label(r1, text="Priority", bg=BG, fg=MUT, font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w")
    cb_pr = ttk.Combobox(r1, width=11, state="readonly", values=[d for d, _v in PRIO]); cb_pr.grid(row=1, column=0, padx=(0, 6))
    tk.Label(r1, text="State", bg=BG, fg=MUT, font=("Segoe UI", 9)).grid(row=0, column=1, sticky="w")
    cb_st = ttk.Combobox(r1, width=12, state="readonly", values=[d for d, _v in STATE]); cb_st.grid(row=1, column=1)

    r2 = tk.Frame(right, bg=BG); r2.pack(fill="x", pady=(4, 0))
    tk.Label(r2, text="List / project", bg=BG, fg=MUT, font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w")
    cb_list = ttk.Combobox(r2, width=13); cb_list.grid(row=1, column=0, padx=(0, 6))
    tk.Label(r2, text="Category", bg=BG, fg=MUT, font=("Segoe UI", 9)).grid(row=0, column=1, sticky="w")
    e_cat = tk.Entry(r2, width=13, bg=PANEL, fg=FG, insertbackground=FG, relief="flat", font=("Segoe UI", 10)); e_cat.grid(row=1, column=1)

    _lab("Repeat")
    cb_rec = ttk.Combobox(right, state="readonly", values=[d for d, _v in RECUR]); cb_rec.pack(fill="x")

    # subtareas
    _lab("Subtasks (double-click to toggle)")
    subwrap = tk.Frame(right, bg=PANEL); subwrap.pack(fill="x")
    sub_sb = ttk.Scrollbar(subwrap, orient="vertical")
    sub_box = tk.Listbox(subwrap, bg=PANEL, fg=FG, selectbackground=ACC, selectforeground="white",
                         borderwidth=0, highlightthickness=0, font=("Segoe UI", 10), height=4,
                         activestyle="none", yscrollcommand=sub_sb.set)
    sub_sb.config(command=sub_box.yview)
    sub_sb.pack(side="right", fill="y")
    sub_box.pack(side="left", fill="both", expand=True)
    subs = []

    def _sub_refresh():
        sub_box.delete(0, "end")
        for s in subs:
            sub_box.insert("end", ("☑ " if s.get("done") else "☐ ") + s.get("text", ""))

    def sub_add():
        txt = sube.get().strip()
        if txt:
            subs.append({"text": txt, "done": False}); sube.delete(0, "end"); _sub_refresh()

    def sub_toggle(_e=None):
        i = sub_box.curselection()
        if i:
            subs[i[0]]["done"] = not subs[i[0]].get("done"); _sub_refresh()
    sub_box.bind("<Double-1>", sub_toggle)

    def sub_del():
        i = sub_box.curselection()
        if i:
            del subs[i[0]]; _sub_refresh()
    subr = tk.Frame(right, bg=BG); subr.pack(fill="x", pady=(2, 0))
    sube = tk.Entry(subr, bg=PANEL, fg=FG, insertbackground=FG, relief="flat", font=("Segoe UI", 10))
    sube.pack(side="left", fill="x", expand=True, ipady=2)
    sube.bind("<Return>", lambda e: sub_add())
    tk.Button(subr, text="+", command=sub_add, bg="#2a2f3a", fg=FG, relief="flat", width=2,
              font=("Segoe UI", 10, "bold"), cursor="hand2").pack(side="left", padx=2)
    tk.Button(subr, text="–", command=sub_del, bg="#2a2f3a", fg=FG, relief="flat", width=2,
              font=("Segoe UI", 10, "bold"), cursor="hand2").pack(side="left")

    # botones
    def set_dt(d):
        cb_m.set(f"{d.month:02d}"); cb_d.set(f"{d.day:02d}"); cb_y.set(str(d.year))
        cb_h.set(str(d.hour % 12 or 12)); cb_min.set(f"{d.minute:02d}"); cb_ap.set("PM" if d.hour >= 12 else "AM")

    def get_due():
        if not v_due.get():
            return None
        try:
            h = int(cb_h.get())
            if cb_ap.get() == "PM" and h != 12:
                h += 12
            if cb_ap.get() == "AM" and h == 12:
                h = 0
            return dt.datetime(int(cb_y.get()), int(cb_m.get()), int(cb_d.get()), h, int(cb_min.get())).isoformat()
        except Exception:
            return None

    def clear_form():
        sel["id"] = None
        e_title.delete(0, "end"); e_desc.delete("1.0", "end"); e_cat.delete(0, "end")
        v_due.set(False); _due_toggle(); set_dt(dt.datetime.now() + dt.timedelta(hours=1))
        cb_pr.set("Normal"); cb_st.set("Pending"); cb_rec.set("No repeat"); cb_list.set("Inbox")
        subs.clear(); _sub_refresh()

    def _cur():
        return next((t for t in store.get("tasks", []) if t.get("id") == sel["id"]), None) \
            or next((t for t in store.get("trash", []) if t.get("id") == sel["id"]), None)

    def load_form(t):
        sel["id"] = t.get("id")
        e_title.delete(0, "end"); e_title.insert(0, t.get("title", ""))
        e_desc.delete("1.0", "end"); e_desc.insert("1.0", t.get("desc", ""))
        e_cat.delete(0, "end"); e_cat.insert(0, t.get("category", ""))
        d = TD.parse_due(t.get("due"))
        v_due.set(d is not None); _due_toggle()
        set_dt(d or (dt.datetime.now() + dt.timedelta(hours=1)))
        cb_pr.set(next((x for x, v in PRIO if v == t.get("priority", "normal")), "Normal"))
        cb_st.set(next((x for x, v in STATE if v == t.get("state", "pending")), "Pending"))
        cb_rec.set(next((x for x, v in RECUR if v == t.get("recurring", "none")), "No repeat"))
        cb_list.set(t.get("list", "Inbox"))
        subs.clear(); subs.extend({"text": s.get("text", ""), "done": bool(s.get("done"))} for s in t.get("subtasks", []))
        _sub_refresh()

    def save():
        t = _cur()
        if t is None or sel["id"] is None:
            t = {"id": TD.new_id(), "created": dt.datetime.now().isoformat(), "completed_at": None}
            store.setdefault("tasks", []).append(t)
        t.update({"title": e_title.get().strip() or "Task", "desc": e_desc.get("1.0", "end-1c").strip(),
                  "due": get_due(), "priority": next((v for d, v in PRIO if d == cb_pr.get()), "normal"),
                  "state": next((v for d, v in STATE if d == cb_st.get()), "pending"),
                  "recurring": next((v for d, v in RECUR if d == cb_rec.get()), "none"),
                  "list": (cb_list.get().strip() or "Inbox"), "category": e_cat.get().strip(),
                  "subtasks": [dict(s) for s in subs]})
        TD.save_store(store); refresh(); clear_form()

    def complete():
        t = _cur()
        if t and t in store.get("tasks", []):
            TD.complete_task(store, t); TD.save_store(store); refresh(); clear_form()

    def delete():
        t = _cur()
        if not t:
            return
        if view["name"] == "trash":
            if messagebox.askyesno("Delete forever", f"Permanently delete “{t.get('title')}”?", parent=root, icon="warning", default="no"):
                store["trash"] = [x for x in store.get("trash", []) if x.get("id") != t.get("id")]
                TD.save_store(store); refresh(); clear_form()
        else:
            TD.to_trash(store, t); TD.save_store(store); refresh(); clear_form()

    def restore():
        t = _cur()
        if t and view["name"] == "trash":
            TD.restore(store, t.get("id")); TD.save_store(store); refresh(); clear_form()

    brow = tk.Frame(right, bg=BG); brow.pack(fill="x", pady=(8, 2))
    tk.Button(brow, text="New", command=clear_form, bg="#2a2f3a", fg=FG, relief="flat",
              font=("Segoe UI", 10, "bold"), cursor="hand2").pack(side="left", padx=2)
    tk.Button(brow, text="Save", command=save, bg=ACC, fg="white", relief="flat",
              font=("Segoe UI", 10, "bold"), cursor="hand2").pack(side="left", padx=2)
    tk.Button(brow, text="Complete", command=complete, bg="#2a6b4a", fg="white", relief="flat",
              font=("Segoe UI", 10, "bold"), cursor="hand2").pack(side="left", padx=2)
    tk.Button(brow, text="Restore", command=restore, bg="#2a3f5a", fg="white", relief="flat",
              font=("Segoe UI", 10, "bold"), cursor="hand2").pack(side="left", padx=2)
    tk.Button(brow, text="Delete", command=delete, bg="#5a2a36", fg="white", relief="flat",
              font=("Segoe UI", 10, "bold"), cursor="hand2").pack(side="left", padx=2)

    # ================= refresco =================
    def on_select(_e=None):
        s = tree.selection()
        if s:
            allt = store.get("tasks", []) + store.get("trash", [])
            t = next((x for x in allt if x.get("id") == s[0]), None)
            if t:
                load_form(t)
    tree.bind("<<TreeviewSelect>>", on_select)

    def refresh():
        nonlocal store
        store = TD.load_store()
        ls = TD.lists(store)
        list_cb.configure(values=["(all)"] + ls)
        if list_cb.get() not in (["(all)"] + ls):
            list_cb.set("(all)")
        tree.delete(*tree.get_children())
        if view["name"] == "trash":
            items = store.get("trash", [])
        else:
            lf = None if list_cb.get() in ("", "(all)") else list_cb.get()
            items = TD.get_view(store, view["name"], search.get(), lf)
        for t in items:
            d = TD.parse_due(t.get("due"))
            tree.insert("", "end", iid=t.get("id"),
                        text=("✔ " if t.get("state") == "completed" else "") + (t.get("title") or "")[:34],
                        values=(d.strftime("%m/%d %H:%M") if d else "",
                                t.get("priority", "normal"),
                                t.get("state", "pending").replace("_", " ")),
                        tags=(t.get("priority", "normal"),))
        pend = TD.pending_count(store); today = TD.today_count(store)
        count_lbl.config(text=f"{today} today · {pend} pending · {len(store.get('trash', []))} in trash")

    set_view("today"); clear_form()
    try:
        root.lift(); root.focus_force(); q_entry.focus_set()
    except Exception:
        pass
    root.mainloop()


def main(argv=None):
    if TD is None:
        import tkinter as tk
        r = tk.Tk(); r.configure(bg=BG)
        tk.Label(r, text="todos module not available", bg=BG, fg="#ff8a8a").pack(padx=20, pady=20)
        r.mainloop(); return
    run()


if __name__ == "__main__":
    main(sys.argv)
