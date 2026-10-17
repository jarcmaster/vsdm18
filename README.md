# Stream Dock M18 by JARCMASTER

**v1.0.0** — A free, open, Python alternative to configure and use the
**VSDinside / Mirabox Stream Dock M18** (USB `0x5548:0x1000`) **without the
official software**.

It talks USB-HID directly to the device (custom driver, community-documented
protocol), with a visual configurator (Flet), a server that runs in the system
tray, and **Scenes → Pages** navigation just like the official app.

> ⚠️ **Use it entirely at your own risk.** This is not an official Mirabox/VSD
> product. The author assumes no responsibility for any damage. **MIT** licensed.

---

## ✨ Features

- **Scenes → Pages (unlimited).** *Scenes* (profiles) panel on the left; a *pages*
  bar `1 2 3 +` under the device. Reorder scenes with drag & drop, mark the default
  scene/page with ★, export/import individual scenes.
- **15 LCD keys + 3 side buttons** (PREV / HOME / NEXT), fully configurable.
- **Action library** (drag & drop):
  - **Website**, **Hotkey**, **HotkeySwitch**, **Super Hotkeys** (visual key picker),
  - **Mouse event**: click/scroll, move to **X/Y per monitor**, and **record/replay
    mouse routines** (+ keyboard) with 1×–5× speed, a stop hotkey and an on-screen notice,
  - **Open / Open an app / Close** (close or *kill* apps by name or path),
  - **Text**, **Password**, **Multimedia**, **Brightness**, **devsleep**,
  - **Operation Flow**: Action flow, Carousel, Action Toggle,
  - **OBS Studio**: record, stream, virtual camera, scene, source, mixer, etc.
  - **Navigation**: Previous/Next Page, Go to Page, Page Indicator, **Scene Shift**, Go to Scene.
- **Copy / Paste / Move** keys (right-click and drag & drop between keys).
- **Built-in icon gallery** + custom per-key images.
- **Device settings (⚙):** serial number, firmware, automatic screen-off,
  **rotation** (0/90/180/270, software-side), **side LED color & intensity**,
  **start with Windows**, and **export/import** of the whole configuration.
- **11 languages:** EN · ES · IT · RU · ZH · JA · KO · FR · DE · PT · AR.
- **Tray + live reflection:** the server keeps the device running and **any change
  in the configurator is applied instantly** on the hardware.
- **Starts with Windows** automatically, in a single executable.

---

## 🚀 Installation (end user)

**A single executable.** No Python installation required.

1. Download/build `StreamDockM18.exe` (see *Build*).
2. Run it. On first launch it:
   - copies icons and config to `%APPDATA%\Stream Dock M18 by JARCMASTER`,
   - registers itself to **start with Windows**,
   - launches the **server** and lives in the **system tray**.
3. **Right-click the tray icon → Open Configurator** to open the UI
   (or a shortcut with the `--config` parameter).

Requirements: **Windows 10/11 (64-bit)**, a **USB-C data cable**, and **close the
official VSD software** (the device allows only one USB owner). On first run Windows
SmartScreen may warn (unsigned exe) → *More info → Run anyway*.

### Installer (optional)
`iscc installer.iss` (requires **Inno Setup 6**) produces a single *Setup.exe* that
installs the app, creates shortcuts, registers startup and launches it.

---

## 🧑‍💻 From source

```bash
pip install -r requirements.txt   # hidapi, Pillow (+ pyautogui, flet optional)

python configurator_flet.py       # open the configurator
python run_config.py              # run a config on the device (headless)
python tray_app.py                # server + tray
```

## 🔨 Build to .exe

```bash
pip install pyinstaller flet
python build.py                   # -> dist/StreamDockM18.exe  (single exe)
iscc installer.iss                # -> installer (optional, Inno Setup)
```

The single exe acts as **server/tray** (no args) and as the **configurator** (`--config`).

---

## 🧭 How to use (quick reference)

| Element | What it does |
|---|---|
| **Scenes** (left panel) | Profiles. `+` / 🗑 / ⬆ export / ⬇ import · ★ default · drag to reorder |
| **Pages** (`1 2 3 +` bar) | Screens of the current scene · double-click a number = Home |
| **Keys** | Drag an action from the library · double-click to edit · right-click Copy/Paste/Clear · drag one key onto another to move |
| **PREV / HOME / NEXT** | Click to assign a navigation action |
| **⚙ Settings** | Serial/firmware, screen-off, rotation, LED, start with Windows, export/import |
| **Tray** | Open Configurator · Exit |

In-app: **⚙ → How to use** (full guide) and **⚙ → About**.

---

## 📁 Project layout

```
configurator_flet.py   configurator UI (Flet)
tray_app.py            server + tray (Win32)
main.py                single entry point (server / --config dispatch)
m18_paths.py           shared paths, autostart, user data
i18n_extra.py          translations (11 languages)
mouse_overlay.py       floating notice for mouse record/replay
run_config.py          run a config without the UI
streamdock_m18/        HID driver + actions + app layer
icons/ · assets/       icon library and resources
build.py · installer.iss   packaging
```

---

## ⚖️ License

**MIT** © 2026 **Jose A. Rodriguez C.** — see [LICENSE](LICENSE).

The software is provided "AS IS", **without warranty**. You use it **at your own
risk**; the author assumes **no responsibility** for any damage to your device or
computer.

## 👤 Author

**Jose A. Rodriguez C.** · ✉️ jarcmaster@gmail.com · 🔗 https://github.com/jarcmaster/vsdm18
