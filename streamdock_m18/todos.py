# -*- coding: utf-8 -*-
"""
To-Do (categoria Practical): gestor de tareas.

Almacen central en todos.json (data_dir): tareas + papelera. Cada tarea tiene
titulo, descripcion, fecha limite, prioridad, categoria, lista/proyecto, estado
(pendiente/en progreso/completada/pospuesta), recurrencia y subtareas.
"""

from __future__ import annotations

import datetime as _dt
import json
import os

PRIORITY_COLORS = {
    "urgent": (230, 40, 40), "work": (210, 150, 40), "personal": (60, 140, 230),
    "stream": (170, 70, 210), "normal": (120, 130, 150),
}
STATES = ("pending", "in_progress", "completed", "postponed")


def todos_path():
    try:
        import m18_paths
        return os.path.join(m18_paths.data_dir(), "todos.json")
    except Exception:
        return os.path.join(os.path.expanduser("~"), "m18_todos.json")


def load_store():
    try:
        with open(todos_path(), "r", encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict):
            d.setdefault("tasks", [])
            d.setdefault("trash", [])
            return d
    except Exception:
        pass
    return {"tasks": [], "trash": []}


def save_store(store):
    try:
        p = todos_path()
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(store, f, indent=2, ensure_ascii=False)
        os.replace(tmp, p)
        return True
    except Exception as e:
        print("[todo] save:", e)
        return False


def new_id():
    return _dt.datetime.now().strftime("%Y%m%d%H%M%S%f")


def parse_due(s):
    try:
        return _dt.datetime.fromisoformat(s) if s else None
    except Exception:
        return None


def _add_month(dt):
    import calendar
    m = dt.month + 1; y = dt.year
    if m > 12:
        m = 1; y += 1
    return dt.replace(year=y, month=m, day=min(dt.day, calendar.monthrange(y, m)[1]))


def advance_due(due, recurring):
    if due is None:
        return None
    if recurring == "daily":
        return due + _dt.timedelta(days=1)
    if recurring == "weekly":
        return due + _dt.timedelta(days=7)
    if recurring == "monthly":
        return _add_month(due)
    return None


_ACTIVE = ("pending", "in_progress", "postponed")


def active_tasks(store):
    return [t for t in store.get("tasks", []) if t.get("state", "pending") in _ACTIVE]


def pending_count(store):
    return len(active_tasks(store))


def _is_today(due, now):
    return due is not None and due.date() == now.date()


def today_count(store):
    now = _dt.datetime.now()
    n = 0
    for t in active_tasks(store):
        d = parse_due(t.get("due"))
        if d is not None and d.date() <= now.date():   # hoy o vencidas
            n += 1
    return n


def _sort_key(t):
    pr = {"urgent": 0, "work": 1, "stream": 2, "personal": 3, "normal": 4}
    d = parse_due(t.get("due"))
    return (d is None, d or _dt.datetime.max, pr.get(t.get("priority", "normal"), 4))


def next_task(store):
    """La tarea activa mas relevante (hoy/vencidas por prioridad; si no, la mas proxima)."""
    act = active_tasks(store)
    if not act:
        return None
    return sorted(act, key=_sort_key)[0]


def get_view(store, view="today", search="", list_filter=None, sort="smart"):
    now = _dt.datetime.now()
    tasks = store.get("tasks", [])
    out = []
    q = (search or "").lower().strip()
    for t in tasks:
        state = t.get("state", "pending")
        d = parse_due(t.get("due"))
        if view == "completed":
            if state != "completed":
                continue
        elif view == "today":
            if state not in _ACTIVE or d is None or d.date() > now.date():
                continue
        elif view == "upcoming":
            if state not in _ACTIVE or d is None or d.date() <= now.date():
                continue
        elif view == "all":
            if state == "completed":
                continue
        elif view == "list" and list_filter is not None:
            if t.get("list", "Inbox") != list_filter or state == "completed":
                continue
        if q and q not in (t.get("title", "") + " " + t.get("desc", "")).lower():
            continue
        out.append(t)
    if sort == "due":
        out.sort(key=lambda t: (parse_due(t.get("due")) is None, parse_due(t.get("due")) or _dt.datetime.max))
    elif sort == "priority":
        pr = {"urgent": 0, "work": 1, "stream": 2, "personal": 3, "normal": 4}
        out.sort(key=lambda t: pr.get(t.get("priority", "normal"), 4))
    else:
        out.sort(key=_sort_key)
    return out


def lists(store):
    names = set()
    for t in store.get("tasks", []):
        names.add(t.get("list", "Inbox") or "Inbox")
    names.add("Inbox")
    return sorted(names)


def complete_task(store, task):
    """Marca completada. Si es recurrente, crea la siguiente ocurrencia pendiente."""
    task["state"] = "completed"
    task["completed_at"] = _dt.datetime.now().isoformat()
    rec = task.get("recurring", "none")
    if rec and rec != "none":
        d = parse_due(task.get("due"))
        nd = advance_due(d or _dt.datetime.now(), rec)
        if nd:
            nt = dict(task)
            nt["id"] = new_id()
            nt["state"] = "pending"
            nt["completed_at"] = None
            nt["due"] = nd.isoformat()
            nt["subtasks"] = [{"text": s.get("text", ""), "done": False} for s in task.get("subtasks", [])]
            store.setdefault("tasks", []).append(nt)


def to_trash(store, task):
    store["tasks"] = [t for t in store.get("tasks", []) if t.get("id") != task.get("id")]
    task["trashed_at"] = _dt.datetime.now().isoformat()
    store.setdefault("trash", []).insert(0, task)
    store["trash"] = store["trash"][:100]


def restore(store, tid):
    item = next((t for t in store.get("trash", []) if t.get("id") == tid), None)
    if item:
        store["trash"] = [t for t in store["trash"] if t.get("id") != tid]
        item.pop("trashed_at", None)
        store.setdefault("tasks", []).append(item)


def empty_trash(store):
    store["trash"] = []
