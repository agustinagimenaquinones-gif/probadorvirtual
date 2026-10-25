# ==========================================================
# PROYECTO: PROBADOR VIRTUAL INTELIGENTE
# MÓDULO: LIMPIEZA DE LAS FOTOS DE PRENDAS (SE HACE UNA VEZ, AL CARGAR)
# ==========================================================
# Las fotos de producto se recortan quitando un fondo de color parejo (casi
# siempre blanco). Eso deja dos problemas que se notan mucho en la cámara:
#
#   1. Partes BLANCAS de la prenda borradas junto con el fondo (por ejemplo, el
#      cuello blanco de una chomba): quedan transparentes y sólo se ve su contorno.
#   2. Debajo de la parte transparente sigue el color del fondo. Al deformar y
#      suavizar la prenda, ese color se mezcla con el borde y aparece un "halo"
#      blanco (o negro) alrededor del cuello, las mangas y el ruedo.
#
# recuperar_partes_borradas() arregla el punto 1 y extender_color_de_la_tela()
# el punto 2. La foto original en 'prendas/' no se modifica.

import numpy as np
import cv2

# Diferencia mínima con el color del fondo para considerar que un píxel es tela
UMBRAL_DIFERENCIA_FONDO = 12
# Una parte recuperada tiene que ser al menos esta fracción de la prenda
AREA_MINIMA_RECUPERADA = 0.002
# ... y tocar la prenda en al menos esta fracción de su contorno (una sombra o
# una mancha del fondo casi no la toca; un cuello borrado sí)
CONTACTO_MINIMO = 0.12


def recuperar_partes_borradas(img_rgba):
    """
    Devuelve una copia con el alfa reparado: las zonas transparentes cuyo color es
    claramente distinto del fondo y que están pegadas a la prenda vuelven a ser tela.
    Si el fondo no es de un color parejo, no cambia nada.
    """
    if img_rgba is None or img_rgba.ndim != 3 or img_rgba.shape[2] != 4:
        return img_rgba
    alfa = img_rgba[:, :, 3]
    transparente = alfa == 0
    tela = alfa > 25
    if transparente.sum() < 500 or tela.sum() < 500:
        return img_rgba

    bgr = img_rgba[:, :, :3].astype(np.int16)
    muestra = bgr[transparente][::7]  # una muestra alcanza para conocer el fondo
    fondo = np.median(muestra, axis=0)
    # El fondo tiene que ser parejo: si no, no se puede distinguir de la tela
    if float(np.percentile(np.abs(muestra - fondo).max(axis=1), 90)) > 6:
        return img_rgba

    distinto = (np.abs(bgr - fondo).max(axis=2) > UMBRAL_DIFERENCIA_FONDO) & transparente
    nucleo = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    candidatos = cv2.morphologyEx(distinto.astype(np.uint8), cv2.MORPH_OPEN, nucleo)
    n, etiquetas, stats, _ = cv2.connectedComponentsWithStats(candidatos, connectivity=8)
    if n <= 1:
        return img_rgba

    cerca_tela = cv2.dilate(tela.astype(np.uint8), nucleo) > 0
    area_tela = float(tela.sum())
    recuperado = np.zeros_like(transparente)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] < area_tela * AREA_MINIMA_RECUPERADA:
            continue
        parte = etiquetas == i
        contorno = parte & ~cv2.erode(parte.astype(np.uint8), nucleo).astype(bool)
        if float(np.mean(cerca_tela[contorno])) >= CONTACTO_MINIMO:
            recuperado |= parte
    if not recuperado.any():
        return img_rgba

    # Cerrar los huecos de 1 o 2 píxeles entre la parte recuperada y la tela
    alfa_nuevo = np.maximum(alfa, recuperado.astype(np.uint8) * 255)
    cerrado = cv2.morphologyEx(alfa_nuevo, cv2.MORPH_CLOSE, nucleo)
    resultado = img_rgba.copy()
    resultado[:, :, 3] = np.where(cv2.dilate(recuperado.astype(np.uint8), nucleo) > 0, cerrado, alfa_nuevo)
    return resultado


def extender_color_de_la_tela(img_rgba, alfa_solido=250):
    """
    Reemplaza el color de los píxeles transparentes y semitransparentes por el color
    de la tela más cercana. El alfa no cambia: la prenda se ve igual, pero al
    deformarla y suavizar los bordes ya no aparece el color del fondo.
    """
    if img_rgba is None or img_rgba.ndim != 3 or img_rgba.shape[2] != 4:
        return img_rgba
    solido = (img_rgba[:, :, 3] >= alfa_solido).astype(np.float32)
    if solido.sum() < 50:
        return img_rgba
    bgr = img_rgba[:, :, :3].astype(np.float32)
    pendiente = solido < 1.0
    color = bgr.copy()
    # Promedio ponderado por la tela, de cerca hacia lejos: cada píxel toma el color
    # de la tela más próxima que alcance el desenfoque. Sólo importa una franja de
    # unos pocos píxeles alrededor de la prenda (lo que alcanzan a mezclar la
    # deformación y el suavizado); más lejos se usa el color promedio.
    for sigma in (1.5, 4.0):
        if not pendiente.any():
            break
        peso = cv2.GaussianBlur(solido, (0, 0), sigma)
        suma = cv2.GaussianBlur(bgr * solido[:, :, None], (0, 0), sigma)
        listo = pendiente & (peso > 0.02)
        color[listo] = suma[listo] / peso[listo][:, None]
        pendiente &= ~listo
    if pendiente.any():
        color[pendiente] = bgr[solido > 0].mean(axis=0)
    resultado = img_rgba.copy()
    resultado[:, :, :3] = np.clip(color, 0, 255).astype(np.uint8)
    return resultado
