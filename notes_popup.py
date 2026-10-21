# -*- coding: utf-8 -*-
"""
Ventana de notas (categoria Practical "Calendar Notes").

Proceso independiente que el servidor lanza al pulsar una tecla Calendar Notes.
Gestor de notas libres: lista de notas (titulo + texto), crear/editar/borrar.
Se guardan en el JSON cuyo ruta se pasa como argumento.

Uso:  python notes_popup.py <ruta_notes.json>
Empaquetado:  StreamDockM18.exe --notes-popup <ruta_notes.json>

Formato del archivo:  [{"title": "...", "text": "..."}, ...]
"""

import json
import os
import sys


def _load(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return [{"title": str(n.get("title", "")), "text": str(n.get("text", ""))}
                    for n in data if isinstance(n, dict)]
    except Exception:
        pass
    return []


def _save(path, notes):
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(notes, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
        return True
    except Exception as e:
        print("[notes] save:", e)
        return False


def run_notes(path):
    import tkinter as tk

    notes = _load(path)
    state = {"cur": 0 if notes else None}

    root = tk.Tk()
    root.title("Stream Dock M18 — Notes")
    root.configure(bg="#14161c")
    root.attributes("-topmost", True)
    W, H = 600, 440
    sw = root.winfo_screenwidth(); sh = root.winfo_screenheight()
    root.geometry(f"{W}x{H}+{(sw - W) // 2}+{(sh - H) // 3}")
    root.minsize(480, 320)

    FG = "#e6e6e6"; BG = "#14161c"; PANEL = "#1b1e26"; ACC = "#2d6cdf"

    # --- panel izquierdo: lista + New/Delete ---
    left = tk.Frame(root, bg=BG)
    left.pack(side="left", fill="y", padx=(10, 6), pady=10)
    tk.Label(left, text="Notes", bg=BG, fg="#9fb4d6", font=("Segoe UI", 10, "bold")).pack(anchor="w")
    listbox = tk.Listbox(left, width=22, height=16, bg=PANEL, fg=FG,
                         selectbackground=ACC, selectforeground="white",
                         borderwidth=0, highlightthickness=0, activestyle="none",
                         font=("Segoe UI", 10))
    listbox.pack(fill="y", expand=True, pady=4)
    btns = tk.Frame(left, bg=BG); btns.pack(fill="x")

    # --- panel derecho: titulo + texto ---
    right = tk.Frame(root, bg=BG)
    right.pack(side="left", fill="both", expand=True, padx=(6, 10), pady=10)
    tk.Label(right, text="Title", bg=BG, fg="#9fb4d6", font=("Segoe UI", 10)).pack(anchor="w")
    title_var = tk.StringVar()
    title_entry = tk.Entry(right, textvariable=title_var, bg=PANEL, fg=FG,
                           insertbackground=FG, borderwidth=0, font=("Segoe UI", 11))
    title_entry.pack(fill="x", ipady=5, pady=(2, 8))
    tk.Label(right, text="Note", bg=BG, fg="#9fb4d6", font=("Segoe UI", 10)).pack(anchor="w")
    text = tk.Text(right, bg=PANEL, fg=FG, insertbackground=FG, borderwidth=0,
                   font=("Segoe UI", 11), wrap="word", height=10)
    text.pack(fill="both", expand=True, pady=(2, 8))
    status = tk.Label(right, text="", bg=BG, fg="#6fcf97", font=("Segoe UI", 9))
    status.pack(anchor="w")

    def refresh_list(select=None):
        listbox.delete(0, "end")
        for n in notes:
            listbox.insert("end", (n["title"] or "(untitled)")[:28])
        if select is not None and 0 <= select < len(notes):
            listbox.selection_clear(0, "end")
            listbox.selection_set(select)
            listbox.see(select)

    def load_cur():
        i = state["cur"]
        if i is None or not (0 <= i < len(notes)):
            title_var.set(""); text.delete("1.0", "end")
            return
        title_var.set(notes[i]["title"])
        text.delete("1.0", "end"); text.insert("1.0", notes[i]["text"])

    def commit():
        i = state["cur"]
        if i is not None and 0 <= i < len(notes):
            notes[i]["title"] = title_var.get()
            notes[i]["text"] = text.get("1.0", "end-1c")

    def on_select(_e=None):
        sel = listbox.curselection()
        if not sel:
            return
        commit()
        state["cur"] = sel[0]
        load_cur()
        # reflejar titulo editado en la lista
        refresh_list(select=state["cur"])

    def new_note(_e=None):
        commit()
        notes.append({"title": "New note", "text": ""})
        state["cur"] = len(notes) - 1
        refresh_list(select=state["cur"]); load_cur()
        title_entry.focus_set(); title_entry.select_range(0, "end")

    def del_note(_e=None):
        i = state["cur"]
        if i is None or not (0 <= i < len(notes)):
            return
        from tkinter import messagebox
        title = (notes[i]["title"] or "(untitled)")[:40]
        if not messagebox.askyesno("Delete note", f"Delete “{title}”?",
                                    parent=root, icon="warning", default="no"):
            return
        del notes[i]
        state["cur"] = min(i, len(notes) - 1) if notes else None
        refresh_list(select=state["cur"]); load_cur()
        _save(path, notes)   # persistir el borrado de inmediato

    def save(_e=None):
        commit()
        refresh_list(select=state["cur"])
        if _save(path, notes):
            status.config(text="Saved")
            root.after(1500, lambda: status.config(text=""))

    def on_close():
        save()
        root.destroy()

    tk.Button(btns, text="New", command=new_note, bg=ACC, fg="white", relief="flat",
              activebackground="#2559b8", activeforeground="white",
              font=("Segoe UI", 10, "bold"), cursor="hand2").pack(side="left", padx=(0, 4))
    tk.Button(btns, text="Delete", command=del_note, bg="#3a2330", fg="#ff8a8a", relief="flat",
              activebackground="#512a3a", activeforeground="#ffb0b0",
              font=("Segoe UI", 10), cursor="hand2").pack(side="left")
    tk.Button(right, text="Save", command=save, bg=ACC, fg="white", relief="flat",
              activebackground="#2559b8", activeforeground="white",
              font=("Segoe UI", 11, "bold"), width=12, cursor="hand2").pack(anchor="e")

    listbox.bind("<<ListboxSelect>>", on_select)
    root.protocol("WM_DELETE_WINDOW", on_close)
    root.bind("<Control-s>", save)
    root.bind("<Control-n>", new_note)

    refresh_list(select=state["cur"])
    load_cur()
    try:
        root.lift(); root.focus_force()
    except Exception:
        pass
    root.mainloop()


def main(argv=None):
    argv = argv if argv is not None else sys.argv
    args = [a for a in argv[1:] if not a.startswith("--")]
    path = args[-1] if args else os.path.join(os.path.expanduser("~"), "m18_notes.json")
    run_notes(path)


if __name__ == "__main__":
    main(sys.argv)
