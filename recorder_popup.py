# -*- coding: utf-8 -*-
"""
Ventana del grabador de audio (categoria Practical "Recorder").

Controles grandes (Record/Pause/Resume/Stop), selector de microfono, medidor de
nivel SIEMPRE activo (para ver que el mic funciona), formato y calidad
(recordados), lista de grabaciones con fecha/duracion/tamaño (doble clic para
reproducir) y reproductor con barra de progreso y Play/Pause/Stop.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from streamdock_m18 import recorder as R
except Exception as e:  # noqa
    R = None
    _imp_err = e


def _fmt_size(n):
    n = float(n)
    for unit in ("B", "KB", "MB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def _fmt_time(sec):
    sec = int(sec or 0)
    return f"{sec // 60:02d}:{sec % 60:02d}"


def _fmt_date(mtime):
    try:
        import datetime
        return datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ""


def run(kind=""):
    import tkinter as tk
    from tkinter import ttk, messagebox

    BG = "#14161c"; PANEL = "#1b1e26"; FG = "#e6e6e6"; MUT = "#9fb4d6"; ACC = "#2d6cdf"
    if R is None:
        root = tk.Tk(); root.configure(bg=BG)
        tk.Label(root, text="sounddevice / soundfile no disponibles", bg=BG, fg="#ff8a8a",
                 font=("Segoe UI", 12)).pack(pady=40)
        root.mainloop(); return

    rec = R.Recorder()
    monitor = R.Monitor()
    player = R.Player()
    try:
        R.recover_orphans(kind)
    except Exception:
        pass
    settings = R.load_settings()

    _klabel = {"hold": "Hold and Record", "long": "Long Recorder"}.get(kind, "")
    root = tk.Tk()
    root.title("Stream Dock M18 — Recorder" + (f" · {_klabel}" if _klabel else ""))
    root.configure(bg=BG)
    root.attributes("-topmost", True)
    W, H = 600, 740
    sw = root.winfo_screenwidth(); sh = root.winfo_screenheight()
    root.geometry(f"{W}x{H}+{(sw - W) // 2}+{max(10, (sh - H) // 6)}")
    root.minsize(540, 680)

    from tkinter import font as tkfont
    tv_font = tkfont.Font(family="Segoe UI", size=10)
    row_h = tv_font.metrics("linespace") + 8   # escala con la DPI (evita filas encimadas)
    style = ttk.Style()
    try:
        style.theme_use("clam")
        style.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=FG,
                        rowheight=row_h, borderwidth=0, font=tv_font)
        style.configure("Treeview.Heading", background="#232733", foreground=MUT, borderwidth=0)
        style.map("Treeview", background=[("selected", ACC)], foreground=[("selected", "white")])
        style.configure("TScale", background=BG)
    except Exception:
        pass

    # --- fila superior: microfono / formato / calidad (recordados) ---
    top = tk.Frame(root, bg=BG); top.pack(fill="x", padx=12, pady=(12, 2))
    tk.Label(top, text="Microphone", bg=BG, fg=MUT, font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w")
    mics = R.list_inputs()
    mic_cb = ttk.Combobox(top, width=34, state="readonly", values=(mics or ["(default)"]))
    mic_cb.set(settings.get("device") if settings.get("device") in mics else (mics[0] if mics else "(default)"))
    mic_cb.grid(row=1, column=0, padx=(0, 10), pady=(0, 2), sticky="w")
    tk.Label(top, text="Format", bg=BG, fg=MUT, font=("Segoe UI", 9)).grid(row=0, column=1, sticky="w")
    fmt_cb = ttk.Combobox(top, width=7, state="readonly", values=["mp3", "wav", "flac"])
    fmt_cb.set(settings.get("format", "mp3")); fmt_cb.grid(row=1, column=1, padx=(0, 10), sticky="w")
    tk.Label(top, text="Quality", bg=BG, fg=MUT, font=("Segoe UI", 9)).grid(row=0, column=2, sticky="w")
    q_cb = ttk.Combobox(top, width=8, state="readonly", values=["high", "medium", "low"])
    q_cb.set(settings.get("quality", "medium")); q_cb.grid(row=1, column=2, sticky="w")

    def save_settings(*_a):
        try:
            v = int(vol.get())
        except Exception:
            v = 100
        try:
            g = int(mic_gain.get())
        except Exception:
            g = 100
        R.save_settings({"device": (mic_cb.get() if mic_cb.get() != "(default)" else ""),
                         "format": fmt_cb.get(), "quality": q_cb.get(), "volume": v, "gain": g})

    def on_mic(*_a):
        save_settings()
        if not rec.is_recording():
            monitor.start(mic_cb.get() if mic_cb.get() != "(default)" else "")
    mic_cb.bind("<<ComboboxSelected>>", on_mic)
    fmt_cb.bind("<<ComboboxSelected>>", save_settings)
    q_cb.bind("<<ComboboxSelected>>", save_settings)

    # --- medidor de nivel (SIEMPRE activo) ---
    tk.Label(root, text="Input level", bg=BG, fg=MUT, font=("Segoe UI", 9)).pack(anchor="w", padx=14, pady=(4, 0))
    canvas = tk.Canvas(root, height=20, bg=PANEL, highlightthickness=0)
    canvas.pack(fill="x", padx=12)
    warn_lbl = tk.Label(root, text="", bg=BG, fg="#e6b800", font=("Segoe UI", 9, "bold"))
    warn_lbl.pack(anchor="w", padx=14)

    # --- ganancia del microfono (Mic) ---
    microw = tk.Frame(root, bg=BG); microw.pack(fill="x", padx=12, pady=(1, 2))
    tk.Label(microw, text="🎤 Mic", bg=BG, fg=MUT, font=("Segoe UI", 9)).pack(side="left")

    def on_gain(_v=None):
        g = mic_gain.get() / 100.0
        rec.set_gain(g); monitor.set_gain(g)
        mic_lbl.config(text=f"{int(mic_gain.get())}%")
    mic_gain = ttk.Scale(microw, from_=0, to=300, orient="horizontal")
    mic_gain.pack(side="left", fill="x", expand=True, padx=8)
    mic_lbl = tk.Label(microw, text="100%", bg=BG, fg=MUT, font=("Consolas", 9), width=5)
    mic_lbl.pack(side="right")
    mic_gain.configure(command=on_gain)
    mic_gain.set(int(settings.get("gain", 100)))
    mic_gain.bind("<ButtonRelease-1>", save_settings)

    # --- tiempo + estado ---
    time_lbl = tk.Label(root, text="00:00", bg=BG, fg=FG, font=("Consolas", 22, "bold"))
    time_lbl.pack(pady=(2, 0))
    state_lbl = tk.Label(root, text="Ready", bg=BG, fg=MUT, font=("Segoe UI", 10))
    state_lbl.pack()

    # --- controles de grabacion ---
    ctrl = tk.Frame(root, bg=BG); ctrl.pack(pady=6)

    def big(parent, txt, cmd, color):
        return tk.Button(parent, text=txt, command=cmd, bg=color, fg="white", relief="flat",
                         activebackground=color, activeforeground="white", width=9, height=2,
                         font=("Segoe UI", 11, "bold"), cursor="hand2")

    def do_record():
        if rec.is_recording():
            return
        monitor.stop()
        rec.start(folder=R.recordings_dir(kind),
                  device=(mic_cb.get() if mic_cb.get() != "(default)" else ""),
                  fmt=fmt_cb.get(), quality=q_cb.get(), channels=1, samplerate=44100)
        rec.set_gain(mic_gain.get() / 100.0)
        _sync_rec()

    def do_pause():
        rec.pause(); _sync_rec()

    def do_resume():
        rec.resume(); _sync_rec()

    def do_stop_rec():
        rec.stop(); _sync_rec(); refresh_list()
        monitor.start(mic_cb.get() if mic_cb.get() != "(default)" else "")

    rec_btn = big(ctrl, "● Record", do_record, "#c0392b")
    pause_btn = big(ctrl, "⏸ Pause", do_pause, "#6b5b2a")
    resume_btn = big(ctrl, "▶ Resume", do_resume, "#2a6b4a")
    stoprec_btn = big(ctrl, "■ Stop", do_stop_rec, "#3a3f4a")
    for i, b in enumerate((rec_btn, pause_btn, resume_btn, stoprec_btn)):
        b.grid(row=0, column=i, padx=4)

    def _sync_rec():
        recing = rec.is_recording(); paused = rec.is_paused()
        rec_btn.config(state="disabled" if recing else "normal")
        pause_btn.config(state="normal" if (recing and not paused) else "disabled")
        resume_btn.config(state="normal" if (recing and paused) else "disabled")
        stoprec_btn.config(state="normal" if recing else "disabled")
        state_lbl.config(text=("Paused" if paused else "Recording…") if recing else "Ready",
                         fg=("#e6b800" if paused else "#ff6b6b") if recing else MUT)

    # --- lista de grabaciones (grid) ---
    rec_hdr = tk.Frame(root, bg=BG); rec_hdr.pack(fill="x", padx=12, pady=(4, 0))
    tk.Label(rec_hdr, text="Recordings", bg=BG, fg=MUT, font=("Segoe UI", 9, "bold")).pack(side="left")
    tk.Button(rec_hdr, text="Deselect", command=lambda: tree.selection_remove(*tree.selection()),
              bg="#2a2f3a", fg=FG, relief="flat", font=("Segoe UI", 8), cursor="hand2",
              padx=6).pack(side="right", padx=(4, 0))
    tk.Button(rec_hdr, text="Select all", command=lambda: tree.selection_set(tree.get_children()),
              bg="#2a2f3a", fg=FG, relief="flat", font=("Segoe UI", 8), cursor="hand2",
              padx=6).pack(side="right")
    cols = ("date", "dur", "size")
    tree = ttk.Treeview(root, columns=cols, show="tree headings", height=7, selectmode="extended")
    tree.heading("#0", text="Name"); tree.column("#0", width=250, anchor="w")
    tree.heading("date", text="Recorded"); tree.column("date", width=130, anchor="center")
    tree.heading("dur", text="Length"); tree.column("dur", width=70, anchor="center")
    tree.heading("size", text="Size"); tree.column("size", width=70, anchor="e")
    tree.pack(fill="both", expand=True, padx=12, pady=(2, 4))
    recs = []

    def refresh_list():
        nonlocal recs
        recs = R.list_recordings(kind)
        tree.delete(*tree.get_children())
        for i, r in enumerate(recs):
            tree.insert("", "end", iid=str(i), text=r["name"],
                        values=(_fmt_date(r["mtime"]), _fmt_time(r["duration"]), _fmt_size(r["size"])))

    def _sel():
        s = tree.selection()
        if s and s[0].isdigit() and int(s[0]) < len(recs):
            return recs[int(s[0])]
        return None

    # --- barra de reproduccion + controles ---
    pbar_wrap = tk.Frame(root, bg=BG); pbar_wrap.pack(fill="x", padx=12, pady=(0, 2))
    pos_lbl = tk.Label(pbar_wrap, text="00:00 / 00:00", bg=BG, fg=MUT, font=("Consolas", 9))
    pos_lbl.pack(side="right")
    seek = {"drag": False, "dur": 0.0}
    pbar = ttk.Scale(pbar_wrap, from_=0, to=100, orient="horizontal")
    pbar.pack(side="left", fill="x", expand=True, padx=(0, 8))

    def on_seek_press(_e):
        seek["drag"] = True

    def on_seek_release(_e):
        if player.is_active():
            player.seek(float(pbar.get()))   # reproduciendo/pausado -> saltar en vivo
        else:   # parado -> recordar el punto; se usa al pulsar Play
            pos_lbl.config(text=f"{_fmt_time(float(pbar.get()))} / {_fmt_time(seek['dur'])}")
        seek["drag"] = False

    def on_pbar_cmd(_v):
        if seek["drag"]:   # mostrar la posicion mientras se arrastra el indicador
            pos_lbl.config(text=f"{_fmt_time(float(pbar.get()))} / {_fmt_time(seek['dur'])}")
    pbar.configure(command=on_pbar_cmd)
    pbar.bind("<Button-1>", on_seek_press)
    pbar.bind("<ButtonRelease-1>", on_seek_release)

    pstate = {"ended": False}

    def update_play_btn():
        playing = player.is_started() and not player.finished()
        if playing and not player.is_paused():
            play_btn.config(text="⏸ Pause"); stopplay_btn.config(state="normal")
        elif playing and player.is_paused():
            play_btn.config(text="▶ Resume"); stopplay_btn.config(state="normal")
        else:   # idle o terminado
            play_btn.config(text="▶ Play"); stopplay_btn.config(state="disabled")

    def _start_selected(from_start=False):
        r = _sel()
        if r:
            seek["dur"] = r["duration"]
            pbar.configure(to=max(1.0, r["duration"]))
            pstate["ended"] = False
            startpos = 0.0 if from_start else float(pbar.get())
            player.play(r["path"])
            player.set_volume(vol.get() / 100.0)
            if 0 < startpos < r["duration"]:
                player.seek(startpos)   # empezar desde donde esta el indicador

    def on_tree_select(_e=None):
        # al elegir una grabacion (sin reproducir), cargar su duracion en la barra
        r = _sel()
        if r and not (player.is_started() and not player.finished()):
            seek["dur"] = r["duration"]
            pbar.configure(to=max(1.0, r["duration"]))
            pbar.set(0); pstate["ended"] = False
            pos_lbl.config(text=f"00:00 / {_fmt_time(r['duration'])}")
    tree.bind("<<TreeviewSelect>>", on_tree_select)

    def play_pause():
        if player.is_started() and not player.finished():
            player.resume() if player.is_paused() else player.pause()
        else:   # idle o terminado -> empezar desde el principio
            _start_selected()
        update_play_btn()

    def stop_play():
        player.stop(); pbar.set(0); pstate["ended"] = False; update_play_btn()
        pos_lbl.config(text=f"00:00 / {_fmt_time(seek['dur'])}")

    def on_dbl(_e):
        pbar.set(0); _start_selected(from_start=True); update_play_btn()
    tree.bind("<Double-1>", on_dbl)

    def do_rename():
        r = _sel()
        if not r:
            return
        from tkinter import simpledialog
        cur = os.path.splitext(r["name"])[0]
        new = simpledialog.askstring("Rename", "New name:", initialvalue=cur, parent=root)
        if new is None or not new.strip():
            return
        if player.is_started():
            player.stop(); update_play_btn()
        R.rename_recording(r["path"], new.strip())
        refresh_list()

    def _sel_all():
        out = []
        for iid in tree.selection():
            if iid.isdigit() and int(iid) < len(recs):
                out.append(recs[int(iid)])
        return out

    def do_delete():
        items = _sel_all()
        if not items:
            return
        msg = (f"Delete “{items[0]['name']}”?" if len(items) == 1
               else f"Delete {len(items)} recordings?")
        if messagebox.askyesno("Delete recordings", msg, parent=root, icon="warning", default="no"):
            if player.is_started():
                player.stop(); update_play_btn()
            for r in items:
                R.delete_recording(r["path"])
            refresh_list()

    def do_folder():
        try:
            os.startfile(R.recordings_dir(kind))
        except Exception:
            pass

    # --- volumen de reproduccion ---
    volrow = tk.Frame(root, bg=BG); volrow.pack(fill="x", padx=12, pady=(0, 2))
    tk.Label(volrow, text="🔊 Volume", bg=BG, fg=MUT, font=("Segoe UI", 9)).pack(side="left")

    def on_vol(_v=None):
        player.set_volume(vol.get() / 100.0)
        vol_lbl.config(text=f"{int(vol.get())}%")
    vol = ttk.Scale(volrow, from_=0, to=150, orient="horizontal")
    vol.pack(side="left", fill="x", expand=True, padx=8)
    vol_lbl = tk.Label(volrow, text="100%", bg=BG, fg=MUT, font=("Consolas", 9), width=5)
    vol_lbl.pack(side="right")
    vol.configure(command=on_vol)
    vol.set(int(settings.get("volume", 100)))   # dispara on_vol con vol_lbl ya creado
    vol.bind("<ButtonRelease-1>", save_settings)

    pbtns = tk.Frame(root, bg=BG); pbtns.pack(fill="x", padx=12, pady=(0, 10))
    play_btn = tk.Button(pbtns, text="▶ Play", command=play_pause, bg=ACC, fg="white", relief="flat",
                         activebackground=ACC, activeforeground="white", width=9,
                         font=("Segoe UI", 10, "bold"), cursor="hand2")
    play_btn.pack(side="left", padx=3)
    stopplay_btn = tk.Button(pbtns, text="■ Stop", command=stop_play, bg="#3a3f4a", fg="white", relief="flat",
                             activebackground="#3a3f4a", activeforeground="white", width=7,
                             font=("Segoe UI", 10, "bold"), cursor="hand2", state="disabled")
    stopplay_btn.pack(side="left", padx=3)
    tk.Button(pbtns, text="Rename", command=do_rename, bg="#2a3f5a", fg="white", relief="flat",
              font=("Segoe UI", 10, "bold"), cursor="hand2").pack(side="left", padx=3)
    tk.Button(pbtns, text="Delete", command=do_delete, bg="#5a2a36", fg="white", relief="flat",
              font=("Segoe UI", 10, "bold"), cursor="hand2").pack(side="left", padx=3)
    tk.Button(pbtns, text="Folder", command=do_folder, bg="#2a2f3a", fg="white", relief="flat",
              font=("Segoe UI", 10), cursor="hand2").pack(side="left", padx=3)
    tk.Button(pbtns, text="Refresh", command=refresh_list, bg="#2a2f3a", fg=FG, relief="flat",
              font=("Segoe UI", 10), cursor="hand2").pack(side="right", padx=3)

    # mover la barra de progreso DEBAJO de los botones de reproduccion
    pbar_wrap.pack_forget()
    pbar_wrap.pack(fill="x", padx=12, pady=(2, 10))

    # --- liberar el microfono cuando la ventana esta en segundo plano ---------
    # (asi la tecla "Long Recorder" puede grabar aunque esta ventana siga abierta;
    #  el medidor de nivel solo necesita el mic mientras la ventana esta activa)
    def _mic_name():
        return mic_cb.get() if mic_cb.get() != "(default)" else ""

    _fg = {"check": None}
    try:
        import ctypes as _ct
        _u32 = _ct.windll.user32
        _u32.GetForegroundWindow.restype = _ct.c_void_p
        _u32.GetWindowThreadProcessId.argtypes = (_ct.c_void_p, _ct.POINTER(_ct.c_ulong))
        _our_pid = os.getpid()

        def _app_is_foreground():
            try:
                hwnd = _u32.GetForegroundWindow()
                pid = _ct.c_ulong()
                _u32.GetWindowThreadProcessId(hwnd, _ct.byref(pid))
                return pid.value == _our_pid
            except Exception:
                return True
        _fg["check"] = _app_is_foreground
    except Exception:
        _fg["check"] = lambda: True

    def _manage_mic():
        """Suelta/recupera el mic del monitor segun si la ventana esta activa."""
        if rec.is_recording():
            return   # grabando: el Recorder ya tiene el mic
        fg = _fg["check"]()
        if fg and not monitor.active():
            monitor.start(_mic_name())
        elif (not fg) and monitor.active():
            monitor.stop()

    # --- bucle de refresco (medidor + tiempo + progreso) ---
    low_since = {"t": None}

    def tick():
        _manage_mic()
        # medidor: grabando -> nivel del recorder; si no -> monitor (si esta activo)
        lvl = rec.level() if rec.is_recording() else (monitor.level() if monitor.active() else 0.0)
        w = canvas.winfo_width() or W
        fillw = int(min(1.0, lvl) * w)
        canvas.delete("all")
        col = "#3cb44a" if lvl < 0.7 else ("#e6b800" if lvl < 0.95 else "#e62828")
        if fillw > 0:
            canvas.create_rectangle(0, 0, fillw, 20, fill=col, width=0)
        # avisos solo mientras graba
        if rec.is_recording() and not rec.is_paused():
            el = int(rec.elapsed())
            time_lbl.config(text=f"{el // 60:02d}:{el % 60:02d}")
            import time as _t
            if lvl >= 0.98:
                warn_lbl.config(text="⚠ Too loud / clipping", fg="#e62828"); low_since["t"] = None
            elif lvl < 0.02:
                low_since["t"] = low_since["t"] or _t.monotonic()
                if _t.monotonic() - low_since["t"] > 2:
                    warn_lbl.config(text="⚠ Signal too low — check mic", fg="#e6b800")
            else:
                low_since["t"] = None; warn_lbl.config(text="")
        elif not rec.is_recording():
            warn_lbl.config(text="")
        # progreso / fin de reproduccion
        update_play_btn()
        if player.is_started():
            if player.finished():
                if not pstate["ended"]:   # llego al final: dejar barra al final
                    pbar.set(player.duration() or seek["dur"])
                    pos_lbl.config(text=f"{_fmt_time(player.duration())} / {_fmt_time(player.duration())}")
                    pstate["ended"] = True
            elif not seek["drag"]:
                pstate["ended"] = False
                pbar.set(player.position())
                pos_lbl.config(text=f"{_fmt_time(player.position())} / {_fmt_time(player.duration())}")
        root.after(60, tick)

    def on_close():
        try:
            if rec.is_recording():
                rec.stop()
            player.stop(); monitor.stop()
        except Exception:
            pass
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    _sync_rec(); refresh_list(); update_play_btn()
    monitor.start(mic_cb.get() if mic_cb.get() != "(default)" else "")
    tick()
    try:
        root.lift(); root.focus_force()
    except Exception:
        pass
    root.mainloop()


def main(argv=None):
    argv = argv if argv is not None else sys.argv
    kind = next((a for a in (argv or []) if a in ("hold", "long")), "")
    run(kind)


if __name__ == "__main__":
    main(sys.argv)
