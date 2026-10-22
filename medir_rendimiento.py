# ==========================================================
# PROYECTO: PROBADOR VIRTUAL INTELIGENTE
# HERRAMIENTA: MEDIR QUÉ PARTE DEL PROBADOR ES LENTA EN ESTA COMPU
# ==========================================================
# Uso:  python medir_rendimiento.py
# Abre la cámara, procesa 40 cuadros y muestra cuántos milisegundos tarda cada etapa.

import sys
import time
import numpy as np
import cv2

from pose_tracker import PoseTracker
from clothing_warper import deformar_malla_prenda
from body_layering import componer_prenda_con_capas
from catalogo import cargar_catalogo_completo, holgura_de_talle
from ajuste_silueta import ajustar_prenda_completa

ANCHO_PROCESO = 640  # igual que main.py
ANCHO_MEDIAPIPE = 480
CADA_N_CUADROS_MEDIAPIPE = 2


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # tildes bien aunque se redirija la salida
    except Exception:
        pass
    print("Cargando catálogo y modelo...")
    catalogo = cargar_catalogo_completo()
    prenda = catalogo[0]
    tracker = PoseTracker(ancho_mediapipe=ANCHO_MEDIAPIPE, cada_n_cuadros=CADA_N_CUADROS_MEDIAPIPE)
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    if not cap.isOpened():
        print("[ERROR] No se pudo abrir la cámara.")
        return

    tiempos = {"camara": [], "mediapipe+medidas": [], "malla+escaner": [], "composicion": []}
    detectados = 0
    print("Parate frente a la cámara. Midiendo 40 cuadros...")
    for i in range(45):
        t0 = time.perf_counter()
        ok, frame = cap.read()
        if not ok:
            print("[ERROR] La cámara no entrega imágenes.")
            break
        frame = cv2.flip(frame, 1)
        if frame.shape[1] > ANCHO_PROCESO:
            esc = ANCHO_PROCESO / float(frame.shape[1])
            frame = cv2.resize(frame, (ANCHO_PROCESO, int(round(frame.shape[0] * esc))), interpolation=cv2.INTER_AREA)
        t1 = time.perf_counter()
        _, info = tracker.procesar_frame(frame)
        t2 = time.perf_counter()
        t3 = t4 = t2
        if info is not None:
            detectados += 1
            dst = tracker.calcular_puntos_destino_malla(info, prenda["tiene_mangas"], holgura_talle=holgura_de_talle("M"),
                                                        calce=prenda.get("calce", "regular"))
            parche, x1, y1, x2, y2 = deformar_malla_prenda(prenda["imagen_cv"], prenda["src_puntos"], dst,
                                                           frame.shape[1], frame.shape[0], prenda["tiene_mangas"])
            if info.get("mascara") is not None:
                parche = ajustar_prenda_completa(parche, x1, y1, info["mascara"], info,
                                                  holgura=holgura_de_talle("M"), calce=prenda.get("calce", "regular"),
                                                  frame_bgr=frame)
            t3 = time.perf_counter()
            componer_prenda_con_capas(frame, parche, x1, y1, x2, y2, info, talle="M")
            t4 = time.perf_counter()
        if i >= 5:  # los primeros cuadros son más lentos (arranque)
            tiempos["camara"].append(t1 - t0)
            tiempos["mediapipe+medidas"].append(t2 - t1)
            tiempos["malla+escaner"].append(t3 - t2)
            tiempos["composicion"].append(t4 - t3)

    cap.release()
    tracker.cerrar()
    print("\n========== RESULTADO ==========")
    print(f"Resolución de proceso: {frame.shape[1]}x{frame.shape[0]} | MediaPipe a {ANCHO_MEDIAPIPE} px, "
          f"1 de cada {CADA_N_CUADROS_MEDIAPIPE} cuadros | persona detectada en {detectados} cuadros")
    total = 0.0
    for etapa, valores in tiempos.items():
        ms = float(np.mean(valores)) * 1000 if valores else 0.0
        total += ms
        print(f"  {etapa:<20} {ms:7.1f} ms")
    print(f"  {'TOTAL':<20} {total:7.1f} ms  ->  {1000.0 / max(total, 1e-3):.1f} FPS")
    print("================================")


if __name__ == "__main__":
    main()
