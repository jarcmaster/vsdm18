"""
Capa de alto nivel: paginas, teclas y acciones.

Una PAGINA es un conjunto de hasta 15 teclas (posiciones 0..14). La app puede
tener varias paginas y cambiar entre ellas (p.ej. con los botones laterales o
con teclas de navegacion). Tambien carga/guarda la configuracion en JSON para
usarla con la app de configuracion.

Posiciones de las teclas LCD:
     0  1  2  3  4
     5  6  7  8  9
    10 11 12 13 14
Botones laterales (sin pantalla): "left", "mid", "right".
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Callable

from . import actions
from .actions import (PageNav, DeviceCommand, TimerCommand, CalendarCommand,
                      AlarmCommand, RecorderCommand, RecorderToggleCommand,
                      ReminderCommand, TodoCommand, CalcCommand, SeqRepeatCommand)
from . import reminders as _reminders
from . import todos as _todos
from .device import KeyEvent, StreamDockM18

Action = Callable[[KeyEvent], None]


@dataclass
class Key:
    """Configuracion de una tecla."""
    text: str | None = None
    image: str | None = None            # ruta a imagen (solo teclas LCD)
    on_press: object | None = None      # Action o PageNav
    on_release: object | None = None
    on_double: object | None = None     # doble-tap: Action o PageNav (None = sin doble-tap)
    fg: tuple = (255, 255, 255)
    bg: tuple = (0, 0, 0)
    font: str | None = None             # ruta a .ttf/.ttc (None = Arial)
    page_indicator: bool = False        # muestra "pagina/total" dinamico


@dataclass
class Page:
    """Una pagina = nombre + teclas (posicion -> Key) + combos (2 teclas)."""
    name: str = "pagina"
    keys: dict[int, Key] = field(default_factory=dict)
    combos: list = field(default_factory=list)   # [{"keys":[a,b], "action": callable}]


@dataclass
class Scene:
    """Una escena = nombre + lista de paginas + pagina por defecto."""
    name: str = "Scene"
    pages: list = field(default_factory=lambda: [Page()])
    default_page: int = 0


class StreamDockApp:
    """Orquesta el dispositivo: escenas, paginas, pintado y despacho de acciones."""

    def __init__(
        self,
        scenes: list[Scene] | None = None,
        pages: list[Page] | None = None,        # compat: una escena
        keys: dict[int, Key] | None = None,     # atajo: una sola pagina
        aux: dict[str, Key] | None = None,      # botones laterales
        brightness: int = 80,
        default_page: int = 0,                  # pagina por defecto de la escena
        default_scene: int = 0,                 # escena que se carga al arrancar
        device: StreamDockM18 | None = None,
        device_cfg: dict | None = None,         # ajustes de hardware (LED, screen-off...)
    ):
        self.device_cfg = dict(device_cfg) if device_cfg else {}
        if scenes is None:
            if pages is None:
                pages = [Page("default", dict(keys))] if keys else [Page("default", {})]
            scenes = [Scene("Scene 1", pages, default_page)]
        self.scenes = scenes or [Scene("Scene 1", [Page("default", {})], 0)]
        self.aux = dict(aux) if aux else {}
        self.brightness = brightness
        self.device = device or StreamDockM18()
        self.default_scene = max(0, min(default_scene, len(self.scenes) - 1))
        self.scene_idx = self.default_scene
        self.current = max(0, min(self.scene.default_page, len(self.pages) - 1))
        self._timers = {}   # (scene_idx, page_idx, pos) -> TimerState (categoria Practical)
        self._calendar_last = None   # ultima fecha pintada en teclas Calendar Notes
        self._notes_mtime = 0        # mtime de notes.json (para refrescar el badge)
        self._notes_proc = None      # proceso de la ventana de notas (si esta abierta)
        self._locale_set = False
        self._alarms = {}            # (scene,page,pos) -> AlarmState (categoria Practical)
        self._alarm_info_proc = None # ventana informativa de alarma (si esta abierta)
        self._collect_alarms()
        self._recorder = None        # grabador de audio (mantener-presionado)
        self._rec_active = None      # estado de grabacion en curso (dict) o None
        self._rec_proc = None        # ventana de grabaciones (si esta abierta)
        self._rec_win_open = False   # para refrescar el badge al cerrarse la ventana
        self._rec_blink = False
        self._rec_blink_next = 0.0
        self._rec_toggle = None      # Long Recorder: sesion de grabacion activa (dict) o None
        self._rect_press = None      # Long Recorder: pulsacion en curso (para distinguir long press)
        # Calculadora (categoria Practical): estado y pulsacion en curso
        self._calc = {"cur": "", "acc": None, "op": None, "fresh": True, "err": False}
        self._calc_press = None
        # Sequence Repeat (grabador de macro raton+teclado)
        self._seq_rec = None     # grabacion en curso: {tkey,key,stop,thread,result}
        self._seq_play = None    # reproduccion en curso: {tkey,key,thread}
        self._seq_press = None   # pulsacion pendiente (distinguir tap vs long press)
        self._seq_blink = False
        self._seq_blink_next = 0.0
        # Marcador visual de teclas con long-press (pulso lento)
        self._lp_phase = True
        self._lp_next = 0.0
        # Doble-tap y combos: se resuelven en el bucle de eventos (como el long-press).
        self._defer = {}     # ident -> {"t","key","ev"} pulsacion pendiente de resolver
        self._held = set()   # idents fisicamente pulsados ahora mismo
        # Reminders (indicador global)
        self._rem_store = _reminders.load_store()
        self._rem_mtime = 0
        self._rem_ring = {}          # id -> {"popup":proc, "r":reminder}
        self._rem_proc = None        # ventana de recordatorios
        self._rem_blink = False
        self._rem_blink_next = 0.0
        self._rem_last_key = None
        # To-Do (indicador global)
        self._todo_store = _todos.load_store()
        self._todo_mtime = 0
        self._todo_proc = None
        try:
            from . import recorder as _recmod
            # recuperar grabaciones interrumpidas (base + subcarpetas por tipo)
            for _k in ("", "hold", "long"):
                _recmod.recover_orphans(_k)
        except Exception as e:
            print(f"[rec] recover: {e}")

    # --- escenas y paginas --------------------------------------------------
    @property
    def scene(self) -> Scene:
        return self.scenes[self.scene_idx]

    @property
    def pages(self) -> list:
        return self.scene.pages

    @property
    def default_page(self) -> int:
        return self.scene.default_page

    @property
    def page(self) -> Page:
        return self.pages[self.current]

    def goto_page(self, index: int, render: bool = True) -> None:
        if not self.pages:
            return
        self.current = index % len(self.pages)
        if render:
            self.render_page()

    def next_page(self) -> None:
        self.goto_page(self.current + 1)

    def prev_page(self) -> None:
        self.goto_page(self.current - 1)

    def goto_default(self) -> None:
        """Carga la pagina por defecto de la escena actual."""
        self.goto_page(self.scene.default_page)

    def goto_scene(self, index: int, render: bool = True) -> None:
        """Cambia de escena y va a su pagina por defecto."""
        if not self.scenes:
            return
        self.scene_idx = index % len(self.scenes)
        self.current = max(0, min(self.scene.default_page, len(self.pages) - 1))
        if render:
            self.render_page()

    def next_scene(self) -> None:
        self.goto_scene(self.scene_idx + 1)

    def prev_scene(self) -> None:
        self.goto_scene(self.scene_idx - 1)

    def add_page(self, name: str = "pagina") -> Page:
        p = Page(name, {})
        self.pages.append(p)
        return p

    # --- pintar -------------------------------------------------------------
    def render_page(self) -> None:
        """Limpia todas las teclas y pinta la pagina actual."""
        # al cambiar de pagina/escena descartamos pulsaciones a medio resolver
        self._defer.clear()
        self._held.clear()
        self.device.clear_all_keys(refresh=False)
        for pos, key in self.page.keys.items():
            if key.page_indicator:
                key.text = f"{self.current + 1}/{len(self.pages)}"
            if isinstance(key.on_press, CalendarCommand):
                self._render_calendar(pos, key)   # fecha de hoy en vivo
            elif isinstance(key.on_press, AlarmCommand):
                pass   # lo pinta _render_current_alarms (segun estado)
            elif isinstance(key.on_press, (RecorderCommand, RecorderToggleCommand)):
                pass   # lo pinta _render_current_recorders
            elif isinstance(key.on_press, ReminderCommand):
                pass   # lo pinta _render_current_reminders
            elif isinstance(key.on_press, TodoCommand):
                pass   # lo pinta _render_current_todos
            elif isinstance(key.on_press, SeqRepeatCommand):
                pass   # lo pinta _render_current_seq
            else:
                self._render_key(pos, key)
        # posiciones que SOLO participan en un combo (sin Key propia): tile minimo
        for c in self._page_combos():
            for m in c["keys"]:
                if isinstance(m, int) and m not in self.page.keys:
                    self._render_badge_tile(m)
        self.device.refresh()
        self._render_current_timers()   # timers activos de esta pagina (si los hay)
        self._render_current_alarms()   # alarmas (hora / sonando / pospuesta)
        self._render_current_recorders()  # teclas Recorder (REC / grabando)
        self._render_current_reminders()  # tecla Reminder (proximo + pendientes)
        self._render_current_todos()      # tecla To-Do (proxima tarea + pendientes)
        self._calc_render()               # tecla '=' de la calculadora (display)
        self._render_current_seq()        # teclas Sequence Repeat (idle/REC/PLAY)

    @property
    def rotate(self) -> int:
        r = self.device_cfg.get("rotate", 0)
        try:
            return int(r) % 360
        except (TypeError, ValueError):
            return 0

    def _phys_pos(self, pos: int) -> int:
        """Posicion fisica para una posicion logica, segun la rotacion (M18 3x5)."""
        return 14 - pos if self.rotate == 180 else pos

    def _long_press_kind(self, key):
        """'req' = el long-press es necesario para la funcion principal;
        'extra' = el long-press hace una funcion secundaria; None = sin long-press."""
        op = key.on_press
        if isinstance(op, (RecorderCommand, SeqRepeatCommand)):
            return "req"
        if isinstance(op, RecorderToggleCommand):
            return "extra"
        if isinstance(op, CalcCommand) and op.cfg.get("role") in ("add", "sub", "back"):
            return "extra"
        return None

    def _draw_lp_marker(self, img, kind, phase=True):
        """Dibuja el distintivo de long-press en la esquina inferior-izquierda.
        req = anillo ambar (⟲); extra = dos puntos cian (••). `phase` False = atenuado
        (para el pulso). Comparte el patron de los badges (PIL.ImageDraw)."""
        try:
            from PIL import ImageDraw
            from . import device as _dev
            sz = _dev.KEY_IMAGE_SIZE
            d = ImageDraw.Draw(img)
            base = (240, 170, 40) if kind == "req" else (80, 200, 230)
            col = base if phase else tuple(int(c * 0.4) for c in base)
            if kind == "req":          # anillo tipo reload
                cx, cy, r = 11, sz - 11, 7
                d.arc([cx - r, cy - r, cx + r, cy + r], start=100, end=65, fill=col, width=2)
                d.polygon([(cx + r - 2, cy - r), (cx + r + 3, cy - r - 1),
                           (cx + r, cy - r + 4)], fill=col)
            else:                      # dos puntos
                cy = sz - 10
                for cx in (8, 16):
                    d.ellipse([cx - 2, cy - 2, cx + 2, cy + 2], fill=col)
        except Exception as e:
            print(f"[lp] marker: {e}")

    def _extra_badges(self, pos, key) -> list:
        """Distintivos estaticos de la tecla: 'double' (doble-tap), 'combo' (miembro
        de un combo de la pagina). Independientes del long-press."""
        out = []
        if key is not None and getattr(key, "on_double", None) is not None:
            out.append("double")
        if any(pos in c["keys"] for c in self._page_combos()):
            out.append("combo")
        return out

    def _draw_badge(self, img, kind) -> None:
        """Distintivo estatico: doble-tap (doble chevron verde, arriba-dcha);
        combo (cruz morada, arriba-izq)."""
        try:
            from PIL import ImageDraw
            from . import device as _dev
            sz = _dev.KEY_IMAGE_SIZE
            d = ImageDraw.Draw(img)
            if kind == "double":
                col = (120, 230, 120)
                x, y = sz - 20, 7
                for dx in (0, 6):
                    d.line([(x + dx, y), (x + dx + 4, y + 5), (x + dx, y + 10)], fill=col, width=2)
            elif kind == "combo":
                col = (210, 130, 240)
                cx, cy, r = 12, 12, 5
                d.line([(cx - r, cy), (cx + r, cy)], fill=col, width=2)
                d.line([(cx, cy - r), (cx, cy + r)], fill=col, width=2)
        except Exception as e:
            print(f"[badge] {e}")

    def _render_lp_idle(self, pos, key, refresh=True) -> None:
        """Pinta una tecla long-press en reposo con su titulo/icono + el marcador."""
        from . import device as _dev
        kind = self._long_press_kind(key)
        badges = self._extra_badges(pos, key)
        text, bg = key.text, (tuple(key.bg) if key.bg else (0, 0, 0))
        if not (key.text or key.image) and isinstance(key.on_press, SeqRepeatCommand):
            text, bg = "SEQ", (30, 30, 44)
        img = _dev.compose_key_image(
            text=text, image=key.image or None,
            fg=tuple(key.fg) if key.fg else (255, 255, 255), bg=bg,
            font=key.font, rotate=0)
        if kind:
            self._draw_lp_marker(img, kind, self._lp_phase)
        for b in badges:
            self._draw_badge(img, b)
        if self.rotate:
            img = img.rotate(-int(self.rotate), expand=False)
        self.device.set_key_image(self._phys_pos(pos), img, refresh=refresh)

    def _render_badge_tile(self, pos) -> None:
        """Tile minimo para una posicion que SOLO participa en un combo (sin Key propia)."""
        from . import device as _dev
        img = _dev.compose_key_image(text=None, image=None, fg=(255, 255, 255),
                                     bg=(18, 18, 26), rotate=0)
        self._draw_badge(img, "combo")
        if self.rotate:
            img = img.rotate(-int(self.rotate), expand=False)
        self.device.set_key_image(self._phys_pos(pos), img, refresh=False)

    def _render_lp_key(self, pos, key, refresh=True) -> None:
        """Re-pinta una tecla long-press en reposo por el camino adecuado segun su tipo."""
        if isinstance(key.on_press, (RecorderCommand, RecorderToggleCommand)):
            self._render_recorder(pos, key, toggle=isinstance(key.on_press, RecorderToggleCommand))
        else:
            self._render_lp_idle(pos, key, refresh=refresh)

    def _render_key(self, pos: int, key: Key) -> None:
        has = bool(key.image or key.text)
        needs = bool(self._long_press_kind(key) or self._extra_badges(pos, key))
        if needs:   # con contenido o sin el: compone imagen + distintivos
            self._render_lp_idle(pos, key, refresh=False)
        elif has:
            self.device.set_key(self._phys_pos(pos), text=key.text, image=key.image,
                                 fg=key.fg, bg=key.bg, font=key.font, refresh=False,
                                 rotate=self.rotate)

    # --- bucle principal ----------------------------------------------------
    def apply_device_cfg(self) -> None:
        """Aplica los ajustes de hardware (LED lateral) al dispositivo."""
        dc = self.device_cfg
        col = dc.get("led_color")
        inten = dc.get("led_intensity")
        try:
            if col:
                self.device.set_led_color(col, brightness=inten, refresh=True)
            elif inten is not None:
                self.device.set_led_brightness(int(inten))
        except Exception as e:
            print(f"[led] {e}")

    @staticmethod
    def _norm_cfg_no_led(cfg: dict) -> str | None:
        """Serializa el cfg IGNORANDO brillo y LED (color/intensidad), para
        detectar cambios que SOLO tocan esos ajustes."""
        try:
            c = json.loads(json.dumps(cfg or {}))
        except Exception:
            return None
        c.pop("brightness", None)
        d = c.get("device")
        if isinstance(d, dict):
            d.pop("led_color", None)
            d.pop("led_intensity", None)
        return json.dumps(c, sort_keys=True, ensure_ascii=False)

    def _only_led_bright_change(self, prev: dict, cur: dict) -> bool:
        """True si la unica diferencia entre prev y cur es brillo y/o LED."""
        a = self._norm_cfg_no_led(prev)
        b = self._norm_cfg_no_led(cur)
        return a is not None and a == b

    def reload_from_cfg(self, cfg: dict) -> None:
        """Recarga escenas/aux/ajustes desde un dict de config, en caliente."""
        # Cambio SOLO de brillo/LED -> aplicar en caliente SIN reconstruir escenas,
        # sin resetear timers/alarmas/grabaciones ni repintar todas las teclas.
        prev = getattr(self, "_raw_cfg", None)
        try:
            self._raw_cfg = json.loads(json.dumps(cfg)) if cfg else {}
        except Exception:
            self._raw_cfg = None
        if prev is not None and self._only_led_bright_change(prev, cfg):
            try:
                self.brightness = int(cfg.get("brightness", self.brightness))
                self.device_cfg = cfg.get("device") or {}
                self.device.set_brightness(self.brightness)
                self.apply_device_cfg()
            except Exception as e:
                print(f"[reload-led] {e}")
            return
        # cancelar timers/alarmas activos (las teclas se reconstruyen -> refs obsoletas)
        for tkey in list(self._timers.keys()):
            self._timer_reset(tkey)
        self._alarms_cleanup()
        # cerrar cualquier grabacion en curso: las teclas se reconstruyen y el
        # estado quedaria huerfano (bloqueando futuras grabaciones).
        try:
            if self._recorder is not None and self._recorder.is_recording():
                self._recorder.stop()
        except Exception as e:
            print(f"[reload] rec stop: {e}")
        self._rec_active = None
        self._rec_toggle = None
        self._rect_press = None
        migrate_cfg(cfg)
        actions.set_routines(cfg.get("routines"))
        scenes, aux = _scenes_from_cfg(cfg)
        actions.set_obs_config(cfg.get("obs"))
        self.scenes = scenes or [Scene("Scene 1", [Page("default", {})], 0)]
        self.aux = aux
        self.brightness = int(cfg.get("brightness", self.brightness))
        self.device_cfg = cfg.get("device") or {}
        self.default_scene = max(0, min(int(cfg.get("default_scene", 0)), len(self.scenes) - 1))
        self.scene_idx = min(self.scene_idx, len(self.scenes) - 1)
        self.current = max(0, min(self.current, len(self.pages) - 1))
        self._collect_alarms()
        try:
            self.device.set_brightness(self.brightness)
            self.apply_device_cfg()
            self.render_page()
        except Exception as e:
            print(f"[reload] {e}")

    def run(self, poll_ms: int = 50, reload_cb=None, resume_cb=None) -> None:
        import time as _time
        screen_off_s = _parse_screen_off(self.device_cfg.get("screen_off"))
        with self.device:
            self.device.set_brightness(self.brightness)
            self.apply_device_cfg()
            self.render_page()
            print(f"Stream Dock M18 en marcha ({len(self.scenes)} escena/s). "
                  f"Ctrl+C para salir.")
            last_activity = _time.monotonic()
            dimmed = False
            errors = 0            # errores de HID consecutivos
            reconnecting = False  # tras resume: reabrir HID hasta que re-enumere
            try:
                while True:
                    if reload_cb is not None:
                        newcfg = reload_cb()
                        if newcfg is False:      # senal de parada
                            break
                        if newcfg:
                            self.reload_from_cfg(newcfg)
                            screen_off_s = _parse_screen_off(self.device_cfg.get("screen_off"))
                            last_activity = _time.monotonic(); dimmed = False
                    # El PC reanudo de suspension: el handle HID quedo obsoleto.
                    # Reabrir y repintar; si el equipo aun no re-enumero, reintentar.
                    if resume_cb is not None and resume_cb():
                        reconnecting = True
                    if reconnecting:
                        if self.device.reopen():
                            try:
                                self.device.set_brightness(self.brightness)
                                self.apply_device_cfg()
                                self.render_page()
                                print("[resume] dispositivo reconectado.")
                            except Exception as e:
                                print(f"[resume] repintado: {e}")
                            reconnecting = False
                            errors = 0
                            last_activity = _time.monotonic(); dimmed = False
                        else:
                            _time.sleep(0.5)   # el USB aun no esta listo; reintentar
                            continue
                    try:
                        self.device.keepalive()
                        ev = self.device.read_event(poll_ms)
                        errors = 0
                    except OSError as e:
                        # Lectura/escritura HID fallida: suele ser transitoria, o el
                        # equipo lo tiene el software oficial / se desconecto.
                        errors += 1
                        if errors == 1:
                            print(f"[aviso] error de lectura HID: {e}")
                        if errors >= 40:
                            print("Error de HID persistente. Cierra el software oficial "
                                  "de VSD / revisa el cable USB-C de datos. Saliendo.")
                            break
                        _time.sleep(0.2)
                        continue
                    now = _time.monotonic()
                    if ev is not None:
                        if dimmed:   # despertar la pantalla con cualquier tecla
                            self.device.set_brightness(self.brightness)
                            dimmed = False
                        last_activity = now
                        self._dispatch(ev)
                    # timers de la categoria Practical (cuenta regresiva en la tecla)
                    self._tick_timers()
                    self._tick_calendar()   # refresca la fecha si cambio el dia
                    self._tick_alarms()     # programacion de alarmas
                    self._tick_recorder()   # grabacion en curso (mantener-presionado)
                    self._tick_reminders()  # recordatorios (indicador global)
                    self._tick_todos()      # refresca la tecla To-Do si cambio el archivo
                    self._tick_calc()       # pulsacion larga de +,-,back (x, /, limpiar)
                    self._tick_seq()        # Sequence Repeat (long press graba / tap reproduce)
                    self._tick_defer()      # doble-tap / combos (resuelve pulsaciones pendientes)
                    self._tick_lp_marker(dimmed)   # pulso del distintivo de long-press
                    if (self._timers or self._alarm_ringing_any() or self._rec_active
                            or self._rec_toggle or self._rem_ring or self._seq_rec
                            or self._seq_play):
                        if dimmed:   # un timer activo despierta la pantalla
                            self.device.set_brightness(self.brightness)
                            dimmed = False
                        last_activity = now   # no apagar la pantalla con timers en curso
                    elif screen_off_s and not dimmed and (now - last_activity) >= screen_off_s:
                        self.device.set_brightness(0)
                        dimmed = True
            except KeyboardInterrupt:
                print("\nSaliendo...")

    def _dispatch(self, ev: KeyEvent) -> None:
        # Buscar la tecla: LCD en la pagina actual; laterales en self.aux
        if ev.is_aux:
            key = self.aux.get(ev.key)
            ident = ev.key
        else:
            # la posicion fisica pulsada -> posicion logica (inversa de la rotacion)
            logical = 14 - ev.key if self.rotate == 180 else ev.key
            key = self.page.keys.get(logical)
            ident = logical
        # Doble-tap / combos: interceptar teclas "normales". Las mini-apps (calc,
        # recorder, seq...) tienen su propio press/release y quedan excluidas.
        # Incluye posiciones sin accion que solo existan para formar un combo.
        if self._wants_defer(key, ident):
            self._defer_event(ident, key, ev)
            return
        if key is None:
            return
        # Recorder: necesita press Y release (mantener=graba, clic=abre ventana).
        # Se maneja ANTES de resolver action (el release no tiene on_release propio).
        if isinstance(key.on_press, RecorderCommand) and not ev.is_aux:
            logical = 14 - ev.key if self.rotate == 180 else ev.key
            self._recorder_event(logical, key, key.on_press, ev.pressed)
            return
        # Calculadora: digitos/./= actuan al pulsar; +,-,back distinguen pulsacion
        # corta vs larga (se deciden al soltar).
        if isinstance(key.on_press, CalcCommand) and not ev.is_aux:
            logical = 14 - ev.key if self.rotate == 180 else ev.key
            self._calc_event(logical, key, key.on_press, ev.pressed)
            return
        # Sequence Repeat: long press graba, re-pulsar detiene, tap reproduce.
        if isinstance(key.on_press, SeqRepeatCommand) and not ev.is_aux:
            logical = 14 - ev.key if self.rotate == 180 else ev.key
            self._seq_event(logical, key, key.on_press, ev.pressed)
            return
        # Long Recorder: clic corto alterna grabacion; long press abre la ventana.
        if isinstance(key.on_press, RecorderToggleCommand) and not ev.is_aux:
            logical = 14 - ev.key if self.rotate == 180 else ev.key
            self._recorder_toggle_event(logical, key, key.on_press, ev.pressed)
            return
        action = key.on_press if ev.pressed else key.on_release
        if action is None:
            return
        # Navegacion de pagina
        if isinstance(action, PageNav):
            if ev.pressed:
                self._do_nav(action)
            return
        # Comando de dispositivo (p.ej. brillo)
        if isinstance(action, DeviceCommand):
            if ev.pressed:
                self._do_device(action)
            return
        # Timer (categoria Practical): pulsar inicia / para / descarta
        if isinstance(action, TimerCommand):
            if ev.pressed and not ev.is_aux:   # solo teclas LCD (los aux no tienen pantalla)
                logical = 14 - ev.key if self.rotate == 180 else ev.key
                self._timer_press(logical, key, action)
            return
        # Calendar Notes: pulsar abre la ventana de notas
        if isinstance(action, CalendarCommand):
            if ev.pressed:
                self._open_notes()
            return
        # Alarm: pulsar pospone (si suena) o reconoce (si pospuesta)
        if isinstance(action, AlarmCommand):
            if ev.pressed and not ev.is_aux:
                logical = 14 - ev.key if self.rotate == 180 else ev.key
                st = self._alarms.get((self.scene_idx, self.current, logical))
                if st is not None:
                    self._alarm_press(st)
            return
        # Reminder: pulsar abre la ventana de recordatorios
        if isinstance(action, ReminderCommand):
            if ev.pressed:
                self._open_reminders()
            return
        # To-Do: pulsar abre la ventana de tareas
        if isinstance(action, TodoCommand):
            if ev.pressed:
                self._open_todos()
            return
        # Accion normal
        try:
            action(ev)
        except Exception as e:
            print(f"[accion {ev.key!r}] error: {e}")

    # --- doble-tap y combos -------------------------------------------------
    # mini-apps con press/release propio: no admiten doble-tap/combo
    _SPECIAL = (RecorderCommand, CalcCommand, SeqRepeatCommand, RecorderToggleCommand,
                TimerCommand, AlarmCommand, CalendarCommand, ReminderCommand, TodoCommand)
    DEFER_WINDOW = 0.28   # s: ventana para el 2o tap (doble) o la tecla companera (combo)

    def _is_special(self, key) -> bool:
        return key is not None and isinstance(key.on_press, self._SPECIAL)

    def _page_combos(self) -> list:
        return getattr(self.page, "combos", None) or []

    def _in_combo(self, ident) -> bool:
        return any(ident in c["keys"] for c in self._page_combos())

    def _wants_defer(self, key, ident) -> bool:
        """True si esta tecla/posicion debe diferir su accion (doble-tap o combo)."""
        if self._is_special(key):
            return False
        if key is not None and key.on_double is not None:
            return True
        return self._in_combo(ident)

    def _run_action(self, action, ev) -> None:
        """Ejecuta una accion simple (normal / PageNav / DeviceCommand)."""
        if action is None:
            return
        if isinstance(action, PageNav):
            self._do_nav(action); return
        if isinstance(action, DeviceCommand):
            self._do_device(action); return
        try:
            action(ev)
        except Exception as e:
            print(f"[accion] error: {e}")

    def _match_combo(self, ident):
        """Combo de 2 teclas cuya OTRA tecla sigue pulsada y pendiente (simultaneas)."""
        for c in self._page_combos():
            ks = c["keys"]
            if len(ks) == 2 and ident in ks:
                other = ks[0] if ks[1] == ident else ks[1]
                if other in self._defer and other in self._held:
                    return c
        return None

    def _fire_combo(self, combo, ev) -> None:
        for m in combo["keys"]:
            self._defer.pop(m, None)   # sus acciones individuales ya no se disparan
        self._run_action(combo.get("action"), ev)

    def _defer_event(self, ident, key, ev) -> None:
        if not ev.pressed:
            self._held.discard(ident)
            return
        self._held.add(ident)
        now = time.monotonic()
        # 1) combo: la companera ya estaba pulsada -> disparar combo y consumir ambas
        combo = self._match_combo(ident)
        if combo is not None:
            self._fire_combo(combo, ev)
            return
        # 2) doble-tap: 2o tap de la misma tecla dentro de la ventana
        pend = self._defer.get(ident)
        if (pend is not None and key is not None and key.on_double is not None
                and (now - pend["t"]) <= self.DEFER_WINDOW):
            del self._defer[ident]
            self._run_action(key.on_double, ev)
            return
        # 3) primer tap: queda pendiente (lo resuelve _tick_defer al vencer la ventana)
        self._defer[ident] = {"t": now, "key": key, "ev": ev}

    def _tick_defer(self) -> None:
        """Dispara la accion simple de las pulsaciones cuya ventana ya vencio."""
        if not self._defer:
            return
        now = time.monotonic()
        due = [i for i, p in self._defer.items() if (now - p["t"]) >= self.DEFER_WINDOW]
        for i in due:
            p = self._defer.pop(i)
            k = p["key"]
            if k is not None:
                self._run_action(k.on_press, p["ev"])

    def _do_device(self, cmd: DeviceCommand) -> None:
        if cmd.kind == "brightness":
            v = max(0, min(100, int(cmd.value)))
            self.brightness = v
            self.device.set_brightness(v)
        elif cmd.kind == "sleep":
            self.brightness = 0
            self.device.set_brightness(0)

    def _do_nav(self, nav: PageNav) -> None:
        tgt = nav.target
        if tgt == "next":
            self.next_page()
        elif tgt == "prev":
            self.prev_page()
        elif tgt == "home":
            self.goto_default()
        elif tgt == "scene_next":
            self.next_scene()
        elif tgt == "scene_prev":
            self.prev_scene()
        elif tgt == "scene_home":
            self.goto_scene(self.default_scene)
        elif isinstance(tgt, tuple) and len(tgt) == 2 and tgt[0] == "scene":
            self.goto_scene(int(tgt[1]))
        elif isinstance(tgt, int):
            self.goto_page(tgt)

    # --- Timer (categoria Practical) ----------------------------------------
    @staticmethod
    def _fmt_remaining(remaining: float) -> str:
        """Segundos restantes -> 'MM:SS' (los minutos pueden pasar de 59)."""
        s = int(remaining + 0.999)   # redondeo hacia arriba
        if s < 0:
            s = 0
        return f"{s // 60:02d}:{s % 60:02d}"

    def _timer_press(self, logical, key, cmd: TimerCommand) -> None:
        tkey = (self.scene_idx, self.current, logical)
        st = self._timers.get(tkey)
        if st is None:
            self._timer_start(tkey, logical, key, cmd.cfg)     # iniciar cuenta
        else:
            # en marcha -> parar y volver a normal;  terminado -> descartar
            self._timer_reset(tkey)

    def _timer_start(self, tkey, logical, key, cfg) -> None:
        import time as _t
        secs = max(1, int(cfg.get("seconds", 300)))
        blink = cfg.get("blink") or [[255, 90, 0], [25, 0, 0]]
        st = {"tkey": tkey, "pos": logical, "key": key, "seconds": secs,
              "end": _t.monotonic() + secs, "status": "running", "last_shown": None,
              "notify": bool(cfg.get("notify", True)), "sound": bool(cfg.get("sound", True)),
              "exec": cfg.get("exec") if cfg.get("type") == "timer_exec" else None,
              "blink": blink, "blink_on": False, "blink_next": 0.0, "popup": None}
        self._timers[tkey] = st
        self._render_timer(st)

    def _tick_timers(self) -> None:
        """Avanza todos los timers (se llama en cada vuelta del bucle principal)."""
        if not self._timers:
            return
        import time as _t
        now = _t.monotonic()
        for tkey, st in list(self._timers.items()):
            if st["status"] == "running":
                remaining = st["end"] - now
                if remaining <= 0:
                    self._timer_fire(st)
                else:
                    label = self._fmt_remaining(remaining)
                    if label != st["last_shown"]:
                        st["last_shown"] = label
                        self._render_timer(st)
            elif st["status"] == "done":
                if now >= st["blink_next"]:
                    st["blink_on"] = not st["blink_on"]
                    st["blink_next"] = now + 0.5
                    self._render_timer(st)
                p = st.get("popup")
                if p is not None and p.poll() is not None:   # popup cerrado (Dismiss)
                    self._timer_reset(tkey)

    def _render_timer(self, st) -> None:
        """Pinta la tecla del timer (solo si su escena/pagina esta visible)."""
        scn, pg, pos = st["tkey"]
        if scn != self.scene_idx or pg != self.current:
            return
        import time as _t
        key = st["key"]
        phys = self._phys_pos(pos)
        try:
            if st["status"] == "running":
                label = self._fmt_remaining(max(0.0, st["end"] - _t.monotonic()))
                self.device.set_key(phys, text=label, fg=(255, 255, 255),
                                    bg=(20, 45, 80), font=key.font,
                                    refresh=True, rotate=self.rotate)
            else:  # done -> parpadeo entre dos colores
                col = st["blink"][0] if st["blink_on"] else st["blink"][1]
                self.device.set_key(phys, text="00:00", fg=(255, 255, 255),
                                    bg=tuple(col), font=key.font,
                                    refresh=True, rotate=self.rotate)
        except Exception as e:
            print(f"[timer] render: {e}")

    def _render_current_timers(self) -> None:
        """Re-pinta los timers activos de la pagina actual (tras cambiar de pagina)."""
        for st in self._timers.values():
            scn, pg, _pos = st["tkey"]
            if scn == self.scene_idx and pg == self.current:
                st["last_shown"] = None
                self._render_timer(st)

    def _timer_fire(self, st) -> None:
        """La cuenta llego a 0: notifica, suena y empieza a parpadear."""
        import time as _t
        st["status"] = "done"
        st["blink_on"] = True
        st["blink_next"] = _t.monotonic() + 0.5
        self._render_timer(st)
        if st["sound"]:
            self._timer_sound_start()
        if st["notify"]:
            st["popup"] = self._timer_popup(st)
        if st.get("exec"):
            self._run_timer_exec(st["exec"])

    def _run_timer_exec(self, exec_cfg) -> None:
        """Ejecuta la accion final de 'On Timer Execute' (app / tecla / rutina)."""
        import threading as _th
        kind = (exec_cfg or {}).get("kind")
        try:
            if kind == "app":
                act = actions.from_spec({"type": "open_app", "path": exec_cfg.get("path", "")})
            elif kind == "key":
                act = actions.from_spec({"type": "hotkey", "keys": exec_cfg.get("keys", [])})
            elif kind == "routine":
                act = actions.routine_action(exec_cfg.get("name", ""))
            else:
                return
        except Exception as e:
            print(f"[timer] exec build: {e}")
            return
        if not callable(act):
            return

        def run():
            try:
                act(None)
            except Exception as e:
                print(f"[timer] exec: {e}")
        _th.Thread(target=run, daemon=True).start()

    def _timer_reset(self, tkey) -> None:
        """Para/descarta un timer y devuelve la tecla a su aspecto normal."""
        st = self._timers.pop(tkey, None)
        if st is None:
            return
        p = st.get("popup")
        if p is not None and p.poll() is None:
            try:
                p.terminate()
            except Exception:
                pass
        self._timer_sound_stop_if_idle()
        scn, pg, pos = tkey
        if scn == self.scene_idx and pg == self.current:
            self._restore_tile(pos, st["key"])

    def _restore_tile(self, pos, key) -> None:
        phys = self._phys_pos(pos)
        try:
            if key.image or key.text:
                self.device.set_key(phys, text=key.text, image=key.image, fg=key.fg,
                                    bg=key.bg, font=key.font, refresh=True, rotate=self.rotate)
            else:
                self.device.clear_key(phys, refresh=True)
        except Exception as e:
            print(f"[timer] restore: {e}")

    def _timer_sound_start(self) -> None:
        try:
            import winsound
            winsound.PlaySound("SystemExclamation",
                               winsound.SND_ALIAS | winsound.SND_ASYNC | winsound.SND_LOOP)
        except Exception as e:
            print(f"[timer] sound: {e}")

    def _timer_sound_stop_if_idle(self) -> None:
        # si aun queda algun timer sonando, no cortar
        if any(s["status"] == "done" and s["sound"] for s in self._timers.values()):
            return
        try:
            import winsound
            winsound.PlaySound(None, 0)
        except Exception:
            pass

    def _timer_popup(self, st):
        """Lanza la ventana de aviso con boton Dismiss (proceso aparte)."""
        import subprocess
        import sys as _sys
        title = (st["key"].text or "Timer").replace("\n", " ").strip() or "Timer"
        flags = 0x08000000   # CREATE_NO_WINDOW
        try:
            if getattr(_sys, "frozen", False):
                args = [_sys.executable, "--timer-popup", title]
            else:
                script = os.path.join(os.path.dirname(os.path.dirname(__file__)), "timer_popup.py")
                args = [_sys.executable, script, title]
            return subprocess.Popen(args, creationflags=flags)
        except Exception as e:
            print(f"[timer] popup: {e}")
            return None

    # --- Calendar Notes (categoria Practical) -------------------------------
    def _calendar_text(self):
        """Fecha de hoy en 3 lineas: dia-semana / numero / mes (locale del sistema)."""
        import time as _t
        if not self._locale_set:
            try:
                import locale
                locale.setlocale(locale.LC_TIME, "")   # region de Windows
            except Exception:
                pass
            self._locale_set = True
        wd = _t.strftime("%a").strip()[:3]
        day = _t.strftime("%d").lstrip("0") or "0"
        mon = _t.strftime("%b").strip()[:3]
        return f"{wd}\n{day}\n{mon}"

    def _notes_path(self):
        try:
            import m18_paths
            return os.path.join(m18_paths.data_dir(), "notes.json")
        except Exception:
            return os.path.join(os.path.expanduser("~"), "m18_notes.json")

    def _notes_count(self) -> int:
        try:
            with open(self._notes_path(), "r", encoding="utf-8") as f:
                data = json.load(f)
            return len(data) if isinstance(data, list) else 0
        except Exception:
            return 0

    def _render_calendar(self, pos, key) -> None:
        phys = self._phys_pos(pos)
        date = self._calendar_text()
        count = self._notes_count()
        fg = tuple(key.fg) if key.fg else (255, 255, 255)
        bg = tuple(key.bg) if key.bg else (30, 40, 60)
        try:
            from . import device as _dev
            from PIL import Image, ImageDraw
            sz = _dev.KEY_IMAGE_SIZE
            img = Image.new("RGB", (sz, sz), bg)
            d = ImageDraw.Draw(img)
            # fecha alineada a la IZQUIERDA (deja libre la esquina sup-derecha del badge)
            lines = (date.split("\n") + ["", "", ""])[:3]
            f = _dev._font(15, key.font)
            asc, desc = f.getmetrics(); lh = asc + desc
            ys = [2, (sz - lh) / 2, sz - 2 - lh]
            for ln, y in zip(lines, ys):
                if ln:
                    d.text((3, y), ln, font=f, fill=fg)
            if count > 0:   # badge con el numero de notas (esquina sup-derecha)
                r = 12
                cx = sz - r - 1; cy = r + 1
                d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(220, 60, 60))
                s = str(count) if count < 100 else "99+"
                bf = _dev._font(14 if len(s) < 2 else 11)
                tw = d.textlength(s, font=bf)
                ba, bd = bf.getmetrics()
                d.text((cx - tw / 2, cy - (ba + bd) / 2), s, font=bf, fill=(255, 255, 255))
            if self.rotate:
                img = img.rotate(-int(self.rotate), expand=False)
            self.device.set_key_image(phys, img, refresh=True)
        except Exception as e:
            print(f"[calendar] render: {e}")
            try:   # respaldo: solo texto
                self.device.set_key(phys, text=date, fg=fg, bg=bg, font=key.font,
                                    refresh=True, rotate=self.rotate)
            except Exception:
                pass

    def _tick_calendar(self) -> None:
        """Re-pinta las teclas Calendar de la pagina actual si cambio el dia o las notas."""
        cal_keys = [(p, k) for p, k in self.page.keys.items()
                    if isinstance(k.on_press, CalendarCommand)]
        if not cal_keys:
            return
        day = self._calendar_text()
        try:
            mt = os.path.getmtime(self._notes_path())
        except OSError:
            mt = 0
        if day == self._calendar_last and mt == self._notes_mtime:
            return
        self._calendar_last = day
        self._notes_mtime = mt
        for pos, key in cal_keys:
            self._render_calendar(pos, key)

    def _open_notes(self) -> None:
        """Abre la ventana de notas (proceso aparte). No relanza si ya esta abierta."""
        import subprocess
        import sys as _sys
        if self._notes_proc is not None and self._notes_proc.poll() is None:
            return   # ya hay una ventana de notas abierta
        notes_path = self._notes_path()
        flags = 0x08000000   # CREATE_NO_WINDOW
        try:
            if getattr(_sys, "frozen", False):
                args = [_sys.executable, "--notes-popup", notes_path]
            else:
                script = os.path.join(os.path.dirname(os.path.dirname(__file__)), "notes_popup.py")
                args = [_sys.executable, script, notes_path]
            self._notes_proc = subprocess.Popen(args, creationflags=flags)
        except Exception as e:
            print(f"[calendar] notes: {e}")

    # --- Alarmas (categoria Practical) --------------------------------------
    _ALARM_COLORS = {
        "urgent": (230, 40, 40), "reminder": (60, 140, 230), "break": (60, 180, 120),
        "work": (210, 150, 40), "stream": (170, 70, 210), "normal": (230, 120, 0),
    }

    # --- estado persistente / historial de alarmas ---
    def _alarm_state_path(self):
        try:
            import m18_paths
            return os.path.join(m18_paths.data_dir(), "alarms_state.json")
        except Exception:
            return os.path.join(os.path.expanduser("~"), "m18_alarms_state.json")

    def _load_alarm_state(self):
        try:
            with open(self._alarm_state_path(), "r", encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict):
                d.setdefault("alarms", {}); d.setdefault("history", [])
                return d
        except Exception:
            pass
        return {"alarms": {}, "history": []}

    def _save_alarm_state(self):
        try:
            p = self._alarm_state_path()
            tmp = p + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._alarm_state, f, indent=2, ensure_ascii=False)
            os.replace(tmp, p)
        except Exception as e:
            print(f"[alarm] state save: {e}")

    def _append_history(self, note, event):
        import datetime as _dt
        h = self._alarm_state.setdefault("history", [])
        h.insert(0, {"t": _dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
                     "note": (note or "Alarm")[:40], "event": event})
        self._alarm_state["history"] = h[:50]

    def _prev_occurrence(self, cfg, before):
        """Ultima ocurrencia programada ANTES de `before` (para detectar omitidas)."""
        import datetime as _dt
        repeat = cfg.get("repeat", "once")
        if repeat == "interval":
            return None
        hh, mm = self._parse_hhmm(cfg.get("time", "07:00"))
        base = before.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if repeat in ("once", "daily"):
            return base if base <= before else base - _dt.timedelta(days=1)
        allowed = {0, 1, 2, 3, 4} if repeat == "weekdays" else set(int(d) for d in cfg.get("days", []))
        if not allowed:
            return None
        for sub in range(0, 8):
            cand = base - _dt.timedelta(days=sub)
            if cand <= before and cand.weekday() in allowed:
                return cand
        return None

    def _collect_alarms(self) -> None:
        """Escanea TODAS las escenas/paginas y arma las alarmas (con estado persistente)."""
        import datetime as _dt
        self._alarm_state = self._load_alarm_state()
        astates = self._alarm_state.setdefault("alarms", {})
        self._alarms = {}
        now = _dt.datetime.now()
        changed = False
        for si, scene in enumerate(self.scenes):
            for pi, pg in enumerate(scene.pages):
                for pos, key in pg.keys.items():
                    if not isinstance(key.on_press, AlarmCommand):
                        continue
                    cfg = key.on_press.cfg
                    skey = f"{si}:{pi}:{pos}"
                    saved = astates.get(skey, {})
                    # si cambio la programacion (edicion), resetear el estado guardado
                    sig = f"{cfg.get('time')}|{cfg.get('repeat')}|{cfg.get('interval_min')}|{sorted(cfg.get('days', []))}"
                    if saved.get("sig") != sig:
                        saved = {"sig": sig}
                        astates[skey] = saved
                        changed = True
                    st = {"tkey": (si, pi, pos), "pos": pos, "key": key, "cfg": cfg,
                          "skey": skey, "status": "armed", "snooze_count": 0,
                          "snooze_until": None, "ring_since": 0.0, "blink_on": False,
                          "blink_next": 0.0, "popup": None, "escalated": False,
                          "next_fire": None}
                    note = (cfg.get("note") or (key.text or "Alarm")).replace("\n", " ").strip() or "Alarm"
                    repeat = cfg.get("repeat", "once")

                    def _as_dt(v):
                        try:
                            return _dt.datetime.fromisoformat(v) if v else None
                        except Exception:
                            return None

                    if repeat == "once":
                        # 'once' usa un objetivo guardado (armed_for), no la hora-del-dia,
                        # para distinguir "recien creada" de "omitida mientras apagado".
                        if saved.get("done"):
                            st["status"] = "done"
                        else:
                            af = _as_dt(saved.get("armed_for"))
                            if af is None:
                                af = self._compute_next_fire(cfg, now)
                                astates.setdefault(skey, {})["armed_for"] = af.isoformat() if af else None
                                changed = True
                            if af is not None and af <= now:   # el objetivo ya paso
                                if not saved.get("last_fired"):
                                    self._append_history(note, "missed")
                                astates.setdefault(skey, {})["done"] = True
                                st["status"] = "done"
                                changed = True
                            else:
                                st["next_fire"] = af
                    else:
                        # recurrentes: deteccion de ocurrencia omitida (apagon/suspension)
                        prev = self._prev_occurrence(cfg, now)
                        lf = _as_dt(saved.get("last_fired"))
                        if (prev is not None and (now - prev) < _dt.timedelta(hours=18)
                                and (lf is None or lf < prev)):
                            self._append_history(note, "missed")
                            astates.setdefault(skey, {})["last_fired"] = prev.isoformat()
                            changed = True
                        st["next_fire"] = self._compute_next_fire(cfg, now)
                    self._alarms[(si, pi, pos)] = st
        if changed:
            self._save_alarm_state()

    def _alarms_cleanup(self) -> None:
        for st in list(self._alarms.values()):
            self._close_alarm_popup(st)
        self._alarms = {}
        self._alarm_sound_stop()

    @staticmethod
    def _parse_hhmm(s):
        try:
            parts = str(s or "7:0").strip().replace(".", ":").replace("h", ":").replace(" ", "").split(":")
            hh = int(parts[0])
            mm = int(parts[1]) if len(parts) > 1 and parts[1] != "" else 0
            return max(0, min(23, hh)), max(0, min(59, mm))
        except Exception:
            return 7, 0

    def _compute_next_fire(self, cfg, after):
        import datetime as _dt
        repeat = cfg.get("repeat", "once")
        if repeat == "interval":
            return after + _dt.timedelta(minutes=max(1, int(cfg.get("interval_min", 60))))
        hh, mm = self._parse_hhmm(cfg.get("time", "07:00"))
        base = after.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if repeat in ("once", "daily"):
            if base <= after:
                base += _dt.timedelta(days=1)
            return base
        allowed = {0, 1, 2, 3, 4} if repeat == "weekdays" else set(int(d) for d in cfg.get("days", []))
        if not allowed:
            return None
        for add in range(0, 8):
            cand = base + _dt.timedelta(days=add)
            if cand > after and cand.weekday() in allowed:
                return cand
        return None

    def _alarm_color(self, cfg):
        return self._ALARM_COLORS.get(cfg.get("priority", "normal"), self._ALARM_COLORS["normal"])

    def _alarm_time_label(self, cfg):
        if cfg.get("repeat") == "interval":
            return f"{int(cfg.get('interval_min', 60))}m"
        return cfg.get("time", "07:00")

    def _alarm_ringing_any(self):
        return any(s["status"] == "ringing" for s in self._alarms.values())

    def _tick_alarms(self) -> None:
        if not self._alarms:
            return
        import datetime as _dt
        import time as _t
        now = _dt.datetime.now()
        mono = _t.monotonic()
        for st in list(self._alarms.values()):
            status = st["status"]
            if status == "armed":
                nf = st.get("next_fire")
                if nf is not None and now >= nf:
                    self._alarm_fire(st)
            elif status == "snoozed":
                su = st.get("snooze_until")
                if su is not None and now >= su:
                    self._alarm_fire(st)
            elif status == "ringing":
                if mono >= st["blink_next"]:
                    st["blink_on"] = not st["blink_on"]
                    st["blink_next"] = mono + (0.25 if st["escalated"] else 0.5)
                    self._render_alarm(st)
                if st["cfg"].get("escalate") and not st["escalated"] and (mono - st["ring_since"]) > 30:
                    st["escalated"] = True
                    if st["cfg"].get("sound", True):
                        self._alarm_sound_start(urgent=True)
                p = st.get("popup")
                if p is not None:
                    rc = p.poll()
                    if rc is not None:
                        st["popup"] = None
                        if rc == 10:
                            self._alarm_snooze(st)
                        else:
                            self._alarm_ack(st)

    def _alarm_fire(self, st) -> None:
        import time as _t
        import datetime as _dt
        st["status"] = "ringing"
        st["ring_since"] = _t.monotonic()
        st["blink_on"] = True
        st["blink_next"] = _t.monotonic() + 0.5
        st["escalated"] = False
        cfg = st["cfg"]
        # historial + persistencia (ultimo disparo)
        self._append_history(self._alarm_note(st), "rang")
        self._alarm_state.setdefault("alarms", {}).setdefault(st["skey"], {})["last_fired"] = \
            _dt.datetime.now().isoformat()
        self._save_alarm_state()
        self._render_alarm(st)
        if cfg.get("sound", True):
            # escalada: empieza discreto (se sube tras 30s en _tick_alarms)
            self._alarm_sound_start(urgent=not cfg.get("escalate", False) and False)
        if cfg.get("notify", True):
            st["popup"] = self._alarm_popup(st)
        exec_cfg = cfg.get("exec")
        if exec_cfg and exec_cfg.get("kind") not in (None, "none", ""):
            self._run_timer_exec(exec_cfg)   # app / tecla / rutina

    def _alarm_snooze(self, st) -> None:
        import datetime as _dt
        cfg = st["cfg"]
        if st["snooze_count"] >= int(cfg.get("snooze_max", 3)):
            self._alarm_ack(st)
            return
        st["snooze_count"] += 1
        mins = max(1, int(cfg.get("snooze_min", 5)))
        st["snooze_until"] = _dt.datetime.now() + _dt.timedelta(minutes=mins)
        st["status"] = "snoozed"
        st["escalated"] = False
        self._append_history(self._alarm_note(st), "snoozed")
        self._save_alarm_state()
        self._close_alarm_popup(st)
        self._alarm_sound_stop_if_idle()
        self._render_alarm(st)

    def _alarm_ack(self, st) -> None:
        import datetime as _dt
        cfg = st["cfg"]
        st["snooze_count"] = 0
        st["snooze_until"] = None
        st["escalated"] = False
        self._close_alarm_popup(st)
        self._alarm_sound_stop_if_idle()
        if cfg.get("repeat", "once") == "once":
            st["status"] = "done"
            st["next_fire"] = None
            self._alarm_state.setdefault("alarms", {}).setdefault(st["skey"], {})["done"] = True
        else:
            st["status"] = "armed"
            st["next_fire"] = self._compute_next_fire(cfg, _dt.datetime.now())
        self._append_history(self._alarm_note(st), "dismissed")
        self._save_alarm_state()
        self._render_alarm(st)

    def _alarm_press(self, st) -> None:
        if st["status"] == "ringing":
            self._alarm_snooze(st)
        elif st["status"] == "snoozed":
            self._alarm_ack(st)
        else:   # armed / done -> abrir ventana informativa (proxima alarma)
            self._alarm_info(st)

    def _render_alarm(self, st) -> None:
        scn, pg, pos = st["tkey"]
        if scn != self.scene_idx or pg != self.current:
            return
        key = st["key"]; cfg = st["cfg"]
        phys = self._phys_pos(pos)
        label = self._alarm_time_label(cfg)
        try:
            status = st["status"]
            if status == "ringing":
                col = self._alarm_color(cfg)
                bg = col if st["blink_on"] else (10, 10, 10)
                self.device.set_key(phys, text=label, fg=(255, 255, 255), bg=bg,
                                    font=key.font, refresh=True, rotate=self.rotate)
            elif status == "snoozed":
                self.device.set_key(phys, text="Zzz\n" + label, fg=(210, 200, 120),
                                    bg=(45, 40, 20), font=key.font, refresh=True, rotate=self.rotate)
            elif status == "done":
                try:
                    from . import device as _dev
                    from PIL import Image, ImageDraw
                    sz = _dev.KEY_IMAGE_SIZE
                    img = Image.new("RGB", (sz, sz), (22, 34, 26))
                    d = ImageDraw.Draw(img)
                    f = _dev._font(15, key.font)
                    tw = d.textlength(label, font=f)
                    d.text(((sz - tw) / 2, 4), label, font=f, fill=(150, 170, 150))
                    d.line([(sz * 0.26, sz * 0.62), (sz * 0.44, sz * 0.80)], fill=(70, 210, 110), width=5)
                    d.line([(sz * 0.44, sz * 0.80), (sz * 0.76, sz * 0.40)], fill=(70, 210, 110), width=5)
                    if self.rotate:
                        img = img.rotate(-int(self.rotate), expand=False)
                    self.device.set_key_image(phys, img, refresh=True)
                except Exception as e:
                    print(f"[alarm] done render: {e}")
                    self.device.set_key(phys, text=label + "\nOK", fg=(120, 220, 140),
                                        bg=(22, 34, 26), font=key.font, refresh=True, rotate=self.rotate)
            else:  # armed
                self.device.set_key(phys, text=label, fg=(200, 210, 235), bg=(22, 30, 48),
                                    font=key.font, refresh=True, rotate=self.rotate)
        except Exception as e:
            print(f"[alarm] render: {e}")

    def _render_current_alarms(self) -> None:
        for st in self._alarms.values():
            scn, pg, _pos = st["tkey"]
            if scn == self.scene_idx and pg == self.current:
                self._render_alarm(st)

    def _alarm_sound_start(self, urgent=False) -> None:
        try:
            import winsound
            snd = "SystemHand" if urgent else "SystemExclamation"
            winsound.PlaySound(snd, winsound.SND_ALIAS | winsound.SND_ASYNC | winsound.SND_LOOP)
        except Exception as e:
            print(f"[alarm] sound: {e}")

    def _alarm_sound_stop_if_idle(self) -> None:
        if any(s["status"] == "ringing" and s["cfg"].get("sound", True) for s in self._alarms.values()):
            return
        self._alarm_sound_stop()

    def _alarm_sound_stop(self) -> None:
        try:
            import winsound
            winsound.PlaySound(None, 0)
        except Exception:
            pass

    def _spawn_alarm_popup(self, note, when, prio, mode, extras=None):
        import subprocess
        import sys as _sys
        flags = 0x08000000   # CREATE_NO_WINDOW
        tail = [str(x) for x in (extras or [])]
        try:
            if getattr(_sys, "frozen", False):
                args = [_sys.executable, "--alarm-popup", note, when, prio, mode] + tail
            else:
                script = os.path.join(os.path.dirname(os.path.dirname(__file__)), "alarm_popup.py")
                args = [_sys.executable, script, note, when, prio, mode] + tail
            return subprocess.Popen(args, creationflags=flags)
        except Exception as e:
            print(f"[alarm] popup: {e}")
            return None

    def _config_path(self):
        try:
            import m18_paths
            return m18_paths.config_path()
        except Exception:
            return ""

    def _alarm_note(self, st):
        cfg = st["cfg"]
        return (cfg.get("note") or (st["key"].text or "Alarm")).replace("\n", " ").strip() or "Alarm"

    def _alarm_popup(self, st):
        cfg = st["cfg"]
        return self._spawn_alarm_popup(self._alarm_note(st), self._alarm_time_label(cfg),
                                       cfg.get("priority", "normal"), "ring")

    def _alarm_info(self, st) -> None:
        """Ventana informativa (proxima alarma) al pulsar una alarma armada."""
        if self._alarm_info_proc is not None and self._alarm_info_proc.poll() is None:
            return
        import datetime as _dt
        cfg = st["cfg"]
        nf = st.get("next_fire")
        rep = cfg.get("repeat", "once")
        if st["status"] == "done" or nf is None:
            when = "Done"
        else:
            try:
                today = _dt.date.today()
                d = nf.date()
                if d == today:
                    pfx = "Today"
                elif d == today + _dt.timedelta(days=1):
                    pfx = "Tomorrow"
                else:
                    pfx = nf.strftime("%a %d")
                when = f"Next: {pfx} {nf.strftime('%H:%M')}"
            except Exception:
                when = ""
        when = f"{when}   ·   {rep}"
        si, pi, pos = st["tkey"]
        self._alarm_info_proc = self._spawn_alarm_popup(
            self._alarm_note(st), when, cfg.get("priority", "normal"), "info",
            extras=[self._alarm_state_path(), self._config_path(), si, pi, pos])

    def _close_alarm_popup(self, st) -> None:
        p = st.get("popup")
        if p is not None and p.poll() is None:
            try:
                p.terminate()
            except Exception:
                pass
        st["popup"] = None

    # --- Recorder (categoria Practical) -------------------------------------
    HOLD_THRESHOLD = 0.4   # s: < esto = clic (abre ventana); >= esto = grabar
    LONG_PRESS = 0.5       # Long Recorder: >= esto = pulsacion larga (abre ventana)

    def _ensure_recorder(self):
        if self._recorder is None:
            try:
                from . import recorder as _recmod
                self._recorder = _recmod.Recorder()
            except Exception as e:
                print(f"[rec] init: {e}")
        return self._recorder

    def _reclog(self, msg):
        """Traza de diagnostico a <data_dir>/recorder_debug.log (no falla nunca)."""
        try:
            import m18_paths
            import datetime as _dt
            p = os.path.join(m18_paths.data_dir(), "recorder_debug.log")
            with open(p, "a", encoding="utf-8") as f:
                f.write(_dt.datetime.now().strftime("%H:%M:%S ") + msg + "\n")
        except Exception:
            pass

    def _rec_recover_if_stuck(self, rec):
        """Si el grabador quedo grabando sin estado activo asociado, lo libera."""
        if rec is not None and rec.is_recording() and not self._rec_active and not self._rec_toggle:
            self._reclog("recover: grabador pegado -> stop")
            try:
                rec.stop()
            except Exception as e:
                self._reclog(f"recover stop err: {e}")

    def _recorder_event(self, logical, key, cmd, pressed) -> None:
        import time as _t
        if pressed:
            rec = self._ensure_recorder()
            self._reclog(f"HOLD press rec={rec is not None} rec_on={rec.is_recording() if rec else '-'}")
            if rec is None:
                return
            self._rec_recover_if_stuck(rec)
            if rec.is_recording():
                self._reclog("HOLD press: ya grabando (otra sesion) -> ignore")
                return
            cfg = cmd.cfg
            from . import recorder as _recmod
            path = rec.start(folder=_recmod.recordings_dir("hold"),
                             device=cfg.get("device", ""),
                             samplerate=int(cfg.get("samplerate", 44100)),
                             channels=int(cfg.get("channels", 1)),
                             fmt=cfg.get("format", "mp3"),
                             quality=cfg.get("quality", "medium"))
            self._reclog(f"HOLD start dev={cfg.get('device','')!r} -> {path} rec_on={rec.is_recording()}")
            self._rec_active = {"tkey": (self.scene_idx, self.current, logical),
                                "key": key, "press": _t.monotonic(), "started": path is not None}
            self._rec_blink = True
            self._rec_blink_next = _t.monotonic() + 0.4
            self._render_recorder(logical, key)
        else:
            st = self._rec_active
            self._rec_active = None
            rec = self._recorder
            held = (_t.monotonic() - st["press"]) if st else 0.0
            final = rec.stop() if (rec is not None and rec.is_recording()) else None
            self._reclog(f"HOLD release held={held:.2f} final={final}")
            if held < self.HOLD_THRESHOLD:
                # clic corto: descartar la micro-grabacion y abrir la ventana
                if final:
                    try:
                        from . import recorder as _recmod
                        _recmod.delete_recording(final)
                    except Exception:
                        pass
                self._open_recorder("hold")
            if st:
                s, p, pos = st["tkey"]
                if s == self.scene_idx and p == self.current:
                    self._render_recorder(pos, st["key"])

    def _tick_recorder(self) -> None:
        import time as _t
        mono = _t.monotonic()
        # Long Recorder: si se mantiene presionado mas de LONG_PRESS, era una
        # pulsacion larga -> descartar la grabacion recien iniciada y abrir la ventana.
        lp = self._rect_press
        if lp is not None and not lp["opened"] and (mono - lp["press"]) >= self.LONG_PRESS:
            lp["opened"] = True
            if self._rec_toggle is not None and self._recorder is not None:
                final = self._recorder.stop() if self._recorder.is_recording() else None
                if final:
                    try:
                        from . import recorder as _recmod
                        _recmod.delete_recording(final)
                    except Exception:
                        pass
                active = self._rec_toggle
                self._rec_toggle = None
                s, p, pos = active["tkey"]
                if s == self.scene_idx and p == self.current:
                    self._render_recorder(pos, active["key"], toggle=True)
            self._open_recorder("long")
        # al cerrarse la ventana de grabaciones (pudo borrar/crear) -> refrescar
        # el badge de conteo de las teclas Recorder de la pagina actual.
        if self._rec_win_open and (self._rec_proc is None or self._rec_proc.poll() is not None):
            self._rec_win_open = False
            if self._rec_active is None and self._rec_toggle is None:
                self._render_current_recorders()
        # parpadeo "REC" de la grabacion en curso (mantener-presionado o Long Recorder)
        st = self._rec_active or self._rec_toggle
        if st is not None and mono >= self._rec_blink_next:
            self._rec_blink = not self._rec_blink
            self._rec_blink_next = mono + 0.4
            s, p, pos = st["tkey"]
            if s == self.scene_idx and p == self.current:
                self._render_recorder(pos, st["key"], toggle=bool(self._rec_toggle))

    def _render_recorder(self, pos, key, toggle=False) -> None:
        phys = self._phys_pos(pos)
        st = self._rec_toggle if toggle else self._rec_active
        active = bool(st) and self._recorder is not None and self._recorder.is_recording()
        try:
            if active:   # grabando: cronometro REC, sin badge
                el = int(self._recorder.elapsed())
                bg = (210, 40, 40) if self._rec_blink else (45, 12, 12)
                self.device.set_key(phys, text=f"REC\n{el // 60:02d}:{el % 60:02d}",
                                    fg=(255, 255, 255), bg=bg, font=key.font,
                                    refresh=True, rotate=self.rotate)
                return
            # inactivo: componer la tecla y superponer un badge con el numero de
            # grabaciones de ESTE tipo (Long y Hold se cuentan por separado).
            from . import device as _dev
            from . import recorder as _recmod
            from PIL import ImageDraw
            kind = "long" if toggle else "hold"
            if key.image or key.text:   # icono/titulo elegido por el usuario
                img = _dev.compose_key_image(text=key.text, image=key.image or None,
                                             fg=tuple(key.fg) if key.fg else (255, 255, 255),
                                             bg=tuple(key.bg) if key.bg else (40, 22, 22),
                                             font=key.font, rotate=0)
            else:
                img = _dev.compose_key_image(text="REC", image=None, fg=(230, 210, 210),
                                             bg=(40, 22, 22), font=key.font, rotate=0)
            cnt = _recmod.count_recordings(kind)
            if cnt > 0:   # badge con el numero de grabaciones (esquina sup-derecha)
                sz = _dev.KEY_IMAGE_SIZE
                d = ImageDraw.Draw(img)
                r = 12
                cx = sz - r - 1; cy = r + 1
                d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(45, 120, 230))
                s = str(cnt) if cnt < 100 else "99+"
                bf = _dev._font(14 if len(s) < 2 else 11)
                tw = d.textlength(s, font=bf); ba, bd = bf.getmetrics()
                d.text((cx - tw / 2, cy - (ba + bd) / 2), s, font=bf, fill=(255, 255, 255))
            lk = self._long_press_kind(key)   # distintivo de long-press (⟲ / ••)
            if lk:
                self._draw_lp_marker(img, lk, self._lp_phase)
            if self.rotate:
                img = img.rotate(-int(self.rotate), expand=False)
            self.device.set_key_image(phys, img, refresh=True)
        except Exception as e:
            print(f"[rec] render: {e}")

    def _render_current_recorders(self) -> None:
        for pos, key in self.page.keys.items():
            if isinstance(key.on_press, RecorderCommand):
                self._render_recorder(pos, key)
            elif isinstance(key.on_press, RecorderToggleCommand):
                self._render_recorder(pos, key, toggle=True)

    # --- Long Recorder: un toque inicia/para la grabacion; long press abre la ventana
    def _recorder_toggle_event(self, logical, key, cmd, pressed) -> None:
        import time as _t
        if pressed:
            rec = self._ensure_recorder()
            self._reclog(f"LONG press rec={rec is not None} rec_on={rec.is_recording() if rec else '-'} "
                         f"toggle={self._rec_toggle is not None}")
            if rec is None:
                return
            # ya grabando (por esta tecla) -> volver a pulsar DETIENE (y guarda) al instante
            if self._rec_toggle is not None:
                self._rect_press = None
                self._reclog("LONG press: detener grabacion en curso")
                self._stop_toggle_recording()
                return
            self._rec_recover_if_stuck(rec)
            if rec.is_recording():
                self._reclog("LONG press: ya grabando (otra sesion) -> ignore")
                return   # hay otra grabacion (Hold and Record) en curso
            # inactivo -> empezar a grabar YA (feedback inmediato en la tecla)
            cfg = cmd.cfg
            from . import recorder as _recmod
            path = rec.start(folder=_recmod.recordings_dir("long"),
                             device=cfg.get("device", ""),
                             samplerate=int(cfg.get("samplerate", 44100)),
                             channels=int(cfg.get("channels", 1)),
                             fmt=cfg.get("format", "mp3"),
                             quality=cfg.get("quality", "medium"))
            self._reclog(f"LONG start dev={cfg.get('device','')!r} -> {path} rec_on={rec.is_recording()}")
            if not path:
                print("[rec] long recorder: no se pudo iniciar la grabacion")
                return
            tkey = (self.scene_idx, self.current, logical)
            self._rec_toggle = {"tkey": tkey, "key": key}
            # pendiente: si se mantiene presionado, se interpreta como long press
            self._rect_press = {"tkey": tkey, "key": key, "press": _t.monotonic(), "opened": False}
            self._rec_blink = True
            self._rec_blink_next = _t.monotonic() + 0.4
            self._render_recorder(logical, key, toggle=True)
        else:
            # soltar: si fue long press ya se manejo (ventana abierta, grabacion
            # descartada); si fue un toque corto, la grabacion sigue activa y se
            # detendra en la siguiente pulsacion. Nada mas que hacer aqui.
            self._rect_press = None

    def _stop_toggle_recording(self) -> None:
        rec = self._recorder
        active = self._rec_toggle
        self._rec_toggle = None
        if rec is not None and rec.is_recording():
            rec.stop()
        if active:
            s, p, pos = active["tkey"]
            if s == self.scene_idx and p == self.current:
                self._render_recorder(pos, active["key"], toggle=True)

    def _open_recorder(self, kind: str = "") -> None:
        import subprocess
        import sys as _sys
        if self._rec_proc is not None and self._rec_proc.poll() is None:
            return
        flags = 0x08000000   # CREATE_NO_WINDOW
        tail = [kind] if kind in ("hold", "long") else []
        try:
            if getattr(_sys, "frozen", False):
                args = [_sys.executable, "--recorder-popup"] + tail
            else:
                script = os.path.join(os.path.dirname(os.path.dirname(__file__)), "recorder_popup.py")
                args = [_sys.executable, script] + tail
            self._rec_proc = subprocess.Popen(args, creationflags=flags)
            self._rec_win_open = True
        except Exception as e:
            print(f"[rec] window: {e}")

    # --- Calculadora (categoria Practical) ----------------------------------
    def _calc_log(self, msg) -> None:
        """Traza de diagnostico a <data_dir>/calc_debug.log (no falla nunca)."""
        try:
            import m18_paths
            import datetime as _dt
            p = os.path.join(m18_paths.data_dir(), "calc_debug.log")
            with open(p, "a", encoding="utf-8") as f:
                f.write(_dt.datetime.now().strftime("%H:%M:%S ") + msg + "\n")
        except Exception:
            pass

    def _calc_event(self, logical, key, cmd, pressed) -> None:
        import time as _t
        role = (cmd.cfg.get("role") or "").strip()
        value = str(cmd.cfg.get("value", ""))
        self._calc_log(f"event role={role!r} val={value!r} pressed={pressed}")
        if role in ("add", "sub", "back"):
            # pulsacion larga por TICK (feedback al mantener); corta al soltar.
            if pressed:
                self._calc_press = {"mono": _t.monotonic(), "role": role, "fired": False}
                return
            pr = self._calc_press
            self._calc_press = None
            if pr and not pr["fired"]:   # solo corta si la larga no se disparo ya
                if role == "add":
                    self._calc_apply_op("+")
                elif role == "sub":
                    self._calc_apply_op("-")
                else:
                    self._calc_backspace()
                self._calc_render()
            return
        # digito / punto / igual: actuan al pulsar
        if not pressed:
            return
        if role == "digit":
            self._calc_input_digit(value)
        elif role == "dot":
            self._calc_input_dot()
        elif role == "enter":
            self._calc_equals()
        self._calc_render()
        self._calc_log(f"  -> display={self._calc_display()!r}")

    def _tick_calc(self) -> None:
        """Dispara la accion LARGA de +,-,back al alcanzar el umbral (sin soltar)."""
        pr = self._calc_press
        if not pr or pr["fired"]:
            return
        import time as _t
        if (_t.monotonic() - pr["mono"]) >= self.LONG_PRESS:
            pr["fired"] = True
            role = pr["role"]
            if role == "add":
                self._calc_apply_op("*")
            elif role == "sub":
                self._calc_apply_op("/")
            else:   # back
                self._calc_clear()
            self._calc_render()
            self._calc_log(f"  LONG {role} -> display={self._calc_display()!r}")

    def _calc_cur_value(self) -> float:
        s = self._calc["cur"]
        try:
            return float(s) if s not in ("", ".", "-", "-.") else 0.0
        except ValueError:
            return 0.0

    @staticmethod
    def _calc_compute(a, op, b):
        a = 0.0 if a is None else a
        try:
            if op == "+":
                return a + b
            if op == "-":
                return a - b
            if op == "*":
                return a * b
            if op == "/":
                return None if b == 0 else a / b
        except Exception:
            return None
        return b

    def _calc_input_digit(self, d) -> None:
        c = self._calc
        if c["err"] or c["fresh"]:
            c["cur"] = ""; c["err"] = False; c["fresh"] = False
        if len(c["cur"].replace(".", "").replace("-", "")) >= 12:
            return
        if c["cur"] in ("", "0"):
            c["cur"] = d
        else:
            c["cur"] += d

    def _calc_input_dot(self) -> None:
        c = self._calc
        if c["err"] or c["fresh"]:
            c["cur"] = "0"; c["err"] = False; c["fresh"] = False
        if "." not in c["cur"]:
            c["cur"] = (c["cur"] or "0") + "."

    def _calc_apply_op(self, op) -> None:
        c = self._calc
        if c["err"]:
            self._calc_clear()
        cur = self._calc_cur_value()
        if c["op"] is not None and not c["fresh"]:
            res = self._calc_compute(c["acc"], c["op"], cur)
            if res is None:
                self._calc_set_error(); return
            c["acc"] = res
        elif not c["fresh"] or c["acc"] is None:
            c["acc"] = cur
        c["op"] = op
        c["cur"] = ""
        c["fresh"] = True

    def _calc_equals(self) -> None:
        c = self._calc
        if c["err"]:
            return
        if c["op"] is None:
            if c["cur"] not in ("", ".", "-"):
                c["acc"] = self._calc_cur_value()
                c["cur"] = ""; c["fresh"] = True
            return
        b = self._calc_cur_value() if not c["fresh"] else (c["acc"] if c["acc"] is not None else 0.0)
        res = self._calc_compute(c["acc"], c["op"], b)
        if res is None:
            self._calc_set_error(); return
        c["acc"] = res
        c["op"] = None
        c["cur"] = ""
        c["fresh"] = True

    def _calc_backspace(self) -> None:
        c = self._calc
        if c["err"]:
            self._calc_clear(); return
        if c["cur"]:
            c["cur"] = c["cur"][:-1]

    def _calc_clear(self) -> None:
        self._calc = {"cur": "", "acc": None, "op": None, "fresh": True, "err": False}

    def _calc_set_error(self) -> None:
        self._calc = {"cur": "", "acc": None, "op": None, "fresh": True, "err": True}

    @staticmethod
    def _calc_fmt(v) -> str:
        if v is None:
            return "ERR"
        try:
            if v == int(v) and abs(v) < 1e15:
                return str(int(v))
        except (ValueError, OverflowError):
            return "ERR"
        s = f"{v:.6f}".rstrip("0").rstrip(".")
        if len(s.replace("-", "").replace(".", "")) > 12:
            s = f"{v:.4g}"
        return s

    def _calc_display(self) -> str:
        c = self._calc
        if c["err"]:
            return "ERR"
        if c["cur"] not in ("", ".", "-", "-."):
            return c["cur"]
        if c["acc"] is not None:
            return self._calc_fmt(c["acc"])
        return "0"

    def _calc_render(self) -> None:
        disp = self._calc_display()
        for pos, key in self.page.keys.items():
            op = key.on_press
            if isinstance(op, CalcCommand) and (op.cfg.get("role") == "enter"):
                try:
                    self.device.set_key(self._phys_pos(pos), text=disp,
                                        fg=tuple(key.fg) if key.fg else (255, 255, 255),
                                        bg=tuple(key.bg) if key.bg else (20, 40, 60),
                                        font=key.font, refresh=True, rotate=self.rotate)
                except Exception as e:
                    print(f"[calc] render: {e}")

    # --- Sequence Repeat (grabador de macro raton+teclado) ------------------
    def _seq_path(self, tkey):
        import m18_paths
        d = os.path.join(m18_paths.data_dir(), "sequences")
        try:
            os.makedirs(d, exist_ok=True)
        except Exception:
            pass
        s, p, pos = tkey
        return os.path.join(d, f"seq_{s}_{p}_{pos}.json")

    def _seq_save(self, tkey, steps, rec_monitors):
        try:
            with open(self._seq_path(tkey), "w", encoding="utf-8") as f:
                json.dump({"steps": steps, "rec_monitors": rec_monitors or []}, f)
        except Exception as e:
            print("[seq] save:", e)

    def _seq_load(self, tkey):
        try:
            with open(self._seq_path(tkey), "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def _seq_event(self, logical, key, cmd, pressed) -> None:
        import time as _t
        tkey = (self.scene_idx, self.current, logical)
        if pressed:
            if self._seq_rec is not None:       # grabando -> re-pulsar DETIENE
                self._seq_stop_recording()
                return
            if self._seq_play is not None:      # reproduciendo -> ignorar (ESC para)
                return
            # en reposo: marcar pulsacion (tap vs long press se decide luego)
            self._seq_press = {"tkey": tkey, "key": key, "cmd": cmd,
                               "press": _t.monotonic(), "opened": False}
        else:
            pr = self._seq_press
            self._seq_press = None
            if pr and not pr["opened"]:
                if (_t.monotonic() - pr["press"]) < self.LONG_PRESS:   # TAP -> reproducir
                    self._seq_start_playback(pr["tkey"], pr["key"], pr["cmd"])

    @staticmethod
    def _seq_countdown(stop_event, color):
        """Cuenta regresiva 3-2-1 en el aviso flotante (el mismo contador que ya
        existe, modo 'count'). Devuelve False si se cancelo durante la cuenta."""
        import time as _t
        for n in (3, 2, 1):
            if stop_event.is_set():
                return False
            try:
                actions.show_overlay(str(n), color, mode="count")
            except Exception:
                pass
            _t.sleep(0.9)
        try:
            actions.close_overlay()
        except Exception:
            pass
        return not stop_event.is_set()

    def _seq_rec_thread(self, stop_event, holder, cfg):
        # cuenta regresiva ANTES de grabar (da tiempo a colocarse)
        if not self._seq_countdown(stop_event, "#c0392b"):
            holder["steps"] = []
            holder["done"] = True
            return
        holder["recording"] = True   # ahora el tile muestra REC
        try:
            steps, mons = actions.record_macro_loop(
                lambda: stop_event.is_set(),
                rec_keys=bool(cfg.get("record_keys", True)),
                stop_hotkey=cfg.get("stop", "ESC"))
            holder["steps"] = steps
            holder["rec_monitors"] = mons
        except Exception as e:
            print("[seq] rec:", e)
            holder["steps"] = []
        holder["done"] = True

    def _seq_start_recording(self, tkey, key, cmd) -> None:
        import threading as _th
        import time as _t
        if self._seq_rec is not None or self._seq_play is not None:
            return
        stop_event = _th.Event()
        holder = {"recording": False}
        th = _th.Thread(target=self._seq_rec_thread,
                        args=(stop_event, holder, cmd.cfg), daemon=True)
        self._seq_rec = {"tkey": tkey, "key": key, "stop": stop_event,
                         "thread": th, "holder": holder}
        self._seq_blink = True
        self._seq_blink_next = _t.monotonic() + 0.4
        th.start()   # durante la cuenta el overlay muestra 3-2-1; el tile sigue idle

    def _seq_stop_recording(self) -> None:
        rec = self._seq_rec
        if rec is None:
            return
        rec["stop"].set()
        rec["thread"].join(timeout=1.5)
        self._seq_finalize_recording()

    def _seq_finalize_recording(self) -> None:
        rec = self._seq_rec
        if rec is None:
            return
        self._seq_rec = None
        try:
            actions.close_overlay()
        except Exception:
            pass
        steps = rec["holder"].get("steps", [])
        if steps:
            self._seq_save(rec["tkey"], steps, rec["holder"].get("rec_monitors"))
        self._render_seq_key(rec["tkey"], rec["key"], "idle")

    def _seq_start_playback(self, tkey, key, cmd) -> None:
        import threading as _th
        import time as _t
        if self._seq_rec is not None or self._seq_play is not None:
            return
        data = self._seq_load(tkey)
        if not data or not data.get("steps"):
            return   # nada grabado todavia
        cfg = cmd.cfg
        act = actions.mouse_macro(
            data["steps"], repeat=int(cfg.get("repeat", 1)),
            stop=cfg.get("stop", "ESC"), overlay=False,   # sin banner; el tile muestra PLAY
            speed=float(cfg.get("speed", 1) or 1),
            rec_monitors=data.get("rec_monitors"))

        play = {"tkey": tkey, "key": key, "thread": None, "playing": False}

        def run():
            # cuenta regresiva ANTES de reproducir (mismo contador)
            if not self._seq_countdown(play.get("stop_event"), "#1f7a4d"):
                return
            play["playing"] = True   # ahora el tile muestra PLAY
            try:
                act(None)
            except Exception as e:
                print("[seq] play:", e)
        play["stop_event"] = _th.Event()
        th = _th.Thread(target=run, daemon=True)
        play["thread"] = th
        self._seq_play = play
        self._seq_blink = True
        self._seq_blink_next = _t.monotonic() + 0.4
        th.start()   # durante la cuenta el overlay muestra 3-2-1; el tile sigue idle

    def _tick_seq(self) -> None:
        import time as _t
        mono = _t.monotonic()
        # pulsacion larga -> empezar a grabar
        pr = self._seq_press
        if pr is not None and not pr["opened"] and (mono - pr["press"]) >= self.LONG_PRESS:
            pr["opened"] = True
            self._seq_start_recording(pr["tkey"], pr["key"], pr["cmd"])
        # fin de grabacion por hotkey de parada (el hilo marco 'done')
        rec = self._seq_rec
        if rec is not None and rec["holder"].get("done"):
            self._seq_finalize_recording()
        # fin de reproduccion
        play = self._seq_play
        if play is not None and not play["thread"].is_alive():
            self._seq_play = None
            self._render_seq_key(play["tkey"], play["key"], "idle")
        # parpadeo REC / PLAY (solo tras la cuenta regresiva; durante la cuenta el
        # tile sigue en reposo y el contador 3-2-1 se ve en el aviso flotante)
        rec_on = self._seq_rec is not None and self._seq_rec["holder"].get("recording")
        play_on = self._seq_play is not None and self._seq_play.get("playing")
        if (rec_on or play_on) and mono >= self._seq_blink_next:
            self._seq_blink = not self._seq_blink
            self._seq_blink_next = mono + 0.4
            if rec_on:
                self._render_seq_key(self._seq_rec["tkey"], self._seq_rec["key"], "rec")
            else:
                self._render_seq_key(self._seq_play["tkey"], self._seq_play["key"], "play")

    def _render_seq_key(self, tkey, key, state) -> None:
        s, p, pos = tkey
        if s != self.scene_idx or p != self.current:
            return
        phys = self._phys_pos(pos)
        try:
            if state == "rec":
                bg = (210, 40, 40) if self._seq_blink else (45, 12, 12)
                self.device.set_key(phys, text="REC", fg=(255, 255, 255), bg=bg,
                                    font=key.font, refresh=True, rotate=self.rotate)
            elif state == "play":
                bg = (30, 150, 70) if self._seq_blink else (12, 45, 20)
                self.device.set_key(phys, text="PLAY", fg=(255, 255, 255), bg=bg,
                                    font=key.font, refresh=True, rotate=self.rotate)
            else:   # reposo: titulo/icono (o "SEQ") + distintivo de long-press (⟲)
                self._render_lp_idle(pos, key, refresh=True)
        except Exception as e:
            print(f"[seq] render: {e}")

    def _render_current_seq(self) -> None:
        for pos, key in self.page.keys.items():
            if isinstance(key.on_press, SeqRepeatCommand):
                self._render_seq_key((self.scene_idx, self.current, pos), key, "idle")

    def _tick_lp_marker(self, dimmed) -> None:
        """Pulso lento del distintivo de long-press: alterna la fase cada ~0.9 s y
        re-pinta SOLO las teclas long-press en reposo de la pagina actual. Se omite
        con la pantalla apagada o mientras hay grabacion/reproduccion activa."""
        if dimmed or self._rec_active or self._rec_toggle or self._seq_rec or self._seq_play:
            return
        import time as _t
        mono = _t.monotonic()
        if mono < self._lp_next:
            return
        self._lp_next = mono + 0.9
        self._lp_phase = not self._lp_phase
        for pos, key in self.page.keys.items():
            if self._long_press_kind(key):
                self._render_lp_key(pos, key, refresh=True)

    # --- Reminders (categoria Practical, indicador global) ------------------
    def _rem_save(self):
        _reminders.save_store(self._rem_store)
        try:
            self._rem_mtime = os.path.getmtime(_reminders.reminders_path())
        except OSError:
            pass

    def _rem_find(self, rid):
        for r in self._rem_store.get("reminders", []):
            if r.get("id") == rid:
                return r
        return None

    def _tick_reminders(self) -> None:
        import datetime as _dt
        # recargar si la ventana cambio el archivo
        try:
            mt = os.path.getmtime(_reminders.reminders_path())
        except OSError:
            mt = 0
        if mt != self._rem_mtime:
            self._rem_mtime = mt
            self._rem_store = _reminders.load_store()
            self._render_current_reminders()
        now = _dt.datetime.now()
        # disparar los que vencen
        for r in _reminders.pending(self._rem_store):
            rid = r.get("id")
            if rid in self._rem_ring:
                continue
            due = _reminders.parse_due(r.get("due", ""))
            if due is not None and due <= now:
                self._rem_fire(r)
        # parpadeo de la tecla mientras algo suena
        if self._rem_ring:
            import time as _t
            mono = _t.monotonic()
            if mono >= self._rem_blink_next:
                self._rem_blink = not self._rem_blink
                self._rem_blink_next = mono + 0.5
                self._render_current_reminders()
        # resolver popups cerrados (0=completar, 10=posponer, 20/otro=descartar)
        for rid, st in list(self._rem_ring.items()):
            p = st.get("popup")
            if p is not None:
                rc = p.poll()
                if rc is not None:
                    st["popup"] = None
                    self._rem_resolve(rid, rc)

    def _rem_fire(self, r) -> None:
        import datetime as _dt
        rid = r.get("id")
        title = r.get("title") or "Reminder"
        _reminders.append_history(self._rem_store, title, "fired")
        r["last_fired"] = _dt.datetime.now().isoformat()
        self._rem_save()
        self._rem_ring[rid] = {"r": r, "popup": None}
        notify = r.get("notify", "both")
        if notify in ("sound", "both"):
            self._alarm_sound_start(urgent=(r.get("priority") == "urgent"))
        # ventana de aviso (siempre, para poder Completar/Posponer/Descartar)
        self._rem_ring[rid]["popup"] = self._spawn_reminder_fire(r)
        ex = r.get("exec")
        if ex and ex.get("kind") not in (None, "none", ""):
            self._run_timer_exec(ex)
        self._render_current_reminders()

    def _rem_resolve(self, rid, code) -> None:
        import datetime as _dt
        r = self._rem_find(rid)
        self._rem_ring.pop(rid, None)
        if r is None:
            self._rem_sound_idle(); return
        now = _dt.datetime.now()
        title = r.get("title") or "Reminder"
        repeat = r.get("repeat", "once")
        if code == 0:            # Completar
            _reminders.append_history(self._rem_store, title, "completed")
            if repeat == "once":
                r["status"] = "completed"
            else:
                nxt = _reminders.advance_due(_reminders.parse_due(r.get("due", "")) or now, repeat, r.get("days"))
                if nxt:
                    r["due"] = nxt.isoformat()
                else:
                    r["status"] = "completed"
        elif code == 10:         # Posponer
            mins = max(1, int(r.get("snooze_min", 10)))
            r["due"] = (now + _dt.timedelta(minutes=mins)).isoformat()
            r["snooze_count"] = int(r.get("snooze_count", 0)) + 1
            _reminders.append_history(self._rem_store, title, "snoozed")
        else:                    # Descartar (o cierre)
            if r.get("repeat_until_confirm"):
                # seguir avisando hasta confirmar: reintenta en 1 min
                r["due"] = (now + _dt.timedelta(minutes=1)).isoformat()
                _reminders.append_history(self._rem_store, title, "snoozed")
            elif repeat == "once":
                r["status"] = "completed"
                _reminders.append_history(self._rem_store, title, "dismissed")
            else:
                nxt = _reminders.advance_due(_reminders.parse_due(r.get("due", "")) or now, repeat, r.get("days"))
                r["due"] = nxt.isoformat() if nxt else r.get("due")
                if not nxt:
                    r["status"] = "completed"
                _reminders.append_history(self._rem_store, title, "dismissed")
        self._rem_save()
        self._rem_sound_idle()
        self._render_current_reminders()

    def _rem_sound_idle(self):
        if not self._rem_ring:
            self._alarm_sound_stop()

    def _render_current_reminders(self) -> None:
        for pos, key in self.page.keys.items():
            if isinstance(key.on_press, ReminderCommand):
                self._render_reminder(pos, key)

    def _render_reminder(self, pos, key) -> None:
        import datetime as _dt
        phys = self._phys_pos(pos)
        store = self._rem_store
        cnt = _reminders.pending_count(store)
        ringing = bool(self._rem_ring)
        try:
            from . import device as _dev
            from PIL import Image, ImageDraw
            sz = _dev.KEY_IMAGE_SIZE
            if ringing:
                rid = next(iter(self._rem_ring))
                rr = self._rem_ring[rid]["r"]
                col = _reminders.PRIORITY_COLORS.get(rr.get("priority", "normal"), (210, 150, 40))
                bg = col if self._rem_blink else (20, 20, 20)
                title = (rr.get("title") or "Reminder")[:10]
                img = _dev.compose_key_image(text=title, image=None, fg=(255, 255, 255),
                                             bg=bg, font=key.font, rotate=0)
            elif key.image:   # icono elegido -> usarlo de fondo (solo badge encima)
                img = _dev.compose_key_image(text=None, image=key.image,
                                             fg=tuple(key.fg) if key.fg else (255, 255, 255),
                                             bg=tuple(key.bg) if key.bg else (28, 32, 44),
                                             font=key.font, rotate=0)
            else:
                nxt = _reminders.next_reminder(store)
                bg = (28, 32, 44)
                if nxt:
                    due = _reminders.parse_due(nxt.get("due", ""))
                    tline = due.strftime("%H:%M") if due else ""
                    dline = ""
                    if due:
                        today = _dt.date.today()
                        if due.date() == today:
                            dline = "today"
                        elif due.date() == today + _dt.timedelta(days=1):
                            dline = "tmrw"
                        else:
                            dline = due.strftime("%m/%d")
                    txt = f"{(nxt.get('title') or 'Rem')[:9]}\n{tline}\n{dline}"
                else:
                    txt = "No\nreminders"
                img = _dev.compose_key_image(text=txt, image=None, fg=(210, 220, 240),
                                             bg=bg, font=key.font, rotate=0)
            if cnt > 0:   # badge con pendientes
                d = ImageDraw.Draw(img)
                r = 12
                cx = sz - r - 1; cy = r + 1
                d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(220, 60, 60))
                s = str(cnt) if cnt < 100 else "99+"
                bf = _dev._font(14 if len(s) < 2 else 11)
                tw = d.textlength(s, font=bf); ba, bd = bf.getmetrics()
                d.text((cx - tw / 2, cy - (ba + bd) / 2), s, font=bf, fill=(255, 255, 255))
            if self.rotate:
                img = img.rotate(-int(self.rotate), expand=False)
            self.device.set_key_image(phys, img, refresh=True)
        except Exception as e:
            print(f"[rem] render: {e}")

    def _spawn_reminder_fire(self, r):
        return self._spawn_reminder_popup("ring", r)

    def _open_reminders(self):
        if self._rem_proc is not None and self._rem_proc.poll() is None:
            return
        self._rem_proc = self._spawn_reminder_popup("manage", None)

    def _spawn_reminder_popup(self, mode, r):
        import subprocess
        import sys as _sys
        flags = 0x08000000
        extra = []
        if mode == "ring" and r is not None:
            extra = [r.get("id", ""), r.get("title", "Reminder"), r.get("note", ""),
                     r.get("due", ""), r.get("priority", "normal")]
        try:
            if getattr(_sys, "frozen", False):
                args = [_sys.executable, "--reminders-popup", mode] + extra
            else:
                script = os.path.join(os.path.dirname(os.path.dirname(__file__)), "reminders_popup.py")
                args = [_sys.executable, script, mode] + extra
            return subprocess.Popen(args, creationflags=flags)
        except Exception as e:
            print(f"[rem] popup: {e}")
            return None

    # --- To-Do (categoria Practical, indicador global) ----------------------
    def _tick_todos(self) -> None:
        try:
            mt = os.path.getmtime(_todos.todos_path())
        except OSError:
            mt = 0
        if mt != self._todo_mtime:
            self._todo_mtime = mt
            self._todo_store = _todos.load_store()
            self._render_current_todos()

    def _render_current_todos(self) -> None:
        for pos, key in self.page.keys.items():
            if isinstance(key.on_press, TodoCommand):
                self._render_todo(pos, key)

    def _render_todo(self, pos, key) -> None:
        import datetime as _dt
        phys = self._phys_pos(pos)
        store = self._todo_store
        pend = _todos.pending_count(store)
        today = _todos.today_count(store)
        nxt = _todos.next_task(store)
        try:
            from . import device as _dev
            from PIL import Image, ImageDraw
            sz = _dev.KEY_IMAGE_SIZE
            if key.image:   # el usuario eligio icono -> usarlo de fondo (solo badge encima)
                img = _dev.compose_key_image(text=None, image=key.image, fg=tuple(key.fg) if key.fg else (255, 255, 255),
                                             bg=tuple(key.bg) if key.bg else (24, 34, 28), font=key.font, rotate=0)
            elif nxt:
                title = (nxt.get("title") or "Task")[:9]
                due = _todos.parse_due(nxt.get("due"))
                dline = ""
                if due:
                    d = due.date(); tod = _dt.date.today()
                    dline = "today" if d == tod else ("tmrw" if d == tod + _dt.timedelta(days=1) else due.strftime("%m/%d"))
                col = _todos.PRIORITY_COLORS.get(nxt.get("priority", "normal"), (120, 130, 150))
                bg = (col[0] // 4, col[1] // 4, col[2] // 4)   # tinte oscuro de la prioridad
                txt = f"{title}\n{dline}" if dline else title
                img = _dev.compose_key_image(text=txt, image=None, fg=(220, 228, 240), bg=bg, font=key.font, rotate=0)
            else:
                img = _dev.compose_key_image(text="To-Do\n0", image=None, fg=(150, 170, 150),
                                             bg=(24, 34, 28), font=key.font, rotate=0)
            # badge: tareas de HOY (si hay) o pendientes totales
            badge = today if today > 0 else pend
            if badge > 0:
                d = ImageDraw.Draw(img)
                r = 12
                cx = sz - r - 1; cy = r + 1
                bcol = (220, 60, 60) if today > 0 else (90, 120, 200)
                d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=bcol)
                s = str(badge) if badge < 100 else "99+"
                bf = _dev._font(14 if len(s) < 2 else 11)
                tw = d.textlength(s, font=bf); ba, bd = bf.getmetrics()
                d.text((cx - tw / 2, cy - (ba + bd) / 2), s, font=bf, fill=(255, 255, 255))
            if self.rotate:
                img = img.rotate(-int(self.rotate), expand=False)
            self.device.set_key_image(phys, img, refresh=True)
        except Exception as e:
            print(f"[todo] render: {e}")

    def _open_todos(self):
        import subprocess
        import sys as _sys
        if self._todo_proc is not None and self._todo_proc.poll() is None:
            return
        flags = 0x08000000
        try:
            if getattr(_sys, "frozen", False):
                args = [_sys.executable, "--todos-popup"]
            else:
                script = os.path.join(os.path.dirname(os.path.dirname(__file__)), "todos_popup.py")
                args = [_sys.executable, script]
            self._todo_proc = subprocess.Popen(args, creationflags=flags)
        except Exception as e:
            print(f"[todo] window: {e}")


# valores del desplegable "apagar pantalla": clave -> segundos (0 = nunca)
SCREEN_OFF_SECONDS = {
    "never": 0, "1m": 60, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "2h": 7200, "system": 0,
}


def _parse_screen_off(val) -> int:
    if val in (None, "", "never", "system"):
        return 0
    if isinstance(val, (int, float)):
        return int(val)
    return SCREEN_OFF_SECONDS.get(str(val), 0)


# --- configuracion JSON -----------------------------------------------------
def _key_from_spec(ks: dict) -> Key:
    return Key(
        text=ks.get("text"),
        image=ks.get("image"),
        fg=tuple(ks.get("fg", (255, 255, 255))),
        bg=tuple(ks.get("bg", (0, 0, 0))),
        font=ks.get("font"),
        page_indicator=(ks.get("action", {}) or {}).get("type") == "page_indicator",
        on_press=actions.from_spec(ks.get("action")),
        on_release=actions.from_spec(ks.get("action_release")),
        on_double=actions.from_spec(ks.get("action_double")),
    )


def _combo_key(v):
    """Normaliza un id de tecla de combo: int (LCD 0..14) o str (lateral)."""
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, int):
        return v
    s = str(v)
    return int(s) if s.lstrip("-").isdigit() else s


def _combos_from_spec(specs) -> list:
    """Combos de 2 teclas a partir de la config de la pagina."""
    out = []
    for c in specs or []:
        ks = [_combo_key(k) for k in (c.get("keys") or [])]
        if len(ks) != 2 or ks[0] == ks[1]:
            continue   # solo combos de 2 teclas distintas
        out.append({"keys": ks, "action": actions.from_spec(c.get("action"))})
    return out


def migrate_cfg(cfg: dict) -> dict:
    """Convierte configs antiguas (pages planas) al modelo de escenas."""
    if cfg.get("scenes"):
        return cfg
    pages = cfg.get("pages")
    if pages is not None:
        cfg["scenes"] = [{"name": "Scene 1",
                          "default_page": int(cfg.get("default_page", 0)),
                          "pages": pages}]
    else:
        cfg["scenes"] = [{"name": "Scene 1", "default_page": 0, "pages": [{"keys": {}}]}]
    cfg.setdefault("default_scene", 0)
    return cfg


def _scenes_from_cfg(cfg: dict):
    """(scenes, aux) a partir del dict de config (ya migrado)."""
    scenes = []
    for sc in cfg.get("scenes", []):
        pages = []
        for p in sc.get("pages", []):
            keys = {int(pos): _key_from_spec(ks) for pos, ks in p.get("keys", {}).items()}
            combos = _combos_from_spec(p.get("combos"))
            pages.append(Page(p.get("name", "pagina"), keys, combos))
        if not pages:
            pages = [Page("default", {})]
        scenes.append(Scene(sc.get("name", "Scene"), pages, int(sc.get("default_page", 0))))
    if not scenes:
        scenes = [Scene("Scene 1", [Page("default", {})], 0)]
    aux = {name: _key_from_spec(ks) for name, ks in cfg.get("aux", {}).items()}
    return scenes, aux


def build_app_from_config(cfg: dict, device: StreamDockM18 | None = None) -> StreamDockApp:
    """Construye una StreamDockApp a partir de un dict de configuracion."""
    migrate_cfg(cfg)
    actions.set_routines(cfg.get("routines"))   # rutinas por nombre (antes de construir teclas)
    scenes, aux = _scenes_from_cfg(cfg)
    actions.set_obs_config(cfg.get("obs"))   # conexion OBS global
    app = StreamDockApp(
        scenes=scenes, aux=aux,
        brightness=int(cfg.get("brightness", 80)),
        default_scene=int(cfg.get("default_scene", 0)),
        device=device,
        device_cfg=cfg.get("device") or {},
    )
    try:
        app._raw_cfg = json.loads(json.dumps(cfg)) if cfg else {}
    except Exception:
        app._raw_cfg = None
    return app


def load_config(path: str, device: StreamDockM18 | None = None) -> StreamDockApp:
    """Carga un config.json y devuelve la app lista para .run()."""
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    return build_app_from_config(cfg, device=device)


def default_config() -> dict:
    """Config minima de ejemplo (1 escena con 2 paginas)."""
    return {
        "brightness": 80,
        "default_scene": 0,
        "scenes": [
            {"name": "Scene 1", "default_page": 0, "pages": [
                {"keys": {
                    "0": {"text": "Notas", "action": {"type": "run", "args": ["notepad.exe"]}},
                    "4": {"text": ">>", "bg": [0, 60, 0], "action": {"type": "next_page"}},
                }},
                {"keys": {
                    "0": {"text": "Web", "action": {"type": "open_url", "url": "https://google.com"}},
                    "4": {"text": "<<", "bg": [60, 0, 0], "action": {"type": "prev_page"}},
                }},
            ]},
        ],
        "aux": {
            # botones fisicos: ciclan entre ESCENAS (no entre paginas)
            "left": {"action": {"type": "scene_shift", "target": "prev"}},   # PREV
            "mid": {"action": {"type": "scene_shift", "target": "home"}},    # HOME -> escena por defecto
            "right": {"action": {"type": "scene_shift", "target": "next"}},  # NEXT
        },
    }
