# -*- coding: utf-8 -*-
"""
Recordatorios (categoria Practical "Reminder").

Almacen central en reminders.json (data_dir): lista de recordatorios + historial.
Cada recordatorio tiene fecha+hora, repeticion (once/daily/weekly/monthly/days),
posponer, forma de aviso, prioridad/categoria, accion ligada y
repetir-hasta-confirmar. El servidor los programa y dispara; la ventana los
crea/gestiona.
"""

from __future__ import annotations

import datetime as _dt
import json
import os

PRIORITY_COLORS = {
    "urgent": (230, 40, 40), "work": (210, 150, 40), "break": (60, 180, 120),
    "stream": (170, 70, 210), "personal": (60, 140, 230), "normal": (120, 130, 150),
}


def reminders_path():
    try:
        import m18_paths
        return os.path.join(m18_paths.data_dir(), "reminders.json")
    except Exception:
        return os.path.join(os.path.expanduser("~"), "m18_reminders.json")


def load_store():
    try:
        with open(reminders_path(), "r", encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict):
            d.setdefault("reminders", [])
            d.setdefault("history", [])
            return d
    except Exception:
        pass
    return {"reminders": [], "history": []}


def save_store(store):
    try:
        p = reminders_path()
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(store, f, indent=2, ensure_ascii=False)
        os.replace(tmp, p)
        return True
    except Exception as e:
        print("[rem] save:", e)
        return False


def append_history(store, title, event):
    h = store.setdefault("history", [])
    h.insert(0, {"t": _dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
                 "title": (title or "Reminder")[:40], "event": event})
    store["history"] = h[:80]


def new_id():
    return _dt.datetime.now().strftime("%Y%m%d%H%M%S%f")


def parse_due(s):
    try:
        return _dt.datetime.fromisoformat(s)
    except Exception:
        return None


def _add_month(dt):
    import calendar
    m = dt.month + 1
    y = dt.year
    if m > 12:
        m = 1
        y += 1
    day = min(dt.day, calendar.monthrange(y, m)[1])
    return dt.replace(year=y, month=m, day=day)


def advance_due(due, repeat, days):
    """Siguiente ocurrencia DESPUES de `due` (un paso). None si 'once'."""
    if repeat == "daily":
        return due + _dt.timedelta(days=1)
    if repeat == "weekly":
        return due + _dt.timedelta(days=7)
    if repeat == "monthly":
        return _add_month(due)
    if repeat == "days":
        allowed = set(int(d) for d in (days or []))
        if not allowed:
            return None
        for add in range(1, 8):
            cand = due + _dt.timedelta(days=add)
            if cand.weekday() in allowed:
                return cand
        return None
    return None   # once


def catch_up(due, repeat, days, now):
    """Avanza `due` hasta que sea > now (ocurrencias pasadas = omitidas).
    Devuelve (nuevo_due_o_None, n_omitidas)."""
    missed = 0
    while due is not None and due <= now:
        nxt = advance_due(due, repeat, days)
        if nxt is None:
            return None, missed   # once ya paso -> sin siguiente
        due = nxt
        missed += 1
    return due, missed


def pending(store):
    return [r for r in store.get("reminders", []) if r.get("status", "pending") == "pending"]


def pending_count(store):
    return len(pending(store))


def next_reminder(store):
    """El recordatorio pendiente con la fecha mas proxima (o None)."""
    best = None
    best_due = None
    for r in pending(store):
        d = parse_due(r.get("due", ""))
        if d is None:
            continue
        if best_due is None or d < best_due:
            best = r
            best_due = d
    return best
