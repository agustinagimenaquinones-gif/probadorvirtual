# ==========================================================
# PROYECTO: PROBADOR VIRTUAL INTELIGENTE
# HERRAMIENTA: RECORTAR LAS PRENDAS DE LA COLECCIÓN ACTUAL
# ==========================================================
# Uso (desde la carpeta del proyecto):
#     .venv\Scripts\python.exe importar_coleccion.py
#
# Deja en 'prendas/' cada prenda con fondo transparente, a partir de las fotos de
# 'fotos_originales/'. Hay fotos de la prenda sola y fotos de la prenda puesta: para
# no llevarse el pelo, la piel ni el pantalón de la modelo, cada una lleva un contorno
# marcado a mano ('zona') y se queda sólo con lo que tiene el color de la tela.
#
# Coordenadas en píxeles de la foto original.

import os

import cv2
import numpy as np
from PIL import Image

from limpieza_prenda import enderezar_prenda, extender_color_de_la_tela

CARPETA_FOTOS = "fotos_originales"
CARPETA_PRENDAS = "prendas"
LADO_MAXIMO_SALIDA = 1000

PRENDAS = {
    "musculosa_acanalada_negra": {
        "foto": "foto_11.webp", "gris_maximo": 170,
        # Las puntas de los breteles están levantadas en la foto: se emparejan
        "zona": [(0, 46), (1094, 46), (1094, 1237), (0, 1237)],
        # Hueco del cuello: lo que se ve es la espalda por dentro, con la etiqueta
        "quitar": [[(394, 0), (394, 25), (399, 55), (413, 94), (435, 130), (469, 158), (520, 172), (560, 174),
                    (608, 167), (641, 147), (663, 117), (688, 72), (703, 35), (708, 0)],
                   # Los breteles bajan hacia el hombro, sin esquinas que sobresalgan
                   [(250, 0), (398, 0), (398, 46), (300, 115), (250, 115)],
                   [(850, 0), (703, 0), (703, 46), (800, 115), (850, 115)]],
    },
    "top_halter_cuello_alto_negro": {
        # La modelo está de costado: la prenda se endereza (y el cuello queda recto)
        "foto": "foto_12.webp", "gris_maximo": 85, "croma_maximo": 16, "enderezar": True,
        "zona": [(552, 490), (552, 625), (530, 660), (470, 770), (395, 880), (395, 1000), (425, 1100), (395, 1200),
                 (355, 1320), (340, 1393), (500, 1412), (700, 1422), (975, 1412), (980, 1300), (960, 1100),
                 (995, 960), (990, 880), (905, 740), (812, 575), (792, 490)],
    },
    "top_halter_drapeado_panuelo": {
        # Foto chica: se agranda antes de recortar. Lleva un pañuelo que cae más abajo del ruedo.
        "foto": "foto_13.png", "gris_maximo": 100, "croma_maximo": 22, "agrandar": 2.5,
        "zona": [(247, 176), (322, 176), (325, 200), (350, 205), (374, 220), (384, 250), (392, 300), (392, 420),
                 (380, 470), (374, 490), (378, 590), (358, 614), (349, 600), (347, 487), (290, 484), (183, 472),
                 (195, 440), (200, 425), (203, 360), (200, 300), (205, 270), (222, 232), (245, 208)],
    },
    "buzo_capucha_bordo": {
        # Fondo gris con sombra: la tela se reconoce porque tiene color y el fondo no
        "foto": "foto_15.png", "gris_maximo": 170, "croma_minimo": 28, "rellenar_huecos": True,
        # Adentro de la capucha va el cuello de la persona: se abre hasta el borde de arriba
        "quitar": [[(252, 130), (258, 210), (308, 271), (351, 301), (398, 322), (438, 301), (486, 268), (526, 237),
                    (550, 210), (556, 130)]],
    },
    "buzo_cuello_redondo_marron": {
        # Hay dos buzos en la foto: el marrón está adelante, el crema se genera tiñéndolo
        "foto": "foto_16.png", "gris_maximo": 135, "rellenar_huecos": True,
        # La parte de adentro del cuello y la etiqueta de atrás irían sobre el cuello de la persona
        "quitar": [[(700, 340), (703, 368), (719, 391), (745, 399), (780, 402), (815, 399), (841, 390), (858, 368),
                    (860, 340)]],
    },
    "buzo_capucha_corto_negro": {
        "foto": "foto_17.png", "gris_maximo": 200, "rellenar_huecos": True,
        "quitar": [[(440, 30), (440, 230), (455, 290), (510, 340), (570, 372), (630, 340), (680, 290), (690, 230),
                    (690, 30)]],
    },
    "remera_entallada_blanca": {
        "foto": "foto_14.webp", "gris_maximo": 250,
        "quitar": [[(800, 120), (798, 195), (808, 253), (850, 312), (917, 345), (1017, 357), (1100, 328),
                    (1142, 270), (1158, 200), (1165, 120)]],
    },
}


def _poligono(forma, puntos, escala):
    mascara = np.zeros(forma, np.uint8)
    cv2.fillPoly(mascara, [np.int32(np.array(puntos, np.float32) * escala)], 255)
    return mascara


def _rellenar_agujeros_chicos(mascara, area_maxima):
    """Rellena los puntitos sueltos, sin tapar huecos reales como el escote."""
    invertida = cv2.bitwise_not(mascara)
    cantidad, etiquetas, datos, _ = cv2.connectedComponentsWithStats(invertida, connectivity=4)
    for i in range(1, cantidad):
        if datos[i, cv2.CC_STAT_AREA] < area_maxima:
            mascara[etiquetas == i] = 255
    return mascara


def recortar(cfg):
    imagen = cv2.cvtColor(np.array(Image.open(os.path.join(CARPETA_FOTOS, cfg["foto"])).convert("RGB")),
                          cv2.COLOR_RGB2BGR)
    escala = float(cfg.get("agrandar", 1.0))
    if escala != 1.0:
        imagen = cv2.resize(imagen, None, fx=escala, fy=escala, interpolation=cv2.INTER_LANCZOS4)
    gris = cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY)
    mascara = (gris < cfg["gris_maximo"]).astype(np.uint8) * 255
    if cfg.get("croma_maximo"):
        # Tela negra: casi sin color. Así no se lleva la piel en sombra, el pelo ni el jean
        croma = imagen.max(axis=2).astype(np.int16) - imagen.min(axis=2).astype(np.int16)
        mascara[croma > cfg["croma_maximo"]] = 0
    if cfg.get("croma_minimo"):
        croma = imagen.max(axis=2).astype(np.int16) - imagen.min(axis=2).astype(np.int16)
        mascara[croma < cfg["croma_minimo"]] = 0
    if cfg.get("zona"):
        mascara = cv2.bitwise_and(mascara, _poligono(gris.shape, cfg["zona"], escala))
    for puntos in cfg.get("quitar", []):
        # Curva suave: el contorno marcado a mano son tramos rectos
        lado = max(3, int(max(gris.shape) * 0.02) | 1)
        hueco = cv2.GaussianBlur(_poligono(gris.shape, puntos, escala), (lado, lado), 0)
        mascara[hueco > 127] = 0

    # Se queda con la pieza más grande y le saca los puntitos que dejó el umbral
    if cfg.get("croma_maximo") or cfg.get("croma_minimo"):
        mascara = cv2.morphologyEx(mascara, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    cantidad, etiquetas, datos, _ = cv2.connectedComponentsWithStats(mascara, connectivity=8)
    if cantidad > 1:
        mascara = ((etiquetas == 1 + int(np.argmax(datos[1:, cv2.CC_STAT_AREA]))) * 255).astype(np.uint8)
    mascara = _rellenar_agujeros_chicos(mascara, mascara.size * 0.002)
    if cfg.get("rellenar_huecos"):
        # Etiquetas o brillos dentro de la tela: se tapa todo lo que no llega hasta el fondo
        contornos, _ = cv2.findContours(mascara, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(mascara, contornos, -1, 255, cv2.FILLED)

    # Borde suave, sin halo del fondo
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mascara = cv2.GaussianBlur(cv2.erode(mascara, k), (3, 3), 0)
    rgba = np.dstack([imagen, mascara])

    filas, columnas = np.where(mascara > 25)
    rgba = rgba[filas.min():filas.max() + 1, columnas.min():columnas.max() + 1]
    lado = max(rgba.shape[:2])
    if lado > LADO_MAXIMO_SALIDA:
        f = LADO_MAXIMO_SALIDA / lado
        rgba = cv2.resize(rgba, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    return rgba


def main():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    os.makedirs(CARPETA_PRENDAS, exist_ok=True)
    for codigo, cfg in PRENDAS.items():
        rgba = recortar(cfg)
        if cfg.get("enderezar"):
            rgba = enderezar_prenda(rgba)
        cv2.imwrite(os.path.join(CARPETA_PRENDAS, f"{codigo}.png"), extender_color_de_la_tela(rgba))
        print(f"[OK] {codigo}: {rgba.shape[1]}x{rgba.shape[0]} desde {cfg['foto']}")


if __name__ == "__main__":
    main()
