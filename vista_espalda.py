# ==========================================================
# PROYECTO: PROBADOR VIRTUAL INTELIGENTE
# MÓDULO: VISTA DE ESPALDA DE LAS PRENDAS
# ==========================================================
# Cuando la persona se da vuelta, no tiene sentido mostrarle el FRENTE de la
# remera (logo, botones, escote en V) sobre la espalda.
#
# 1. Si existe una foto de la espalda, se usa:  prendas/<nombre>_espalda.png
# 2. Si no existe, se genera una espalda AUTOMÁTICA a partir del frente:
#    - se detectan los detalles (logos, letras, botones, costuras marcadas),
#    - se "borran" rellenándolos con la tela de alrededor (inpainting de OpenCV),
#    - y se espeja la imagen (la espalda se ve como el frente dado vuelta).

import os
import cv2
import numpy as np

SUFIJO_ESPALDA = "_espalda"


def ruta_espalda(ruta_frente):
    """prendas/polo.png -> prendas/polo_espalda.png"""
    base, ext = os.path.splitext(ruta_frente)
    return f"{base}{SUFIJO_ESPALDA}{ext or '.png'}"


def es_archivo_espalda(ruta):
    """True si el archivo es la foto de espalda de otra prenda (no es una prenda nueva)."""
    return os.path.splitext(os.path.basename(ruta))[0].endswith(SUFIJO_ESPALDA)


def generar_espalda_automatica(img_rgba):
    """
    Crea una versión 'de espalda' de la prenda: misma silueta y color de tela,
    sin logos, letras ni botones, y espejada.
    """
    if img_rgba is None or img_rgba.ndim != 3 or img_rgba.shape[2] != 4:
        return img_rgba
    alto, ancho = img_rgba.shape[:2]
    alfa = img_rgba[:, :, 3]
    tela = alfa > 40

    # Trabajamos en tamaño reducido para que sea rápido (se hace una sola vez al cargar)
    escala = min(1.0, 420.0 / max(alto, ancho))
    peq = cv2.resize(img_rgba, (max(8, int(ancho * escala)), max(8, int(alto * escala))),
                     interpolation=cv2.INTER_AREA)
    bgr = peq[:, :, :3].copy()
    tela_p = peq[:, :, 3] > 40

    # Color "esperado" de la tela en cada lugar: mediana grande (no ve logos chicos)
    k = max(9, (min(bgr.shape[:2]) // 8) | 1)
    base = cv2.medianBlur(bgr, min(k, 255) if k % 2 else k + 1)
    diferencia = np.linalg.norm(bgr.astype(np.float32) - base.astype(np.float32), axis=2)

    # Detalles = lo que se aparta mucho del color de la tela (logos, letras, botones)
    umbral = max(28.0, float(np.percentile(diferencia[tela_p], 90)) if np.any(tela_p) else 28.0)
    detalles = ((diferencia > umbral) & tela_p).astype(np.uint8) * 255
    detalles = cv2.dilate(detalles, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
    # No tocar el borde de la prenda (el contorno no es un "detalle")
    borde = cv2.erode(tela_p.astype(np.uint8) * 255, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
    detalles = cv2.bitwise_and(detalles, borde)

    limpio = cv2.inpaint(bgr, detalles, 6, cv2.INPAINT_TELEA)
    # Suavizado leve para que no queden "manchas" donde estaban los logos
    limpio = cv2.bilateralFilter(limpio, 7, 30, 7)

    # Volver al tamaño original y conservar la silueta exacta
    limpio = cv2.resize(limpio, (ancho, alto), interpolation=cv2.INTER_LINEAR)
    resultado = img_rgba.copy()
    resultado[:, :, :3][tela] = limpio[tela]

    # La espalda se ve como el frente espejado
    return cv2.flip(resultado, 1)


def cargar_espalda(ruta_frente, img_frente_procesada, preparar):
    """
    Devuelve (imagen_espalda, es_automatica).
    preparar: función que limpia, recorta y agrega margen (la misma que se usa para el frente).
    """
    ruta = ruta_espalda(ruta_frente)
    if os.path.exists(ruta):
        img = cv2.imread(ruta, cv2.IMREAD_UNCHANGED)
        if img is not None and img.ndim == 3 and img.shape[2] == 4:
            return preparar(img), False
    return generar_espalda_automatica(img_frente_procesada), True
