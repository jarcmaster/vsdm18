"""
Ejemplo: configura las teclas del Stream Dock M18 y sus acciones.

Ejecuta:  python example_config.py

Teclas LCD numeradas 0..14 (izquierda->derecha, arriba->abajo):
    0  1  2  3  4
    5  6  7  8  9
   10 11 12 13 14
Botones fisicos auxiliares: "left", "mid", "right".
"""

from streamdock_m18 import StreamDockApp, Key, actions


def volumen_arriba():
    print(">> subir volumen (pon aqui tu logica)")


app = StreamDockApp(
    brightness=80,
    keys={
        # Tecla 0: etiqueta de texto + lanza el Bloc de notas
        0: Key(text="Notas", on_press=actions.run("notepad.exe")),

        # Tecla 1: abre una web
        1: Key(text="VSD", on_press=actions.open_url("https://www.vsdinside.com")),

        # Tecla 2: una funcion tuya de Python
        2: Key(text="Vol +", on_press=actions.func(volumen_arriba)),

        # Tecla 3: combinacion de teclas (necesita pyautogui)
        3: Key(text="Copiar", on_press=actions.hotkey("ctrl", "c")),

        # Tecla 4: imagen propia (debe existir el archivo; se reescala a 64x64)
        # 4: Key(image="mi_icono.png", on_press=actions.run("calc.exe")),

        # Tecla 14: enciende el anillo RGB en rojo
        14: Key(text="RGB", on_press=lambda ev: _rgb_rojo()),

        # Boton fisico derecho (sin pantalla): solo accion
        "right": Key(on_press=actions.func(lambda: print(">> boton derecho"))),
    },
)


def _rgb_rojo():
    app.device.set_leds([(255, 0, 0)] * 24)
    app.device.set_led_brightness(60)


if __name__ == "__main__":
    app.run()
