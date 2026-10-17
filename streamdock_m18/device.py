"""
Driver de bajo nivel para el VSD / Mirabox Stream Dock M18.

Habla USB HID directamente con el dispositivo, sin el software del fabricante.
Protocolo documentado por la comunidad (bidoofgoo/streamdock-m18) y verificado
en hardware real.

Formato de escritura (salida):
    1025 bytes = [0x00 report id] + [reporte de 1024 bytes]
    El reporte empieza SIEMPRE con el prefijo "CRT\\0\\0" seguido del comando ASCII.
    Si el payload supera 1024 bytes (imagenes), se trocea en paginas de 1024.

Formato de lectura (entrada): reportes de 512 bytes.
    offset 0-7 : "ACK\\0\\0OK\\0"
    offset 9   : id de tecla (hardware)
    offset 10  : estado (0x01 = pulsada, 0x00 = soltada)
"""

from __future__ import annotations

import io
import struct
import time
from dataclasses import dataclass

import hid  # paquete: hidapi

try:
    from PIL import Image, ImageDraw, ImageFont
    _HAS_PIL = True
except ImportError:  # Pillow es opcional si solo lees teclas
    _HAS_PIL = False


# --- Identificacion del dispositivo -----------------------------------------
VENDOR_ID = 0x5548
PRODUCT_ID = 0x1000

# Interfaz de control: el M18 expone dos interfaces HID. La de control usa un
# usage_page vendor-defined (0xffa0); la otra es un teclado (no sirve).
_CONTROL_USAGE_PAGE = 0xFFA0

# --- Constantes del protocolo -----------------------------------------------
_PREFIX = b"CRT\x00\x00"          # prefijo magico de todo reporte de salida
_REPORT_SIZE = 1024               # tamano exacto del reporte (sin el report id)
_INPUT_SIZE = 512                 # tamano del reporte de entrada

KEY_IMAGE_SIZE = 64               # las teclas LCD son de 64x64 px
NUM_LCD_KEYS = 15
NUM_LEDS = 24                     # anillo RGB

# OJO: el dispositivo usa numeraciones DISTINTAS para escribir imagenes y para
# leer pulsaciones (estan invertidas verticalmente). Posicion logica 0..14 va
# de izquierda a derecha y de arriba a abajo:
#     0  1  2  3  4
#     5  6  7  8  9
#    10 11 12 13 14
#
# IDs para ESCRIBIR imagenes (posicion -> id hardware):
IMAGE_KEY_IDS = [
    0x0B, 0x0C, 0x0D, 0x0E, 0x0F,
    0x06, 0x07, 0x08, 0x09, 0x0A,
    0x01, 0x02, 0x03, 0x04, 0x05,
]
# IDs para LEER pulsaciones (posicion -> id hardware):
INPUT_KEY_IDS = [
    0x01, 0x02, 0x03, 0x04, 0x05,
    0x06, 0x07, 0x08, 0x09, 0x0A,
    0x0B, 0x0C, 0x0D, 0x0E, 0x0F,
]
KEY_IDS = IMAGE_KEY_IDS  # alias retro-compatible (escritura de imagenes)
_INPUT_ID_TO_POS = {hw: pos for pos, hw in enumerate(INPUT_KEY_IDS)}

# Botones fisicos auxiliares (no tienen pantalla). Nombre logico -> id hardware.
AUX_KEYS = {"left": 0x25, "mid": 0x30, "right": 0x31}
_AUX_ID_TO_NAME = {hw: name for name, hw in AUX_KEYS.items()}


@dataclass
class KeyEvent:
    """Un evento de tecla ya traducido a algo util."""
    key: int | str      # posicion 0..14 para teclas LCD, o "left"/"mid"/"right"
    pressed: bool       # True = se pulso, False = se solto
    is_aux: bool        # True si es un boton fisico auxiliar
    raw_id: int         # id de hardware original


class StreamDockM18:
    """
    Controlador del Stream Dock M18.

    Uso tipico:
        dev = StreamDockM18()
        dev.open()
        dev.set_brightness(80)
        dev.set_key_text(0, "Hola")
        for ev in dev.events():
            print(ev)
    """

    def __init__(self, vendor_id: int = VENDOR_ID, product_id: int = PRODUCT_ID):
        self.vendor_id = vendor_id
        self.product_id = product_id
        self._hid: hid.device | None = None
        self._brightness = 80
        self._last_keepalive = 0.0

    # --- ciclo de vida ------------------------------------------------------
    def _find_control_path(self) -> bytes | None:
        """Localiza la interfaz de control (usage_page vendor 0xffa0)."""
        matches = [d for d in hid.enumerate(self.vendor_id, self.product_id)]
        for d in matches:
            if d.get("usage_page") == _CONTROL_USAGE_PAGE:
                return d["path"]
        # fallback: interfaz 0 si no se detecta el usage_page
        for d in matches:
            if d.get("interface_number") == 0:
                return d["path"]
        return matches[0]["path"] if matches else None

    def open(self) -> None:
        """Abre el dispositivo (interfaz de control) y hace el handshake inicial."""
        self._hid = hid.device()
        path = self._find_control_path()
        if path is None:
            raise RuntimeError(
                "No se encontro el Stream Dock M18 "
                f"(VID={self.vendor_id:#06x} PID={self.product_id:#06x}). "
                "Revisa el cable USB-C (de datos) y cierra el software oficial."
            )
        self._hid.open_path(path)
        self._hid.set_nonblocking(True)
        # Secuencia de inicializacion: DIS -> CONNECT -> CLE 0xff -> STP
        self._cmd(b"DIS")
        self._cmd(b"CONNECT")
        self.clear_all_keys()
        self.refresh()

    def close(self) -> None:
        """Cierra limpiamente la conexion."""
        if self._hid is not None:
            try:
                self._cmd(b"HAN")   # hang up
            finally:
                self._hid.close()
                self._hid = None

    def __enter__(self) -> "StreamDockM18":
        self.open()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # --- envio de reportes (bajo nivel) -------------------------------------
    def _send(self, report: bytes) -> None:
        """Rellena a 1024 (o multiplo) y envia en paginas de 1024 bytes."""
        if self._hid is None:
            raise RuntimeError("Dispositivo no abierto; llama a open() primero")
        pad = (-len(report)) % _REPORT_SIZE
        if pad:
            report += b"\x00" * pad
        for i in range(0, len(report), _REPORT_SIZE):
            page = report[i:i + _REPORT_SIZE]
            self._hid.write(b"\x00" + page)   # 0x00 = report id

    def _cmd(self, command_and_payload: bytes) -> None:
        """Construye un reporte: CRT\\0\\0 + comando + payload."""
        self._send(_PREFIX + command_and_payload)

    def refresh(self) -> None:
        """STP: confirma/aplica las transferencias pendientes (imagenes, LEDs)."""
        self._cmd(b"STP")

    # --- pantalla / brillo --------------------------------------------------
    def set_brightness(self, value: int) -> None:
        """Brillo de las pantallas LCD (0-100)."""
        value = max(0, min(100, int(value)))
        self._brightness = value
        self._cmd(b"LIG\x00\x00" + bytes([value]))

    def keepalive(self) -> None:
        """
        Reenvia el brillo cada ~8s para que el dispositivo no vuelva a su
        pantalla de fabrica. Llamar periodicamente desde el bucle de eventos.
        """
        now = time.monotonic()
        if now - self._last_keepalive >= 8.0:
            self._cmd(b"LIG\x00\x00" + bytes([self._brightness]))
            self._last_keepalive = now

    # --- imagenes de las teclas ---------------------------------------------
    def _key_hw_id(self, pos: int) -> int:
        if pos not in range(NUM_LCD_KEYS):
            raise ValueError(f"posicion de tecla fuera de rango 0..14: {pos}")
        return KEY_IDS[pos]

    def set_key_jpeg(self, pos: int, jpeg: bytes, refresh: bool = True) -> None:
        """
        Envia un JPEG (debe ser 64x64) a la tecla `pos`.

        Protocolo correcto:
          1) reporte de cabecera: CRT + "BAT" + longitud(u16be) + id_tecla
          2) el JPEG en paginas CRUDAS de 1024 bytes, SIN el prefijo CRT
          3) STP para confirmar
        """
        if len(jpeg) > 10240:
            raise ValueError("JPEG demasiado grande (max 10240 bytes)")
        hw = self._key_hw_id(pos)
        # 1) cabecera BAT (con prefijo CRT, en su propia pagina).
        #    OJO: el comando es "BAT\0\0" (5 bytes), el tamano va DESPUES.
        self._cmd(b"BAT\x00\x00" + struct.pack(">H", len(jpeg)) + bytes([hw]))
        # 2) datos JPEG en paginas crudas de 1024 (sin prefijo)
        self._send(jpeg)
        if refresh:
            # 3) STP
            self.refresh()

    def set_key_image(self, pos: int, image, refresh: bool = True) -> None:
        """Acepta una ruta a imagen o un objeto PIL.Image y lo manda a la tecla."""
        self.set_key_jpeg(pos, _encode_key_image(image), refresh=refresh)

    def set_key_text(
        self,
        pos: int,
        text: str,
        fg=(255, 255, 255),
        bg=(0, 0, 0),
        refresh: bool = True,
    ) -> None:
        """Dibuja texto (hasta 3 lineas) en una tecla."""
        self.set_key_jpeg(pos, _render_text(text, fg, bg), refresh=refresh)

    def set_key(
        self,
        pos: int,
        text: str | None = None,
        image=None,
        fg=(255, 255, 255),
        bg=(0, 0, 0),
        font=None,
        refresh: bool = True,
        rotate: int = 0,
    ) -> None:
        """
        Compone y envia una tecla: imagen de fondo (opcional) con texto
        superpuesto (opcional, hasta 3 lineas con distribucion vertical).
        `rotate` gira la imagen (0/90/180/270).
        """
        self.set_key_jpeg(pos, compose_key_jpeg(text, image, fg, bg, font, rotate=rotate),
                          refresh=refresh)

    def clear_key(self, pos: int, refresh: bool = True) -> None:
        """Borra la imagen de una tecla."""
        hw = self._key_hw_id(pos)
        self._cmd(b"CLE\x00\x00\x00" + bytes([hw]))
        if refresh:
            self.refresh()

    def clear_all_keys(self, refresh: bool = True) -> None:
        """Borra todas las teclas (0xff)."""
        self._cmd(b"CLE\x00\x00\x00" + bytes([0xFF]))
        if refresh:
            self.refresh()

    # --- anillo RGB ---------------------------------------------------------
    def set_leds(self, colors, refresh: bool = True) -> None:
        """
        Fija el color de los 24 LEDs.
        `colors`: lista de tuplas (r, g, b). Si hay menos de 24 se rellena a negro.
        """
        data = bytearray()
        for i in range(NUM_LEDS):
            r, g, b = colors[i] if i < len(colors) else (0, 0, 0)
            data += bytes([r & 0xFF, g & 0xFF, b & 0xFF])
        self._cmd(b"SETLB" + bytes(data))
        if refresh:
            self.refresh()

    def set_led_brightness(self, value: int) -> None:
        """Brillo del anillo RGB (0-100). Enviar DESPUES del color."""
        value = max(0, min(100, int(value)))
        self._cmd(b"LBLIG" + bytes([value]))

    def set_led_color(self, rgb, brightness=None, refresh: bool = True) -> None:
        """Fija un color unico en todo el anillo RGB (y opcional su brillo)."""
        r, g, b = (int(rgb[0]) & 0xFF, int(rgb[1]) & 0xFF, int(rgb[2]) & 0xFF)
        self.set_leds([(r, g, b)] * NUM_LEDS, refresh=False)
        if brightness is not None:
            self.set_led_brightness(int(brightness))
        if refresh:
            self.refresh()

    def clear_leds(self) -> None:
        """Apaga/resetea el anillo RGB."""
        self._cmd(b"DELED")

    @staticmethod
    def enumerate_info(vendor_id: int = VENDOR_ID, product_id: int = PRODUCT_ID):
        """Info de los dispositivos conectados (serial, producto, release) via HID."""
        out = []
        try:
            for d in hid.enumerate(vendor_id, product_id):
                rel = d.get("release_number") or 0
                out.append({
                    "serial": d.get("serial_number") or "",
                    "product": d.get("product_string") or "",
                    "manufacturer": d.get("manufacturer_string") or "",
                    "release": rel,
                    "release_str": f"{(rel >> 8) & 0xFF}.{rel & 0xFF:02d}" if rel else "",
                })
        except Exception:
            pass
        # dedup por serial/path
        seen, uniq = set(), []
        for info in out:
            k = info["serial"] or id(info)
            if k not in seen:
                seen.add(k); uniq.append(info)
        return uniq

    # --- lectura de teclas --------------------------------------------------
    def read_event(self, timeout_ms: int = 50) -> KeyEvent | None:
        """Lee un evento de tecla, o None si no hay nada en `timeout_ms`."""
        if self._hid is None:
            raise RuntimeError("Dispositivo no abierto; llama a open() primero")
        data = self._hid.read(_INPUT_SIZE, timeout_ms)
        if not data or len(data) < 11:
            return None
        raw_id = data[9]
        state = data[10]
        pressed = state == 0x01
        if raw_id in _AUX_ID_TO_NAME:
            return KeyEvent(_AUX_ID_TO_NAME[raw_id], pressed, True, raw_id)
        if raw_id in _INPUT_ID_TO_POS:
            return KeyEvent(_INPUT_ID_TO_POS[raw_id], pressed, False, raw_id)
        return None  # id desconocido / reporte sin tecla

    def events(self, poll_ms: int = 50):
        """Generador infinito de KeyEvent. Incluye keepalive automatico."""
        while True:
            self.keepalive()
            ev = self.read_event(poll_ms)
            if ev is not None:
                yield ev


# --- utilidades de imagen ---------------------------------------------------
def _require_pil() -> None:
    if not _HAS_PIL:
        raise RuntimeError("Necesitas Pillow para imagenes/texto: pip install Pillow")


def _encode_key_image(image) -> bytes:
    """Normaliza una imagen (ruta o PIL.Image) a JPEG 64x64."""
    _require_pil()
    if isinstance(image, (str, bytes)) or hasattr(image, "__fspath__"):
        image = Image.open(image)
    image = image.convert("RGB").resize((KEY_IMAGE_SIZE, KEY_IMAGE_SIZE))
    return _to_jpeg(image)


def _font(size: int, font_path: str | None = None):
    for cand in (font_path, "arial.ttf"):
        if not cand:
            continue
        try:
            return ImageFont.truetype(cand, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _draw_multiline(img, text, fg, outline: bool, font_path: str | None = None) -> None:
    """
    Dibuja hasta 3 lineas (separadas por \\n) con distribucion vertical:
    1 linea = centro; 2 = arriba/abajo; 3 = arriba/medio/abajo. Centrado en X.
    `outline`: contorno negro para legibilidad (util sobre imagenes).
    """
    draw = ImageDraw.Draw(img)
    lines = text.split("\n")[:3]
    while len(lines) > 1 and lines[-1].strip() == "":
        lines.pop()
    lines = [ln for ln in lines if ln.strip() != ""] or ([lines[0]] if lines else [])
    n = len(lines)
    if n == 0:
        return
    size = img.width
    pad = 3
    font = _font(14, font_path)
    for fs in range(20, 6, -1):
        font = _font(fs, font_path)
        widths = [draw.textlength(ln, font=font) for ln in lines]
        asc, desc = font.getmetrics()
        lh = asc + desc
        if max(widths) <= size - 2 * pad and n * lh <= size - 2 * pad:
            break
    asc, desc = font.getmetrics()
    lh = asc + desc
    if n == 1:
        ys = [(size - lh) / 2]
    elif n == 2:
        ys = [pad, size - pad - lh]
    else:
        ys = [pad, (size - lh) / 2, size - pad - lh]
    for ln, y in zip(lines, ys):
        w = draw.textlength(ln, font=font)
        x = (size - w) / 2
        if outline:
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                draw.text((x + dx, y + dy), ln, font=font, fill=(0, 0, 0))
        draw.text((x, y), ln, font=font, fill=tuple(fg))


def compose_key_image(text=None, image=None, fg=(255, 255, 255), bg=(0, 0, 0), font=None,
                      rotate=0):
    """Compone una PIL.Image 64x64: imagen de fondo (opcional) + texto encima.
    `rotate` (0/90/180/270) gira la imagen final (el M18 no rota por hardware)."""
    _require_pil()
    base = Image.new("RGB", (KEY_IMAGE_SIZE, KEY_IMAGE_SIZE), tuple(bg))
    has_image = False
    if image is not None and image != "":
        try:
            im = image
            if isinstance(im, (str, bytes)) or hasattr(im, "__fspath__"):
                im = Image.open(im)
            base = im.convert("RGB").resize((KEY_IMAGE_SIZE, KEY_IMAGE_SIZE))
            has_image = True
        except Exception:
            base = Image.new("RGB", (KEY_IMAGE_SIZE, KEY_IMAGE_SIZE), tuple(bg))
    if text:
        _draw_multiline(base, text, fg, outline=has_image, font_path=font)
    if rotate:
        base = base.rotate(-int(rotate), expand=False)
    return base


def compose_key_jpeg(text=None, image=None, fg=(255, 255, 255), bg=(0, 0, 0), font=None,
                     rotate=0) -> bytes:
    """Como compose_key_image pero devuelve JPEG listo para el dispositivo."""
    return _to_jpeg(compose_key_image(text, image, fg, bg, font, rotate=rotate))


def _render_text(text: str, fg, bg) -> bytes:
    """Texto (hasta 3 lineas) sobre fondo solido -> JPEG 64x64."""
    return compose_key_jpeg(text, None, fg, bg)


def _to_jpeg(img, max_bytes: int = 10240) -> bytes:
    """Codifica a JPEG bajando la calidad hasta caber en `max_bytes`."""
    data = b""
    for quality in (90, 85, 70, 55, 40, 30, 20, 10):
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        data = buf.getvalue()
        if len(data) <= max_bytes:
            return data
    return data  # ultimo intento aunque pase (improbable en 64x64)
