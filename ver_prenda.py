# ==========================================================
# PROYECTO: PROBADOR VIRTUAL INTELIGENTE
# Etapa 5: Visualizador y verificación de prendas PNG con canal Alfa
# ==========================================================

import os
import cv2
import numpy as np

def inspeccionar_prenda(ruta_archivo):
    """
    Carga una imagen PNG y explica cómo están organizados sus 4 canales (BGRA).
    """
    if not os.path.exists(ruta_archivo):
        print(f"[ERROR] No se encontró el archivo: {ruta_archivo}")
        return

    # cv2.IMREAD_UNCHANGED (-1): Le indica a OpenCV que cargue los 4 canales (BGR + Alfa)
    # Si usamos cv2.imread normal, ignoraría la transparencia y rellenaría el fondo de negro.
    prenda_rgba = cv2.imread(ruta_archivo, cv2.IMREAD_UNCHANGED)

    alto, ancho, canales = prenda_rgba.shape
    print(f"\n--- Información de la Prenda: {os.path.basename(ruta_archivo)} ---")
    print(f"Dimensiones: {ancho}x{alto} píxeles")
    print(f"Cantidad de canales: {canales} (Azul, Verde, Rojo, Transparencia/Alfa)")

    # Separar los canales para entender qué hace cada uno
    b, g, r, a = cv2.split(prenda_rgba)
    pixeles_visibles = np.count_nonzero(a > 0)
    pixeles_transparentes = np.count_nonzero(a == 0)
    
    print(f"Píxeles con tela (visibles): {pixeles_visibles}")
    print(f"Píxeles de fondo (transparentes): {pixeles_transparentes}")

    # Crear una cuadrícula tipo "ajedrez" (como en Photoshop) para apreciar la transparencia
    patron_ajedrez = np.zeros((alto, ancho, 3), dtype=np.uint8)
    tam_celda = 20
    for y in range(0, alto, tam_celda):
        for x in range(0, ancho, tam_celda):
            if ((x // tam_celda) + (y // tam_celda)) % 2 == 0:
                patron_ajedrez[y:y+tam_celda, x:x+tam_celda] = (220, 220, 220)
            else:
                patron_ajedrez[y:y+tam_celda, x:x+tam_celda] = (255, 255, 255)

    # Superponer la prenda sobre el patrón de ajedrez
    # Usamos la máscara alfa: donde a > 0 ponemos el color de la remera, donde a == 0 queda el fondo
    mascara_normalizada = a / 255.0  # Valores entre 0.0 y 1.0
    prenda_bgr = cv2.merge([b, g, r])

    vista_final = np.zeros_like(patron_ajedrez)
    for c in range(3):
        vista_final[:, :, c] = (mascara_normalizada * prenda_bgr[:, :, c] +
                                (1.0 - mascara_normalizada) * patron_ajedrez[:, :, c]).astype(np.uint8)

    # Mostrar la imagen
    cv2.putText(
        vista_final,
        "Prenda PNG con Canal Alfa (Presiona cualquier tecla para cerrar)",
        (20, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (50, 50, 50),
        1
    )
    cv2.imshow("Etapa 5 - Inspeccion de Prenda PNG", vista_final)
    print("\nMostrando la prenda sobre fondo transparente. Presioná cualquier tecla en la ventana para continuar...")
    cv2.waitKey(0)
    cv2.destroyAllWindows()

def main():
    print("=" * 60)
    print("   PROBADOR VIRTUAL - ETAPA 5: PRENDAS PNG Y CANAL ALFA")
    print("=" * 60)
    
    ruta_remera = os.path.join("prendas", "remera_azul.png")
    inspeccionar_prenda(ruta_remera)

if __name__ == "__main__":
    main()
