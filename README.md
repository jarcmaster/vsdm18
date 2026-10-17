# Manejador propio para VSD / Mirabox Stream Dock M18

Driver en Python que habla **USB HID directamente** con el Stream Dock M18, sin
el software del fabricante. Permite **configurar cada tecla y su acción**.

El M18 tiene 15 teclas LCD (64×64 px), 3 botones físicos, un anillo RGB de 24
LEDs y se conecta por USB-C. Identificación HID: `VID 0x5548 / PID 0x1000`.

## Instalación

```powershell
pip install -r requirements.txt
```

`hidapi` (comunicación USB) y `Pillow` (imágenes de las teclas) son obligatorios.
`pyautogui` solo si usas acciones de combinaciones de teclas.

> **Importante:** cierra el software oficial de VSD/Mirabox antes de usar esto.
> Si está abierto, tiene tomado el dispositivo y el acceso HID fallará.

## Prueba rápida

```powershell
python scan.py            # ¿se ve el dispositivo? vuelca las pulsaciones en crudo
python configurator.py    # app grafica para crear paginas/teclas y guardarlas
python run_config.py config.json   # ejecuta la config que guardaste
```

## App de configuración (recomendado)

```powershell
python configurator.py
```

Con la app puedes, sin tocar código:

- **Páginas:** crear, borrar, renombrar y **reordenar** (▲ Subir / ▼ Bajar).
  Cada página tiene sus 15 teclas (0–14).
- **Teclas:** clic en una tecla del grid para editar texto, color de letra/fondo,
  icono (imagen) y **acción**.
- **Acciones:** `run` (lanzar app), `open_url`, `hotkey`, `write_text`,
  y navegación entre páginas: `next_page`, `prev_page`, `goto_page`, `home`.
- **Página por defecto:** botón **★ Marcar por defecto**. Esa página (marcada
  con ★) es la que se carga al arrancar, y deja el **botón central** con la
  acción `home`, de modo que al pulsarlo se vuelve a ella desde cualquier página.
- **Botones laterales** (`left`/`mid`/`right`): asignarles una acción
  (típico: left=anterior, right=siguiente, mid=página por defecto).
- **Conectar** + **Previsualizar página**: ver la página en el M18 real mientras
  la diseñas.
- **Guardar/Cargar** la configuración en `config.json`.

Luego la pones en marcha con:

```powershell
python run_config.py config.json
```

## Configurar teclas y acciones

```python
from streamdock_m18 import StreamDockApp, Key, actions

app = StreamDockApp(
    brightness=80,
    keys={
        0:  Key(text="Notas", on_press=actions.run("notepad.exe")),
        1:  Key(text="VSD",   on_press=actions.open_url("https://www.vsdinside.com")),
        3:  Key(text="Copiar", on_press=actions.hotkey("ctrl", "c")),
        14: Key(image="icono.png", on_press=actions.func(mi_funcion)),
        "right": Key(on_press=actions.func(lambda: print("botón derecho"))),
    },
)
app.run()
```

Numeración de las teclas LCD (izquierda→derecha, arriba→abajo):

```
 0  1  2  3  4
 5  6  7  8  9
10 11 12 13 14
```

Botones físicos (sin pantalla): `"left"`, `"mid"`, `"right"`.

### Acciones disponibles (`streamdock_m18.actions`)

| Acción | Qué hace |
|---|---|
| `run("app.exe", ...)` | Lanza un programa |
| `open_url("https://...")` | Abre una URL |
| `hotkey("ctrl", "c")` | Envía una combinación de teclas (necesita `pyautogui`) |
| `write_text("hola")` | Teclea un texto (necesita `pyautogui`) |
| `func(mi_funcion)` | Ejecuta una función tuya |
| `sequence(a1, a2, ...)` | Varias acciones en orden |

También puedes usar cualquier `callable` que reciba el `KeyEvent`.

## API de bajo nivel (`streamdock_m18.device.StreamDockM18`)

```python
from streamdock_m18 import StreamDockM18

with StreamDockM18() as dev:
    dev.set_brightness(80)                 # brillo LCD 0-100
    dev.set_key_text(0, "Hola")            # texto en una tecla
    dev.set_key_image(1, "icono.png")      # imagen (se reescala a 64x64)
    dev.clear_key(2)                       # borra una tecla
    dev.set_leds([(0, 128, 255)] * 24)     # anillo RGB
    dev.set_led_brightness(60)             # (enviar DESPUÉS del color)
    for ev in dev.events():                # bucle de pulsaciones
        print(ev)
```

## Cómo funciona el protocolo (resumen)

- **Escritura:** 1025 bytes = `0x00` (report id) + reporte de 1024 bytes. El
  reporte empieza con `CRT\0\0` seguido del comando ASCII
  (`CONNECT`, `LIG`, `SETLB`, ...).
- **Imágenes (`BAT`):** cabecera `CRT\0\0` + `BAT\0\0` + tamaño (u16 big-endian)
  + id_tecla en su propia página; luego el **JPEG en páginas crudas de 1024
  bytes SIN prefijo**; y por último `STP` para confirmar.
  > ⚠️ Detalle crítico: el comando es `BAT\0\0` (5 bytes), el tamaño va DESPUÉS
  > de esos dos nulls. Si pegas el tamaño justo tras `BAT`, el dispositivo no
  > pinta nada (y no da error).
- **Lectura:** reportes de 512 bytes; el id de tecla está en el offset 9 y el
  estado (1=pulsada, 0=soltada) en el 10.
- **Numeración de teclas:** ⚠️ es DISTINTA para imágenes y para pulsaciones
  (invertida verticalmente). Imágenes: fila de arriba `0x0b–0x0f`. Pulsaciones:
  fila de arriba `0x01–0x05`. El driver ya mapea ambas a la misma posición
  lógica 0..14, así que no tienes que preocuparte.
- **Keepalive:** hay que reenviar el brillo (`LIG`) cada ~8 s o el dispositivo
  vuelve a su pantalla de fábrica. El bucle de eventos ya lo hace solo.

## Créditos del protocolo

Ingeniería inversa de la comunidad:
[bidoofgoo/streamdock-m18](https://github.com/bidoofgoo/streamdock-m18).
