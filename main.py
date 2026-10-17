"""
Punto de entrada unico de "Stream Dock M18 by JARCMASTER".

Un solo ejecutable:
  - sin argumentos  -> arranca el SERVER + bandeja (maneja el equipo). En la 1a
    ejecucion se auto-registra para iniciar con Windows y copia los datos.
  - con  --config   -> abre el CONFIGURADOR (misma app).

La bandeja abre el configurador relanzando este mismo exe con --config.
"""

import os
import sys

# asegurar que los modulos del proyecto se encuentren (empaquetado o repo)
if getattr(sys, "frozen", False):
    _BASE = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
else:
    _BASE = os.path.dirname(os.path.abspath(__file__))
if _BASE not in sys.path:
    sys.path.insert(0, _BASE)


def main():
    if "--config" in sys.argv[1:]:
        import configurator_flet
        configurator_flet.run_app()
    else:
        import tray_app
        tray_app.run_tray()


if __name__ == "__main__":
    main()
