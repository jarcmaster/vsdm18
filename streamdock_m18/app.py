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
from dataclasses import dataclass, field
from typing import Callable

from . import actions
from .actions import PageNav, DeviceCommand
from .device import KeyEvent, StreamDockM18

Action = Callable[[KeyEvent], None]


@dataclass
class Key:
    """Configuracion de una tecla."""
    text: str | None = None
    image: str | None = None            # ruta a imagen (solo teclas LCD)
    on_press: object | None = None      # Action o PageNav
    on_release: object | None = None
    fg: tuple = (255, 255, 255)
    bg: tuple = (0, 0, 0)
    font: str | None = None             # ruta a .ttf/.ttc (None = Arial)
    page_indicator: bool = False        # muestra "pagina/total" dinamico


@dataclass
class Page:
    """Una pagina = nombre + teclas (posicion -> Key)."""
    name: str = "pagina"
    keys: dict[int, Key] = field(default_factory=dict)


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
        self.device.clear_all_keys(refresh=False)
        for pos, key in self.page.keys.items():
            if key.page_indicator:
                key.text = f"{self.current + 1}/{len(self.pages)}"
            self._render_key(pos, key)
        self.device.refresh()

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

    def _render_key(self, pos: int, key: Key) -> None:
        if key.image or key.text:
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

    def reload_from_cfg(self, cfg: dict) -> None:
        """Recarga escenas/aux/ajustes desde un dict de config, en caliente."""
        migrate_cfg(cfg)
        scenes, aux = _scenes_from_cfg(cfg)
        actions.set_obs_config(cfg.get("obs"))
        self.scenes = scenes or [Scene("Scene 1", [Page("default", {})], 0)]
        self.aux = aux
        self.brightness = int(cfg.get("brightness", self.brightness))
        self.device_cfg = cfg.get("device") or {}
        self.default_scene = max(0, min(int(cfg.get("default_scene", 0)), len(self.scenes) - 1))
        self.scene_idx = min(self.scene_idx, len(self.scenes) - 1)
        self.current = max(0, min(self.current, len(self.pages) - 1))
        try:
            self.device.set_brightness(self.brightness)
            self.apply_device_cfg()
            self.render_page()
        except Exception as e:
            print(f"[reload] {e}")

    def run(self, poll_ms: int = 50, reload_cb=None) -> None:
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
                    elif screen_off_s and not dimmed and (now - last_activity) >= screen_off_s:
                        self.device.set_brightness(0)
                        dimmed = True
            except KeyboardInterrupt:
                print("\nSaliendo...")

    def _dispatch(self, ev: KeyEvent) -> None:
        # Buscar la tecla: LCD en la pagina actual; laterales en self.aux
        if ev.is_aux:
            key = self.aux.get(ev.key)
        else:
            # la posicion fisica pulsada -> posicion logica (inversa de la rotacion)
            logical = 14 - ev.key if self.rotate == 180 else ev.key
            key = self.page.keys.get(logical)
        if key is None:
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
        # Accion normal
        try:
            action(ev)
        except Exception as e:
            print(f"[accion {ev.key!r}] error: {e}")

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
        elif isinstance(tgt, tuple) and len(tgt) == 2 and tgt[0] == "scene":
            self.goto_scene(int(tgt[1]))
        elif isinstance(tgt, int):
            self.goto_page(tgt)


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
    )


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
            pages.append(Page(p.get("name", "pagina"), keys))
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
    scenes, aux = _scenes_from_cfg(cfg)
    actions.set_obs_config(cfg.get("obs"))   # conexion OBS global
    return StreamDockApp(
        scenes=scenes, aux=aux,
        brightness=int(cfg.get("brightness", 80)),
        default_scene=int(cfg.get("default_scene", 0)),
        device=device,
        device_cfg=cfg.get("device") or {},
    )


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
            "left": {"action": {"type": "prev_page"}},
            "mid": {"action": {"type": "home"}},       # boton central -> pagina por defecto
            "right": {"action": {"type": "next_page"}},
        },
    }
