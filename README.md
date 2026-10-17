# Stream Dock M18 by JARCMASTER

**v1.0.0** — Alternativa libre, en Python, para configurar y usar el **VSDinside /
Mirabox Stream Dock M18** (USB `0x5548:0x1000`) **sin el software oficial**.

Habla USB-HID directo con el equipo (driver propio, protocolo documentado por la
comunidad), con un configurador visual (Flet), un server que corre en la bandeja
del sistema y navegación por **Escenas → Páginas** como el software oficial.

> ⚠️ **Úsalo bajo tu propio riesgo.** No es un producto oficial de Mirabox/VSD.
> El autor no asume ninguna responsabilidad por daños. Licencia **MIT**.

---

## ✨ Funciones

- **Escenas → Páginas (infinitas).** Panel de *Escenas* (perfiles) a la izquierda;
  barra de *páginas* `1 2 3 +` bajo el equipo. Reordena escenas con *drag & drop*,
  marca la escena/página por defecto con ★, exporta/importa escenas sueltas.
- **15 teclas LCD + 3 botones laterales** (PREV / HOME / NEXT) totalmente configurables.
- **Librería de acciones** (arrastrar y soltar):
  - **Website**, **Hotkey**, **HotkeySwitch**, **Super Hotkeys** (selector visual de teclas),
  - **Mouse event**: clic/scroll, mover a **X/Y por monitor**, y **grabar/reproducir rutinas**
    del ratón (+ teclado) con velocidad 1×–5×, hotkey de parada y aviso en pantalla,
  - **Open / Open an app / Close** (cerrar o *matar* apps por nombre o ruta),
  - **Text**, **Password**, **Multimedia**, **Brillo**, **devsleep**,
  - **Operation Flow**: Action flow, Carousel, Action Toggle,
  - **OBS Studio**: grabar, transmitir, cámara virtual, escena, fuente, mixer, etc.
  - **Navegación**: Previous/Next Page, Go to Page, Page Indicator, **Scene Shift**, Go to Scene.
- **Copiar / Pegar / Mover** teclas (clic derecho y *drag & drop* entre teclas).
- **Galería de iconos** integrada + imágenes personalizadas por tecla.
- **Ajustes del equipo (⚙):** nº de serie, firmware, apagado automático de pantalla,
  **rotación** (0/90/180/270, por software), **color e intensidad del LED lateral**,
  **iniciar con Windows**, y **exportar/importar** toda la configuración.
- **11 idiomas:** EN · ES · IT · RU · ZH · JA · KO · FR · DE · PT · AR.
- **Bandeja + reflejo en vivo:** el server mantiene el equipo funcionando y **cualquier
  cambio en el configurador se aplica al instante** en el hardware.
- **Arranque con Windows** automático y un solo ejecutable.

---

## 🚀 Instalación (usuario final)

**Un solo ejecutable.** No necesitas instalar Python.

1. Descarga/genera `StreamDockM18.exe` (ver *Compilar*).
2. Ejecútalo. La primera vez:
   - copia iconos y config a `%APPDATA%\Stream Dock M18 by JARCMASTER`,
   - se registra para **iniciar con Windows**,
   - arranca el **server** y queda en la **bandeja** del sistema.
3. **Clic derecho en el icono de la bandeja → Open Configurator** para abrir la UI
   (o un acceso directo con el parámetro `--config`).

Requisitos: **Windows 10/11 (64 bits)**, cable **USB-C de datos**, y **cerrar el
software oficial de VSD** (el equipo admite un solo dueño del USB). La primera vez
Windows SmartScreen puede avisar (exe sin firmar) → *Más información → Ejecutar de todos modos*.

### Instalador (opcional)
`iscc installer.iss` (requiere **Inno Setup 6**) genera un único *Setup.exe* que
instala, crea accesos directos, registra el arranque y lanza la app.

---

## 🧑‍💻 Desde el código fuente

```bash
pip install -r requirements.txt   # hidapi, Pillow (+ pyautogui, flet opcionales)

python configurator_flet.py       # abrir el configurador
python run_config.py              # ejecutar la config en el equipo (headless)
python tray_app.py                # server + bandeja
```

## 🔨 Compilar a .exe

```bash
pip install pyinstaller flet
python build.py                   # -> dist/StreamDockM18.exe  (un solo exe)
iscc installer.iss                # -> instalador (opcional, Inno Setup)
```

El exe único hace de **server/bandeja** (sin args) y de **configurador** (`--config`).

---

## 🧭 Cómo se usa (resumen)

| Elemento | Qué hace |
|---|---|
| **Escenas** (panel izq.) | Perfiles. `+` / 🗑 / ⬆ exportar / ⬇ importar · ★ por defecto · arrastra para reordenar |
| **Páginas** (barra `1 2 3 +`) | Pantallas de la escena actual · doble clic en un nº = Inicio |
| **Teclas** | Arrastra una acción de la librería · doble clic para editar · clic derecho Copiar/Pegar/Vaciar · arrastra una tecla sobre otra para mover |
| **PREV / HOME / NEXT** | Clic para asignarles acción de navegación |
| **⚙ Ajustes** | Serial/firmware, screen-off, rotación, LED, inicio con Windows, export/import |
| **Bandeja** | Open Configurator · Exit |

Dentro de la app: **⚙ → Cómo usar** (guía completa) y **⚙ → Acerca de**.

---

## 📁 Estructura

```
configurator_flet.py   UI del configurador (Flet)
tray_app.py            server + bandeja (Win32)
main.py                punto de entrada único (dispatch server / --config)
m18_paths.py           rutas compartidas, autostart, datos de usuario
i18n_extra.py          traducciones (11 idiomas)
mouse_overlay.py       aviso flotante para grabar/reproducir ratón
run_config.py          ejecutar una config sin UI
streamdock_m18/        driver HID + acciones + capa de app
icons/ · assets/       librería de iconos y recursos
build.py · installer.iss   empaquetado
```

---

## ⚖️ Licencia

**MIT** © 2026 **Jose A. Rodriguez C.** — ver [LICENSE](LICENSE).

El software se entrega "TAL CUAL", **sin garantía**. Lo usas **bajo tu propio riesgo**;
el autor **no asume responsabilidad** por ningún daño en tu equipo o computadora.

## 👤 Autor

**Jose A. Rodriguez C.** · ✉️ jarcmaster@gmail.com · 🔗 https://github.com/jarcmaster/vsdm18
