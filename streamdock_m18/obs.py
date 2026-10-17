"""
Cliente OBS WebSocket v5 (obs-websocket) y acciones de OBS Studio.

Cada accion abre una conexion, se identifica (con autenticacion si OBS la pide),
envia la peticion y cierra. La configuracion global (host/port/password) la fija
la app desde config.json via actions.set_obs_config().
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time

from . import actions as _a


class ObsError(Exception):
    pass


class ObsClient:
    def __init__(self, host="127.0.0.1", port=4455, password=""):
        self.url = f"ws://{host}:{int(port)}/"
        self.password = password or ""
        self.ws = None
        self._id = 0

    def __enter__(self):
        import websocket  # websocket-client
        self.ws = websocket.create_connection(self.url, timeout=5)
        hello = json.loads(self.ws.recv())
        d = hello.get("d", {})
        ident = {"op": 1, "d": {"rpcVersion": d.get("rpcVersion", 1)}}
        auth = d.get("authentication")
        if auth:
            if not self.password:
                raise ObsError("OBS requiere contrasena (configurala en el plugin OBS)")
            secret = base64.b64encode(
                hashlib.sha256((self.password + auth["salt"]).encode()).digest()).decode()
            resp = base64.b64encode(
                hashlib.sha256((secret + auth["challenge"]).encode()).digest()).decode()
            ident["d"]["authentication"] = resp
        self.ws.send(json.dumps(ident))
        got = json.loads(self.ws.recv())
        if got.get("op") != 2:
            raise ObsError(f"OBS no se identifico: {got}")
        return self

    def __exit__(self, *exc):
        try:
            if self.ws:
                self.ws.close()
        except Exception:
            pass

    def req(self, request_type, data=None):
        self._id += 1
        rid = str(self._id)
        self.ws.send(json.dumps({"op": 6, "d": {
            "requestType": request_type, "requestId": rid,
            "requestData": data or {}}}))
        while True:
            m = json.loads(self.ws.recv())
            if m.get("op") == 7 and m["d"].get("requestId") == rid:
                dd = m["d"]
                status = dd.get("requestStatus", {})
                if not status.get("result", False):
                    raise ObsError(status.get("comment") or f"{request_type} fallo")
                return dd.get("responseData") or {}


# --- helpers de conexion (usados por el configurador) -----------------------
def _client(cfg):
    cfg = cfg or _a.get_obs_config()
    return ObsClient(cfg.get("host", "127.0.0.1"), cfg.get("port", 4455),
                     cfg.get("password", ""))


def test_connection(cfg):
    with _client(cfg) as o:
        return o.req("GetVersion").get("obsVersion", "?")


def get_scenes(cfg):
    with _client(cfg) as o:
        return [s["sceneName"] for s in o.req("GetSceneList").get("scenes", [])]


def get_sources(cfg, scene):
    with _client(cfg) as o:
        return [it["sourceName"]
                for it in o.req("GetSceneItemList", {"sceneName": scene}).get("sceneItems", [])]


def get_inputs(cfg):
    with _client(cfg) as o:
        return [i["inputName"] for i in o.req("GetInputList").get("inputs", [])]


# --- acciones ---------------------------------------------------------------
def _run(fn):
    def action(event):
        try:
            with _client(None) as o:
                fn(o)
        except Exception as e:
            print("[OBS] error:", e)
    return action


def _toggle_studio(o):
    cur = o.req("GetStudioModeEnabled").get("studioModeEnabled", False)
    o.req("SetStudioModeEnabled", {"studioModeEnabled": not cur})


def _screenshot(o, spec):
    scene = o.req("GetCurrentProgramScene").get("currentProgramSceneName")
    folder = spec.get("folder") or os.path.join(os.path.expanduser("~"), "Pictures")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, time.strftime("obs_%Y%m%d_%H%M%S.png"))
    o.req("SaveSourceScreenshot", {"sourceName": scene, "imageFormat": "png",
                                   "imageFilePath": path})


def _source_vis(o, spec):
    scene, source = spec.get("scene", ""), spec.get("source", "")
    mode = spec.get("mode", "toggle")
    item_id = o.req("GetSceneItemId", {"sceneName": scene,
                                       "sourceName": source}).get("sceneItemId")
    if mode == "toggle":
        en = o.req("GetSceneItemEnabled", {"sceneName": scene,
                                           "sceneItemId": item_id}).get("sceneItemEnabled", False)
        new = not en
    else:
        new = (mode == "show")
    o.req("SetSceneItemEnabled", {"sceneName": scene, "sceneItemId": item_id,
                                  "sceneItemEnabled": new})


def _audio(o, spec):
    inp, mode = spec.get("input", ""), spec.get("mode", "toggle")
    if mode == "toggle":
        o.req("ToggleInputMute", {"inputName": inp})
    else:
        o.req("SetInputMute", {"inputName": inp, "inputMuted": (mode == "mute")})


def _move(o, spec, delta):
    scene, source = spec.get("scene", ""), spec.get("source", "")
    items = o.req("GetSceneItemList", {"sceneName": scene}).get("sceneItems", [])
    cur = next((it for it in items if it.get("sourceName") == source), None)
    if not cur:
        return
    idx = cur.get("sceneItemIndex", 0)
    o.req("SetSceneItemIndex", {"sceneName": scene, "sceneItemId": cur["sceneItemId"],
                                "sceneItemIndex": max(0, idx + delta)})


def action_from_spec(spec):
    t = spec.get("type")
    simple = {
        "obs_record": lambda o: o.req("ToggleRecord"),
        "obs_stream": lambda o: o.req("ToggleStream"),
        "obs_vcam": lambda o: o.req("ToggleVirtualCam"),
        "obs_studio_mode": _toggle_studio,
        "obs_transition": lambda o: o.req("TriggerStudioModeTransition"),
    }
    if t in simple:
        return _run(simple[t])
    if t == "obs_screenshot":
        return _run(lambda o: _screenshot(o, spec))
    if t == "obs_scene":
        return _run(lambda o: o.req("SetCurrentProgramScene",
                                    {"sceneName": spec.get("scene", "")}))
    if t == "obs_source":
        return _run(lambda o: _source_vis(o, spec))
    if t == "obs_audio":
        return _run(lambda o: _audio(o, spec))
    if t == "obs_green_up":
        return _run(lambda o: _move(o, spec, +1))
    if t == "obs_green_dn":
        return _run(lambda o: _move(o, spec, -1))
    return None
