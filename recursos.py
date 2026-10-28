# ==========================================================
# PROYECTO: PROBADOR VIRTUAL INTELIGENTE - BOUTIQUE FEMENINA
# MÓDULO: RECURSOS (modelo de MediaPipe, carpetas y capturas)
# ==========================================================

import os
import sys
import glob
import urllib.request

from crear_prendas import (
    procesar_top_champagne_si_existe,
    procesar_polo_azul_marino_si_existe,
    procesar_polo_ralph_lauren_si_existe,
    procesar_top_asimetrico_negro_si_existe
)
from config import (
    MODEL_FILENAME,
    MODEL_URL,
    USAR_PELO_DELANTE,
    MODELO_PELO,
    MODELO_PELO_URL,
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

    if USAR_PELO_DELANTE and not os.path.exists(MODELO_PELO):
        print("[+] Descargando modelo de pelo de MediaPipe...")
        try:
            urllib.request.urlretrieve(MODELO_PELO_URL, MODELO_PELO)
        except Exception as e:
            # Sin este modelo el probador funciona igual (sólo el pelo no queda delante)
            print(f"[AVISO] No se pudo descargar el modelo de pelo: {e}")

    os.makedirs(CARPETA_PRENDAS, exist_ok=True)
    os.makedirs(CARPETA_CAPTURAS, exist_ok=True)

    # Preparar las fotos de prendas que lo necesitan. Las remeras dibujadas por
    # programa ya no se generan: el catálogo usa sólo fotos de prendas reales
    # (para agregar prendas nuevas, ver importar_prendas.py).
    if not glob.glob(os.path.join(CARPETA_PRENDAS, "*.png")):
        print("[AVISO] No hay prendas en 'prendas/'. Ejecutá importar_prendas.py y cargar_prendas_mysql.py.")
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
