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
    args = sys.argv[1:]
    if "--timer-popup" in args:
        import timer_popup
        timer_popup.main(sys.argv)
    elif "--mouse-overlay" in args:
        import mouse_overlay
        mouse_overlay.main()
    elif "--notes-popup" in args:
        import notes_popup
        notes_popup.main(sys.argv)
    elif "--alarm-popup" in args:
        import alarm_popup
        alarm_popup.main(sys.argv)
    elif "--recorder-popup" in args:
        import recorder_popup
        recorder_popup.main(sys.argv)
    elif "--reminders-popup" in args:
        import reminders_popup
        reminders_popup.main(sys.argv)
    elif "--todos-popup" in args:
        import todos_popup
        todos_popup.main(sys.argv)
    elif "--region-capture" in args:
        import region_capture
        region_capture.main(sys.argv)
    elif "--tray-toast" in args:
        import tray_toast
        tray_toast.main(sys.argv)
    elif "--hid-scan" in args:
        import hid_scan
        hid_scan.main(sys.argv)
    elif "--config" in args:
        import configurator_flet
        configurator_flet.run_app()
    else:
        import tray_app
        tray_app.run_tray()


if __name__ == "__main__":
    main()
