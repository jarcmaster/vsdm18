# -*- coding: utf-8 -*-
"""
Grabador de audio para la accion "Recorder" (categoria Practical).

Motor: sounddevice (InputStream) + soundfile (escribe WAV/MP3/FLAC). Para
resistir cierres inesperados graba primero a un archivo RAW (int16) + meta JSON;
al detener convierte RAW -> formato final y borra el RAW. Al arrancar, los RAW
huerfanos se recuperan (se convierten) automaticamente.

    pip install sounddevice soundfile
"""

from __future__ import annotations

import json
import os
import queue
import threading
import time

_sd = None
_sf = None
_np = None
_import_err = None

# formato -> (formato soundfile, subtype, extension)
FORMATS = {
    "mp3": ("MP3", None, "mp3"),
    "wav": ("WAV", "PCM_16", "wav"),
    "flac": ("FLAC", "PCM_16", "flac"),
}
# calidad -> compression_level (0.0 mejor ... 1.0 menor) para MP3/FLAC
QUALITY = {"high": 0.1, "medium": 0.4, "low": 0.7}


def _ensure_libs() -> bool:
    global _sd, _sf, _np, _import_err
    if _sd is not None:
        return True
    try:
        import numpy as np
        import sounddevice as sd
        import soundfile as sf
        _np, _sd, _sf = np, sd, sf
        return True
    except Exception as e:
        _import_err = e
        return False


def libs_available() -> bool:
    return _ensure_libs()


def recordings_dir(kind: str = "") -> str:
    """Carpeta de grabaciones. `kind` separa los tipos de accion que graban:
    'hold' (Hold and Record) y 'long' (Long Recorder) usan subcarpetas propias
    para mantenerse separados; sin `kind` se usa la carpeta base (compatibilidad)."""
    try:
        import m18_paths
        base = os.path.join(m18_paths.data_dir(), "recordings")
    except Exception:
        base = os.path.join(os.path.expanduser("~"), "StreamDockM18_recordings")
    d = os.path.join(base, kind) if kind in ("hold", "long") else base
    os.makedirs(d, exist_ok=True)
    return d


def count_recordings(kind: str = "") -> int:
    """Numero de grabaciones (archivos de audio) en la carpeta del tipo dado.
    Rapido: solo cuenta por extension, sin abrir los archivos."""
    d = recordings_dir(kind)
    n = 0
    try:
        for fn in os.listdir(d):
            if fn.lower().endswith((".mp3", ".wav", ".flac", ".ogg")):
                n += 1
    except Exception:
        pass
    return n


_FAKE = ("microsoft sound mapper", "primary sound capture", "sound mapper")


def list_inputs():
    """Nombres de dispositivos de ENTRADA (micrófonos), WASAPI primero, sin duplicados."""
    if not _ensure_libs():
        return []
    try:
        devs = list(_sd.query_devices())
        apis = list(_sd.query_hostapis())
    except Exception as e:
        print("[rec] list_inputs:", e)
        return []
    wasapi = next((i for i, a in enumerate(apis) if "wasapi" in a.get("name", "").lower()), None)

    def collect(api):
        names, seen = [], set()
        for d in devs:
            if d.get("max_input_channels", 0) <= 0:
                continue
            if api is not None and d.get("hostapi") != api:
                continue
            n = (d.get("name") or "").strip()
            if not n or n.lower() in _FAKE or n in seen:
                continue
            seen.add(n); names.append(n)
        return names
    return (collect(wasapi) if wasapi is not None else []) or collect(None)


def _resolve_input(name):
    name = (name or "").strip()
    if not name:
        return None
    try:
        devs = list(_sd.query_devices())
    except Exception:
        return None
    for want in (lambda n: n == name, lambda n: n.startswith(name) or name.startswith(n)):
        for i, d in enumerate(devs):
            if d.get("max_input_channels", 0) > 0 and want(d.get("name", "")):
                return i
    return None


def _pick_input_settings(name, want_sr, want_ch):
    """Elige (device_index, samplerate, channels) que el micro ACEPTE de verdad.

    Muchos micros USB no admiten 44100 (solo 48000). Prueba la tasa pedida y, si
    el dispositivo no la soporta, usa su tasa nativa / 48000 / 44100. Prefiere la
    variante WASAPI del dispositivo y, como ultimo recurso, el micro por defecto.
    Devuelve (device_index_o_None, samplerate_int, channels_int).
    """
    want_sr = int(want_sr or 44100)
    want_ch = max(1, int(want_ch or 1))
    if not _ensure_libs():
        return (_resolve_input(name), want_sr, want_ch)
    try:
        devs = list(_sd.query_devices())
        apis = list(_sd.query_hostapis())
    except Exception:
        return (_resolve_input(name), want_sr, want_ch)

    def _is_wasapi(d):
        try:
            return "wasapi" in (apis[d["hostapi"]].get("name", "").lower())
        except Exception:
            return False

    nm = (name or "").strip()
    if not nm:
        # dispositivo por defecto: resolver su NOMBRE para aplicarle el mismo
        # recorte de canales (min entre variantes WASAPI/DirectSound) que a uno
        # elegido por nombre. Asi un micro mono que sobre-reporta 2 canales por
        # WASAPI se graba en mono (sin el "ruido" del 2o canal fantasma).
        try:
            _di = _sd.default.device[0]
            if _di is not None and int(_di) >= 0:
                nm = (devs[int(_di)].get("name") or "").strip()
        except Exception:
            nm = ""
    if nm:
        matches = [i for i, d in enumerate(devs)
                   if d.get("max_input_channels", 0) > 0
                   and (d.get("name", "") == nm or d.get("name", "").startswith(nm) or nm.startswith(d.get("name", "")))]
        matches.sort(key=lambda i: 0 if _is_wasapi(devs[i]) else 1)
    else:
        matches = []
    # muchos micros mono reportan 2 canales por WASAPI pero el 2o canal es ruido;
    # limitar a los canales REALES = minimo entre las variantes del mismo micro
    # (p.ej. DirectSound=1, WASAPI=2 -> usar 1). Una interfaz estereo real da 2.
    if matches:
        try:
            true_max = min(int(devs[i].get("max_input_channels", 1)) for i in matches)
            want_ch = max(1, min(want_ch, true_max))
        except Exception:
            pass
    # indice real del dispositivo por defecto (para conocer sus canales/tasa)
    try:
        _def_in = _sd.default.device[0]
        _def_in = int(_def_in) if (_def_in is not None and int(_def_in) >= 0) else None
    except Exception:
        _def_in = None
    cand_devs = matches + [None]   # None = dispositivo de entrada por defecto
    for di in cand_devs:
        # para el "por defecto" (None) usar los datos del dispositivo real por
        # defecto: asi se limitan canales (micros mono) y se usa su tasa nativa.
        info_idx = di if di is not None else _def_in
        try:
            dinfo = devs[info_idx] if info_idx is not None else None
        except Exception:
            dinfo = None
        maxch = int(dinfo.get("max_input_channels", 1)) if dinfo else 1
        ch = min(want_ch, max(1, maxch))
        # tasa NATIVA primero: WASAPI (modo compartido) solo captura bien a la
        # tasa de mezcla del dispositivo; pedir otra provoca remuestreo/ruido.
        srlist = []
        try:
            if dinfo is not None:
                srlist.append(int(dinfo.get("default_samplerate") or 0))
        except Exception:
            pass
        srlist += [want_sr, 48000, 44100]
        seen = set()
        for sr in srlist:
            sr = int(sr or 0)
            if sr <= 0 or sr in seen:
                continue
            seen.add(sr)
            try:
                _sd.check_input_settings(device=di, channels=ch, samplerate=sr, dtype="int16")
                return (di, sr, ch)
            except Exception:
                continue
    return (_resolve_input(name), want_sr, want_ch)


def _reclog(msg):
    """Traza de diagnostico a <data_dir>/recorder_debug.log (no falla nunca)."""
    try:
        import m18_paths
        import datetime as _dt
        p = os.path.join(m18_paths.data_dir(), "recorder_debug.log")
        with open(p, "a", encoding="utf-8") as f:
            f.write(_dt.datetime.now().strftime("%H:%M:%S ") + "[eng] " + msg + "\n")
    except Exception:
        pass


def _dev_summary(di):
    """Descripcion corta del dispositivo (nombre + host API) para el log."""
    if di is None:
        return "default"
    try:
        d = _sd.query_devices()[di]
        api = _sd.query_hostapis()[d["hostapi"]].get("name", "?")
        return f"idx={di} '{d.get('name','?')}' api={api} maxch={d.get('max_input_channels')}"
    except Exception:
        return f"idx={di}"


def _timestamp_name():
    # sin usar datetime.now de forma que rompa nada: aqui si es un proceso normal
    import datetime
    return "rec_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


def _convert_raw(raw_path, meta):
    """Convierte un .rawrec (int16 intercalado) al formato final. Devuelve ruta final o None."""
    if not _ensure_libs():
        return None
    try:
        ch = int(meta.get("channels", 1))
        sr = int(meta.get("samplerate", 44100))
        fmt = meta.get("format", "mp3")
        quality = meta.get("quality", "medium")
        sfmt, subtype, ext = FORMATS.get(fmt, FORMATS["mp3"])
        with open(raw_path, "rb") as f:
            raw = f.read()
        if not raw:
            return None
        data = _np.frombuffer(raw, dtype="<i2")
        if ch > 1:
            data = data[: (len(data) // ch) * ch].reshape(-1, ch)
        final = os.path.splitext(raw_path)[0] + "." + ext
        kw = {"format": sfmt}
        if subtype:
            kw["subtype"] = subtype
        if fmt in ("mp3", "flac"):
            kw["compression_level"] = QUALITY.get(quality, 0.4)
        _sf.write(final, data, sr, **kw)
        return final
    except Exception as e:
        print("[rec] convert:", e)
        return None


def recover_orphans(kind: str = ""):
    """Convierte RAW huerfanos (grabaciones interrumpidas por un cierre inesperado)."""
    d = recordings_dir(kind)
    recovered = []
    try:
        for fn in os.listdir(d):
            if not fn.endswith(".rawrec"):
                continue
            raw = os.path.join(d, fn)
            meta_path = raw + ".json"
            meta = {}
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
            except Exception:
                meta = {}
            meta["note"] = (meta.get("note", "") + " (recuperada)").strip()
            final = _convert_raw(raw, meta)
            if final:
                recovered.append(final)
            for p in (raw, meta_path):
                try:
                    os.remove(p)
                except Exception:
                    pass
    except Exception as e:
        print("[rec] recover:", e)
    return recovered


class Recorder:
    """Graba audio del micrófono a un archivo (crash-safe vía RAW intermedio)."""

    def __init__(self):
        self._stream = None
        self._q = queue.Queue()
        self._writer = None
        self._raw_fh = None
        self._raw_path = None
        self._meta = {}
        self._stop = threading.Event()
        self._paused = False
        self._active = False
        self._peak = 0.0
        self._t0 = 0.0
        self._gain = 1.0
        self._lock = threading.Lock()

    def set_gain(self, v):
        self._gain = max(0.0, float(v))

    def is_recording(self):
        return self._active

    def is_paused(self):
        return self._paused

    def level(self):
        """Pico actual 0..1 (y se auto-atenua)."""
        p = self._peak
        self._peak *= 0.6
        return p

    def elapsed(self):
        return (time.monotonic() - self._t0) if self._active else 0.0

    def start(self, folder=None, device="", samplerate=44100, channels=1,
              fmt="mp3", quality="medium", note=""):
        if self._active:
            return None
        if not _ensure_libs():
            print("[rec] faltan sounddevice/soundfile:", _import_err)
            return None
        folder = folder or recordings_dir()
        name = _timestamp_name()
        # Grabador de MICROFONO: siempre MONO. Muchos micros (USB, webcams, arrays)
        # son fisicamente mono pero exponen 2 canales por el driver; grabar en
        # estereo captura un 2o canal "fantasma" que es ruido blanco. Forzar mono
        # evita ese ruido en cualquier equipo (el estereo real no aporta nada en
        # un unico microfono).
        dev, samplerate, ch = _pick_input_settings(device, samplerate, 1)
        _reclog(f"start req_dev={device!r} req_ch={channels} -> {_dev_summary(dev)} sr={samplerate} ch={ch} fmt={fmt} q={quality}")
        self._raw_path = os.path.join(folder, name + ".rawrec")
        self._meta = {"samplerate": int(samplerate), "channels": int(ch),
                      "format": fmt, "quality": quality, "note": note}
        try:
            with open(self._raw_path + ".json", "w", encoding="utf-8") as f:
                json.dump(self._meta, f)
            self._raw_fh = open(self._raw_path, "wb")
        except Exception as e:
            print("[rec] start file:", e)
            return None
        self._stop.clear()
        self._paused = False
        self._peak = 0.0

        def callback(indata, frames, time_info, status):
            if self._stop.is_set():
                raise _sd.CallbackStop()
            data = indata
            if self._gain != 1.0:   # ganancia de microfono (por software)
                data = _np.clip(indata.astype(_np.int32) * self._gain, -32768, 32767).astype(_np.int16)
            try:
                self._peak = max(self._peak, float(_np.abs(data).max()) / 32768.0)
            except Exception:
                pass
            if not self._paused:
                self._q.put(bytes(data))

        try:
            self._stream = _sd.InputStream(samplerate=int(samplerate), channels=ch,
                                           device=dev, dtype="int16", callback=callback)
        except Exception as e:
            print("[rec] input stream:", e)
            _reclog(f"InputStream FAIL sr={samplerate} ch={ch}: {e!r}")
            self._cleanup_files()
            return None
        try:
            _reclog(f"stream open sr={self._stream.samplerate} ch={ch}")
        except Exception:
            pass

        def writer():
            while True:
                try:
                    chunk = self._q.get(timeout=0.2)
                except queue.Empty:
                    if self._stop.is_set() and self._q.empty():
                        break
                    continue
                if chunk is None:
                    break
                try:
                    self._raw_fh.write(chunk)
                except Exception:
                    pass

        self._writer = threading.Thread(target=writer, daemon=True)
        self._writer.start()
        self._active = True
        self._t0 = time.monotonic()
        try:
            self._stream.start()
        except Exception as e:
            print("[rec] stream start:", e)
            self.stop()
            return None
        return self._raw_path

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def stop(self):
        """Detiene, convierte RAW->formato final y devuelve la ruta final (o None)."""
        if not self._active and self._stream is None:
            return None
        self._stop.set()
        s = self._stream
        self._stream = None
        if s is not None:
            try:
                s.stop(); s.close()
            except Exception:
                pass
        try:
            self._q.put_nowait(None)
        except Exception:
            pass
        if self._writer is not None:
            self._writer.join(timeout=2.0)
            self._writer = None
        if self._raw_fh is not None:
            try:
                self._raw_fh.flush(); self._raw_fh.close()
            except Exception:
                pass
            self._raw_fh = None
        self._active = False
        self._paused = False
        final = None
        if self._raw_path and os.path.exists(self._raw_path):
            final = _convert_raw(self._raw_path, self._meta)
            self._cleanup_files()
        return final

    def _cleanup_files(self):
        for p in (self._raw_path, (self._raw_path + ".json") if self._raw_path else None):
            if p:
                try:
                    os.remove(p)
                except Exception:
                    pass
        self._raw_path = None


# --- gestion de la carpeta de grabaciones -----------------------------------
def _duration(path):
    if not _ensure_libs():
        return 0.0
    try:
        info = _sf.info(path)
        return float(info.frames) / info.samplerate if info.samplerate else 0.0
    except Exception:
        return 0.0


def list_recordings(kind: str = ""):
    """Lista [{name, path, size, mtime, duration}] de grabaciones, mas recientes primero."""
    d = recordings_dir(kind)
    out = []
    try:
        for fn in sorted(os.listdir(d)):
            if fn.endswith((".rawrec", ".json")):
                continue
            if not fn.lower().endswith((".mp3", ".wav", ".flac", ".ogg")):
                continue
            p = os.path.join(d, fn)
            try:
                out.append({"name": fn, "path": p, "size": os.path.getsize(p),
                            "mtime": os.path.getmtime(p), "duration": _duration(p)})
            except OSError:
                pass
    except Exception as e:
        print("[rec] list:", e)
    out.sort(key=lambda r: r["mtime"], reverse=True)
    return out


def delete_recording(path):
    try:
        os.remove(path)
        return True
    except Exception as e:
        print("[rec] delete:", e)
        return False


def rename_recording(path, new_base):
    """Renombra una grabacion conservando su extension. Devuelve la nueva ruta o None."""
    try:
        d = os.path.dirname(path)
        ext = os.path.splitext(path)[1]
        clean = "".join(c for c in (new_base or "") if c not in '\\/:*?"<>|').strip()
        if not clean:
            return None
        newp = os.path.join(d, clean + ext)
        if os.path.abspath(newp) == os.path.abspath(path):
            return path
        base = clean; i = 2
        while os.path.exists(newp):   # evitar sobrescribir
            newp = os.path.join(d, f"{base}_{i}{ext}"); i += 1
        os.rename(path, newp)
        return newp
    except Exception as e:
        print("[rec] rename:", e)
        return None


# --- ajustes recordados de la ventana (mic/formato/calidad) ------------------
def _settings_path():
    return os.path.join(recordings_dir(), "_recorder_settings.json")


def load_settings():
    try:
        with open(_settings_path(), "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save_settings(d):
    try:
        with open(_settings_path(), "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print("[rec] settings save:", e)


# --- monitor de nivel de entrada (siempre vivo, para ver el microfono) -------
class Monitor:
    def __init__(self):
        self._stream = None
        self._peak = 0.0
        self._gain = 1.0

    def set_gain(self, v):
        self._gain = max(0.0, float(v))

    def start(self, device=""):
        self.stop()
        if not _ensure_libs():
            return
        dev, sr, ch = _pick_input_settings(device, 44100, 1)

        def cb(indata, frames, time_info, status):
            try:
                self._peak = max(self._peak, float(_np.abs(indata).max()) / 32768.0 * self._gain)
            except Exception:
                pass
        try:
            self._stream = _sd.InputStream(samplerate=int(sr), channels=int(ch), device=dev,
                                           dtype="int16", callback=cb)
            self._stream.start()
        except Exception as e:
            print("[rec] monitor:", e)
            self._stream = None

    def level(self):
        p = self._peak
        self._peak *= 0.5
        return p

    def active(self):
        return self._stream is not None

    def stop(self):
        s = self._stream
        self._stream = None
        if s is not None:
            try:
                s.stop(); s.close()
            except Exception:
                pass


# --- reproductor con pausa/stop/posicion (para la ventana) -------------------
class Player:
    def __init__(self):
        self._stream = None
        self._data = None
        self._sr = 0
        self._ch = 1
        self._pos = 0
        self._paused = False
        self._done = False
        self._volume = 1.0
        self._gen = 0

    def set_volume(self, v):
        self._volume = max(0.0, float(v))

    def play(self, path):
        self.stop()
        if not _ensure_libs():
            return
        try:
            data, sr = _sf.read(path, dtype="float32", always_2d=True)
        except Exception as e:
            print("[rec] play read:", e)
            return
        self._data = data; self._sr = sr; self._ch = data.shape[1]
        self._pos = 0; self._paused = False; self._done = False
        self._gen += 1
        gen = self._gen   # solo el stream de esta generacion puede marcar "terminado"
        # (evita que el finished_callback de un stream viejo marque _done en la nueva reproduccion)

        def _finish():
            if gen == self._gen:
                self._done = True

        def cb(outdata, frames, time_info, status):
            if self._paused:
                outdata[:] = 0
                return
            i = self._pos; n = len(self._data); end = i + frames
            if i >= n:
                outdata[:] = 0
                raise _sd.CallbackStop()
            block = self._data[i:min(end, n)]
            if self._volume != 1.0:
                block = _np.clip(block * self._volume, -1.0, 1.0)
            if end <= n:
                outdata[:] = block; self._pos = end
            else:
                k = n - i
                outdata[:k] = block; outdata[k:] = 0; self._pos = n
                raise _sd.CallbackStop()
        try:
            self._stream = _sd.OutputStream(samplerate=sr, channels=self._ch, dtype="float32",
                                            callback=cb, finished_callback=_finish)
            self._stream.start()
        except Exception as e:
            print("[rec] play stream:", e)
            self._stream = None

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def stop(self):
        self._gen += 1   # invalida el finished_callback del stream que vamos a cerrar
        s = self._stream
        self._stream = None
        if s is not None:
            try:
                s.stop(); s.close()
            except Exception:
                pass
        self._pos = 0; self._paused = False; self._done = False

    def is_active(self):
        return self._stream is not None and not self._done

    def is_started(self):
        return self._stream is not None

    def is_paused(self):
        return self._paused

    def finished(self):
        return self._done

    def position(self):
        return (self._pos / self._sr) if self._sr else 0.0

    def duration(self):
        return (len(self._data) / self._sr) if (self._data is not None and self._sr) else 0.0

    def seek(self, sec):
        if self._data is not None and self._sr:
            self._pos = max(0, min(len(self._data), int(sec * self._sr)))
