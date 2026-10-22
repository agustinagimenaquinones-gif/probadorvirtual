# ==========================================================
# PROYECTO: PROBADOR VIRTUAL INTELIGENTE - BOUTIQUE FEMENINA
# Flujo: Galería Visual -> Elección -> Confirmación -> Cámara en Vivo -> Calce Realista
# ==========================================================
#
# Módulos de la aplicación:
#   config.py           constantes (rendimiento, archivos, suavizado y colores)
#   recursos.py         modelo de MediaPipe, carpetas y nombres de capturas
#   galeria.py          interfaz Tkinter: galería, confirmación y tabla de medidas
#   probador_camara.py  bucle de la cámara: detección, malla, escáner y teclas
#   hud.py              textos y líneas de medidas dibujados sobre la cámara

import sys
import tkinter as tk

from galeria import BoutiqueVirtualApp


# =========================================================================
# PUNTO DE ENTRADA PRINCIPAL
# =========================================================================
def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # tildes bien aunque se redirija la salida
    except Exception:
        pass
    root = tk.Tk()
    app = BoutiqueVirtualApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
