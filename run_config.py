"""
Ejecuta una configuracion de teclas/paginas en el Stream Dock M18.

Uso:
    python run_config.py [config.json]

Si no pasas ruta, usa 'config.json' en esta carpeta. Si no existe, crea uno
de ejemplo. Edita la config con la app:  python configurator.py
"""

import json
import os
import sys

from streamdock_m18 import load_config, default_config

DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "config.json")


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PATH
    if not os.path.exists(path):
        print(f"No existe {path}; creando uno de ejemplo.")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default_config(), f, indent=2, ensure_ascii=False)
    print(f"Cargando {path} ...")
    app = load_config(path)
    app.run()


if __name__ == "__main__":
    main()
