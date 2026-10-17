"""
Configurador MODERNO (Flet) para el Stream Dock M18.  -- version en desarrollo --

Reutiliza el backend de `streamdock_m18` (driver, acciones, compositor de teclas)
y comparte config.json con el configurador clasico (Tkinter), que sigue intacto
como respaldo (configurator.py).

Ejecuta:  python configurator_flet.py
"""

import colorsys
import json
import os
import shutil
import sys
import tempfile
import threading
import time

import flet as ft
from PIL import Image

from streamdock_m18 import default_config, StreamDockM18, build_app_from_config
from streamdock_m18 import device as sd_device
from streamdock_m18 import obs as sd_obs
from streamdock_m18 import actions as sd_actions
# helpers puros (sin GUI) reutilizados del configurador clasico
from configurator import get_system_fonts, get_installed_apps, BROWSERS

IMG_EXT = (".png", ".jpg", ".jpeg", ".gif", ".bmp")

# --- identidad de la app ----------------------------------------------------
APP_VERSION = "1.0.0"
APP_NAME = "Stream Dock M18 by JARCMASTER"
WINDOW_TITLE = f"{APP_NAME} Version {APP_VERSION}"

# --- rutas / assets ---------------------------------------------------------
import m18_paths
HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = m18_paths.config_path()
ICONS_DIR = m18_paths.icons_dir()
DEVICE_IMG = os.path.join(m18_paths.assets_dir(), "device.png")
FLAGS_DIR = os.path.join(m18_paths.assets_dir(), "flags")
ASSETS = os.path.join(tempfile.gettempdir(), "m18_flet_assets")
os.makedirs(ASSETS, exist_ok=True)

# geometria del equipo (fracciones de la imagen 472x414)
DEV_COLX = [0.180, 0.335, 0.489, 0.644, 0.799]
DEV_ROWY = [0.223, 0.401, 0.580]
DEV_KEY_N = 0.123
DEV_AUXX = [0.34, 0.50, 0.655]
DEV_AUXY = 0.800
DEV_KEY_DY = -0.002   # ajuste fino vertical (fraccion del alto): - sube, + baja
DEV_KEY_DX = 0.006    # ajuste fino horizontal (fraccion del ancho): + derecha
DISP_W = 560
DISP_H = int(DISP_W * 414 / 472)

# --- libreria de acciones (con iconos Material flat) ------------------------
I = ft.Icons
ACTION_LIBRARY = [
    ("Stream Dock", I.DASHBOARD, [
        ("Create Folder", I.CREATE_NEW_FOLDER, "create_folder"),
        ("Scene Shift", I.SWAP_HORIZ, "scene_shift"),
        ("Previous Page", I.ARROW_BACK, "prev_page"),
        ("Next Page", I.ARROW_FORWARD, "next_page"),
        ("Go to Page", I.TAG, "goto_page"),
        ("Page Indicator", I.LINEAR_SCALE, "page_indicator"),
        ("Brightness", I.LIGHT_MODE, "brightness"),
        ("devsleep", I.BEDTIME, "devsleep"),
    ]),
    ("Toolbox", I.HANDYMAN, [
        ("Website", I.PUBLIC, "open_url"),
        ("Hotkey", I.KEYBOARD, "hotkey"),
        ("HotkeySwitch", I.KEYBOARD_ALT, "hotkey_switch"),
        ("Super Hotkeys", I.KEYBOARD_DOUBLE_ARROW_RIGHT, "super_hotkeys"),
        ("Mouse event", I.MOUSE, "mouse"),
        ("Open", I.OPEN_IN_NEW, "open"),
        ("Open an app", I.LAUNCH, "open_app"),
        ("Close", I.CLOSE, "close"),
        ("Text", I.TITLE, "write_text"),
        ("Password", I.LOCK, "password"),
        ("Multimedia", I.PLAY_CIRCLE, "multimedia"),
    ]),
    ("Audio Player", I.VOLUME_UP, [
        ("Play Audio", I.PLAY_ARROW, "play_audio"),
        ("Stop Audio", I.STOP, "stop_audio"),
    ]),
    ("Operation Flow", I.ACCOUNT_TREE, [
        ("Action flow", I.ACCOUNT_TREE, "action_flow"),
        ("Carousel", I.VIEW_CAROUSEL, "carousel"),
        ("Action Toggle", I.TOGGLE_ON, "action_toggle"),
    ]),
    ("OBS Studio", I.VIDEOCAM, [
        ("Record", I.FIBER_MANUAL_RECORD, "obs_record"),
        ("Stream", I.LIVE_TV, "obs_stream"),
        ("Virtual camera", I.CAMERA, "obs_vcam"),
        ("Scene", I.LAYERS, "obs_scene"),
        ("Source Visibility", I.VISIBILITY, "obs_source"),
        ("Audio Mixer", I.VOLUME_OFF, "obs_audio"),
        ("Studio Mode", I.GROUPS, "obs_studio_mode"),
        ("Screenshot", I.SCREENSHOT_MONITOR, "obs_screenshot"),
        ("Transition", I.TRANSFORM, "obs_transition"),
        ("Green background image UP", I.ARROW_UPWARD, "obs_green_up"),
        ("Green background image DN", I.ARROW_DOWNWARD, "obs_green_dn"),
    ]),
]

ACTION_TYPES = ["none", "run", "open", "open_app", "open_url", "hotkey",
                "write_text", "password", "multimedia", "brightness",
                "close", "mouse", "devsleep", "scene_shift", "page_indicator",
                "hotkey_switch", "super_hotkeys", "action_flow", "carousel", "action_toggle",
                "play_audio", "stop_audio",
                "next_page", "prev_page", "goto_page", "home"]

SUB_TYPES = ["hotkey", "run", "open", "open_url", "write_text", "multimedia", "mouse", "close"]

# --- catalogo de teclas para el selector visual de Super Hotkeys -------------
# (display, nombre pyautogui)
HK_MODS = [("Ctrl", "ctrl"), ("Shift", "shift"), ("Alt", "alt"), ("Win", "win")]
HK_LETTERS = [(str(d), str(d)) for d in range(10)] + \
             [(c, c.lower()) for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"]
HK_ARROWS = [("Left", "left"), ("Up", "up"), ("Right", "right"), ("Down", "down")]
HK_COMMON = [("Tab", "tab"), ("Caps", "capslock"), ("Space", "space"), ("Esc", "esc"),
             ("Enter", "enter"), ("Backspace", "backspace"), ("Applications", "apps"),
             ("Ins", "insert"), ("Del", "delete"), ("Home", "home"), ("End", "end"),
             ("PgUp", "pageup"), ("PgDown", "pagedown"), ("Print Screen", "printscreen"),
             ("Pause Break", "pause"), ("Help", "help")]
HK_NUMPAD = [("NumPad Lock", "numlock")] + \
            [(f"NumPad {d}", f"num{d}") for d in range(10)] + \
            [("NumPad +", "add"), ("NumPad -", "subtract"), ("NumPad *", "multiply"),
             ("NumPad /", "divide"), ("NumPad .", "decimal"), ("NumPad Clear", "clear"),
             ("NumPad Enter", "enter")]
HK_FKEY = [(f"F{i}", f"f{i}") for i in range(1, 25)]
HK_OTHER = [("`", "`"), ("-", "-"), ("=", "="), ("[", "["), ("]", "]"), ("\\", "\\"),
            (";", ";"), ("'", "'"), (",", ","), (".", "."), ("/", "/")]
HK_MOD_ONLY = [("L-Win", "winleft"), ("L-Shift", "shiftleft"), ("L-Ctrl", "ctrlleft"),
               ("L-Alt", "altleft"), ("R-Win", "winright"), ("R-Shift", "shiftright"),
               ("R-Ctrl", "ctrlright"), ("R-Alt", "altright")]


# inicio automatico con Windows (compartido con la bandeja)
is_startup_enabled = m18_paths.is_autostart
set_startup = m18_paths.set_autostart


def ensure_server_running():
    """En modo empaquetado, arranca el server (mismo exe sin args; mutex dedup)."""
    import subprocess
    if not getattr(sys, "frozen", False):
        return
    try:
        subprocess.Popen([sys.executable], close_fds=True)
    except Exception as e:
        print("[server]", e)


def get_running_apps():
    """Procesos en ejecucion con ventana visible: {imagen.exe: titulo}. Windows."""
    import subprocess
    import csv
    import io
    apps = {}
    try:
        out = subprocess.run(["tasklist", "/v", "/fo", "csv", "/nh"],
                             capture_output=True, text=True, creationflags=0x08000000).stdout
    except Exception:
        return apps
    noise = ("OleMainThreadWndName", "Default IME", "MSCTFIME UI", "WndName",
             "WindowClass", "BroadcastEventWindow", "DWM Notification",
             "GDI+ Window", "Hidden Window", ".NET-")
    for row in csv.reader(io.StringIO(out)):
        if len(row) < 9:
            continue
        img, title = row[0], row[8]
        if not img.lower().endswith(".exe"):
            continue
        if not title or title in ("N/A", "") or img in apps:
            continue
        if any(n in title for n in noise):
            continue
        apps[img] = title
    return dict(sorted(apps.items(), key=lambda kv: kv[0].lower()))

# --- i18n -------------------------------------------------------------------
LANGS = [("English", "en"), ("Español", "es"), ("Italiano", "it"), ("Русский", "ru"),
         ("中文", "zh"), ("日本語", "ja"), ("한국어", "ko"), ("Français", "fr"),
         ("Deutsch", "de"), ("Português", "pt"), ("العربية", "ar")]
LANG_CODES = [c for _, c in LANGS]
LANG_STATE = {"cur": "en"}

# claves -> {idioma: texto}. "en" es la base; si falta una, cae a "en" o a la clave.
TR = {
    "en": {
        "save": "Save", "connect": "Connect", "disconnect": "Disconnect", "preview": "Preview",
        "obs_btn": "OBS...", "language": "Language", "pages": "Pages",
        "action_library": "Action library", "select_key_hint": "Select a key then an action",
        "new": "New", "delete": "Delete", "title": "Title", "icon": "Icon",
        "gallery": "Gallery", "remove": "Remove", "clear_key": "Clear key",
        "cancel": "Cancel", "ok": "OK", "info_select_key": "Select a key first (click on the grid).",
        "cat_toolbox": "Toolbox", "cat_audio": "Audio Player", "cat_opflow": "Operation Flow",
        "a_create_folder": "Create Folder", "a_scene_shift": "Scene Shift", "a_prev_page": "Previous Page",
        "a_next_page": "Next Page", "a_goto_page": "Go to Page", "a_page_indicator": "Page Indicator",
        "a_brightness": "Brightness", "a_devsleep": "devsleep", "a_website": "Website", "a_hotkey": "Hotkey",
        "a_hotkey_switch": "HotkeySwitch", "a_super_hotkeys": "Super Hotkeys", "a_mouse": "Mouse event",
        "a_open": "Open", "a_open_app": "Open an app", "a_close": "Close", "a_text": "Text",
        "a_password": "Password", "a_multimedia": "Multimedia", "a_play_audio": "Play Audio",
        "a_stop_audio": "Stop Audio", "a_action_flow": "Action flow", "a_carousel": "Carousel",
        "a_action_toggle": "Action Toggle", "a_obs_record": "Record", "a_obs_stream": "Stream",
        "a_obs_vcam": "Virtual camera", "a_obs_scene": "Scene", "a_obs_source": "Source Visibility",
        "a_obs_audio": "Audio Mixer", "a_obs_studio": "Studio Mode", "a_obs_screenshot": "Screenshot",
        "a_obs_transition": "Transition", "a_obs_green_up": "Green background image UP",
        "a_obs_green_dn": "Green background image DN",
    },
    "es": {
        "save": "Guardar", "connect": "Conectar", "disconnect": "Desconectar", "preview": "Previsualizar",
        "obs_btn": "OBS...", "language": "Idioma", "pages": "Páginas",
        "action_library": "Librería de acciones", "select_key_hint": "Selecciona una tecla y luego una acción",
        "new": "Nueva", "delete": "Borrar", "title": "Título", "icon": "Icono",
        "gallery": "Galería", "remove": "Quitar", "clear_key": "Vaciar tecla",
        "cancel": "Cancelar", "ok": "OK", "info_select_key": "Selecciona primero una tecla (clic en el grid).",
        "cat_toolbox": "Herramientas", "cat_audio": "Reproductor de audio", "cat_opflow": "Flujo de operaciones",
        "a_create_folder": "Crear carpeta", "a_scene_shift": "Cambiar escena", "a_prev_page": "Página anterior",
        "a_next_page": "Página siguiente", "a_goto_page": "Ir a página", "a_page_indicator": "Indicador de página",
        "a_brightness": "Brillo", "a_devsleep": "Suspender", "a_website": "Sitio web", "a_hotkey": "Atajo",
        "a_hotkey_switch": "Atajo alterno", "a_super_hotkeys": "Súper atajos", "a_mouse": "Evento de ratón",
        "a_open": "Abrir", "a_open_app": "Abrir una app", "a_close": "Cerrar", "a_text": "Texto",
        "a_password": "Contraseña", "a_multimedia": "Multimedia", "a_play_audio": "Reproducir audio",
        "a_stop_audio": "Detener audio", "a_action_flow": "Flujo de acciones", "a_carousel": "Carrusel",
        "a_action_toggle": "Acción alterna", "a_obs_record": "Grabar", "a_obs_stream": "Transmitir",
        "a_obs_vcam": "Cámara virtual", "a_obs_scene": "Escena", "a_obs_source": "Visibilidad de fuente",
        "a_obs_audio": "Mezclador de audio", "a_obs_studio": "Modo estudio", "a_obs_screenshot": "Captura",
        "a_obs_transition": "Transición", "a_obs_green_up": "Imagen de fondo verde ARRIBA",
        "a_obs_green_dn": "Imagen de fondo verde ABAJO",
    },
    "it": {
        "save": "Salva", "connect": "Connetti", "disconnect": "Disconnetti", "preview": "Anteprima",
        "obs_btn": "OBS...", "language": "Lingua", "pages": "Pagine",
        "action_library": "Libreria azioni", "select_key_hint": "Seleziona un tasto e poi un'azione",
        "new": "Nuova", "delete": "Elimina", "title": "Titolo", "icon": "Icona",
        "gallery": "Galleria", "remove": "Rimuovi", "clear_key": "Svuota tasto",
        "cancel": "Annulla", "ok": "OK", "info_select_key": "Seleziona prima un tasto (clic sulla griglia).",
        "cat_toolbox": "Strumenti", "cat_audio": "Lettore audio", "cat_opflow": "Flusso operazioni",
        "a_create_folder": "Crea cartella", "a_scene_shift": "Cambia scena", "a_prev_page": "Pagina precedente",
        "a_next_page": "Pagina successiva", "a_goto_page": "Vai alla pagina", "a_page_indicator": "Indicatore pagina",
        "a_brightness": "Luminosità", "a_devsleep": "Sospendi", "a_website": "Sito web", "a_hotkey": "Scorciatoia",
        "a_hotkey_switch": "Scorciatoia alternata", "a_super_hotkeys": "Super scorciatoie", "a_mouse": "Evento mouse",
        "a_open": "Apri", "a_open_app": "Apri un'app", "a_close": "Chiudi", "a_text": "Testo",
        "a_password": "Password", "a_multimedia": "Multimedia", "a_play_audio": "Riproduci audio",
        "a_stop_audio": "Ferma audio", "a_action_flow": "Flusso di azioni", "a_carousel": "Carosello",
        "a_action_toggle": "Azione alternata", "a_obs_record": "Registra", "a_obs_stream": "Trasmetti",
        "a_obs_vcam": "Webcam virtuale", "a_obs_scene": "Scena", "a_obs_source": "Visibilità sorgente",
        "a_obs_audio": "Mixer audio", "a_obs_studio": "Modalità studio", "a_obs_screenshot": "Schermata",
        "a_obs_transition": "Transizione", "a_obs_green_up": "Immagine sfondo verde SU",
        "a_obs_green_dn": "Immagine sfondo verde GIÙ",
    },
    "ru": {
        "save": "Сохранить", "connect": "Подключить", "disconnect": "Отключить", "preview": "Предпросмотр",
        "obs_btn": "OBS...", "language": "Язык", "pages": "Страницы",
        "action_library": "Библиотека действий", "select_key_hint": "Выберите кнопку, затем действие",
        "new": "Новая", "delete": "Удалить", "title": "Заголовок", "icon": "Значок",
        "gallery": "Галерея", "remove": "Убрать", "clear_key": "Очистить кнопку",
        "cancel": "Отмена", "ok": "ОК", "info_select_key": "Сначала выберите кнопку (клик по сетке).",
        "cat_toolbox": "Инструменты", "cat_audio": "Аудиоплеер", "cat_opflow": "Поток операций",
        "a_create_folder": "Создать папку", "a_scene_shift": "Смена сцены", "a_prev_page": "Пред. страница",
        "a_next_page": "След. страница", "a_goto_page": "Перейти к странице", "a_page_indicator": "Индикатор страницы",
        "a_brightness": "Яркость", "a_devsleep": "Сон", "a_website": "Веб-сайт", "a_hotkey": "Горячая клавиша",
        "a_hotkey_switch": "Переключатель", "a_super_hotkeys": "Супер клавиши", "a_mouse": "Событие мыши",
        "a_open": "Открыть", "a_open_app": "Открыть приложение", "a_close": "Закрыть", "a_text": "Текст",
        "a_password": "Пароль", "a_multimedia": "Мультимедиа", "a_play_audio": "Воспроизвести",
        "a_stop_audio": "Остановить", "a_action_flow": "Поток действий", "a_carousel": "Карусель",
        "a_action_toggle": "Переключение действий", "a_obs_record": "Запись", "a_obs_stream": "Трансляция",
        "a_obs_vcam": "Виртуальная камера", "a_obs_scene": "Сцена", "a_obs_source": "Видимость источника",
        "a_obs_audio": "Аудиомикшер", "a_obs_studio": "Студийный режим", "a_obs_screenshot": "Скриншот",
        "a_obs_transition": "Переход", "a_obs_green_up": "Зелёный фон ВВЕРХ",
        "a_obs_green_dn": "Зелёный фон ВНИЗ",
    },
    "zh": {
        "save": "保存", "connect": "连接", "disconnect": "断开", "preview": "预览",
        "obs_btn": "OBS...", "language": "语言", "pages": "页面",
        "action_library": "动作库", "select_key_hint": "先选择一个按键，再选择动作",
        "new": "新建", "delete": "删除", "title": "标题", "icon": "图标",
        "gallery": "图库", "remove": "移除", "clear_key": "清空按键",
        "cancel": "取消", "ok": "确定", "info_select_key": "请先选择一个按键（点击网格）。",
        "cat_toolbox": "工具箱", "cat_audio": "音频播放器", "cat_opflow": "操作流程",
        "a_create_folder": "创建文件夹", "a_scene_shift": "切换场景", "a_prev_page": "上一页",
        "a_next_page": "下一页", "a_goto_page": "跳转页面", "a_page_indicator": "页面指示器",
        "a_brightness": "亮度", "a_devsleep": "休眠", "a_website": "网站", "a_hotkey": "快捷键",
        "a_hotkey_switch": "快捷键切换", "a_super_hotkeys": "超级快捷键", "a_mouse": "鼠标事件",
        "a_open": "打开", "a_open_app": "打开应用", "a_close": "关闭", "a_text": "文本",
        "a_password": "密码", "a_multimedia": "多媒体", "a_play_audio": "播放音频",
        "a_stop_audio": "停止音频", "a_action_flow": "动作流", "a_carousel": "轮播",
        "a_action_toggle": "动作切换", "a_obs_record": "录制", "a_obs_stream": "推流",
        "a_obs_vcam": "虚拟摄像头", "a_obs_scene": "场景", "a_obs_source": "来源可见性",
        "a_obs_audio": "音频混合器", "a_obs_studio": "工作室模式", "a_obs_screenshot": "截图",
        "a_obs_transition": "转场", "a_obs_green_up": "绿色背景图 上",
        "a_obs_green_dn": "绿色背景图 下",
    },
    "ja": {
        "save": "保存", "connect": "接続", "disconnect": "切断", "preview": "プレビュー",
        "obs_btn": "OBS...", "language": "言語", "pages": "ページ",
        "action_library": "アクションライブラリ", "select_key_hint": "キーを選んでからアクションを選択",
        "new": "新規", "delete": "削除", "title": "タイトル", "icon": "アイコン",
        "gallery": "ギャラリー", "remove": "削除", "clear_key": "キーを空に",
        "cancel": "キャンセル", "ok": "OK", "info_select_key": "先にキーを選択してください（グリッドをクリック）。",
        "cat_toolbox": "ツールボックス", "cat_audio": "オーディオプレーヤー", "cat_opflow": "操作フロー",
        "a_create_folder": "フォルダ作成", "a_scene_shift": "シーン切替", "a_prev_page": "前のページ",
        "a_next_page": "次のページ", "a_goto_page": "ページへ移動", "a_page_indicator": "ページ表示",
        "a_brightness": "明るさ", "a_devsleep": "スリープ", "a_website": "ウェブサイト", "a_hotkey": "ホットキー",
        "a_hotkey_switch": "ホットキー切替", "a_super_hotkeys": "スーパーホットキー", "a_mouse": "マウス操作",
        "a_open": "開く", "a_open_app": "アプリを開く", "a_close": "閉じる", "a_text": "テキスト",
        "a_password": "パスワード", "a_multimedia": "マルチメディア", "a_play_audio": "音声再生",
        "a_stop_audio": "音声停止", "a_action_flow": "アクションフロー", "a_carousel": "カルーセル",
        "a_action_toggle": "アクション切替", "a_obs_record": "録画", "a_obs_stream": "配信",
        "a_obs_vcam": "仮想カメラ", "a_obs_scene": "シーン", "a_obs_source": "ソース表示",
        "a_obs_audio": "音声ミキサー", "a_obs_studio": "スタジオモード", "a_obs_screenshot": "スクショ",
        "a_obs_transition": "トランジション", "a_obs_green_up": "緑背景画像 上",
        "a_obs_green_dn": "緑背景画像 下",
    },
    "ko": {
        "save": "저장", "connect": "연결", "disconnect": "연결 해제", "preview": "미리보기",
        "obs_btn": "OBS...", "language": "언어", "pages": "페이지",
        "action_library": "동작 라이브러리", "select_key_hint": "키를 선택한 후 동작을 선택하세요",
        "new": "새로", "delete": "삭제", "title": "제목", "icon": "아이콘",
        "gallery": "갤러리", "remove": "제거", "clear_key": "키 비우기",
        "cancel": "취소", "ok": "확인", "info_select_key": "먼저 키를 선택하세요 (그리드 클릭).",
        "cat_toolbox": "도구상자", "cat_audio": "오디오 플레이어", "cat_opflow": "작업 흐름",
        "a_create_folder": "폴더 만들기", "a_scene_shift": "장면 전환", "a_prev_page": "이전 페이지",
        "a_next_page": "다음 페이지", "a_goto_page": "페이지 이동", "a_page_indicator": "페이지 표시",
        "a_brightness": "밝기", "a_devsleep": "절전", "a_website": "웹사이트", "a_hotkey": "단축키",
        "a_hotkey_switch": "단축키 전환", "a_super_hotkeys": "슈퍼 단축키", "a_mouse": "마우스 이벤트",
        "a_open": "열기", "a_open_app": "앱 열기", "a_close": "닫기", "a_text": "텍스트",
        "a_password": "비밀번호", "a_multimedia": "멀티미디어", "a_play_audio": "오디오 재생",
        "a_stop_audio": "오디오 정지", "a_action_flow": "동작 흐름", "a_carousel": "캐러셀",
        "a_action_toggle": "동작 전환", "a_obs_record": "녹화", "a_obs_stream": "방송",
        "a_obs_vcam": "가상 카메라", "a_obs_scene": "장면", "a_obs_source": "소스 표시",
        "a_obs_audio": "오디오 믹서", "a_obs_studio": "스튜디오 모드", "a_obs_screenshot": "스크린샷",
        "a_obs_transition": "전환", "a_obs_green_up": "녹색 배경 이미지 위",
        "a_obs_green_dn": "녹색 배경 이미지 아래",
    },
    "fr": {
        "save": "Enregistrer", "connect": "Connecter", "disconnect": "Déconnecter", "preview": "Aperçu",
        "obs_btn": "OBS...", "language": "Langue", "pages": "Pages",
        "action_library": "Bibliothèque d'actions", "select_key_hint": "Sélectionne une touche puis une action",
        "new": "Nouvelle", "delete": "Supprimer", "title": "Titre", "icon": "Icône",
        "gallery": "Galerie", "remove": "Retirer", "clear_key": "Vider la touche",
        "cancel": "Annuler", "ok": "OK", "info_select_key": "Sélectionne d'abord une touche (clic sur la grille).",
        "cat_toolbox": "Boîte à outils", "cat_audio": "Lecteur audio", "cat_opflow": "Flux d'opérations",
        "a_create_folder": "Créer un dossier", "a_scene_shift": "Changer de scène", "a_prev_page": "Page précédente",
        "a_next_page": "Page suivante", "a_goto_page": "Aller à la page", "a_page_indicator": "Indicateur de page",
        "a_brightness": "Luminosité", "a_devsleep": "Veille", "a_website": "Site web", "a_hotkey": "Raccourci",
        "a_hotkey_switch": "Raccourci alterné", "a_super_hotkeys": "Super raccourcis", "a_mouse": "Événement souris",
        "a_open": "Ouvrir", "a_open_app": "Ouvrir une app", "a_close": "Fermer", "a_text": "Texte",
        "a_password": "Mot de passe", "a_multimedia": "Multimédia", "a_play_audio": "Lire l'audio",
        "a_stop_audio": "Arrêter l'audio", "a_action_flow": "Flux d'actions", "a_carousel": "Carrousel",
        "a_action_toggle": "Bascule d'action", "a_obs_record": "Enregistrer", "a_obs_stream": "Diffuser",
        "a_obs_vcam": "Caméra virtuelle", "a_obs_scene": "Scène", "a_obs_source": "Visibilité source",
        "a_obs_audio": "Mixeur audio", "a_obs_studio": "Mode studio", "a_obs_screenshot": "Capture",
        "a_obs_transition": "Transition", "a_obs_green_up": "Image fond vert HAUT",
        "a_obs_green_dn": "Image fond vert BAS",
    },
    "de": {
        "save": "Speichern", "connect": "Verbinden", "disconnect": "Trennen", "preview": "Vorschau",
        "obs_btn": "OBS...", "language": "Sprache", "pages": "Seiten",
        "action_library": "Aktionsbibliothek", "select_key_hint": "Wähle eine Taste, dann eine Aktion",
        "new": "Neu", "delete": "Löschen", "title": "Titel", "icon": "Symbol",
        "gallery": "Galerie", "remove": "Entfernen", "clear_key": "Taste leeren",
        "cancel": "Abbrechen", "ok": "OK", "info_select_key": "Wähle zuerst eine Taste (Klick auf das Raster).",
        "cat_toolbox": "Werkzeuge", "cat_audio": "Audioplayer", "cat_opflow": "Ablauf",
        "a_create_folder": "Ordner erstellen", "a_scene_shift": "Szene wechseln", "a_prev_page": "Vorherige Seite",
        "a_next_page": "Nächste Seite", "a_goto_page": "Zur Seite", "a_page_indicator": "Seitenanzeige",
        "a_brightness": "Helligkeit", "a_devsleep": "Ruhezustand", "a_website": "Webseite", "a_hotkey": "Tastenkürzel",
        "a_hotkey_switch": "Kürzel-Umschalter", "a_super_hotkeys": "Super-Kürzel", "a_mouse": "Maus-Ereignis",
        "a_open": "Öffnen", "a_open_app": "App öffnen", "a_close": "Schließen", "a_text": "Text",
        "a_password": "Passwort", "a_multimedia": "Multimedia", "a_play_audio": "Audio abspielen",
        "a_stop_audio": "Audio stoppen", "a_action_flow": "Aktionsablauf", "a_carousel": "Karussell",
        "a_action_toggle": "Aktion umschalten", "a_obs_record": "Aufnahme", "a_obs_stream": "Stream",
        "a_obs_vcam": "Virtuelle Kamera", "a_obs_scene": "Szene", "a_obs_source": "Quellen-Sichtbarkeit",
        "a_obs_audio": "Audio-Mixer", "a_obs_studio": "Studiomodus", "a_obs_screenshot": "Screenshot",
        "a_obs_transition": "Übergang", "a_obs_green_up": "Grüner Hintergrund HOCH",
        "a_obs_green_dn": "Grüner Hintergrund RUNTER",
    },
    "pt": {
        "save": "Salvar", "connect": "Conectar", "disconnect": "Desconectar", "preview": "Pré-visualizar",
        "obs_btn": "OBS...", "language": "Idioma", "pages": "Páginas",
        "action_library": "Biblioteca de ações", "select_key_hint": "Selecione uma tecla e depois uma ação",
        "new": "Nova", "delete": "Excluir", "title": "Título", "icon": "Ícone",
        "gallery": "Galeria", "remove": "Remover", "clear_key": "Limpar tecla",
        "cancel": "Cancelar", "ok": "OK", "info_select_key": "Selecione primeiro uma tecla (clique na grade).",
        "cat_toolbox": "Ferramentas", "cat_audio": "Player de áudio", "cat_opflow": "Fluxo de operações",
        "a_create_folder": "Criar pasta", "a_scene_shift": "Trocar cena", "a_prev_page": "Página anterior",
        "a_next_page": "Próxima página", "a_goto_page": "Ir para página", "a_page_indicator": "Indicador de página",
        "a_brightness": "Brilho", "a_devsleep": "Suspender", "a_website": "Site", "a_hotkey": "Atalho",
        "a_hotkey_switch": "Atalho alternado", "a_super_hotkeys": "Super atalhos", "a_mouse": "Evento do mouse",
        "a_open": "Abrir", "a_open_app": "Abrir um app", "a_close": "Fechar", "a_text": "Texto",
        "a_password": "Senha", "a_multimedia": "Multimídia", "a_play_audio": "Reproduzir áudio",
        "a_stop_audio": "Parar áudio", "a_action_flow": "Fluxo de ações", "a_carousel": "Carrossel",
        "a_action_toggle": "Alternar ação", "a_obs_record": "Gravar", "a_obs_stream": "Transmitir",
        "a_obs_vcam": "Câmera virtual", "a_obs_scene": "Cena", "a_obs_source": "Visibilidade da fonte",
        "a_obs_audio": "Mixer de áudio", "a_obs_studio": "Modo estúdio", "a_obs_screenshot": "Captura",
        "a_obs_transition": "Transição", "a_obs_green_up": "Imagem de fundo verde CIMA",
        "a_obs_green_dn": "Imagem de fundo verde BAIXO",
    },
    "ar": {
        "save": "حفظ", "connect": "اتصال", "disconnect": "قطع", "preview": "معاينة",
        "obs_btn": "OBS...", "language": "اللغة", "pages": "الصفحات",
        "action_library": "مكتبة الإجراءات", "select_key_hint": "اختر مفتاحًا ثم إجراءً",
        "new": "جديد", "delete": "حذف", "title": "العنوان", "icon": "أيقونة",
        "gallery": "المعرض", "remove": "إزالة", "clear_key": "إفراغ المفتاح",
        "cancel": "إلغاء", "ok": "موافق", "info_select_key": "اختر مفتاحًا أولاً (انقر على الشبكة).",
        "cat_toolbox": "الأدوات", "cat_audio": "مشغل الصوت", "cat_opflow": "تدفق العمليات",
        "a_create_folder": "إنشاء مجلد", "a_scene_shift": "تبديل المشهد", "a_prev_page": "الصفحة السابقة",
        "a_next_page": "الصفحة التالية", "a_goto_page": "الذهاب إلى صفحة", "a_page_indicator": "مؤشر الصفحة",
        "a_brightness": "السطوع", "a_devsleep": "سكون", "a_website": "موقع ويب", "a_hotkey": "اختصار",
        "a_hotkey_switch": "تبديل الاختصار", "a_super_hotkeys": "اختصارات فائقة", "a_mouse": "حدث الفأرة",
        "a_open": "فتح", "a_open_app": "فتح تطبيق", "a_close": "إغلاق", "a_text": "نص",
        "a_password": "كلمة المرور", "a_multimedia": "وسائط", "a_play_audio": "تشغيل الصوت",
        "a_stop_audio": "إيقاف الصوت", "a_action_flow": "تدفق الإجراءات", "a_carousel": "دوّار",
        "a_action_toggle": "تبديل الإجراء", "a_obs_record": "تسجيل", "a_obs_stream": "بث",
        "a_obs_vcam": "كاميرا افتراضية", "a_obs_scene": "مشهد", "a_obs_source": "ظهور المصدر",
        "a_obs_audio": "مازج الصوت", "a_obs_studio": "وضع الاستوديو", "a_obs_screenshot": "لقطة شاشة",
        "a_obs_transition": "انتقال", "a_obs_green_up": "صورة الخلفية الخضراء أعلى",
        "a_obs_green_dn": "صورة الخلفية الخضراء أسفل",
    },
}

# fusionar traducciones adicionales de los diálogos (por-clave, 11 idiomas)
try:
    from i18n_extra import EXTRA as _EXTRA
    for _k, _langs in _EXTRA.items():
        for _lc, _txt in _langs.items():
            TR.setdefault(_lc, {})[_k] = _txt
except Exception as _e:
    print("[i18n_extra]", _e)

# aid de la librería -> clave de traducción del nombre
AID_TR = {
    "create_folder": "a_create_folder", "scene_shift": "a_scene_shift", "prev_page": "a_prev_page",
    "next_page": "a_next_page", "goto_page": "a_goto_page", "page_indicator": "a_page_indicator",
    "brightness": "a_brightness", "devsleep": "a_devsleep", "open_url": "a_website", "hotkey": "a_hotkey",
    "hotkey_switch": "a_hotkey_switch", "super_hotkeys": "a_super_hotkeys", "mouse": "a_mouse",
    "open": "a_open", "open_app": "a_open_app", "close": "a_close", "write_text": "a_text",
    "password": "a_password", "multimedia": "a_multimedia", "action_flow": "a_action_flow",
    "carousel": "a_carousel", "action_toggle": "a_action_toggle",
    "play_audio": "a_play_audio", "stop_audio": "a_stop_audio",
    "obs_record": "a_obs_record", "obs_stream": "a_obs_stream", "obs_vcam": "a_obs_vcam",
    "obs_scene": "a_obs_scene", "obs_source": "a_obs_source", "obs_audio": "a_obs_audio",
    "obs_studio_mode": "a_obs_studio", "obs_screenshot": "a_obs_screenshot",
    "obs_transition": "a_obs_transition", "obs_green_up": "a_obs_green_up", "obs_green_dn": "a_obs_green_dn",
}
# categorías: etiqueta por defecto -> clave (las que son nombre de producto se dejan igual)
CAT_TR = {"Toolbox": "cat_toolbox", "Audio Player": "cat_audio", "Operation Flow": "cat_opflow"}


def t(key):
    d = TR.get(LANG_STATE["cur"], {})
    return d.get(key) or TR["en"].get(key, key)


def tname(aid, default):
    k = AID_TR.get(aid)
    return t(k) if k else default


def tcat(cat):
    k = CAT_TR.get(cat)
    return t(k) if k else cat


def thdr(prefix, name_key):
    """Encabezado de dialogo: 'Prefijo: Nombre'. prefix puede ser una clave de
    categoria (cat_*) o un texto literal de producto (ej. 'Stream Dock')."""
    pfx = t(prefix) if prefix in ("cat_toolbox", "cat_audio", "cat_opflow") else prefix
    return f"{pfx}: {t(name_key)}"

ALL_AIDS = {aid for _c, _i, items in ACTION_LIBRARY for _n, _ic, aid in items}


def read_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = default_config()
    else:
        cfg = default_config()
    # modelo de escenas: cada escena tiene su lista de paginas.
    if not cfg.get("scenes"):
        pages = cfg.get("pages") or [{"keys": {}}]
        cfg["scenes"] = [{"name": "Scene 1",
                          "default_page": int(cfg.get("default_page", 0)),
                          "pages": pages}]
    cfg.pop("pages", None)
    cfg.pop("default_page", None)
    cfg.setdefault("default_scene", 0)
    cfg.setdefault("aux", {})
    cfg.setdefault("brightness", 80)
    return cfg


def hexc(rgb):
    r, g, b = rgb
    return f"#{int(r):02x}{int(g):02x}{int(b):02x}"


_ver = 0


def render_key_src(spec):
    """Compone la tecla (imagen+texto) a PNG en assets y devuelve su src."""
    global _ver
    img_path = (spec or {}).get("image")
    text = (spec or {}).get("text")
    img = sd_device.compose_key_image(
        text=text,
        image=img_path if (img_path and os.path.exists(img_path)) else None,
        fg=tuple((spec or {}).get("fg", [255, 255, 255])),
        bg=tuple((spec or {}).get("bg", [0, 0, 0])),
        font=(spec or {}).get("font"))
    img = img.resize((128, 128))
    _ver += 1
    name = f"k_{_ver}.png"
    img.save(os.path.join(ASSETS, name))
    return "/" + name


_icon_cache = {}


def icon_thumb_src(path):
    """Copia un icono como PNG a assets y devuelve su src (cacheado)."""
    if path in _icon_cache:
        return _icon_cache[path]
    try:
        im = Image.open(path).convert("RGBA")
        im.thumbnail((96, 96))
        name = f"ic_{len(_icon_cache)}.png"
        im.save(os.path.join(ASSETS, name))
        _icon_cache[path] = "/" + name
        return "/" + name
    except Exception:
        return None


def _clamp_lines(tf, maxlines=3):
    """Recorta un TextField a `maxlines` lineas (max maxlines-1 Enters)."""
    v = tf.value or ""
    if v.count("\n") > maxlines - 1:
        tf.value = "\n".join(v.split("\n")[:maxlines])
        tf.update()


def _normkey(k):
    m = {"enter": "enter", " ": "space", "escape": "esc", "arrow up": "up",
         "arrow down": "down", "arrow left": "left", "arrow right": "right",
         "backspace": "backspace", "delete": "delete", "tab": "tab"}
    kl = (k or "").lower()
    return m.get(kl, kl)


def main(page: ft.Page):
    page.title = WINDOW_TITLE
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 0
    try:
        # Tamano por defecto ajustado para que la imagen central del equipo y los
        # tres paneles se vean completos sin espacio sobrante. El usuario puede
        # maximizar o redimensionar luego (se respetan los minimos).
        page.window.width = 1371
        page.window.height = 868
        page.window.min_width = 1100   # 250 (escenas) + ~560 (equipo) + 270 (libreria)
        page.window.min_height = 700
        try:
            page.window.center()       # centrar en la pantalla al abrir
        except Exception:
            page.window.top = 20
        _ico = os.path.join(m18_paths.assets_dir(), "app.ico")
        if os.path.exists(_ico):
            page.window.icon = _ico
    except Exception:
        pass

    state = {"cfg": read_config(), "sel_scene": 0, "sel_page": 0, "sel_key": None,
             "dragging": None, "dev": None, "devlock": threading.Lock()}
    LANG_STATE["cur"] = state["cfg"].get("lang", "en")
    file_picker = ft.FilePicker()
    page.services.append(file_picker)

    # copiar imagen del equipo y banderas a assets servibles
    if os.path.exists(DEVICE_IMG):
        shutil.copy(DEVICE_IMG, os.path.join(ASSETS, "device.png"))
    for _code in LANG_CODES:
        _fsrc = os.path.join(FLAGS_DIR, _code + ".png")
        if os.path.exists(_fsrc):
            shutil.copy(_fsrc, os.path.join(ASSETS, f"flag_{_code}.png"))

    def flag_src(code):
        return f"/flag_{code}.png" if os.path.exists(os.path.join(ASSETS, f"flag_{code}.png")) else ""

    scenes_list = ft.Column(spacing=2, scroll=ft.ScrollMode.AUTO, expand=True)
    device_stack = ft.Stack(width=DISP_W, height=DISP_H)
    # barra horizontal de paginas (estilo oficial: 1 2 3 +)
    page_bar = ft.Row(spacing=8, scroll=ft.ScrollMode.AUTO,
                      vertical_alignment=ft.CrossAxisAlignment.CENTER)
    device_holder = ft.Container(
        expand=True, bgcolor="#1b202a",
        content=ft.Column([
            ft.Container(content=device_stack, alignment=ft.Alignment(0, 0), expand=True),
            ft.Container(content=page_bar, padding=ft.Padding(12, 6, 12, 14),
                         alignment=ft.Alignment(0, 0)),
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True))

    def cur_scene():
        scs = state["cfg"]["scenes"]
        if state["sel_scene"] >= len(scs):
            state["sel_scene"] = 0
        return scs[state["sel_scene"]]

    def scene_pages():
        return cur_scene().setdefault("pages", [{"keys": {}}])

    def cur_page():
        pgs = scene_pages()
        if state["sel_page"] >= len(pgs):
            state["sel_page"] = 0
        return pgs[state["sel_page"]]

    def keys_of_page():
        return cur_page().setdefault("keys", {})

    # ---------- helpers de diálogos ----------
    def info(msg):
        page.show_dialog(ft.AlertDialog(title=ft.Text(t("ui_info")), content=ft.Text(msg),
            actions=[ft.TextButton(t("ok"), on_click=lambda e: page.pop_dialog())]))

    def hk_capture(tf):
        def onkey(e):
            k = getattr(e, "key", None)
            if not k or k.lower() in ("control", "alt", "shift", "meta"):
                return
            mods = []
            if getattr(e, "ctrl", False):
                mods.append("ctrl")
            if getattr(e, "alt", False):
                mods.append("alt")
            if getattr(e, "shift", False):
                mods.append("shift")
            tf.value = "+".join(mods + [_normkey(k)]); tf.update()
            page.on_keyboard_event = None
        page.on_keyboard_event = onkey

    def _keys_of(v):
        return [k.strip() for k in (v or "").replace(",", "+").split("+") if k.strip()]

    def pick_color(initial, apply):
        SQ, HBW = 240, 240
        r0, g0, b0 = [int(x) for x in initial]
        h0, s0, v0 = colorsys.rgb_to_hsv(r0 / 255, g0 / 255, b0 / 255)
        cur = {"h": h0, "s": s0, "v": v0}

        def rgb():
            r, g, b = colorsys.hsv_to_rgb(cur["h"], cur["s"], cur["v"])
            return [int(round(r * 255)), int(round(g * 255)), int(round(b * 255))]

        def hue_hex():
            r, g, b = colorsys.hsv_to_rgb(cur["h"], 1, 1)
            return hexc([int(r * 255), int(g * 255), int(b * 255)])

        prev = ft.Container(width=56, height=56, border_radius=8, bgcolor=hexc([r0, g0, b0]))
        hexf = ft.TextField(label="#hex", value=hexc([r0, g0, b0]), width=130)
        sv_base = ft.Container(width=SQ, height=SQ, border_radius=6,
            gradient=ft.LinearGradient(begin=ft.Alignment(-1, 0), end=ft.Alignment(1, 0),
                                       colors=["#ffffff", hue_hex()]))
        sv_black = ft.Container(width=SQ, height=SQ, border_radius=6,
            gradient=ft.LinearGradient(begin=ft.Alignment(0, -1), end=ft.Alignment(0, 1),
                                       colors=["#00000000", "#000000"]))
        sv_mark = ft.Container(width=14, height=14, border_radius=7, bgcolor="#ffffffcc",
                               left=s0 * SQ - 7, top=(1 - v0) * SQ - 7)
        hue_bar = ft.Container(width=HBW, height=20, border_radius=6,
            gradient=ft.LinearGradient(begin=ft.Alignment(-1, 0), end=ft.Alignment(1, 0),
                colors=["#ff0000", "#ffff00", "#00ff00", "#00ffff", "#0000ff", "#ff00ff", "#ff0000"]))
        hue_mark = ft.Container(width=6, height=24, border_radius=3, bgcolor="#ffffff",
                                left=h0 * HBW - 3, top=-2)

        def refresh_all():
            sv_base.gradient = ft.LinearGradient(begin=ft.Alignment(-1, 0), end=ft.Alignment(1, 0),
                                                 colors=["#ffffff", hue_hex()])
            sv_mark.left = cur["s"] * SQ - 7
            sv_mark.top = (1 - cur["v"]) * SQ - 7
            hue_mark.left = cur["h"] * HBW - 3
            c = rgb(); prev.bgcolor = hexc(c); hexf.value = hexc(c)
            sv_base.update(); sv_mark.update(); hue_mark.update(); prev.update(); hexf.update()

        def clamp(x, lo, hi):
            return max(lo, min(hi, x))

        def sv_set(x, y):
            cur["s"] = clamp(x / SQ, 0, 1); cur["v"] = clamp(1 - y / SQ, 0, 1); refresh_all()

        def sv_tap(e):
            sv_set(e.local_position.x, e.local_position.y)

        def sv_pan(e):
            sv_set(cur["s"] * SQ + e.local_delta.x, (1 - cur["v"]) * SQ + e.local_delta.y)

        def hue_set(x):
            cur["h"] = clamp(x / HBW, 0, 0.999); refresh_all()

        def hue_tap(e):
            hue_set(e.local_position.x)

        def hue_pan(e):
            hue_set(cur["h"] * HBW + e.local_delta.x)

        def from_hex(e):
            c = _hex2rgb(hexf.value)
            cur["h"], cur["s"], cur["v"] = colorsys.rgb_to_hsv(c[0] / 255, c[1] / 255, c[2] / 255)
            refresh_all()
        hexf.on_change = from_hex

        presets = [[255, 255, 255], [0, 0, 0], [255, 0, 0], [0, 200, 0], [0, 120, 255],
                   [255, 200, 0], [160, 0, 220], [255, 120, 0], [40, 40, 60], [20, 70, 40]]

        def set_preset(c):
            cur["h"], cur["s"], cur["v"] = colorsys.rgb_to_hsv(c[0] / 255, c[1] / 255, c[2] / 255)
            refresh_all()
        pr = ft.Row([ft.Container(width=24, height=24, border_radius=5, bgcolor=hexc(c),
                                  ink=True, on_click=lambda e, cc=c: set_preset(cc)) for c in presets], wrap=True)

        sv_gd = ft.GestureDetector(on_tap_down=sv_tap, on_pan_update=sv_pan,
            content=ft.Stack([sv_base, sv_black, sv_mark], width=SQ, height=SQ))
        hue_gd = ft.GestureDetector(on_tap_down=hue_tap, on_pan_update=hue_pan,
            content=ft.Stack([hue_bar, hue_mark], width=HBW, height=20))

        dlg = ft.AlertDialog(modal=True, title=ft.Text(t("ui_color_picker")),
            content=ft.Container(width=420, height=620, content=ft.Column([
                sv_gd, hue_gd, ft.Row([prev, hexf]), ft.Text(t("ui_palettes")), pr], spacing=12)),
            actions=[ft.FilledButton(t("ok"), on_click=lambda e: (page.pop_dialog(), apply(rgb()))),
                     ft.TextButton(t("cancel"), on_click=lambda e: page.pop_dialog())])
        page.show_dialog(dlg)

    def show_gallery(on_pick):
        if not os.path.isdir(ICONS_DIR):
            info(t("gal_no_icons")); return
        cats = [d for d in sorted(os.listdir(ICONS_DIR)) if os.path.isdir(os.path.join(ICONS_DIR, d))]
        # recordar la ultima categoria/subcarpeta usada en la sesion (no siempre "general")
        last_cat = state.get("gal_cat")
        default_cat = last_cat if last_cat in cats else (cats[0] if cats else None)
        cat_dd = ft.Dropdown(label=t("ui_category"), value=default_cat,
                             options=[ft.DropdownOption(key=c, text=c) for c in cats],
                             width=180, on_select=lambda e: on_cat())
        sub_dd = ft.Dropdown(label=t("ui_subfolder"), options=[], width=220, on_select=lambda e: load())
        search = ft.TextField(label=t("ui_search"), width=200, on_change=lambda e: load())
        grid = ft.GridView(max_extent=104, child_aspect_ratio=0.88, spacing=8, run_spacing=8, expand=True)

        def folder():
            if not cat_dd.value:
                return None
            base = os.path.join(ICONS_DIR, cat_dd.value)
            return base if (not sub_dd.value or sub_dd.value == t("gal_root")) else os.path.join(base, sub_dd.value)

        def on_cat():
            state["gal_cat"] = cat_dd.value   # recordar categoria elegida
            base = os.path.join(ICONS_DIR, cat_dd.value)
            subs = [d for d in sorted(os.listdir(base)) if os.path.isdir(os.path.join(base, d))]
            has = any(f.lower().endswith(IMG_EXT) for f in os.listdir(base))
            vals = ([t("gal_root")] if has else []) + subs
            sub_dd.options = [ft.DropdownOption(key=v, text=v) for v in vals]
            remembered = state.get("gal_sub")
            sub_dd.value = remembered if remembered in vals else (vals[0] if vals else None)
            sub_dd.update()
            load()

        def load():
            state["gal_sub"] = sub_dd.value   # recordar subcarpeta elegida
            grid.controls.clear()
            fo = folder()
            if fo and os.path.isdir(fo):
                q = (search.value or "").lower()
                files = [f for f in sorted(os.listdir(fo)) if f.lower().endswith(IMG_EXT) and q in f.lower()]
                for fn in files:
                    p = os.path.join(fo, fn)
                    grid.controls.append(ft.Container(
                        content=ft.Column([ft.Image(src=(icon_thumb_src(p) or ""), width=62, height=62),
                                           ft.Text(os.path.splitext(fn)[0][:11], size=9, max_lines=1)],
                                          horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=2),
                        padding=4, border_radius=6, ink=True,
                        on_click=lambda e, pp=p: (page.pop_dialog(), on_pick(pp))))
            grid.update()

        dlg = ft.AlertDialog(modal=True, title=ft.Text(t("ui_icon_gallery")),
            content=ft.Container(width=880, height=720,
                content=ft.Column([ft.Row([cat_dd, sub_dd]), search, grid], expand=True)),
            actions=[ft.TextButton(t("cancel"), on_click=lambda e: page.pop_dialog())])
        page.show_dialog(dlg)
        on_cat()

    def key_shell(pos, header, spec_bg, extra_fn):
        keys = keys_of_page()
        cur = dict(keys.get(str(pos), {}))
        # Colocacion nueva (soltar/elegir de la libreria): empezar en blanco.
        # Edicion (doble clic): conservar titulo e icono.
        fresh = state.pop("fresh", False)
        if fresh:
            cur["text"] = ""
            cur["image"] = ""
        st = {"img": cur.get("image", "")}
        title_tf = ft.TextField(label=t("title") + " " + t("ui_max3"), value=cur.get("text", "") or "",
                                multiline=True, min_lines=3, max_lines=3, width=320,
                                on_change=lambda e: (_clamp_lines(title_tf), do_refresh()))
        preview = ft.Image(src=render_key_src({"text": cur.get("text", "") or "", "image": st["img"],
                                               "fg": [255, 255, 255], "bg": spec_bg}),
                           width=96, height=96, border_radius=8)

        def do_refresh():
            preview.src = render_key_src({"text": title_tf.value, "image": st["img"],
                                          "fg": [255, 255, 255], "bg": spec_bg})
            preview.update()

        extras, build_action = extra_fn(do_refresh, cur)
        icon_row = ft.Row([ft.Text(t("icon") + ":"),
                           ft.FilledButton(t("gallery"), icon=I.IMAGE,
                                           on_click=lambda e: show_gallery(lambda p: (st.update(img=p), do_refresh()))),
                           ft.TextButton(t("remove"), on_click=lambda e: (st.update(img=""), do_refresh()))])

        def save(e):
            s = {"bg": list(spec_bg)}
            a = build_action()
            if a:
                s["action"] = a
            t = "\n".join((title_tf.value or "").split("\n")[:3])
            if st["img"]:
                s["image"] = st["img"]
            if t.strip():
                s["text"] = t
            keys[str(pos)] = s
            page.pop_dialog(); refresh_device()

        def delete(e):
            keys.pop(str(pos), None); page.pop_dialog(); refresh_device()

        content = ft.Container(width=700, height=720, content=ft.Row([
            ft.Container(content=preview, bgcolor="#1b1b22", border_radius=8, padding=4),
            ft.Column([title_tf, *extras, icon_row], expand=True,
                      scroll=ft.ScrollMode.ALWAYS, spacing=10)], spacing=16,
            vertical_alignment=ft.CrossAxisAlignment.START))
        dlg = ft.AlertDialog(modal=True, content=content,
            title=ft.Row([ft.Text(header, weight=ft.FontWeight.BOLD),
                          ft.IconButton(I.DELETE, icon_color="#e05555", tooltip=t("clear_key"), on_click=delete)],
                         alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            actions=[ft.FilledButton(t("save"), icon=I.CHECK, on_click=save),
                     ft.TextButton(t("cancel"), on_click=lambda e: page.pop_dialog())])
        page.show_dialog(dlg)
        do_refresh()

    # ---------- diálogos por acción ----------
    def open_website(pos):
        def ex(refresh, cur):
            act = cur.get("action", {}) if cur.get("action", {}).get("type") == "open_url" else {}
            url = ft.TextField(label="URL", value=act.get("url", ""), width=320)
            bw = ft.Dropdown(label=t("fld_open_mode"), width=240, value=act.get("browser", "default"),
                             options=[ft.DropdownOption(key=v, text=n) for n, v in BROWSERS])

            def build():
                u = (url.value or "").strip()
                if u and "://" not in u:
                    u = "https://" + u
                return {"type": "open_url", "url": u, "browser": bw.value or "default"}
            return ([url, bw], build)
        key_shell(pos, thdr("cat_toolbox", "a_website"), [20, 70, 40], ex)

    def open_password(pos):
        def ex(refresh, cur):
            act = cur.get("action", {}) if cur.get("action", {}).get("type") == "password" else {}
            pwd = ft.TextField(label=t("fld_password"), value=act.get("text", ""), width=320,
                               password=True, can_reveal_password=True)
            en = ft.Checkbox(label=t("chk_press_enter"), value=act.get("enter", False))
            pa = ft.Checkbox(label=t("chk_use_clipboard"), value=act.get("paste", True))

            def build():
                return {"type": "password", "text": pwd.value or "",
                        "enter": en.value, "paste": pa.value}
            note = ft.Text(t("note_pwd_plain"), size=11, color="#d077aa")
            return ([pwd, en, pa, note], build)
        key_shell(pos, thdr("cat_toolbox", "a_password"), [30, 60, 120], ex)

    def open_open(pos):
        def ex(refresh, cur):
            act = cur.get("action", {}) if cur.get("action", {}).get("type") == "open" else {}
            path = ft.TextField(label=t("fld_app_file"), value=act.get("path", ""), width=300)

            async def pick_file(e):
                files = await file_picker.pick_files(allow_multiple=False)
                if files:
                    path.value = files[0].path; path.update()

            async def pick_folder(e):
                d = await file_picker.get_directory_path()
                if d:
                    path.value = d; path.update()

            path_row = ft.Row([path,
                               ft.IconButton(I.FOLDER_OPEN, tooltip=t("ui_choose_folder"), on_click=pick_folder),
                               ft.IconButton(I.INSERT_DRIVE_FILE, tooltip=t("ui_choose_file"), on_click=pick_file)])
            args = ft.TextField(label=t("fld_arguments"), value=" ".join(act.get("args", []) or []), width=340)
            disp = ft.Checkbox(label=t("chk_open_display"),
                               value=act.get("display", False))

            def build():
                return {"type": "open", "path": (path.value or "").strip(),
                        "args": (args.value or "").split(), "display": disp.value}
            return ([path_row, args, disp], build)
        key_shell(pos, thdr("cat_toolbox", "a_open"), [20, 70, 40], ex)

    def open_openapp(pos):
        apps = get_installed_apps()

        def ex(refresh, cur):
            act = cur.get("action", {}) if cur.get("action", {}).get("type") == "open_app" else {}
            curname = next((n for n, p in apps.items() if p == act.get("path")), None)
            dd = ft.Dropdown(label=t("fld_app_name"), width=360, enable_search=True, value=curname,
                             options=[ft.DropdownOption(key=n, text=n) for n in apps.keys()])

            def build():
                return {"type": "open_app", "path": apps.get(dd.value, "")}
            return ([dd, ft.Text(f"{len(apps)} {t('ui_apps_detected')}", size=11, color="#888")], build)
        key_shell(pos, thdr("cat_toolbox", "a_open_app"), [25, 25, 25], ex)

    def open_multimedia(pos):
        CMDS = [("mm_playpause", "playpause", I.PLAY_CIRCLE),
                ("mm_prev", "prevtrack", I.SKIP_PREVIOUS),
                ("mm_next", "nexttrack", I.SKIP_NEXT),
                ("mm_stop", "stop", I.STOP_CIRCLE),
                ("mm_voldown", "volumedown", I.VOLUME_DOWN),
                ("mm_volup", "volumeup", I.VOLUME_UP),
                ("mm_mute", "volumemute", I.VOLUME_OFF)]

        def ex(refresh, cur):
            act = cur.get("action", {}) if cur.get("action", {}).get("type") == "multimedia" else {}
            sel = {"v": act.get("command", "playpause")}
            tiles = {}

            def _style(cont, on):
                cont.bgcolor = "#26324d" if on else "#1b1b22"
                cont.content.controls[0].color = "#4fe3ff" if on else "#cfcfcf"
                cont.content.controls[1].color = "#ffffff" if on else "#9a9a9a"

            def choose(v):
                sel["v"] = v
                for vv, c in tiles.items():
                    _style(c, vv == v); c.update()

            grid = ft.Row(wrap=True, spacing=10, run_spacing=10, width=400)
            for k, v, ic in CMDS:
                cont = ft.Container(
                    width=112, height=78, border_radius=10, padding=6, ink=True,
                    alignment=ft.Alignment(0, 0),
                    content=ft.Column([ft.Icon(ic, size=28),
                                       ft.Text(t(k), size=11, text_align=ft.TextAlign.CENTER,
                                               max_lines=2)],
                                      horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                      alignment=ft.MainAxisAlignment.CENTER, spacing=4),
                    on_click=lambda e, vv=v: choose(vv))
                _style(cont, v == sel["v"])
                tiles[v] = cont
                grid.controls.append(cont)

            def build():
                return {"type": "multimedia", "command": sel["v"]}
            return ([ft.Text(t("fld_command"), size=12, color="#9fb4d6"), grid], build)
        key_shell(pos, thdr("cat_toolbox", "a_multimedia"), [40, 30, 50], ex)

    def open_play_audio(pos):
        from streamdock_m18 import audio as _audio
        OPS = [("ap_op_toggle", "toggle"), ("ap_op_restart", "restart"),
               ("ap_op_pause", "pause"), ("ap_op_loop", "loop"), ("ap_op_stop", "stop")]
        devices = _audio.list_outputs()   # [] si falta sounddevice

        def ex(refresh, cur):
            act = cur.get("action", {}) if cur.get("action", {}).get("type") == "play_audio" else {}
            filef = ft.TextField(label=t("fld_audio_file"), value=act.get("file", ""), width=300)

            async def pick_file(e):
                files = await file_picker.pick_files(
                    allow_multiple=False,
                    allowed_extensions=["wav", "mp3", "ogg", "flac", "aac", "m4a", "wma"])
                if files:
                    filef.value = files[0].path
                    filef.update()

            file_row = ft.Row([filef,
                               ft.IconButton(I.INSERT_DRIVE_FILE, tooltip=t("ui_choose_file"),
                                             on_click=pick_file)])
            op_dd = ft.Dropdown(label=t("fld_operation"), width=300,
                                value=act.get("operation", "toggle"),
                                options=[ft.DropdownOption(key=v, text=t(k)) for k, v in OPS])
            vol = ft.Slider(min=0, max=100, divisions=100, label="{value}",
                            value=act.get("volume", 80))
            out_opts = [ft.DropdownOption(key="", text=t("ap_default_output"))]
            out_opts += [ft.DropdownOption(key=n, text=n) for n in devices]
            curout = act.get("output", "")
            if curout and curout not in devices:
                out_opts.append(ft.DropdownOption(key=curout, text=curout))
            out_dd = ft.Dropdown(label=t("fld_output"), width=360, value=curout,
                                 enable_search=True, options=out_opts)

            extras = [file_row, op_dd,
                      ft.Row([ft.Icon(I.VOLUME_UP, size=18), vol], spacing=6),
                      out_dd]
            if not _audio.libs_available():
                extras.append(ft.Text(t("ap_need_libs"), size=11, color="#d077aa"))

            def build():
                return {"type": "play_audio", "file": (filef.value or "").strip(),
                        "operation": op_dd.value or "toggle", "volume": int(vol.value),
                        "output": out_dd.value or ""}
            return (extras, build)
        key_shell(pos, thdr("cat_audio", "a_play_audio"), [60, 30, 30], ex)

    def open_stop_audio(pos):
        # Como el software oficial: solo Title + icono. Detiene todo el audio.
        def ex(refresh, cur):
            def build():
                return {"type": "stop_audio"}
            return ([], build)
        key_shell(pos, thdr("cat_audio", "a_stop_audio"), [30, 30, 50], ex)

    def open_brightness(pos):
        def ex(refresh, cur):
            act = cur.get("action", {}) if cur.get("action", {}).get("type") == "brightness" else {}
            val = ft.Slider(min=0, max=100, divisions=100, value=act.get("value", 80), label="{value}")

            def build():
                return {"type": "brightness", "value": int(val.value)}
            return ([ft.Text(t("note_brightness")), val], build)
        key_shell(pos, thdr("Stream Dock", "a_brightness"), [50, 50, 20], ex)

    def open_folder(pos):
        keys = keys_of_page()
        cur = dict(keys.get(str(pos), {}))
        st = {"img": cur.get("image", "")}
        title_tf = ft.TextField(label=t("title"), value=t("folder_default_name"), width=320,
                                on_change=lambda e: refr())
        preview = ft.Image(src=render_key_src({"text": t("folder_default_name"), "image": st["img"],
                                               "fg": [255, 255, 255], "bg": [40, 40, 60]}),
                           width=96, height=96, border_radius=8)

        def refr():
            preview.src = render_key_src({"text": title_tf.value, "image": st["img"],
                                          "fg": [255, 255, 255], "bg": [40, 40, 60]})
            preview.update()

        def create(e):
            title = (title_tf.value or t("folder_default_name")).strip()
            parent = state["sel_page"]
            pgs = scene_pages()
            pgs.append({"name": title, "keys": {
                "14": {"text": t("ui_back"), "bg": [60, 0, 0], "action": {"type": "goto_page", "page": parent}}}})
            new = len(pgs) - 1
            s = {"bg": [40, 40, 60], "action": {"type": "goto_page", "page": new}}
            if st["img"]:
                s["image"] = st["img"]
            if title:
                s["text"] = title
            keys[str(pos)] = s
            state["sel_page"] = new
            page.pop_dialog(); refresh_scenes(); refresh_page_bar(); refresh_device()

        content = ft.Container(width=560, height=440, content=ft.Row([
            ft.Container(content=preview, bgcolor="#1b1b22", border_radius=8, padding=4),
            ft.Column([title_tf,
                       ft.Row([ft.FilledButton(t("gallery"), icon=I.IMAGE,
                                               on_click=lambda e: show_gallery(lambda p: (st.update(img=p), refr()))),
                               ft.TextButton(t("remove"), on_click=lambda e: (st.update(img=""), refr()))]),
                       ft.Text(t("note_folder"), size=11, color="#888")],
                      width=400)], spacing=16))
        dlg = ft.AlertDialog(modal=True,
            title=ft.Text(thdr("Stream Dock", "a_create_folder"), weight=ft.FontWeight.BOLD),
            content=content,
            actions=[ft.FilledButton(t("ui_create"), icon=I.CREATE_NEW_FOLDER, on_click=create),
                     ft.TextButton(t("cancel"), on_click=lambda e: page.pop_dialog())])
        page.show_dialog(dlg); refr()

    def _open_url(url):
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:
            pass

    def show_about(e=None):
        rows = [
            ft.Row([ft.Text(f"{t('about_author')}:", width=90, color="#9fb4d6"),
                    ft.Text("Jose A. Rodriguez C.", selectable=True)]),
            ft.Row([ft.Text("Email:", width=90, color="#9fb4d6"),
                    ft.Text("jarcmaster@gmail.com", selectable=True)]),
            ft.Row([ft.Text(f"{t('about_version')}:", width=90, color="#9fb4d6"),
                    ft.Text(APP_VERSION)]),
            ft.Row([ft.Text(f"{t('about_license')}:", width=90, color="#9fb4d6"),
                    ft.Text("MIT License")]),
            ft.Divider(),
            ft.Text(t("about_disclaimer"), size=11, color="#cfcfcf"),
            ft.TextButton("github.com/jarcmaster/vsdm18", icon=I.LINK,
                          on_click=lambda e: _open_url("https://github.com/jarcmaster/vsdm18")),
        ]
        page.show_dialog(ft.AlertDialog(modal=True,
            title=ft.Row([ft.Icon(I.INFO_OUTLINE, color="#4fe3ff"),
                          ft.Text(f"{t('about')} — {APP_NAME} v{APP_VERSION}",
                                  weight=ft.FontWeight.BOLD)]),
            content=ft.Container(width=480, content=ft.Column(rows, tight=True, spacing=8)),
            actions=[ft.TextButton(t("ok"), on_click=lambda e: page.pop_dialog())]))

    def show_help(e=None):
        guide = [(I.LAYERS, "help_scenes"), (I.TAG, "help_pages"),
                 (I.APPS, "help_keys"), (I.HANDYMAN, "help_actions"),
                 (I.SETTINGS, "help_settings"), (I.ALL_INBOX, "help_tray")]
        rows = []
        for ic, key in guide:
            rows.append(ft.Row([ft.Icon(ic, size=18, color="#4fe3ff"),
                                ft.Text(t(key), size=12, expand=True)],
                               vertical_alignment=ft.CrossAxisAlignment.START, spacing=10))
            rows.append(ft.Divider(height=6))
        rows.append(ft.TextButton(t("about"), icon=I.INFO_OUTLINE,
                                  on_click=lambda e: (page.pop_dialog(), show_about())))
        page.show_dialog(ft.AlertDialog(modal=True,
            title=ft.Row([ft.Icon(I.HELP_OUTLINE, color="#4fe3ff"),
                          ft.Text(t("help_title"), weight=ft.FontWeight.BOLD)]),
            content=ft.Container(width=560, height=560,
                content=ft.Column(rows, spacing=8, scroll=ft.ScrollMode.ALWAYS)),
            actions=[ft.TextButton(t("ok"), on_click=lambda e: page.pop_dialog())]))

    def show_device_settings(e=None):
        dev_cfg = state["cfg"].setdefault("device", {})
        try:
            infos = sd_device.StreamDockM18.enumerate_info()
        except Exception:
            infos = []
        info0 = infos[0] if infos else {}
        serial = info0.get("serial") or t("set_not_connected")
        fw = info0.get("release_str") or t("set_not_connected")

        ROT = [("default", t("rot_default")), ("90", "90°"), ("180", "180°"), ("270", "270°")]
        rot_dd = ft.Dropdown(label=t("set_rotate"), width=320,
                             value=str(dev_cfg.get("rotate", "default")),
                             options=[ft.DropdownOption(key=k, text=v) for k, v in ROT])
        SO = [("never", t("so_never")), ("1m", t("so_1m")), ("5m", t("so_5m")),
              ("15m", t("so_15m")), ("30m", t("so_30m")), ("1h", t("so_1h")),
              ("2h", t("so_2h")), ("system", t("so_system"))]
        so_dd = ft.Dropdown(label=t("set_screen_off"), width=320,
                            value=str(dev_cfg.get("screen_off", "never")),
                            options=[ft.DropdownOption(key=k, text=v) for k, v in SO])

        def _on_startup(e):
            set_startup(startup_chk.value)
            state["cfg"]["autostart"] = bool(startup_chk.value)
            _autosave()
        startup_chk = ft.Checkbox(
            label=t("set_startup"),
            value=state["cfg"].get("autostart", is_startup_enabled()),
            on_change=_on_startup)

        led_rgb = list(dev_cfg.get("led_color", [255, 80, 0]))
        led_sw = ft.Container(width=36, height=36, border_radius=6, bgcolor=hexc(led_rgb), ink=True)
        led_int = ft.Slider(min=0, max=100, divisions=100,
                            value=dev_cfg.get("led_intensity", 80), label="{value}")

        def apply_led(*_):
            if state.get("dev") is not None:
                try:
                    with state["devlock"]:
                        state["dev"].set_led_color(led_rgb, brightness=int(led_int.value))
                except Exception as ex:
                    print("[led]", ex)

        def set_led_sw(rgb):
            led_rgb[:] = list(rgb); led_sw.bgcolor = hexc(led_rgb); led_sw.update()
            apply_led(); mark_dirty()
        led_sw.on_click = lambda e: pick_color(led_rgb, set_led_sw)
        led_int.on_change = lambda e: (apply_led(), mark_dirty())

        def store():
            dev_cfg["rotate"] = rot_dd.value
            dev_cfg["screen_off"] = so_dd.value
            dev_cfg["led_color"] = list(led_rgb)
            dev_cfg["led_intensity"] = int(led_int.value)

        # boton que alterna Apply <-> Close; vuelve a "Apply" si cambia algo
        applied = {"v": False}
        apply_btn = ft.FilledButton(t("set_apply"), icon=I.CHECK)
        cancel_btn = ft.TextButton(t("cancel"), on_click=lambda e: page.pop_dialog())

        def refresh_apply():
            apply_btn.text = t("a_close") if applied["v"] else t("set_apply")
            apply_btn.icon = I.CLOSE if applied["v"] else I.CHECK
            try:
                apply_btn.update()
            except Exception:
                pass

        def mark_dirty(*_):
            if applied["v"]:
                applied["v"] = False
                refresh_apply()

        def on_apply(e):
            if applied["v"]:          # estado "Close" -> cerrar
                page.pop_dialog()
            else:                      # estado "Apply" -> aplicar y pasar a "Close"
                store(); apply_led()
                applied["v"] = True
                refresh_apply()
        apply_btn.on_click = on_apply
        rot_dd.on_change = mark_dirty
        so_dd.on_change = mark_dirty

        async def do_export(e):
            path = await file_picker.save_file(
                dialog_title=t("set_export"), file_name="stream_dock_m18_config.json",
                file_type=ft.FilePickerFileType.CUSTOM, allowed_extensions=["json"])
            if path:
                try:
                    if not path.lower().endswith(".json"):
                        path += ".json"
                    with open(path, "w", encoding="utf-8") as f:
                        json.dump(state["cfg"], f, indent=2, ensure_ascii=False)
                    info(t("set_export_ok"))
                except Exception as ex:
                    info(str(ex))

        def _normalize_imported(cfg):
            if not cfg.get("scenes"):
                pages = cfg.get("pages") or [{"keys": {}}]
                cfg["scenes"] = [{"name": "Scene 1",
                                  "default_page": int(cfg.get("default_page", 0)),
                                  "pages": pages}]
            cfg.pop("pages", None); cfg.pop("default_page", None)
            cfg.setdefault("default_scene", 0)
            cfg.setdefault("aux", {})
            cfg.setdefault("brightness", 80)
            return cfg

        def _apply_imported(cfg):
            _normalize_imported(cfg)
            state["cfg"] = cfg
            state["sel_scene"] = 0; state["sel_page"] = 0; state["sel_key"] = None
            page.pop_dialog()
            if cfg.get("lang") in LANG_CODES:
                LANG_STATE["cur"] = cfg["lang"]; apply_language()
            refresh_scenes(); refresh_page_bar(); refresh_device()
            _autosave()

        async def do_import(e):
            files = await file_picker.pick_files(
                allow_multiple=False, file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["json"])
            if not files:
                return
            try:
                with open(files[0].path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                if not isinstance(cfg, dict) or not (cfg.get("scenes") or cfg.get("pages")):
                    raise ValueError("no config")
            except Exception:
                info(t("set_import_bad")); return
            page.show_dialog(ft.AlertDialog(modal=True, title=ft.Text(t("set_import")),
                content=ft.Text(t("set_import_confirm")),
                actions=[ft.FilledButton(t("ui_yes"), on_click=lambda ev: _apply_imported(cfg)),
                         ft.TextButton(t("ui_no"), on_click=lambda ev: page.pop_dialog())]))

        def do_reload(e):
            # re-lee config.json del disco (descarta cambios en memoria)
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
            except Exception as ex:
                info(str(ex)); return
            _apply_imported(cfg)

        def open_folder(e):
            # carpeta real donde viven config.json + icons/ del usuario
            folder = m18_paths.data_dir()
            if not os.path.isdir(folder):
                folder = (os.path.dirname(sys.executable)
                          if getattr(sys, "frozen", False) else HERE)
            try:
                if folder and os.path.isdir(folder):
                    os.startfile(folder)
            except Exception as ex:
                info(str(ex))

        def user_guide(e):
            import webbrowser
            # README empaquetado o del repo; si no, el repositorio
            for base in (m18_paths.resource_dir(), HERE):
                rd = os.path.join(base, "README.md")
                if os.path.isfile(rd):
                    try:
                        os.startfile(rd)
                        return
                    except Exception:
                        break
            try:
                webbrowser.open("https://github.com/jarcmaster")
            except Exception as ex:
                info(str(ex))

        def reset_device(e):
            def yes(ev):
                page.pop_dialog()
                dev_cfg.clear()
                rot_dd.value = "default"; so_dd.value = "never"
                led_rgb[:] = [255, 80, 0]; led_sw.bgcolor = hexc(led_rgb)
                led_int.value = 80
                for c in (rot_dd, so_dd, led_sw, led_int):
                    c.update()
                apply_led(); mark_dirty()
            page.show_dialog(ft.AlertDialog(modal=True, title=ft.Text(t("set_reset_device")),
                content=ft.Text(t("set_reset_confirm")),
                actions=[ft.FilledButton(t("ui_yes"), on_click=yes),
                         ft.TextButton(t("ui_no"), on_click=lambda e: page.pop_dialog())]))

        def _info_row(label, value):
            return ft.Row([ft.Text(f"{label}:", size=12, color="#9fb4d6"),
                           ft.Text(value, size=12, selectable=True, expand=True,
                                   no_wrap=False, overflow=ft.TextOverflow.VISIBLE)],
                          spacing=8, vertical_alignment=ft.CrossAxisAlignment.START)

        body = ft.Column([
            _info_row(t("set_serial"), serial),
            _info_row(t("set_firmware"), fw),
            ft.Divider(height=8),
            startup_chk,
            so_dd, rot_dd,
            ft.Row([ft.Text(f"{t('set_led_color')}:", size=12), led_sw]),
            ft.Text(f"{t('set_led_intensity')}:", size=12), led_int,
            ft.Divider(height=8),
            ft.Row([ft.FilledButton(t("set_export"), icon=I.FILE_UPLOAD, on_click=do_export),
                    ft.FilledButton(t("set_import"), icon=I.FILE_DOWNLOAD, on_click=do_import),
                    ft.FilledButton(t("set_reload"), icon=I.REFRESH, on_click=do_reload)],
                   wrap=True, spacing=8, run_spacing=8),
            _info_row(t("set_config_path"), CONFIG_PATH),
            ft.Row([ft.TextButton(t("help_title"), icon=I.HELP_OUTLINE, on_click=show_help),
                    ft.TextButton(t("about"), icon=I.INFO_OUTLINE, on_click=show_about)]),
            ft.Row([ft.TextButton(t("set_user_guide"), icon=I.MENU_BOOK, on_click=user_guide),
                    ft.TextButton(t("set_open_folder"), icon=I.FOLDER_OPEN, on_click=open_folder)]),
            ft.TextButton(t("set_reset_device"), icon=I.RESTART_ALT, on_click=reset_device),
        ], spacing=10, scroll=ft.ScrollMode.ALWAYS, expand=True)

        page.show_dialog(ft.AlertDialog(modal=True,
            title=ft.Text(t("set_title"), weight=ft.FontWeight.BOLD),
            content=ft.Container(width=460, height=720, content=ft.Column([
                ft.Container(content=body, expand=True),
                ft.Row([apply_btn, cancel_btn],
                       alignment=ft.MainAxisAlignment.END, spacing=8)]))))

    def show_obs_settings():
        obs = state["cfg"].setdefault("obs", {"host": "127.0.0.1", "port": 4455, "password": ""})
        host = ft.TextField(label=t("fld_server_ip"), value=obs.get("host", "127.0.0.1"), width=280)
        port = ft.TextField(label=t("fld_server_port"), value=str(obs.get("port", 4455)), width=280)
        pwd = ft.TextField(label=t("fld_server_password"), value=obs.get("password", ""), width=280,
                           password=True, can_reveal_password=True)
        status = ft.Text("", size=12)

        def store():
            state["cfg"]["obs"] = {"host": host.value.strip() or "127.0.0.1",
                                   "port": int(port.value or 4455), "password": pwd.value}
            return state["cfg"]["obs"]

        def connect(e):
            try:
                ver = sd_obs.test_connection(store())
                status.value = f"{t('obs_connected')} {ver}"; status.color = "#6c6"
            except Exception as ex:
                status.value = f"{t('err_prefix')} {ex}"; status.color = "#e66"
            status.update()

        def reset(e):
            host.value, port.value, pwd.value = "127.0.0.1", "4455", ""
            store(); host.update(); port.update(); pwd.update()

        dlg = ft.AlertDialog(modal=True, title=ft.Text(t("obs_plugin_title"), weight=ft.FontWeight.BOLD),
            content=ft.Container(width=340, height=460, content=ft.Column([host, port, pwd, status])),
            actions=[ft.FilledButton(t("connect"), on_click=connect),
                     ft.TextButton(t("ui_reset"), on_click=reset),
                     ft.TextButton(t("a_close"), on_click=lambda e: (store(), page.pop_dialog()))])
        page.show_dialog(dlg)

    def obs_header(otype):
        k = AID_TR.get(otype)
        return f"OBS: {t(k)}" if k else "OBS Studio"

    def open_obs(pos, otype):
        def ex(refresh, cur):
            act = cur.get("action", {}) if cur.get("action", {}).get("type") == otype else {}
            fields = {}
            status = ft.Text("", size=11, color="#e66")

            def obscfg():
                return state["cfg"].get("obs", {"host": "127.0.0.1", "port": 4455, "password": ""})

            ctrls = [ft.TextButton(t("obs_connection_btn"), icon=I.SETTINGS,
                                   on_click=lambda e: show_obs_settings())]
            if otype in ("obs_scene", "obs_source", "obs_green_up", "obs_green_dn"):
                scene = ft.Dropdown(label=t("fld_scene"), width=260, enable_search=True,
                                    value=act.get("scene", "") or None, options=[])

                def fsc(e):
                    try:
                        scene.options = [ft.DropdownOption(key=s, text=s) for s in sd_obs.get_scenes(obscfg())]
                        scene.update()
                    except Exception as ex:
                        status.value = f"OBS: {ex}"; status.update()
                ctrls.append(ft.Row([scene, ft.IconButton(I.REFRESH, tooltip=t("tip_fetch_obs"), on_click=fsc)]))
                fields["scene"] = scene
            if otype in ("obs_source", "obs_green_up", "obs_green_dn"):
                source = ft.Dropdown(label=t("fld_source"), width=260, enable_search=True,
                                     value=act.get("source", "") or None, options=[])

                def fsr(e):
                    try:
                        source.options = [ft.DropdownOption(key=s, text=s)
                                          for s in sd_obs.get_sources(obscfg(), fields["scene"].value)]
                        source.update()
                    except Exception as ex:
                        status.value = f"OBS: {ex}"; status.update()
                ctrls.append(ft.Row([source, ft.IconButton(I.REFRESH, on_click=fsr)]))
                fields["source"] = source
            if otype == "obs_source":
                _om = {"toggle": "om_toggle", "show": "om_show", "hide": "om_hide"}
                mode = ft.Dropdown(label=t("fld_mode"), width=200, value=act.get("mode", "toggle"),
                                   options=[ft.DropdownOption(key=m, text=t(_om[m])) for m in ("toggle", "show", "hide")])
                ctrls.append(mode); fields["mode"] = mode
            if otype == "obs_audio":
                inp = ft.Dropdown(label=t("fld_input"), width=260, enable_search=True,
                                  value=act.get("input", "") or None, options=[])

                def fin(e):
                    try:
                        inp.options = [ft.DropdownOption(key=s, text=s) for s in sd_obs.get_inputs(obscfg())]
                        inp.update()
                    except Exception as ex:
                        status.value = f"OBS: {ex}"; status.update()
                _oma = {"toggle": "om_toggle", "mute": "om_mute", "unmute": "om_unmute"}
                mode = ft.Dropdown(label=t("fld_mode"), width=200, value=act.get("mode", "toggle"),
                                   options=[ft.DropdownOption(key=m, text=t(_oma[m])) for m in ("toggle", "mute", "unmute")])
                ctrls.append(ft.Row([inp, ft.IconButton(I.REFRESH, on_click=fin)]))
                ctrls.append(mode); fields["input"] = inp; fields["mode"] = mode
            if otype == "obs_screenshot":
                folder = ft.TextField(label=t("fld_folder_opt"), value=act.get("folder", ""), width=300)

                async def pick_sshot_folder(e):
                    d = await file_picker.get_directory_path()
                    if d:
                        folder.value = d; folder.update()
                ctrls.append(ft.Row([folder, ft.IconButton(I.FOLDER_OPEN, tooltip=t("ui_choose_folder"),
                                                            on_click=pick_sshot_folder)]))
                fields["folder"] = folder
            ctrls.append(status)

            def build():
                s = {"type": otype}
                if "scene" in fields:
                    s["scene"] = fields["scene"].value or ""
                if "source" in fields:
                    s["source"] = fields["source"].value or ""
                if otype == "obs_source":
                    s["mode"] = fields["mode"].value
                if otype == "obs_audio":
                    s["input"] = fields["input"].value or ""
                    s["mode"] = fields["mode"].value
                if otype == "obs_screenshot" and (fields["folder"].value or "").strip():
                    s["folder"] = fields["folder"].value.strip()
                return s
            return (ctrls, build)
        key_shell(pos, obs_header(otype), [40, 20, 60], ex)

    def open_generic(pos, preset=None):
        keys = keys_of_page()
        cur = dict(keys.get(str(pos), {}))
        if state.pop("fresh", False):   # colocacion nueva -> titulo/icono en blanco
            cur["text"] = ""
            cur["image"] = ""
        act = cur.get("action", {}) or {}
        st = {"img": cur.get("image", ""), "fg": cur.get("fg", [255, 255, 255]),
              "bg": cur.get("bg", [0, 0, 0]), "font": cur.get("font")}
        fonts = get_system_fonts()
        fontnames = list(fonts.keys())
        curfont = next((n for n, p in fonts.items() if p == st["font"]),
                       "Arial" if "Arial" in fonts else (fontnames[0] if fontnames else None))
        st["font"] = fonts.get(curfont)
        title_tf = ft.TextField(label=f"{t('fld_text')} {t('ui_max3')}", value=cur.get("text", "") or "",
                                multiline=True, min_lines=3, max_lines=3, width=320,
                                on_change=lambda e: (_clamp_lines(title_tf), refr()))
        preview = ft.Image(src=render_key_src({"text": cur.get("text", "") or "", "image": st["img"],
                                               "fg": st["fg"], "bg": st["bg"], "font": st["font"]}),
                           width=96, height=96, border_radius=8)
        fgsw = ft.Container(width=30, height=30, border_radius=5, bgcolor=hexc(st["fg"]), ink=True,
                            tooltip=t("tip_fg_color"),
                            on_click=lambda e: pick_color(st["fg"], apply_fg))
        bgsw = ft.Container(width=30, height=30, border_radius=5, bgcolor=hexc(st["bg"]), ink=True,
                            tooltip=t("tip_bg_color"),
                            on_click=lambda e: pick_color(st["bg"], apply_bg))
        fgtf = ft.TextField(label=t("fld_fg_hex"), value=hexc(st["fg"]), width=130, on_change=lambda e: setfg())
        bgtf = ft.TextField(label=t("fld_bg_hex"), value=hexc(st["bg"]), width=130, on_change=lambda e: setbg())
        fontdd = ft.Dropdown(label=t("fld_font"), width=240, value=curfont,
                             options=[ft.DropdownOption(key=n, text=n) for n in fontnames],
                             on_select=lambda e: setfont())
        type_dd = ft.Dropdown(label=t("fld_action"), width=220, value=(preset or act.get("type", "none")),
                              options=[ft.DropdownOption(key=_ty, text=_ty) for _ty in ACTION_TYPES],
                              on_select=lambda e: upd())
        param = ft.TextField(label=t("fld_param"), value=_param_from(act), width=260)
        browser_dd = ft.Dropdown(label=t("fld_browser"), width=200, visible=False,
                                 value=act.get("browser", "default"),
                                 options=[ft.DropdownOption(key=v, text=n) for n, v in BROWSERS])
        capture_btn = ft.FilledButton(t("ui_capture"), icon=I.KEYBOARD, visible=False,
                                      on_click=lambda e: capture())

        def refr():
            preview.src = render_key_src({"text": title_tf.value, "image": st["img"],
                                          "fg": st["fg"], "bg": st["bg"], "font": st["font"]})
            preview.update()

        def setfg():
            st["fg"] = _hex2rgb(fgtf.value); fgsw.bgcolor = hexc(st["fg"]); fgsw.update(); refr()

        def setbg():
            st["bg"] = _hex2rgb(bgtf.value); bgsw.bgcolor = hexc(st["bg"]); bgsw.update(); refr()

        def apply_fg(rgb):
            st["fg"] = rgb; fgtf.value = hexc(rgb); fgsw.bgcolor = hexc(rgb)
            fgtf.update(); fgsw.update(); refr()

        def apply_bg(rgb):
            st["bg"] = rgb; bgtf.value = hexc(rgb); bgsw.bgcolor = hexc(rgb)
            bgtf.update(); bgsw.update(); refr()

        def setfont():
            st["font"] = fonts.get(fontdd.value); refr()

        def upd():
            browser_dd.visible = (type_dd.value == "open_url"); browser_dd.update()
            capture_btn.visible = (type_dd.value == "hotkey"); capture_btn.update()

        def capture():
            def onkey(e):
                k = getattr(e, "key", None)
                if not k or k.lower() in ("control", "alt", "shift", "meta"):
                    return
                mods = []
                if getattr(e, "ctrl", False):
                    mods.append("ctrl")
                if getattr(e, "alt", False):
                    mods.append("alt")
                if getattr(e, "shift", False):
                    mods.append("shift")
                param.value = "+".join(mods + [_normkey(k)]); param.update()
                page.on_keyboard_event = None
            page.on_keyboard_event = onkey

        def build():
            if type_dd.value == "open_url":
                u = (param.value or "").strip()
                if u and "://" not in u:
                    u = "https://" + u
                return {"type": "open_url", "url": u, "browser": browser_dd.value or "default"}
            return _build_action(type_dd.value, param.value)

        def save(e):
            s = {"fg": st["fg"], "bg": st["bg"]}
            if st["font"]:
                s["font"] = st["font"]
            t = "\n".join((title_tf.value or "").split("\n")[:3])
            if st["img"]:
                s["image"] = st["img"]
            if t.strip():
                s["text"] = t
            a = build()
            if a:
                s["action"] = a
            keys[str(pos)] = s
            page.pop_dialog(); refresh_device()

        def delete(e):
            keys.pop(str(pos), None); page.pop_dialog(); refresh_device()

        content = ft.Container(width=700, height=720, content=ft.Row([
            ft.Container(content=preview, bgcolor="#1b1b22", border_radius=8, padding=4),
            ft.Column([title_tf, fontdd, ft.Row([fgtf, fgsw, bgtf, bgsw]),
                       ft.Row([ft.FilledButton(t("gallery"), icon=I.IMAGE,
                                               on_click=lambda e: show_gallery(lambda p: (st.update(img=p), refr()))),
                               ft.TextButton(t("remove_icon"), on_click=lambda e: (st.update(img=""), refr()))]),
                       ft.Divider(), ft.Row([type_dd, param]),
                       ft.Row([browser_dd, capture_btn])], expand=True,
                      scroll=ft.ScrollMode.ALWAYS, spacing=8)], spacing=16,
            vertical_alignment=ft.CrossAxisAlignment.START))
        dlg = ft.AlertDialog(modal=True, content=content,
            title=ft.Row([ft.Text(f"{t('ui_key_word')} {pos}", weight=ft.FontWeight.BOLD),
                          ft.IconButton(I.DELETE, icon_color="#e05555", on_click=delete)],
                         alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            actions=[ft.FilledButton(t("save"), icon=I.CHECK, on_click=save),
                     ft.TextButton(t("cancel"), on_click=lambda e: page.pop_dialog())])
        page.show_dialog(dlg); refr(); upd()

    def open_close(pos):
        apps = get_installed_apps()

        def ex(refresh, cur):
            act = cur.get("action", {}) if cur.get("action", {}).get("type") == "close" else {}
            app = ft.TextField(label=t("cls_app"), value=act.get("app", ""), width=320)

            async def pick_exe(e):
                try:
                    files = await file_picker.pick_files(
                        allow_multiple=False, file_type=ft.FilePickerFileType.CUSTOM,
                        allowed_extensions=["exe", "bat", "cmd", "com", "msi", "lnk", "ps1", "vbs"])
                except Exception:
                    files = await file_picker.pick_files(allow_multiple=False)
                if files:
                    app.value = files[0].path; app.update()

            run_dd = ft.Dropdown(label=t("cls_running"), width=300, enable_search=True, options=[])

            def load_running(e=None):
                run_dd.options = [ft.DropdownOption(key=img, text=f"{img}  —  {title}")
                                  for img, title in get_running_apps().items()]
                run_dd.update()

            def on_run(e):
                if run_dd.value:
                    app.value = run_dd.value; app.update()
            run_dd.on_change = on_run

            inst_dd = ft.Dropdown(label=t("cls_installed"), width=300, enable_search=True,
                                  options=[ft.DropdownOption(key=p, text=n) for n, p in apps.items()])

            def on_inst(e):
                if inst_dd.value:
                    app.value = inst_dd.value; app.update()
            inst_dd.on_change = on_inst

            force = ft.Checkbox(label=t("cls_force"), value=act.get("force", False))
            note = ft.Text(t("cls_note"), size=11, color="#888")

            app_row = ft.Row([app, ft.IconButton(I.INSERT_DRIVE_FILE,
                                                 tooltip=t("cls_locate"), on_click=pick_exe)])
            run_row = ft.Row([run_dd, ft.IconButton(I.REFRESH, tooltip=t("cls_refresh"),
                                                    on_click=load_running)])

            def build():
                return {"type": "close", "app": (app.value or "").strip(), "force": force.value}
            return ([app_row, run_row, inst_dd, force, note], build)
        key_shell(pos, thdr("cat_toolbox", "a_close"), [60, 20, 20], ex)

    def open_devsleep(pos):
        def ex(refresh, cur):
            return ([ft.Text(t("devsleep_note"), size=12, color="#888")],
                    lambda: {"type": "devsleep"})
        key_shell(pos, thdr("Stream Dock", "a_devsleep"), [20, 20, 30], ex)

    def open_mouse(pos):
        EVTS = [("mev_left", "left"), ("mev_right", "right"),
                ("mev_double", "double"), ("mev_middle", "middle"),
                ("mev_scroll_up", "scroll_up"), ("mev_scroll_down", "scroll_down"),
                ("mev_move", "move")]
        EV_KEYS = [v for _, v in EVTS]
        try:
            monitors = sd_actions.list_monitors()
        except Exception:
            monitors = []

        def ex(refresh, cur):
            act = cur.get("action", {}) if cur.get("action", {}).get("type") == "mouse" else {}
            rec = {"on": False, "abort": False, "thread": None,
                   "frames": list(act.get("steps", []) or []),
                   "rec_monitors": act.get("rec_monitors") or []}

            # --- evento ---
            dd = ft.Dropdown(label=t("mev_event"), width=240,
                             value=(act.get("event") if act.get("event") in EV_KEYS else "left"),
                             options=[ft.DropdownOption(key=v, text=t(k)) for k, v in EVTS])

            # --- monitor destino ---
            mon_opts = [ft.DropdownOption(key="-1", text=t("mev_full_desktop"))]
            for m in monitors:
                tag = f" ★ {t('mev_primary')}" if m["primary"] else ""
                mon_opts.append(ft.DropdownOption(
                    key=str(m["index"]),
                    text=f"{t('mev_monitor_label')} {m['index'] + 1}: {m['width']}×{m['height']} @ ({m['x']},{m['y']}){tag}"))
            _cm = act.get("monitor")
            mon_dd = ft.Dropdown(label=t("mev_monitor_dest"), width=360,
                                 value=str(_cm) if _cm is not None else "-1",
                                 options=mon_opts)
            mon_hint = ft.Text(f"{len(monitors)} {t('mev_mon_hint')}", size=11, color="#888")

            def _sel_monitor_index():
                v = mon_dd.value
                if v in (None, "-1"):
                    return None
                try:
                    return int(v)
                except (TypeError, ValueError):
                    return None

            # --- coordenadas X/Y ---
            use_xy = ft.Checkbox(label=t("mev_goto_xy"),
                                 value=(act.get("x") is not None and act.get("y") is not None))
            x_tf = ft.TextField(label="X", width=110,
                                value=("" if act.get("x") is None else str(act.get("x"))))
            y_tf = ft.TextField(label="Y", width=110,
                                value=("" if act.get("y") is None else str(act.get("y"))))

            def center_xy(e):
                mi = _sel_monitor_index()
                if mi is not None and 0 <= mi < len(monitors):
                    m = monitors[mi]
                    x_tf.value = str(m["width"] // 2); y_tf.value = str(m["height"] // 2)
                elif monitors:
                    m = next((mm for mm in monitors if mm["primary"]), monitors[0])
                    x_tf.value = str(m["x"] + m["width"] // 2); y_tf.value = str(m["y"] + m["height"] // 2)
                use_xy.value = True
                x_tf.update(); y_tf.update(); use_xy.update()

            def capture_pos(e):
                cap_btn.disabled = True; cap_btn.update()

                def run():
                    import ctypes

                    class POINT(ctypes.Structure):
                        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
                    for s in (3, 2, 1):
                        sd_actions.show_overlay(str(s), "#3a8fd0", mode="count",
                                                subtitle=t("mev_place_cursor"))
                        try:
                            status.value = f"{t('mev_capturing_in')} {s}... {t('mev_place_cursor')}"
                            status.update()
                        except Exception:
                            pass
                        time.sleep(1.0)
                    pt = POINT(); ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
                    sd_actions.close_overlay()
                    ax, ay = int(pt.x), int(pt.y)
                    mi = _sel_monitor_index()
                    if mi is not None and 0 <= mi < len(monitors):
                        ax -= monitors[mi]["x"]; ay -= monitors[mi]["y"]
                    try:
                        x_tf.value = str(ax); y_tf.value = str(ay)
                        use_xy.value = True
                        status.value = f"{t('mev_captured')} ({ax}, {ay})"
                        cap_btn.disabled = False
                        x_tf.update(); y_tf.update(); use_xy.update(); status.update(); cap_btn.update()
                    except Exception:
                        pass
                threading.Thread(target=run, daemon=True).start()

            cap_btn = ft.FilledButton(t("mev_capture_pos"), icon=I.MY_LOCATION, on_click=capture_pos)
            center_btn = ft.TextButton(t("mev_center_monitor"), icon=I.CENTER_FOCUS_STRONG, on_click=center_xy)

            # --- grabador de rutina ---
            counter = ft.Text(f"{t('mev_frames')} {len(rec['frames'])}", size=12, color="#9fb4d6")
            rep_tf = ft.TextField(label=t("mev_repeat"), width=100,
                                  value=str(act.get("repeat", 1) or 1))
            _spd = str(int(act.get("speed", 1) or 1))
            if _spd not in ("1", "2", "3", "4", "5"):
                _spd = "1"
            speed_dd = ft.Dropdown(label=t("mev_speed"), width=120, value=_spd,
                                   options=[ft.DropdownOption(key=str(n), text=f"{n}x")
                                            for n in (1, 2, 3, 4, 5)])
            status = ft.Text("", size=11, color="#d0a877")
            _stop_cur = act.get("stop", "ESC")
            if _stop_cur not in sd_actions.STOP_HOTKEYS:
                _stop_cur = "ESC"
            stop_dd = ft.Dropdown(label=t("mev_stop_key"), width=200, value=_stop_cur,
                                  options=[ft.DropdownOption(key=k, text=k)
                                           for k in sd_actions.STOP_HOTKEYS.keys()])
            kb_chk = ft.Checkbox(label=t("mev_record_keyboard"),
                                 value=bool(act.get("record_keys", False)))

            _win = {"hwnd": 0}

            def _win_minimize(mini):
                # Win32 directo: restaurar desde un hilo con la API de Flet no es
                # fiable cuando la ventana esta minimizada.
                try:
                    import ctypes
                    u = ctypes.windll.user32
                    u.GetForegroundWindow.restype = ctypes.c_void_p
                    u.FindWindowW.restype = ctypes.c_void_p
                    u.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
                    u.SetForegroundWindow.argtypes = [ctypes.c_void_p]
                    if mini:
                        hwnd = u.GetForegroundWindow()
                        if hwnd:
                            _win["hwnd"] = hwnd
                        if _win["hwnd"]:
                            u.ShowWindow(_win["hwnd"], 6)   # SW_MINIMIZE
                    else:
                        hwnd = _win["hwnd"] or u.FindWindowW(
                            None, WINDOW_TITLE)
                        if hwnd:
                            u.ShowWindow(hwnd, 9)           # SW_RESTORE
                            u.SetForegroundWindow(hwnd)
                        else:  # ultimo recurso: API de Flet
                            page.window.minimized = False
                            page.window.focused = True
                            page.window.update()
                except Exception as ex:
                    print("[win]", ex)

            def _repeat():
                try:
                    return max(1, int(rep_tf.value))
                except (TypeError, ValueError):
                    return 1

            def _sync_buttons():
                has = bool(rec["frames"])
                try:
                    rec_btn.text = t("mev_rerecord") if has else t("mev_record")
                    test_btn.disabled = not has
                    clear_btn.disabled = not has
                    rec_btn.update(); test_btn.update(); clear_btn.update()
                except Exception:
                    pass

            def _rec_loop(stopname, rec_keys):
                import ctypes
                user32 = ctypes.windll.user32

                class POINT(ctypes.Structure):
                    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
                pt = POINT()

                def down(vk):
                    return bool(user32.GetAsyncKeyState(vk) & 0x8000)
                stop_vks = sd_actions.STOP_HOTKEYS.get(stopname, [0x1B])
                key_vks = []
                if rec_keys:
                    for vk in range(0x08, 0xFF):
                        if vk in (0x01, 0x02, 0x04, 0x05, 0x06):
                            continue
                        if vk in stop_vks:
                            continue
                        if sd_actions._vk_to_key(vk):
                            key_vks.append(vk)
                mons_rec = sd_actions.list_monitors()
                rec["rec_monitors"] = [{"index": mm["index"], "width": mm["width"],
                                        "height": mm["height"]} for mm in mons_rec]
                frames = []; t0 = time.perf_counter()
                last_pos = None; last_btn = (False, False, False); prev_keys = set()
                last_ui = 0.0
                while rec["on"]:
                    if all(down(v) for v in stop_vks):   # hotkey de parada
                        break
                    user32.GetCursorPos(ctypes.byref(pt))
                    l, r, m = down(0x01), down(0x02), down(0x04)
                    cur_keys = set(v for v in key_vks if down(v)) if rec_keys else set()
                    moved = (last_pos is None or abs(pt.x - last_pos[0]) >= 2
                             or abs(pt.y - last_pos[1]) >= 2)
                    btn_chg = (l, r, m) != last_btn
                    kd = sorted(cur_keys - prev_keys)
                    ku = sorted(prev_keys - cur_keys)
                    if moved or btn_chg or kd or ku:
                        ms = int((time.perf_counter() - t0) * 1000)
                        fr = {"t": ms, "x": int(pt.x), "y": int(pt.y), "l": l, "r": r, "m": m}
                        mi = sd_actions.monitor_at(pt.x, pt.y, mons_rec)
                        if mi is not None:
                            fr["mon"] = mi
                            fr["rx"] = int(pt.x) - mons_rec[mi]["x"]
                            fr["ry"] = int(pt.y) - mons_rec[mi]["y"]
                        if kd:
                            fr["kd"] = kd
                        if ku:
                            fr["ku"] = ku
                        frames.append(fr)
                        last_pos = (pt.x, pt.y); last_btn = (l, r, m); prev_keys = cur_keys
                        if len(frames) >= 8000:
                            break
                    # IMPORTANTE: no actualizar la UI en cada frame (bloquea el hilo
                    # con la ventana minimizada y se pierden muestras). Max ~4 Hz.
                    now = time.perf_counter()
                    if now - last_ui > 0.25:
                        last_ui = now
                        try:
                            counter.value = f"{t('mev_frames')} {len(frames)}"; counter.update()
                        except Exception:
                            pass
                    time.sleep(0.012)
                rec["on"] = False
                rec["frames"] = frames
                sd_actions.close_overlay()
                _win_minimize(False)
                try:
                    status.value = f"{t('mev_rec_stopped')} {len(frames)} {t('mev_frames_word')}."
                    counter.value = f"{t('mev_frames')} {len(frames)}"
                    rec_btn.disabled = False; stop_btn.disabled = True
                    status.update(); counter.update(); rec_btn.update(); stop_btn.update()
                except Exception:
                    pass
                _sync_buttons()

            def _confirm_regrab(e):
                if not rec["frames"]:
                    start_rec(e)
                    return

                def yes(ev):
                    page.pop_dialog()
                    start_rec(ev)
                page.show_dialog(ft.AlertDialog(
                    modal=True, title=ft.Text(t("mev_rerecord")),
                    content=ft.Text(t("mev_regrab_body")),
                    actions=[ft.FilledButton(t("mev_regrab_yes"), icon=I.FIBER_MANUAL_RECORD, on_click=yes),
                             ft.TextButton(t("cancel"), on_click=lambda ev: page.pop_dialog())]))

            def start_rec(e):
                if rec["on"]:
                    return
                rec["abort"] = False
                rec_btn.disabled = True; stop_btn.disabled = False
                test_btn.disabled = True; clear_btn.disabled = True
                rec_btn.update(); stop_btn.update(); test_btn.update(); clear_btn.update()
                stopname = stop_dd.value or "ESC"
                rec_keys = bool(kb_chk.value)
                _win_minimize(True)

                def pre():
                    for s in (3, 2, 1):
                        if rec["abort"]:
                            break
                        sd_actions.show_overlay(str(s), "#f0a030", mode="count",
                                                subtitle=t("ov_preparing"))
                        try:
                            status.value = f"{t('mev_recording_in')} {s}..."; status.update()
                        except Exception:
                            pass
                        time.sleep(1.0)
                    if rec["abort"]:
                        sd_actions.close_overlay(); _win_minimize(False)
                        try:
                            status.value = t("mev_cancelled")
                            rec_btn.disabled = False; stop_btn.disabled = True
                            status.update(); rec_btn.update(); stop_btn.update()
                        except Exception:
                            pass
                        _sync_buttons()
                        return
                    extra = f" {t('ov_plus_keyboard')}" if rec_keys else ""
                    sd_actions.show_overlay(
                        f"{t('ov_rec_mouse')}{extra}  —  {t('ov_press')} {stopname} {t('ov_to_stop')}",
                        "#c0392b")
                    rec["on"] = True
                    _rec_loop(stopname, rec_keys)
                rec["thread"] = threading.Thread(target=pre, daemon=True)
                rec["thread"].start()

            def stop_rec(e):
                rec["abort"] = True; rec["on"] = False
                try:
                    status.value = t("mev_stopping"); status.update()
                except Exception:
                    pass

            def clear_rec(e):
                rec["frames"] = []
                counter.value = f"{t('mev_frames')} 0"
                status.value = t("mev_deleted")
                counter.update(); status.update()
                _sync_buttons()

            def build():
                if rec["frames"]:
                    _stopk = stop_dd.value or "ESC"
                    return {"type": "mouse", "event": "macro",
                            "steps": rec["frames"], "repeat": _repeat(),
                            "speed": int(speed_dd.value or 1),
                            "stop": _stopk,
                            "record_keys": bool(kb_chk.value),
                            "rec_monitors": rec.get("rec_monitors") or [],
                            "overlay_text": f"{t('ov_playing')}  —  {t('ov_press')} {_stopk} {t('ov_to_stop')}"}
                spec = {"type": "mouse", "event": dd.value or "left"}
                mi = _sel_monitor_index()
                if mi is not None:
                    spec["monitor"] = mi
                if use_xy.value and (x_tf.value or "").strip() and (y_tf.value or "").strip():
                    try:
                        spec["x"] = int(float(x_tf.value)); spec["y"] = int(float(y_tf.value))
                    except (TypeError, ValueError):
                        pass
                return spec

            def do_test(e):
                spec = build()
                a = sd_actions.from_spec(spec)
                if not callable(a):
                    return
                is_macro = bool(rec["frames"])

                def run():
                    try:
                        status.value = t("mev_testing"); status.update()
                    except Exception:
                        pass
                    if is_macro:
                        _win_minimize(True); time.sleep(0.4)
                    try:
                        a(None)
                    except Exception as ex:
                        print("[mouse test]", ex)
                    finally:
                        if is_macro:
                            sd_actions.close_overlay(); _win_minimize(False)
                    try:
                        status.value = t("mev_test_done"); status.update()
                    except Exception:
                        pass
                threading.Thread(target=run, daemon=True).start()

            _has0 = bool(rec["frames"])
            rec_btn = ft.FilledButton(t("mev_rerecord") if _has0 else t("mev_record"),
                                      icon=I.FIBER_MANUAL_RECORD, on_click=_confirm_regrab)
            stop_btn = ft.FilledButton(t("mev_stop_btn"), icon=I.STOP, on_click=stop_rec, disabled=True)
            test_btn = ft.OutlinedButton(t("mev_test"), icon=I.PLAY_ARROW, on_click=do_test,
                                         disabled=not _has0)
            clear_btn = ft.TextButton(t("mev_clear"), icon=I.DELETE_SWEEP, on_click=clear_rec,
                                      disabled=not _has0)

            controls = [
                dd,
                ft.Divider(height=6),
                ft.Row([ft.Icon(I.MONITOR, size=16, color="#9fb4d6"),
                        ft.Text(t("mev_monitor_pos"), size=12, weight=ft.FontWeight.BOLD)]),
                mon_dd, mon_hint,
                use_xy,
                ft.Row([x_tf, y_tf, cap_btn, center_btn]),
                ft.Divider(height=6),
                ft.Row([ft.Icon(I.MOUSE, size=16, color="#9fb4d6"),
                        ft.Text(t("mev_recorder"), size=12, weight=ft.FontWeight.BOLD)]),
                ft.Text(t("mev_recorder_note"), size=11, color="#888"),
                stop_dd,
                kb_chk,
                ft.Row([rec_btn, stop_btn]),
                ft.Row([rep_tf, speed_dd]),
                ft.Row([test_btn, clear_btn]),
                counter, status,
            ]
            return (controls, build)
        key_shell(pos, thdr("cat_toolbox", "a_mouse"), [45, 35, 25], ex)

    def open_text(pos):
        def ex(refresh, cur):
            act = cur.get("action", {}) if cur.get("action", {}).get("type") == "write_text" else {}
            txt = ft.TextField(label=t("fld_text"), value=act.get("text", ""), multiline=True,
                               min_lines=6, max_lines=12, width=400)
            counter = ft.Text(f"{len(act.get('text', '') or '')} / 5000", size=11, color="#888")

            def on_txt(e):
                if txt.value and len(txt.value) > 5000:
                    txt.value = txt.value[:5000]; txt.update()
                counter.value = f"{len(txt.value or '')} / 5000"; counter.update()
            txt.on_change = on_txt
            en = ft.Checkbox(label=t("chk_press_enter"), value=act.get("enter", False))
            pa = ft.Checkbox(label=t("chk_use_clipboard"), value=act.get("paste", True))

            def build():
                return {"type": "write_text", "text": txt.value or "",
                        "enter": en.value, "paste": pa.value}
            return ([txt, counter, en, pa], build)
        key_shell(pos, thdr("cat_toolbox", "a_text"), [50, 40, 10], ex)

    def open_scene_shift(pos):
        def ex(refresh, cur):
            act = cur.get("action", {}) if cur.get("action", {}).get("type") == "scene_shift" else {}
            opts = [ft.DropdownOption(key="prev", text=t("scn_prev")),
                    ft.DropdownOption(key="next", text=t("scn_next"))]
            for i, sc in enumerate(state["cfg"]["scenes"]):
                opts.append(ft.DropdownOption(key=str(i), text=f"{i + 1}. {sc.get('name', 'Scene')}"))
            tgt = act.get("target", "next")
            val = tgt if tgt in ("prev", "next") else str(tgt)
            dd = ft.Dropdown(label=t("scn_target"), width=320, value=val, options=opts)

            def build():
                v = dd.value or "next"
                if v in ("prev", "next"):
                    return {"type": "scene_shift", "target": v}
                return {"type": "scene_shift", "target": int(v)}
            return ([dd, ft.Text(t("scene_shift_note"), size=11, color="#888")], build)
        key_shell(pos, thdr("Stream Dock", "a_scene_shift"), [30, 40, 60], ex)

    def open_page_indicator(pos):
        def ex(refresh, cur):
            return ([ft.Text(t("page_ind_note"), size=12, color="#888")],
                    lambda: {"type": "page_indicator"})
        key_shell(pos, thdr("Stream Dock", "a_page_indicator"), [30, 30, 40], ex)

    def open_hotkey_switch(pos):
        def ex(refresh, cur):
            act = cur.get("action", {}) if cur.get("action", {}).get("type") == "hotkey_switch" else {}
            a_tf = ft.TextField(label=t("hs_shortcut_a"), value="+".join(act.get("a", [])), width=220)
            b_tf = ft.TextField(label=t("hs_shortcut_b"), value="+".join(act.get("b", [])), width=220)
            rows = [ft.Row([a_tf, ft.FilledButton(t("hs_capture_a"), on_click=lambda e: hk_capture(a_tf))]),
                    ft.Row([b_tf, ft.FilledButton(t("hs_capture_b"), on_click=lambda e: hk_capture(b_tf))]),
                    ft.Text(t("hs_note"), size=11, color="#888")]

            def build():
                return {"type": "hotkey_switch", "a": _keys_of(a_tf.value), "b": _keys_of(b_tf.value)}
            return (rows, build)
        key_shell(pos, thdr("cat_toolbox", "a_hotkey_switch"), [45, 30, 20], ex)

    def open_super(pos):
        def ex(refresh, cur):
            act = cur.get("action", {}) if cur.get("action", {}).get("type") == "super_hotkeys" else {}
            tf = ft.TextField(label=t("sh_sequence"),
                              value=act.get("script", ""), multiline=True, min_lines=5, max_lines=7, width=380)
            hint = ft.Text(t("super_hint"), size=11, color="#888")

            # --- selector visual de teclas ---
            mods = {v: ft.Checkbox(label=n, value=False) for n, v in HK_MODS}
            delay_tf = ft.TextField(label=t("shk_delay"), width=110, value="")
            preview = ft.Text("—", size=14, weight=ft.FontWeight.BOLD, color="#9fb4d6")
            sel = {"key": None}

            def _combo_keys():
                ks = [v for _n, v in HK_MODS if mods[v].value]
                if sel["key"]:
                    ks.append(sel["key"])
                return ks

            def _upd_preview():
                s = "+".join(_combo_keys())
                preview.value = s or "—"
                try:
                    preview.update()
                except Exception:
                    pass

            for cb in mods.values():
                cb.on_change = lambda e: _upd_preview()

            def add_combo(keys):
                if not keys:
                    return
                line = "+".join(keys)
                d = (delay_tf.value or "").strip()
                if d.isdigit() and int(d) > 0:
                    line += ":" + d
                base = tf.value or ""
                if base and not base.endswith("\n"):
                    base += "\n"
                tf.value = base + line
                tf.update()

            def pick_leaf(val):
                sel["key"] = val
                add_combo(_combo_keys())
                sel["key"] = None
                _upd_preview()

            def leaf(disp, val):
                return ft.MenuItemButton(content=ft.Text(disp),
                                         on_click=lambda e, v=val: pick_leaf(v))

            def submenu(label, items):
                return ft.SubmenuButton(content=ft.Text(label),
                                        controls=[leaf(d, v) for d, v in items])

            menu = ft.MenuBar(controls=[ft.SubmenuButton(
                content=ft.Text(t("shk_select")),
                controls=[
                    submenu(t("shk_letters"), HK_LETTERS),
                    *[leaf(d, v) for d, v in HK_ARROWS],
                    *[leaf(d, v) for d, v in HK_COMMON],
                    submenu(t("shk_numpad"), HK_NUMPAD),
                    submenu(t("shk_fkey"), HK_FKEY),
                    submenu(t("shk_other"), HK_OTHER),
                    submenu(t("shk_mod_only"), HK_MOD_ONLY),
                ])])

            def add_mods_only(e):
                add_combo([v for _n, v in HK_MODS if mods[v].value])

            builder = [
                ft.Divider(height=6),
                ft.Text(t("shk_builder"), size=12, weight=ft.FontWeight.BOLD),
                ft.Row([mods["ctrl"], mods["shift"], mods["alt"], mods["win"]], wrap=True),
                ft.Row([ft.Container(content=menu, width=230), delay_tf],
                       alignment=ft.MainAxisAlignment.START),
                ft.Row([ft.Text(t("shk_preview") + ":"), preview,
                        ft.TextButton(t("shk_add_mods"), icon=I.ADD, on_click=add_mods_only)]),
            ]

            def build():
                return {"type": "super_hotkeys", "script": tf.value or ""}
            return ([tf, hint, *builder], build)
        key_shell(pos, thdr("cat_toolbox", "a_super_hotkeys"), [40, 20, 50], ex)

    def open_flow(pos, kind):
        header = thdr("cat_opflow", "a_action_flow" if kind == "action_flow" else "a_carousel")

        def ex(refresh, cur):
            act = cur.get("action", {}) if cur.get("action", {}).get("type") == kind else {}
            tf = ft.TextField(label=t("flow_actions"),
                              value=act.get("script", ""), multiline=True, min_lines=5, max_lines=9, width=400)
            hint = ft.Text(t("flow_types_hint") + "\n"
                           "hotkey ctrl+c\nrun notepad.exe\nmultimedia playpause", size=11, color="#888")
            note = t("flow_runs_all") if kind == "action_flow" else t("flow_rotates")

            def build():
                return {"type": kind, "script": tf.value or ""}
            return ([tf, ft.Text(note, size=12, color="#9fb4d6"), hint], build)
        key_shell(pos, header, [40, 30, 20], ex)

    def open_toggle(pos):
        def ex(refresh, cur):
            act = cur.get("action", {}) if cur.get("action", {}).get("type") == "action_toggle" else {}
            a, b = act.get("a", {}) or {}, act.get("b", {}) or {}
            at = ft.Dropdown(label=t("tg_a_type"), width=150, value=a.get("type", "hotkey"),
                             options=[ft.DropdownOption(key=_st, text=_st) for _st in SUB_TYPES])
            ap = ft.TextField(label=t("tg_a_param"), value=_param_from(a), width=220)
            bt = ft.Dropdown(label=t("tg_b_type"), width=150, value=b.get("type", "hotkey"),
                             options=[ft.DropdownOption(key=_st, text=_st) for _st in SUB_TYPES])
            bp = ft.TextField(label=t("tg_b_param"), value=_param_from(b), width=220)

            def build():
                return {"type": "action_toggle",
                        "a": _build_action(at.value, ap.value),
                        "b": _build_action(bt.value, bp.value)}
            return ([ft.Row([at, ap]), ft.Row([bt, bp]),
                     ft.Text(t("tg_note"), size=11, color="#888")], build)
        key_shell(pos, thdr("cat_opflow", "a_action_toggle"), [40, 30, 50], ex)

    def open_action(pos, kind):
        state["sel_key"] = pos
        if kind == "create_folder":
            return open_folder(pos)
        if kind == "write_text":
            return open_text(pos)
        if kind == "close":
            return open_close(pos)
        if kind == "devsleep":
            return open_devsleep(pos)
        if kind == "mouse":
            return open_mouse(pos)
        if kind == "scene_shift":
            return open_scene_shift(pos)
        if kind == "page_indicator":
            return open_page_indicator(pos)
        if kind == "hotkey_switch":
            return open_hotkey_switch(pos)
        if kind == "super_hotkeys":
            return open_super(pos)
        if kind in ("action_flow", "carousel"):
            return open_flow(pos, kind)
        if kind == "action_toggle":
            return open_toggle(pos)
        if kind == "open_url":
            return open_website(pos)
        if kind == "password":
            return open_password(pos)
        if kind == "open":
            return open_open(pos)
        if kind == "open_app":
            return open_openapp(pos)
        if kind == "multimedia":
            return open_multimedia(pos)
        if kind == "play_audio":
            return open_play_audio(pos)
        if kind == "stop_audio":
            return open_stop_audio(pos)
        if kind == "brightness":
            return open_brightness(pos)
        if kind and kind.startswith("obs_"):
            return open_obs(pos, kind)
        open_generic(pos, preset=(kind if kind in ACTION_TYPES else None))

    # ---------- drag & drop ----------
    def _aid_from_event(e):
        d = e.data
        if isinstance(d, str) and d in ALL_AIDS:
            return d
        try:
            c = page.get_control(d)
            if c is not None and getattr(c, "data", None):
                return c.data
        except Exception:
            pass
        return d

    def drop_on(pos, aid):
        if not aid:
            return
        keys = keys_of_page()

        def do():
            state["sel_key"] = pos
            refresh_device()
            assign(aid)

        if keys.get(str(pos)):
            page.show_dialog(ft.AlertDialog(modal=True, title=ft.Text(t("ui_replace")),
                content=ft.Text(f"{t('ui_key_word')} {pos} {t('ui_replace_body')}"),
                actions=[ft.FilledButton(t("ui_yes"), on_click=lambda e: (page.pop_dialog(), do())),
                         ft.TextButton(t("ui_no"), on_click=lambda e: page.pop_dialog())]))
        else:
            do()

    # ---------- copiar / pegar / mover teclas ----------
    import copy as _copy

    def _confirm_overwrite(pos, do_fn):
        keys = keys_of_page()
        if keys.get(str(pos)):
            page.show_dialog(ft.AlertDialog(modal=True, title=ft.Text(t("ui_replace")),
                content=ft.Text(f"{t('ui_key_word')} {pos} {t('ui_replace_body')}"),
                actions=[ft.FilledButton(t("ui_yes"), on_click=lambda e: (page.pop_dialog(), do_fn())),
                         ft.TextButton(t("ui_no"), on_click=lambda e: page.pop_dialog())]))
        else:
            do_fn()

    def copy_key(pos):
        spec = keys_of_page().get(str(pos))
        if spec:
            state["clipboard_key"] = _copy.deepcopy(spec)

    def paste_key(pos):
        clip = state.get("clipboard_key")
        if not clip:
            return

        def do():
            keys_of_page()[str(pos)] = _copy.deepcopy(clip)
            refresh_device()
        _confirm_overwrite(pos, do)

    def clear_key_at(pos):
        keys_of_page().pop(str(pos), None); refresh_device()

    def move_key(src, dst):
        if src == dst:
            return
        keys = keys_of_page()
        spec = keys.get(str(src))
        if not spec:
            return

        def do():
            keys[str(dst)] = _copy.deepcopy(spec)
            keys.pop(str(src), None)
            state["sel_key"] = dst
            refresh_device()
        _confirm_overwrite(dst, do)

    def key_menu(pos):
        state["sel_key"] = pos
        has = bool(keys_of_page().get(str(pos)))
        can_paste = bool(state.get("clipboard_key"))
        rows = [ft.TextButton(t("key_copy"), icon=I.CONTENT_COPY, disabled=not has,
                              on_click=lambda e: (page.pop_dialog(), copy_key(pos))),
                ft.TextButton(t("key_paste"), icon=I.CONTENT_PASTE, disabled=not can_paste,
                              on_click=lambda e: (page.pop_dialog(), paste_key(pos))),
                ft.TextButton(t("clear_key"), icon=I.DELETE_SWEEP, disabled=not has,
                              on_click=lambda e: (page.pop_dialog(), clear_key_at(pos)))]
        page.show_dialog(ft.AlertDialog(modal=True,
            title=ft.Text(f"{t('ui_key_word')} {pos}"),
            content=ft.Container(width=220, content=ft.Column(rows, tight=True, spacing=4)),
            actions=[ft.TextButton(t("cancel"), on_click=lambda e: page.pop_dialog())]))

    # ---------- device view ----------
    def key_cell(pos):
        keys = keys_of_page()
        spec = keys.get(str(pos))
        size = DEV_KEY_N * DISP_W
        r, c = divmod(pos, 5)
        cx = (DEV_COLX[c] + DEV_KEY_DX) * DISP_W
        cy = (DEV_ROWY[r] + DEV_KEY_DY) * DISP_H
        selected = (pos == state["sel_key"])
        rad = 9
        if spec and (spec.get("text") or spec.get("image")):
            inner = ft.Image(src=render_key_src(spec), width=size, height=size,
                             fit=ft.BoxFit.COVER, border_radius=rad)
        elif spec:  # solo color/accion
            inner = ft.Container(width=size, height=size, bgcolor=hexc(spec.get("bg", [20, 20, 20])),
                                 border_radius=rad, alignment=ft.Alignment(0, 0),
                                 content=ft.Text(str(pos), size=10, color="#888"))
        else:
            inner = ft.Container(width=size, height=size, bgcolor="#0b0b0f",
                                 border_radius=rad, alignment=ft.Alignment(0, 0),
                                 content=ft.Text(str(pos), size=10, color="#666"))
        cont = ft.Container(
            content=inner, padding=3, border_radius=10, alignment=ft.Alignment(0, 0),
            bgcolor="#4fe3ff" if selected else "#00000000",
            shadow=ft.BoxShadow(blur_radius=16, color="#4fe3ff", spread_radius=1) if selected else None,
        )

        def on_tap(e):
            state["sel_key"] = pos
            refresh_device()

        def on_dbl(e):
            state["sel_key"] = pos
            state["fresh"] = False   # edicion -> conservar titulo/icono
            atype = keys_of_page().get(str(pos), {}).get("action", {}).get("type")
            open_action(pos, atype or "edit")

        gd = ft.GestureDetector(content=cont, on_tap=on_tap, on_double_tap=on_dbl,
                                on_secondary_tap=lambda e, p=pos: key_menu(p))
        has_content = bool(spec)
        # la tecla con contenido se puede arrastrar a otra para MOVER su contenido
        draggable = ft.Draggable(
            group="act", content=gd, data=f"movekey:{pos}",
            on_drag_start=lambda e, p=pos: state.__setitem__("dragging", f"movekey:{p}"),
            content_feedback=ft.Container(
                content=ft.Image(src=render_key_src(spec), width=48, height=48, border_radius=6)
                if has_content and (spec.get("text") or spec.get("image")) else
                ft.Container(width=48, height=48, border_radius=6,
                             bgcolor=hexc(spec.get("bg", [40, 40, 60])) if spec else "#2d6cdf"))
        ) if has_content else gd

        def on_drop(e, p=pos):
            aid = state.get("dragging") or _aid_from_event(e)
            state["dragging"] = None
            if isinstance(aid, str) and aid.startswith("movekey:"):
                move_key(int(aid.split(":", 1)[1]), p)
                return
            drop_on(p, aid)

        dt = ft.DragTarget(group="act", content=draggable,
                           on_will_accept=lambda e: None, on_accept=on_drop)
        return ft.Container(content=dt, left=cx - size / 2 - 3, top=cy - size / 2 - 3)

    def aux_label(name):
        spec = state["cfg"].get("aux", {}).get(name)
        act = spec.get("action", {}).get("type") if spec and spec.get("action") else None
        m = {"prev_page": "PREV", "next_page": "NEXT", "home": "HOME", "goto_page": "GOTO",
             "scene_shift": "SCENE", "goto_scene": "SCENE", "brightness": "BRI",
             "devsleep": "SLEEP"}
        return m.get(act, (act.upper()[:5] if act else name.upper()[:4]))

    AUX_NAMES = {"left": "PREV", "mid": "HOME", "right": "NEXT"}

    def open_aux(name):
        aux = state["cfg"].setdefault("aux", {})
        act = (aux.get(name, {}) or {}).get("action", {}) or {}
        atype = act.get("type") or "none"
        AUX_ACTS = [("none", t("aux_none")), ("prev_page", t("a_prev_page")),
                    ("next_page", t("a_next_page")), ("home", t("nav_home")),
                    ("scene_shift", t("a_scene_shift")), ("goto_scene", t("a_goto_scene")),
                    ("goto_page", t("a_goto_page")), ("brightness", t("a_brightness")),
                    ("devsleep", t("a_devsleep"))]
        dd = ft.Dropdown(label=t("aux_action"), width=300,
                         value=atype if atype in [k for k, _ in AUX_ACTS] else "none",
                         options=[ft.DropdownOption(key=k, text=v) for k, v in AUX_ACTS])
        scns = state["cfg"]["scenes"]
        scene_dd = ft.Dropdown(label=t("scn_target"), width=300, visible=False,
            options=[ft.DropdownOption(key="prev", text=t("scn_prev")),
                     ft.DropdownOption(key="next", text=t("scn_next"))] +
                    [ft.DropdownOption(key=str(i), text=f"{i+1}. {sc.get('name', 'Scene')}")
                     for i, sc in enumerate(scns)])
        goto_scene_dd = ft.Dropdown(label=t("a_goto_scene"), width=300, visible=False,
            options=[ft.DropdownOption(key=str(i), text=f"{i+1}. {sc.get('name', 'Scene')}")
                     for i, sc in enumerate(scns)])
        page_tf = ft.TextField(label=t("goto_page_idx"), width=180, visible=False, value="1")
        bright_tf = ft.TextField(label=f"{t('a_brightness')} (0-100)", width=180, visible=False, value="80")
        if atype == "scene_shift":
            _tg = act.get("target", "next"); scene_dd.value = _tg if _tg in ("prev", "next") else str(_tg)
        if atype == "goto_scene":
            goto_scene_dd.value = str(act.get("scene", 0))
        if atype == "goto_page":
            page_tf.value = str(int(act.get("page", 0)) + 1)
        if atype == "brightness":
            bright_tf.value = str(act.get("value", 80))

        def upd():
            v = dd.value
            scene_dd.visible = (v == "scene_shift")
            goto_scene_dd.visible = (v == "goto_scene")
            page_tf.visible = (v == "goto_page")
            bright_tf.visible = (v == "brightness")
            for c in (scene_dd, goto_scene_dd, page_tf, bright_tf):
                c.update()
        dd.on_change = lambda e: upd()

        def save(e):
            v = dd.value
            if v == "none":
                aux.pop(name, None)
            else:
                spec = {"type": v}
                if v == "scene_shift":
                    sv = scene_dd.value or "next"
                    spec["target"] = sv if sv in ("prev", "next") else int(sv)
                elif v == "goto_scene":
                    spec["scene"] = int(goto_scene_dd.value or 0)
                elif v == "goto_page":
                    try:
                        spec["page"] = max(0, int(page_tf.value) - 1)
                    except (TypeError, ValueError):
                        spec["page"] = 0
                elif v == "brightness":
                    try:
                        spec["value"] = max(0, min(100, int(bright_tf.value)))
                    except (TypeError, ValueError):
                        spec["value"] = 80
                aux[name] = {"action": spec}
            page.pop_dialog(); refresh_device()

        content = ft.Container(width=380, height=440, content=ft.Column(
            [dd, scene_dd, goto_scene_dd, page_tf, bright_tf], spacing=10,
            scroll=ft.ScrollMode.ALWAYS))
        page.show_dialog(ft.AlertDialog(modal=True,
            title=ft.Text(f"{t('aux_title')}: {AUX_NAMES.get(name, name.upper())}"),
            content=content,
            actions=[ft.FilledButton(t("save"), icon=I.CHECK, on_click=save),
                     ft.TextButton(t("cancel"), on_click=lambda e: page.pop_dialog())]))
        upd()

    def refresh_device():
        ctrls = [ft.Image(src="/device.png", left=0, top=0,
                          width=DISP_W, height=DISP_H, fit=ft.BoxFit.FILL,
                          border_radius=ft.BorderRadius(top_left=30, top_right=30,
                                                        bottom_left=30, bottom_right=44))]
        for pos in range(15):
            ctrls.append(key_cell(pos))
        for i, name in enumerate(("left", "mid", "right")):
            bx = DEV_AUXX[i] * DISP_W
            by = DEV_AUXY * DISP_H
            ctrls.append(ft.Container(
                left=bx - 30, top=by - 16, width=60, height=32,
                alignment=ft.Alignment(0, 0), border_radius=16, ink=True,
                content=ft.Text(aux_label(name), size=11, weight=ft.FontWeight.BOLD,
                                color="#ffffff"),
                tooltip=t("aux_title"),
                on_click=lambda e, n=name: open_aux(n)))
        device_stack.controls = ctrls
        page.update()
        _autosave()

    def _autosave():
        # escribe config.json (atomico) para que la bandeja/runtime refleje en vivo
        try:
            tmp = CONFIG_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(state["cfg"], f, indent=2, ensure_ascii=False)
            os.replace(tmp, CONFIG_PATH)
        except Exception as ex:
            print("[autosave]", ex)

    # ---------- escenas (panel izquierdo) ----------
    def move_scene(src, dst):
        scs = state["cfg"]["scenes"]
        if not (0 <= src < len(scs)) or not (0 <= dst < len(scs)) or src == dst:
            return
        sel_id = id(scs[state["sel_scene"]]) if 0 <= state["sel_scene"] < len(scs) else None
        _di = state["cfg"].get("default_scene", 0)
        def_id = id(scs[_di]) if 0 <= _di < len(scs) else None
        item = scs.pop(src)
        scs.insert(dst, item)
        if sel_id is not None:
            state["sel_scene"] = next((j for j, s in enumerate(scs) if id(s) == sel_id), 0)
        if def_id is not None:
            state["cfg"]["default_scene"] = next((j for j, s in enumerate(scs) if id(s) == def_id), 0)
        refresh_scenes(); refresh_page_bar(); refresh_device()

    def _scene_drop(dst):
        src = state.pop("drag_scene", None)
        if src is not None:
            move_scene(src, dst)

    def refresh_scenes():
        scenes_list.controls.clear()
        default = state["cfg"].get("default_scene", 0)
        for i, sc in enumerate(state["cfg"]["scenes"]):
            isdef = (i == default)
            sel = (i == state["sel_scene"])
            npg = len(sc.get("pages", []) or [])
            name = sc.get("name", "Scene")
            star_btn = ft.IconButton(
                I.STAR if isdef else I.STAR_BORDER, icon_size=16,
                icon_color="#ffd36b" if isdef else "#5c6577",
                tooltip=t("scn_set_default"), width=28, height=28,
                on_click=lambda e, idx=i: set_default_scene(idx))
            inner = ft.Row([
                    ft.Icon(I.DRAG_INDICATOR, size=16, color="#5c6577"),
                    ft.Text(name, size=13, expand=True,
                            color="#ffffff" if sel else "#cfcfcf", no_wrap=True),
                    ft.Text(f"{npg}▦", size=11, color="#7f8aa0"),
                    star_btn], spacing=4)
            row = ft.Container(
                content=ft.GestureDetector(
                    content=inner,
                    on_tap=lambda e, idx=i: select_scene(idx),
                    on_double_tap=lambda e, idx=i: rename_scene(idx)),
                bgcolor="#2a3550" if sel else None, border_radius=6,
                padding=ft.Padding(8, 2, 4, 2), tooltip=t("scn_rename_hint"))
            drag = ft.Draggable(
                group="scene", content=row,
                on_drag_start=lambda e, idx=i: state.__setitem__("drag_scene", idx),
                content_feedback=ft.Container(content=ft.Text(name, color="white", size=12),
                                              bgcolor="#2d6cdf", padding=6, border_radius=6))
            scenes_list.controls.append(ft.DragTarget(
                group="scene", content=drag,
                on_accept=lambda e, idx=i: _scene_drop(idx)))
        page.update()

    def select_scene(idx):
        state["sel_scene"] = idx
        state["sel_page"] = 0
        state["sel_key"] = None
        refresh_scenes(); refresh_page_bar(); refresh_device()

    def rename_scene(idx):
        scenes = state["cfg"]["scenes"]
        if not (0 <= idx < len(scenes)):
            return
        sc = scenes[idx]
        tf = ft.TextField(label=t("scn_name"), value=sc.get("name", ""),
                          autofocus=True, width=320)

        def do_save(e=None):
            new = (tf.value or "").strip()
            if new:
                sc["name"] = new
            page.pop_dialog()
            refresh_scenes()

        tf.on_submit = do_save
        page.show_dialog(ft.AlertDialog(modal=True, title=ft.Text(t("scn_rename")),
            content=ft.Container(width=340, content=tf),
            actions=[ft.FilledButton(t("save"), icon=I.CHECK, on_click=do_save),
                     ft.TextButton(t("cancel"), on_click=lambda e: page.pop_dialog())]))

    def new_scene(e):
        state["cfg"]["scenes"].append(
            {"name": f"Scene {len(state['cfg']['scenes'])+1}", "default_page": 0,
             "pages": [{"keys": {}}]})
        select_scene(len(state["cfg"]["scenes"]) - 1)

    def set_default_scene(idx):
        state["cfg"]["default_scene"] = idx
        refresh_scenes()

    def _del_scene_now():
        del state["cfg"]["scenes"][state["sel_scene"]]
        state["sel_scene"] = max(0, state["sel_scene"] - 1)
        if state["cfg"].get("default_scene", 0) >= len(state["cfg"]["scenes"]):
            state["cfg"]["default_scene"] = 0
        state["sel_page"] = 0
        select_scene(state["sel_scene"])

    def del_scene(e):
        if len(state["cfg"]["scenes"]) <= 1:
            return
        page.show_dialog(ft.AlertDialog(modal=True, title=ft.Text(t("scn_del")),
            content=ft.Text(t("scn_del_confirm")),
            actions=[ft.FilledButton(t("ui_yes"), on_click=lambda e: (page.pop_dialog(), _del_scene_now())),
                     ft.TextButton(t("ui_no"), on_click=lambda e: page.pop_dialog())]))

    async def export_scene(e):
        sc = cur_scene()
        import copy as _cp
        name = (sc.get("name") or "scene").strip().replace(" ", "_")
        path = await file_picker.save_file(
            dialog_title=t("scn_export"), file_name=f"m18_scene_{name}.json",
            file_type=ft.FilePickerFileType.CUSTOM, allowed_extensions=["json"])
        if path:
            try:
                if not path.lower().endswith(".json"):
                    path += ".json"
                with open(path, "w", encoding="utf-8") as f:
                    json.dump({"_type": "m18_scene", "scene": _cp.deepcopy(sc)}, f,
                              indent=2, ensure_ascii=False)
                info(t("set_export_ok"))
            except Exception as ex:
                info(str(ex))

    async def import_scene(e):
        files = await file_picker.pick_files(
            allow_multiple=False, file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["json"])
        if not files:
            return
        try:
            with open(files[0].path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            info(t("set_import_bad")); return
        new_scenes = []
        if isinstance(data, dict) and data.get("_type") == "m18_scene" and data.get("scene"):
            new_scenes = [data["scene"]]
        elif isinstance(data, dict) and isinstance(data.get("scenes"), list):
            new_scenes = data["scenes"]          # importar todas las escenas de una config
        elif isinstance(data, dict) and (data.get("pages") or data.get("keys")):
            new_scenes = [data]                  # dict suelto tipo escena
        if not new_scenes:
            info(t("set_import_bad")); return
        scs = state["cfg"]["scenes"]
        for sc in new_scenes:
            sc = dict(sc)
            sc.setdefault("name", f"Scene {len(scs)+1}")
            sc.setdefault("pages", [{"keys": {}}])
            sc.setdefault("default_page", 0)
            scs.append(sc)
        state["sel_scene"] = len(scs) - 1
        state["sel_page"] = 0
        select_scene(state["sel_scene"])
        _autosave()
        info(t("scn_imported"))

    # ---------- paginas de la escena actual (barra inferior) ----------
    def refresh_page_bar():
        page_bar.controls.clear()
        sc = cur_scene()
        default = sc.get("default_page", 0)
        pgs = scene_pages()
        for i, p in enumerate(pgs):
            selp = (i == state["sel_page"])
            isdef = (i == default)
            num = ft.Container(
                width=40, height=40, border_radius=9,
                bgcolor="#2d4a73" if selp else "#20242e",
                alignment=ft.Alignment(0, 0),
                content=ft.Text(str(i + 1), size=15, weight=ft.FontWeight.BOLD,
                                color="#ffffff" if selp else "#9aa6b5"))
            layers = [num]
            if isdef:
                layers.append(ft.Container(right=2, top=1,
                                           content=ft.Icon(I.HOME, size=11, color="#ffd36b")))
            gd = ft.GestureDetector(
                content=ft.Stack(layers, width=40, height=40),
                on_tap=lambda e, idx=i: select_page(idx),
                on_double_tap=lambda e, idx=i: set_home(idx))
            page_bar.controls.append(ft.Container(content=gd, tooltip=t("pg_set_home")))
        page_bar.controls.append(ft.Container(
            width=40, height=40, border_radius=9, bgcolor="#20242e", ink=True,
            alignment=ft.Alignment(0, 0), tooltip=t("pg_new"),
            content=ft.Icon(I.ADD, size=20, color="#cfcfcf"), on_click=new_page))
        if len(pgs) > 1:
            page_bar.controls.append(ft.Container(
                width=40, height=40, border_radius=9, bgcolor="#20242e", ink=True,
                alignment=ft.Alignment(0, 0), tooltip=t("pg_del"),
                content=ft.Icon(I.DELETE_OUTLINE, size=18, color="#d07a9a"), on_click=del_page))
        try:
            page_bar.update()
        except Exception:
            pass

    def set_home(idx):
        cur_scene()["default_page"] = idx
        refresh_page_bar()

    def select_page(idx):
        state["sel_page"] = idx
        state["sel_key"] = None
        refresh_page_bar()
        refresh_device()

    def new_page(e):
        scene_pages().append({"keys": {}})
        select_page(len(scene_pages()) - 1)

    def _del_page_now():
        pgs = scene_pages()
        del pgs[state["sel_page"]]
        state["sel_page"] = max(0, state["sel_page"] - 1)
        sc = cur_scene()
        if sc.get("default_page", 0) >= len(pgs):
            sc["default_page"] = 0
        refresh_scenes(); select_page(state["sel_page"])

    def del_page(e):
        pgs = scene_pages()
        if len(pgs) <= 1:
            return
        if pgs[state["sel_page"]].get("keys"):
            page.show_dialog(ft.AlertDialog(modal=True, title=ft.Text(t("pg_del")),
                content=ft.Text(t("pg_del_confirm")),
                actions=[ft.FilledButton(t("ui_yes"), on_click=lambda e: (page.pop_dialog(), _del_page_now())),
                         ft.TextButton(t("ui_no"), on_click=lambda e: page.pop_dialog())]))
        else:
            _del_page_now()

    # ---------- librería ----------
    def assign(aid):
        if state["sel_key"] is None:
            info(t("info_select_key"))
            return
        pos = state["sel_key"]
        state["fresh"] = True   # colocacion nueva -> titulo/icono en blanco
        if aid.startswith("todo:"):
            info("Esta accion aun no esta implementada.\nPasame sus opciones y la implemento.")
            return
        if aid in ("prev_page", "next_page", "home"):
            keys = keys_of_page()
            lbl = {"prev_page": "◀ Prev", "next_page": "Next ▶", "home": "HOME"}[aid]
            spec = dict(keys.get(str(pos), {}))
            spec["action"] = {"type": aid}
            if not spec.get("text") and not spec.get("image"):
                spec["text"] = lbl
            keys[str(pos)] = spec
            refresh_device()
            return
        open_action(pos, aid)

    def build_library():
        tiles = []
        for cat, cicon, items in ACTION_LIBRARY:
            rows = []
            for name, icn, aid in items:
                label = tname(aid, name)
                entry = ft.Container(
                    content=ft.Row([ft.Icon(icn, size=18, color="#9fb4d6"),
                                    ft.Text(label, size=13)], spacing=10),
                    padding=8, border_radius=6, ink=True,
                    on_click=lambda e, a=aid: assign(a))
                rows.append(ft.Draggable(
                    group="act", data=aid, content=entry,
                    on_drag_start=lambda e, a=aid: state.__setitem__("dragging", a),
                    content_feedback=ft.Container(
                        content=ft.Text(label, color="white", size=12),
                        bgcolor="#2d6cdf", padding=6, border_radius=6)))
            tiles.append(ft.ExpansionTile(
                title=ft.Row([ft.Icon(cicon, size=18), ft.Text(tcat(cat), weight=ft.FontWeight.BOLD)]),
                controls=rows, dense=True))
        return ft.Column(tiles, scroll=ft.ScrollMode.AUTO, expand=True, spacing=0)

    # ---------- guardar / cargar ----------
    def save_cfg(e):
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(state["cfg"], f, indent=2, ensure_ascii=False)
        page.show_dialog(ft.AlertDialog(
            title=ft.Text(t("ui_saved")),
            content=ft.Text(t("ui_save_config_note")),
            actions=[ft.TextButton(t("ok"), on_click=lambda e: page.pop_dialog())]))

    # ---------- dispositivo (conectar / previsualizar / brillo) ----------
    def _ka_loop():
        while state.get("dev") is not None:
            try:
                with state["devlock"]:
                    if state.get("dev"):
                        state["dev"].keepalive()
            except Exception:
                pass
            time.sleep(4)

    def toggle_device(e):
        if state.get("dev") is None:
            try:
                d = StreamDockM18(); d.open()
                with state["devlock"]:
                    d.set_brightness(int(bright_slider.value))
                state["dev"] = d
                threading.Thread(target=_ka_loop, daemon=True).start()
                conn_btn.content = t("disconnect"); conn_btn.update()
                push_preview()
            except Exception as ex:
                info(f"No se pudo conectar al M18:\n{ex}\n\nCierra el software oficial de VSD.")
        else:
            try:
                with state["devlock"]:
                    state["dev"].close()
            finally:
                state["dev"] = None
                conn_btn.content = t("connect"); conn_btn.update()

    def push_preview(e=None):
        if state.get("dev") is None:
            info("Conecta primero con el boton 'Conectar'."); return
        try:
            with state["devlock"]:
                app = build_app_from_config(state["cfg"], device=state["dev"])
                state["dev"].set_brightness(int(bright_slider.value))
                app.goto_scene(state["sel_scene"], render=False)
                app.goto_page(state["sel_page"])
        except Exception as ex:
            info(f"Error al previsualizar:\n{ex}")

    def on_bright(e):
        state["cfg"]["brightness"] = int(bright_slider.value)
        if state.get("dev") is not None:
            try:
                with state["devlock"]:
                    state["dev"].set_brightness(int(bright_slider.value))
            except Exception:
                pass

    conn_btn = ft.FilledButton(t("connect"), icon=I.USB, on_click=toggle_device)
    bright_slider = ft.Slider(min=0, max=100, value=state["cfg"].get("brightness", 80),
                              width=150, label="{value}", on_change=on_bright)

    # ---------- layout ----------
    # --- idioma ---
    def change_lang(code):
        LANG_STATE["cur"] = code
        state["cfg"]["lang"] = code
        apply_language()

    def apply_language():
        save_btn.content = t("save")
        conn_btn.content = t("disconnect") if state.get("dev") else t("connect")
        preview_btn.content = t("preview")
        obs_btn.content = t("obs_btn")
        flag_img.src = flag_src(LANG_STATE["cur"])
        flag_btn.tooltip = t("language")
        pages_title.value = t("scenes_title")
        lib_title.value = t("action_library")
        lib_hint.value = t("select_key_hint")
        new_btn.tooltip = t("scn_new")
        del_btn.tooltip = t("scn_del")
        gear_btn.tooltip = t("set_gear")
        library_col.controls = [lib_title, lib_hint, build_library()]
        refresh_scenes(); refresh_page_bar()
        page.update()

    def open_lang_menu(e=None):
        rows = []
        for name, code in LANGS:
            rows.append(ft.Container(
                content=ft.Row([ft.Image(src=flag_src(code), width=30, height=20, border_radius=3),
                                ft.Text(name)], spacing=12),
                padding=8, border_radius=6, ink=True,
                on_click=lambda e, c=code: (page.pop_dialog(), change_lang(c))))
        page.show_dialog(ft.AlertDialog(modal=True, title=ft.Text(t("language")),
            content=ft.Container(width=280, height=640, content=ft.Column(rows, scroll=ft.ScrollMode.ALWAYS)),
            actions=[ft.TextButton(t("cancel"), on_click=lambda e: page.pop_dialog())]))

    save_btn = ft.FilledButton(t("save"), icon=I.SAVE, on_click=save_cfg)
    preview_btn = ft.TextButton(t("preview"), icon=I.CAST, on_click=push_preview)
    # empaquetado: el server (bandeja) es el dueno del equipo y refleja en vivo;
    # Connect/Preview del configurador sobran y entrarian en conflicto.
    if getattr(sys, "frozen", False):
        conn_btn.visible = False
        preview_btn.visible = False
    obs_btn = ft.TextButton(t("obs_btn"), icon=I.VIDEOCAM, on_click=lambda e: show_obs_settings())
    flag_img = ft.Image(src=flag_src(LANG_STATE["cur"]), width=34, height=22, border_radius=3)
    flag_btn = ft.Container(content=ft.Row([flag_img, ft.Icon(I.ARROW_DROP_DOWN, size=18)], spacing=0),
                            on_click=open_lang_menu, ink=True, padding=6, border_radius=6,
                            tooltip=t("language"))
    pages_title = ft.Text(t("scenes_title"), weight=ft.FontWeight.BOLD)
    lib_title = ft.Text(t("action_library"), weight=ft.FontWeight.BOLD)
    lib_hint = ft.Text(t("select_key_hint"), size=11, color="#888")
    new_btn = ft.IconButton(I.ADD, tooltip=t("scn_new"), on_click=new_scene)
    del_btn = ft.IconButton(I.DELETE, tooltip=t("scn_del"), on_click=del_scene)
    scn_exp_btn = ft.IconButton(I.FILE_UPLOAD, icon_size=18, tooltip=t("scn_export"), on_click=export_scene)
    scn_imp_btn = ft.IconButton(I.FILE_DOWNLOAD, icon_size=18, tooltip=t("scn_import"), on_click=import_scene)
    gear_btn = ft.IconButton(I.SETTINGS, tooltip=t("set_gear"), on_click=show_device_settings)
    library_col = ft.Column([lib_title, lib_hint, build_library()], expand=True)

    topbar = ft.Container(
        bgcolor="#161a22", padding=10,
        content=ft.Row([
            ft.Text(APP_NAME, weight=ft.FontWeight.BOLD, size=15),
            save_btn, conn_btn, preview_btn,
            ft.Row([ft.Icon(I.LIGHT_MODE, size=18), bright_slider], spacing=2),
            obs_btn, flag_btn, gear_btn,
        ], spacing=8, wrap=False, scroll=ft.ScrollMode.AUTO, vertical_alignment=ft.CrossAxisAlignment.CENTER))

    pages_panel = ft.Container(
        width=250, bgcolor="#12141b", padding=10,
        content=ft.Column([
            pages_title,
            ft.Row([new_btn, del_btn, scn_exp_btn, scn_imp_btn], spacing=0),
            scenes_list], expand=True, spacing=4))

    library_panel = ft.Container(width=270, bgcolor="#12141b", padding=6, content=library_col)

    page.add(ft.Column([
        topbar,
        ft.Row([pages_panel, device_holder, library_panel], expand=True, spacing=0),
    ], spacing=0, expand=True))

    refresh_scenes()
    refresh_page_bar()
    refresh_device()


# --- helpers de accion ------------------------------------------------------
def _hex2rgb(s):
    s = (s or "").strip().lstrip("#")
    if len(s) == 6:
        try:
            return [int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)]
        except ValueError:
            pass
    return [255, 255, 255]


def _param_from(act):
    t = act.get("type")
    if t == "run":
        return " ".join(act.get("args", []))
    if t == "open_url":
        return act.get("url", "")
    if t == "hotkey":
        return "+".join(act.get("keys", []))
    if t == "write_text":
        return act.get("text", "")
    if t == "goto_page":
        return str(act.get("page", 0))
    if t == "brightness":
        return str(act.get("value", 80))
    if t == "multimedia":
        return act.get("command", "playpause")
    return ""


def _build_action(t, p):
    p = (p or "").strip()
    if t == "none":
        return None
    if t == "run":
        return {"type": "run", "args": p.split()}
    if t == "open":
        return {"type": "open", "path": p}
    if t == "open_app":
        return {"type": "open_app", "path": p}
    if t == "open_url":
        url = p if "://" in p else "https://" + p
        return {"type": "open_url", "url": url, "browser": "default"}
    if t == "hotkey":
        return {"type": "hotkey", "keys": [k.strip() for k in p.replace(",", "+").split("+") if k.strip()]}
    if t == "write_text":
        return {"type": "write_text", "text": p}
    if t == "password":
        return {"type": "password", "text": p, "enter": False, "paste": True}
    if t == "multimedia":
        return {"type": "multimedia", "command": p or "playpause"}
    if t == "brightness":
        return {"type": "brightness", "value": int(p or 80)}
    if t == "goto_page":
        return {"type": "goto_page", "page": int(p or 0)}
    if t in ("next_page", "prev_page", "home"):
        return {"type": t}
    return None


def run_app():
    """Punto de entrada del configurador (usado por main.py y por ejecucion directa)."""
    m18_paths.ensure_user_data()   # copia iconos/config a %APPDATA% la 1a vez
    ensure_server_running()        # arranca el server del equipo (empaquetado)
    ft.run(main, assets_dir=ASSETS)


if __name__ == "__main__":
    run_app()
