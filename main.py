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

import os
import socket
import sys
import tkinter as tk
from tkinter import messagebox

from galeria import BoutiqueVirtualApp


# =========================================================================
# PUNTO DE ENTRADA PRINCIPAL
# =========================================================================
# Puerto local que "reserva" la copia abierta del probador: dos copias a la vez se
# pelean por la cámara y la segunda no puede abrirla.
PUERTO_UNA_SOLA_COPIA = 47321


def reservar_copia_unica():
    """Devuelve el socket que marca esta copia como la abierta, o None si ya hay otra."""
    marca = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        marca.bind(("127.0.0.1", PUERTO_UNA_SOLA_COPIA))
        return marca
    except OSError:
        marca.close()
        return None


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # tildes bien aunque se redirija la salida
    except Exception:
        pass
    marca = reservar_copia_unica()
    if marca is None:
        aviso = tk.Tk()
        aviso.withdraw()
        messagebox.showinfo("Probador Virtual Inteligente",
                            "El probador ya está abierto. Buscalo en la barra de tareas.")
        aviso.destroy()
        return
    root = tk.Tk()
    app = BoutiqueVirtualApp(root)
    root.mainloop()
    # Terminar el proceso del todo al cerrar la galería: si quedara vivo (por ejemplo, con
    # un hilo de MediaPipe todavía activo), seguiría reteniendo la cámara y la próxima vez
    # que se abra el probador no podría usarla.
    marca.close()
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
