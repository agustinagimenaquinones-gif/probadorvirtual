# ==========================================================
# PROYECTO: PROBADOR VIRTUAL INTELIGENTE
# DÍA 2 / ETAPA 2: Detección de Pose y Puntos con MediaPipe
# ==========================================================

import os
import sys
import urllib.request
import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

MODEL_FILENAME = "pose_landmarker_lite.task"
MODEL_URL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task"

def asegurar_modelo():
    if not os.path.exists(MODEL_FILENAME):
        print("[+] Descargando archivo del modelo de pose...")
        urllib.request.urlretrieve(MODEL_URL, MODEL_FILENAME)
        print("[OK] Modelo descargado exitosamente.")

def main():
    print("=" * 60)
    print("   DÍA 2: DETECCIÓN DE PUNTOS CLAVE (MEDIAPIPE POSE)   ")
    print("=" * 60)
    print("Objetivo: Detectar los 33 puntos corporales y mostrar sus coordenadas.")
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
        cv2.putText(frame, "DIA 2: Puntos Corporales (Landmarks)", (20, 35), cv2.FONT_HERSHEY_DUPLEX, 0.7, (0, 230, 255), 1, cv2.LINE_AA)

        if resultado.pose_landmarks and len(resultado.pose_landmarks) > 0:
            landmarks = resultado.pose_landmarks[0]
            
            # Dibujar todos los puntos
            for idx, lm in enumerate(landmarks):
                px = int(lm.x * ancho)
                py = int(lm.y * alto)
                # Puntos principales en verde, secundarios en amarillo
                color = (0, 255, 0) if idx in [11, 12, 23, 24] else (0, 215, 255)
                cv2.circle(frame, (px, py), 4, color, -1)
                
            # Mostrar coordenadas de los hombros en vivo
            h_izq = landmarks[11]
            h_der = landmarks[12]
            cv2.putText(frame, f"Hombro Izq (11): ({int(h_izq.x*ancho)}, {int(h_izq.y*alto)})", (20, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 1)
            cv2.putText(frame, f"Hombro Der (12): ({int(h_der.x*ancho)}, {int(h_der.y*alto)})", (20, 115), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 1)
            cv2.putText(frame, "Estado: Cuerpo Detectado", (ancho - 260, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 1, cv2.LINE_AA)
        else:
            cv2.putText(frame, "Estado: Buscando persona...", (ancho - 260, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 255), 1, cv2.LINE_AA)

        # Barra inferior
        cv2.rectangle(frame, (0, alto - 40), (ancho, alto), (25, 25, 30), -1)
        cv2.putText(frame, "Presiona 'q' para volver al menu", (20, alto - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1, cv2.LINE_AA)

        cv2.imshow("Dia 2 - Deteccion de Puntos (MediaPipe)", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    detector.close()
    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
