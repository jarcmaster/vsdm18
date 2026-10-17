# -*- coding: utf-8 -*-
"""
Reproductor de audio para la accion "Audio Player: Play Audio".

Opciones soportadas (como el software oficial):
  - File       : ruta del archivo (wav, mp3, ogg, flac...).
  - Operation  : toggle (Play/Stop), restart (Play/Restart), pause (Play/Pause),
                 loop (reproduccion en bucle) o stop (detener).
  - Volume     : 0-100.
  - Output     : nombre del dispositivo de salida (vacio = predeterminado).

Motor: sounddevice + soundfile (dependencias OPCIONALES). Permiten elegir el
dispositivo de salida y ajustar el volumen por muestra. Si no estan instaladas,
la accion avisa por consola y no hace nada (el resto del programa sigue igual).

    pip install sounddevice soundfile

soundfile >= 0.12 trae libsndfile 1.1, que ya lee MP3.
"""

from __future__ import annotations

import threading
import time
import weakref

# Las librerias se importan de forma perezosa: solo cuando se usa el audio.
_sd = None
_sf = None
_np = None
_import_err = None

# Todos los reproductores vivos (para "Stop Audio", que detiene todo).
_players = weakref.WeakSet()
_players_lock = threading.Lock()


def _ensure_libs() -> bool:
    """Importa sounddevice/soundfile/numpy la primera vez. True si estan."""
    global _sd, _sf, _np, _import_err
    if _sd is not None:
        return True
    try:
        import numpy as np
        import sounddevice as sd
        import soundfile as sf
        _np, _sd, _sf = np, sd, sf
        return True
    except Exception as e:   # falta alguna libreria
        _import_err = e
        return False


# entradas de host API que no son dispositivos reales (hay que ocultarlas)
_FAKE_OUTPUTS = ("microsoft sound mapper", "primary sound driver",
                 "sound mapper", "mapeador de sonido")


def list_outputs():
    """
    Lista de nombres de dispositivos de salida (sin duplicados), en orden.
    Vacio si sounddevice no esta disponible. El nombre se usa tal cual en la
    config y se resuelve a indice al reproducir.

    Prioriza el host API WASAPI (nombres completos y enrutado por dispositivo,
    igual que el software oficial). Si no hay WASAPI, usa el resto de host APIs
    (los nombres MME se truncan a 31 caracteres).
    """
    if not _ensure_libs():
        return []
    try:
        devs = list(_sd.query_devices())
        apis = list(_sd.query_hostapis())
    except Exception as e:
        print("[audio] no se pudieron listar dispositivos:", e)
        return []

    wasapi = next((i for i, a in enumerate(apis)
                   if "wasapi" in a.get("name", "").lower()), None)

    def collect(api_filter):
        names, seen = [], set()
        for d in devs:
            if d.get("max_output_channels", 0) <= 0:
                continue
            if api_filter is not None and d.get("hostapi") != api_filter:
                continue
            name = (d.get("name") or "").strip()
            if not name or name.lower() in _FAKE_OUTPUTS or name in seen:
                continue
            seen.add(name)
            names.append(name)
        return names

    names = collect(wasapi) if wasapi is not None else []
    return names or collect(None)


def libs_available() -> bool:
    """True si sounddevice/soundfile se pudieron importar."""
    return _ensure_libs()


def _resolve_device(name):
    """Nombre de dispositivo -> indice de sounddevice. None = predeterminado."""
    name = (name or "").strip()
    if not name:
        return None
    try:
        devs = list(_sd.query_devices())
    except Exception:
        return None
    # 1) coincidencia exacta  2) empieza por  (los nombres MME se truncan a 31)
    for want in (lambda n: n == name, lambda n: n.startswith(name) or name.startswith(n)):
        for i, d in enumerate(devs):
            if d.get("max_output_channels", 0) > 0 and want(d.get("name", "")):
                return i
    return None


class _Player:
    """
    Reproduce un archivo en segundo plano con sounddevice. Reutilizable.

    IMPORTANTE (seguridad entre hilos): el stream de PortAudio lo crea, arranca,
    para y CIERRA un unico hilo (el worker), a traves de `with stream:`. `stop()`
    solo pide la parada con un Event y espera a que el worker cierre su stream.
    Asi se evita el cierre doble desde dos hilos, que provoca un segfault.
    """

    def __init__(self):
        self._stop = threading.Event()
        self._active = threading.Event()   # activo mientras hay un stream vivo
        self._paused = False
        with _players_lock:
            _players.add(self)

    def is_playing(self) -> bool:
        return self._active.is_set()

    def toggle_pause(self):
        self._paused = not self._paused

    def stop(self):
        """Pide la parada y espera a que el worker cierre su stream (<= ~0.5 s)."""
        self._stop.set()
        self._paused = False
        for _ in range(100):               # el callback corre cada pocos ms
            if not self._active.is_set():
                break
            time.sleep(0.005)

    def play(self, path, volume=1.0, device=None, loop=False):
        """Arranca la reproduccion de `path` desde el principio (no bloquea)."""
        self.stop()                        # corta lo anterior y espera su cierre
        if not _ensure_libs():
            print("[audio] instala 'sounddevice' y 'soundfile':", _import_err)
            return
        if not (path or "").strip():
            print("[audio] no hay archivo asignado")
            return
        try:
            data, sr = _sf.read(path, dtype="float32", always_2d=True)
        except Exception as e:
            print("[audio] no se pudo abrir", path, "->", e)
            return
        if float(volume) != 1.0:
            data = data * float(volume)
        dev = _resolve_device(device)
        self._stop.clear()
        self._paused = False
        threading.Thread(target=self._worker, args=(data, sr, dev, loop),
                         daemon=True).start()

    def _worker(self, data, sr, dev, loop):
        total = len(data)
        channels = data.shape[1]
        pos = {"i": 0}
        finished = threading.Event()

        def callback(outdata, frames, time_info, status):
            if self._stop.is_set():
                outdata[:] = 0
                raise _sd.CallbackStop()
            if self._paused:
                outdata[:] = 0      # silencio, sin avanzar
                return
            i = pos["i"]
            end = i + frames
            if end <= total:
                outdata[:] = data[i:end]
                pos["i"] = end
            else:
                n = total - i
                outdata[:n] = data[i:total]
                if loop and not self._stop.is_set():
                    rem = frames - n
                    # el archivo podria ser mas corto que 'rem'
                    rem = min(rem, total)
                    outdata[n:n + rem] = data[0:rem]
                    if n + rem < frames:
                        outdata[n + rem:] = 0
                    pos["i"] = rem
                else:
                    outdata[n:] = 0
                    pos["i"] = total
                    raise _sd.CallbackStop()

        try:
            stream = _sd.OutputStream(samplerate=sr, channels=channels, device=dev,
                                      dtype="float32", callback=callback,
                                      finished_callback=finished.set)
        except Exception as e:
            print("[audio] no se pudo abrir la salida:", e)
            return
        # el stream se arranca y se cierra SOLO en este hilo (context manager)
        self._active.set()
        try:
            with stream:
                finished.wait()
        except Exception as e:
            print("[audio] error de reproduccion:", e)
        finally:
            self._active.clear()


def stop_all():
    """Detiene todos los reproductores vivos (accion 'Stop Audio')."""
    with _players_lock:
        players = list(_players)
    for p in players:
        try:
            p.stop()
        except Exception:
            pass


def play_audio(file="", operation="toggle", volume=100, output=""):
    """
    Devuelve una accion (recibe el KeyEvent) que reproduce audio.

    operation: toggle | restart | pause | loop | stop
    volume:    0-100
    output:    nombre de dispositivo ('' = predeterminado)
    """
    player = _Player()
    try:
        vol = max(0, min(100, int(volume))) / 100.0
    except (TypeError, ValueError):
        vol = 1.0
    op = (operation or "toggle").lower()
    dev = output or None

    def action(event):
        if op == "stop":
            player.stop()
            return
        if op == "pause":
            if player.is_playing():
                player.toggle_pause()
            else:
                player.play(file, volume=vol, device=dev, loop=False)
            return
        if op == "restart":
            player.play(file, volume=vol, device=dev, loop=False)
            return
        if op == "loop":
            if player.is_playing():
                player.stop()
            else:
                player.play(file, volume=vol, device=dev, loop=True)
            return
        # toggle (Play/Stop), por defecto
        if player.is_playing():
            player.stop()
        else:
            player.play(file, volume=vol, device=dev, loop=False)

    return action


def action_from_spec(spec):
    """Construye la accion de audio desde un descriptor dict."""
    t = spec.get("type")
    if t == "stop_audio":
        return lambda event: stop_all()
    # play_audio
    return play_audio(spec.get("file", ""), spec.get("operation", "toggle"),
                      spec.get("volume", 100), spec.get("output", ""))
