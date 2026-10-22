# ==========================================================
# PROYECTO: PROBADOR VIRTUAL INTELIGENTE
# DÍA 1 / ETAPA 1: Captura de Cámara con OpenCV
# ==========================================================

import cv2
import time

def main():
    print("=" * 60)
    print("   DÍA 1: INICIALIZACIÓN DE CÁMARA Y OPENCV   ")
    print("=" * 60)
    print("Objetivo: Abrir la webcam, aplicar efecto espejo y mostrar FPS.")
    print("Presiona la tecla 'q' en la ventana para salir.\n")

    # Abrir la cámara web (0 suele ser la cámara predeterminada)
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("[ERROR] No se pudo acceder a la cámara web. Revisa los permisos.")
        return

    # Configurar resolución recomendada
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    tiempo_anterior = time.time()

    while True:
        ret, frame = cap.read()
        if not ret:
            print("[ERROR] No se pudo leer el cuadro de la cámara.")
            break

        # Efecto espejo (espejo real para probador)
        frame = cv2.flip(frame, 1)

        # Calcular FPS en tiempo real
        tiempo_actual = time.time()
        fps = 1.0 / (tiempo_actual - tiempo_anterior) if (tiempo_actual - tiempo_anterior) > 0 else 30
        tiempo_anterior = tiempo_actual

        alto, ancho, _ = frame.shape

        # Dibujar panel superior con información
        cv2.rectangle(frame, (0, 0), (ancho, 60), (25, 25, 30), -1)
        cv2.putText(frame, "DIA 1: Captura de Video en Vivo", (20, 35), cv2.FONT_HERSHEY_DUPLEX, 0.7, (0, 230, 255), 1, cv2.LINE_AA)
        cv2.putText(frame, f"Resolucion: {ancho}x{alto} | FPS: {int(fps)}", (ancho - 300, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1, cv2.LINE_AA)

        # Barra inferior
        cv2.rectangle(frame, (0, alto - 40), (ancho, alto), (25, 25, 30), -1)
        cv2.putText(frame, "Presiona 'q' para volver al menu", (20, alto - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1, cv2.LINE_AA)

        # Mostrar imagen
        cv2.imshow("Dia 1 - Captura de Camara (OpenCV)", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            print("Cerrando Día 1...")
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
