# ==========================================================
# PROYECTO: PROBADOR VIRTUAL INTELIGENTE
# DÍA 3 / ETAPA 3: Esqueleto Visual y Medidas del Torso
# ==========================================================

import os
import math
import urllib.request
import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

MODEL_FILENAME = "pose_landmarker_lite.task"
MODEL_URL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task"

POSE_CONNECTIONS = [
    (11, 12), (11, 23), (12, 24), (23, 24),
    (11, 13), (13, 15), (12, 14), (14, 16),
    (23, 25), (25, 27), (24, 26), (26, 28)
]

def asegurar_modelo():
    
    if not os.path.exists(MODEL_FILENAME):
        urllib.request.urlretrieve(MODEL_URL, MODEL_FILENAME)

def main():
    print("=" * 60)
    print("   DÍA 3: ESQUELETO COMPLETO Y CÁLCULOS ANATÓMICOS   ")
    print("=" * 60)
    print("Objetivo: Unir articulaciones con huesos y calcular inclinacion/ancho.")
    print("Presiona la tecla 'q' en la ventana para salir.\n")

    asegurar_modelo()

    base_options = python.BaseOptions(model_asset_path=MODEL_FILENAME)
    options = vision.PoseLandmarkerOptions(
        base_options=base_options,
        running_mode=vision.RunningMode.IMAGE,
        min_pose_detection_confidence=0.5,
        min_pose_presence_confidence=0.5,
        min_tracking_confidence=0.5
    )
    detector = vision.PoseLandmarker.create_from_options(options)

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("[ERROR] No se pudo acceder a la cámara web.")
        return

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame = cv2.flip(frame, 1)
        alto, ancho, _ = frame.shape

        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
        resultado = detector.detect(mp_image)

        # Barra superior informativa
        cv2.rectangle(frame, (0, 0), (ancho, 60), (25, 25, 30), -1)
        cv2.putText(frame, "DIA 3: Esqueleto y Medidas del Torso", (20, 35), cv2.FONT_HERSHEY_DUPLEX, 0.7, (0, 230, 255), 1, cv2.LINE_AA)

        if resultado.pose_landmarks and len(resultado.pose_landmarks) > 0:
            landmarks = resultado.pose_landmarks[0]
            
            puntos_px = {}
            for idx, lm in enumerate(landmarks):
                puntos_px[idx] = (int(lm.x * ancho), int(lm.y * alto))

            # Dibujar conexiones óseas
            for p1, p2 in POSE_CONNECTIONS:
                if p1 in puntos_px and p2 in puntos_px:
                    cv2.line(frame, puntos_px[p1], puntos_px[p2], (255, 140, 0), 2, cv2.LINE_AA)

            # Dibujar articulaciones
            for idx in range(11, len(landmarks)):
                if idx in puntos_px:
                    cv2.circle(frame, puntos_px[idx], 5, (0, 255, 0), -1)

            # Cálculos anatómicos
            h_izq, h_der = puntos_px[11], puntos_px[12]
            ancho_hombros = math.hypot(h_der[0] - h_izq[0], h_der[1] - h_izq[1])
            angulo = math.degrees(math.atan2(h_der[1] - h_izq[1], h_der[0] - h_izq[0]))

            cv2.putText(frame, f"Ancho de Hombros: {int(ancho_hombros)} px", (20, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 1)
            cv2.putText(frame, f"Inclinacion Torso: {angulo:.1f} grados", (20, 115), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 1)
            cv2.putText(frame, "Estado: Esqueleto Activo", (ancho - 260, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 1, cv2.LINE_AA)
        else:
            cv2.putText(frame, "Estado: Buscando persona...", (ancho - 260, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 255), 1, cv2.LINE_AA)

        # Barra inferior
        cv2.rectangle(frame, (0, alto - 40), (ancho, alto), (25, 25, 30), -1)
        cv2.putText(frame, "Presiona 'q' para volver al menu", (20, alto - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1, cv2.LINE_AA)

        cv2.imshow("Dia 3 - Esqueleto y Medidas (MediaPipe)", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    detector.close()
    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
