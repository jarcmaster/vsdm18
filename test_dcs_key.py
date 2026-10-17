# -*- coding: utf-8 -*-
"""
Diagnostico: envia LCtrl+C (Canopy - OPEN/CLOSE en DCS) por SCANCODE, aislado
de la app y del server. Uso:

    python test_dcs_key.py

Tras ejecutarlo tienes 5 segundos para pasar a la ventana de DCS (en cabina
del F/A-18C). Mandara Ctrl+C tres veces. Si el canopy se mueve -> el envio por
scancode funciona (el problema estaria en el server/config). Si NO se mueve y
DCS esta como Administrador -> ejecuta DCS y esta prueba al mismo nivel
(ambos normales, o ambos 'Ejecutar como administrador').
"""
import sys, os, time, ctypes

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from streamdock_m18.actions import send_combo_scancode


def _is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def main():
    combo = sys.argv[1].replace(",", "+").split("+") if len(sys.argv) > 1 else ["ctrl", "c"]
    print(f"Esta prueba corre {'COMO ADMINISTRADOR' if _is_admin() else 'en modo normal (no admin)'}.")
    print(f"Combo a enviar: {'+'.join(combo)}")
    print("Pasa a la ventana de DCS AHORA...")
    for s in range(5, 0, -1):
        print(f"  {s}...", end="", flush=True)
        time.sleep(1)
    print()
    for i in range(3):
        ok = send_combo_scancode(combo)
        print(f"  envio #{i+1}: {'OK (enviado por scancode)' if ok else 'FALLO (tecla no reconocida)'}")
        time.sleep(1.0)
    print("Listo. Revisa si el canopy se movio en DCS.")


if __name__ == "__main__":
    main()
