# ==========================================================
# PROYECTO: PROBADOR VIRTUAL INTELIGENTE - BOUTIQUE FEMENINA
# MÓDULO: RECURSOS (modelo de MediaPipe, carpetas y capturas)
# ==========================================================

import os
import sys
import glob
import urllib.request

from crear_prendas import (
    generar_catalogo_inicial,
    procesar_top_champagne_si_existe,
    procesar_polo_azul_marino_si_existe,
    procesar_polo_ralph_lauren_si_existe,
    procesar_top_asimetrico_negro_si_existe
)
from config import (
    MODEL_FILENAME,
    MODEL_URL,
    CARPETA_PRENDAS,
    CARPETA_CAPTURAS,
)


# =========================================================================
# FUNCIONES AUXILIARES Y GESTIÓN DE RECURSOS
# =========================================================================
def asegurar_recursos():
    """Verifica y asegura la existencia del modelo MediaPipe y las carpetas."""
    if not os.path.exists(MODEL_FILENAME):
        print("[+] Descargando modelo MediaPipe Pose Landmarker...")
        try:
            urllib.request.urlretrieve(MODEL_URL, MODEL_FILENAME)
            print("[OK] Modelo descargado exitosamente.")
        except Exception as e:
            print(f"[ERROR] No se pudo descargar el modelo: {e}")
            sys.exit(1)

    os.makedirs(CARPETA_PRENDAS, exist_ok=True)
    os.makedirs(CARPETA_CAPTURAS, exist_ok=True)

    # Verificar y preparar prendas
    pngs = glob.glob(os.path.join(CARPETA_PRENDAS, "*.png"))
    if len(pngs) < 3:
        print("[+] Generando catálogo base de prendas...")
        generar_catalogo_inicial()
    else:
        procesar_polo_azul_marino_si_existe()
        procesar_polo_ralph_lauren_si_existe()
        procesar_top_champagne_si_existe()
        procesar_top_asimetrico_negro_si_existe()





def obtener_siguiente_nombre_captura():
    """Genera un nombre secuencial automático para capturas: capturas/prueba_001.png"""
    os.makedirs(CARPETA_CAPTURAS, exist_ok=True)
    archivos = glob.glob(os.path.join(CARPETA_CAPTURAS, "prueba_*.png"))
    numeros = []
    for a in archivos:
        base = os.path.splitext(os.path.basename(a))[0]
        num_str = base.replace("prueba_", "")
        if num_str.isdigit():
            numeros.append(int(num_str))
    siguiente = (max(numeros) + 1) if numeros else 1
    return os.path.join(CARPETA_CAPTURAS, f"prueba_{siguiente:03d}.png"), f"prueba_{siguiente:03d}.png"
