"""
Diagnostico: comprueba que el Stream Dock M18 se ve por HID y vuelca las
pulsaciones en crudo. Util para verificar el mapeo de teclas.

Ejecuta:  python scan.py
"""

import hid

from streamdock_m18.device import VENDOR_ID, PRODUCT_ID, StreamDockM18


def listar():
    print("Dispositivos HID que coinciden con el M18:")
    encontrados = [d for d in hid.enumerate()
                   if d["vendor_id"] == VENDOR_ID and d["product_id"] == PRODUCT_ID]
    if not encontrados:
        print("  (ninguno) -> revisa el cable USB-C y que no este abierto el")
        print("  software oficial de VSD/Mirabox (bloquea el acceso HID).")
        return False
    for d in encontrados:
        print(f"  path={d['path']}")
        print(f"    producto     : {d.get('product_string')}")
        print(f"    usage_page   : {hex(d.get('usage_page', 0))}  usage: {hex(d.get('usage', 0))}")
        print(f"    interface    : {d.get('interface_number')}")
    return True


def volcar_teclas():
    print("\nAbriendo dispositivo... pulsa teclas (Ctrl+C para salir):")
    with StreamDockM18() as dev:
        dev.set_brightness(80)
        while True:
            ev = dev.read_event(200)
            if ev:
                estado = "PULSADA" if ev.pressed else "soltada"
                tipo = "aux" if ev.is_aux else "lcd"
                print(f"  [{tipo}] tecla={ev.key!r:>8}  {estado:8}  (id hw={hex(ev.raw_id)})")


if __name__ == "__main__":
    if listar():
        try:
            volcar_teclas()
        except KeyboardInterrupt:
            print("\nFin.")
