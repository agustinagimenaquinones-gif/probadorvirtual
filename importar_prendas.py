# ==========================================================
# PROYECTO: PROBADOR VIRTUAL INTELIGENTE
# HERRAMIENTA: CONVERTIR FOTOS DE PRENDAS EN PNG PARA EL PROBADOR
# ==========================================================
# Uso (desde la carpeta del proyecto):
#     .venv\Scripts\python.exe importar_prendas.py
#
# Toma las fotos de 'fotos_originales/' y deja en 'prendas/' cada prenda recortada,
# derecha y con fondo transparente. Hay dos tipos de foto:
#
#   * PRENDA SUELTA (sobre una mesa, alfombra o fondo liso): se recorta con GrabCut.
#     Cada foto puede llevar marcas a mano: zonas que SEGURO son prenda (por ejemplo,
#     un cuello blanco sobre una sábana blanca) o fondo (auriculares, una lupa),
#     una rotación para enderezarla y "completar_espejo" para rellenar la parte
#     tapada o cortada copiando el otro lado de la prenda.
#
#   * PRENDA PUESTA POR UN MODELO: los brazos tapan los costados, así que no sirve
#     recortarla. Se recorta sólo el ESTAMPADO y se lo aplica sobre una remera lisa
#     de base (otra prenda ya recortada, cambiada al color de la remera original).

import os
import cv2
import numpy as np

from colores_prenda import recolorear, hex_a_bgr
from vista_espalda import generar_espalda_automatica
from limpieza_prenda import extender_color_de_la_tela

CARPETA_FOTOS = "fotos_originales"
CARPETA_PRENDAS = "prendas"
LADO_MAXIMO_SALIDA = 1000
LADO_GRABCUT = 900

# --------------------------------------------------------------------------
# PRENDAS SUELTAS (coordenadas en píxeles de la foto original)
# --------------------------------------------------------------------------
PRENDAS_SUELTAS = {
    "remera_fitted_negra": {"foto": "foto_04.jpg"},
    # Dentro de la tira del halter se ve el cemento: se quita lo que tiene su color
    "top_halter_seamless": {"foto": "foto_05.jpg", "quitar_color_fondo": True},
    "top_halter_escote_v": {"foto": "foto_06.jpg"},
    "top_asimetrico_animal_print": {"foto": "foto_07.jpg"},
    "top_halter_lunares": {"foto": "foto_08.jpg"},
    "chomba_crop_rosa": {
        "foto": "foto_09.jpg",
        "rectangulo": (5, 95, 745, 800),
        # Cuello blanco sobre la sábana blanca
        "seguro_prenda": [[(205, 145), (258, 118), (452, 118), (508, 145), (510, 240),
                           (420, 245), (355, 330), (290, 248), (200, 252)]],
        # Auriculares y la lupa con el detalle del bordado
        "seguro_fondo": [[(525, 55), (750, 55), (750, 310), (600, 310), (560, 255), (525, 150)]],
        "circulos_fondo": [((600, 835), 168)],
        "completar_espejo": (358, 300),   # punto sobre el eje de la prenda (centro del cuello)
    },
    "remera_retro_champs": {
        "foto": "foto_10.jpg",
        "rectangulo": (5, 220, 735, 1020),
        "elipses_prenda": [((488, 302), (98, 68), 8)],  # cuello acanalado crema
        "seguro_prenda": [[(28, 398), (58, 392), (146, 540), (118, 558)],      # puño izquierdo
                          [(645, 628), (733, 592), (733, 638), (660, 682)]],   # puño derecho
        "seguro_fondo": [[(0, 830), (120, 835), (300, 1105), (0, 1105)]],      # libro
        "rotacion": 13.0,                  # está torcida en la foto
        "completar_espejo": (488, 302),    # la manga derecha queda cortada por el borde
    },
}

# --------------------------------------------------------------------------
# REMERAS PUESTAS POR MODELOS: se toma sólo el estampado
# --------------------------------------------------------------------------
BASE_REMERA_LISA = "remera_fitted_negra"   # forma de remera que se usa de base
REMERAS_CON_ESTAMPADO = {
    "remera_oversize_hot_wheels": {
        "foto": "foto_01.jpg", "estampado": (168, 306, 394, 454),
        "color_remera": "#ECE7DA", "ancho_relativo": 0.50, "altura_centro": 0.36,
    },
    "remera_oversize_la_milano": {
        "foto": "foto_02.jpg", "estampado": (352, 618, 908, 882),
        "color_remera": "#F4F3F0", "ancho_relativo": 0.46, "altura_centro": 0.34,
    },
    "remera_oversize_that_silence": {
        "foto": "foto_03.jpg", "estampado": (418, 668, 802, 972),
        "color_remera": "#F1EFE9", "ancho_relativo": 0.40, "altura_centro": 0.38,
    },
}


def _escalar(img, lado):
    e = min(1.0, lado / float(max(img.shape[:2])))
    return (cv2.resize(img, None, fx=e, fy=e, interpolation=cv2.INTER_AREA) if e < 1.0 else img), e


def _componente_mayor(mascara):
    n, etiquetas, stats, _ = cv2.connectedComponentsWithStats(mascara.astype(np.uint8), connectivity=8)
    if n <= 1:
        return mascara.astype(bool)
    return etiquetas == 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))


def _rellenar_agujeros(mascara, img, color_fondo):
    """
    Rellena los agujeros de la prenda (logos claros, etiquetas) salvo los que tienen
    el color del fondo: por ejemplo, el hueco de la tira de un top halter.
    """
    m = mascara.astype(np.uint8)
    alto, ancho = m.shape
    relleno = m.copy()
    borde = np.zeros((alto + 2, ancho + 2), np.uint8)
    cv2.floodFill(relleno, borde, (0, 0), 2)
    agujeros = relleno == 0
    n, etiquetas = cv2.connectedComponents(agujeros.astype(np.uint8))
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB).astype(np.float32)
    fondo_lab = cv2.cvtColor(np.uint8([[color_fondo]]), cv2.COLOR_BGR2LAB)[0, 0].astype(np.float32)
    resultado = mascara.copy()
    chico = max(30, int(mascara.sum() * 0.0005))  # huequitos de GrabCut (se agrandarían al achicar el borde)
    for i in range(1, n):
        zona = etiquetas == i
        if zona.sum() <= chico or float(np.linalg.norm(lab[zona].mean(axis=0) - fondo_lab)) > 18:
            resultado |= zona
    return resultado


def recortar_prenda_suelta(cfg):
    original = cv2.imread(os.path.join(CARPETA_FOTOS, cfg["foto"]))
    alto0, ancho0 = original.shape[:2]
    img, e = _escalar(original, LADO_GRABCUT)
    alto, ancho = img.shape[:2]

    def esc(p):
        return (int(round(p[0] * e)), int(round(p[1] * e)))

    marcas = np.full((alto, ancho), cv2.GC_PR_BGD, np.uint8)
    x0, y0, x1, y1 = cfg.get("rectangulo", (ancho0 * 0.04, alto0 * 0.04, ancho0 * 0.96, alto0 * 0.96))
    (a, b), (c, d) = esc((x0, y0)), esc((x1, y1))
    marcas[b:d, a:c] = cv2.GC_PR_FGD
    franja = max(3, int(min(alto, ancho) * 0.015))
    marcas[:franja, :] = marcas[-franja:, :] = cv2.GC_BGD
    marcas[:, :franja] = marcas[:, -franja:] = cv2.GC_BGD
    for poligono in cfg.get("seguro_fondo", []):
        cv2.fillPoly(marcas, [np.int32([esc(p) for p in poligono])], cv2.GC_BGD)
    for centro, radio in cfg.get("circulos_fondo", []):
        cv2.circle(marcas, esc(centro), int(radio * e), cv2.GC_BGD, -1)
    for poligono in cfg.get("seguro_prenda", []):
        cv2.fillPoly(marcas, [np.int32([esc(p) for p in poligono])], cv2.GC_FGD)
    for centro, ejes, angulo in cfg.get("elipses_prenda", []):
        cv2.ellipse(marcas, esc(centro), esc(ejes), angulo, 0, 360, cv2.GC_FGD, -1)

    bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    cv2.grabCut(img, marcas, None, bgd, fgd, 8, cv2.GC_INIT_WITH_MASK)
    prenda = (marcas == cv2.GC_FGD) | (marcas == cv2.GC_PR_FGD)
    nucleo = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    prenda = cv2.morphologyEx(prenda.astype(np.uint8), cv2.MORPH_OPEN, nucleo) > 0
    prenda = _componente_mayor(prenda)
    color_fondo = np.median(img[marcas == cv2.GC_BGD], axis=0).astype(np.uint8)
    prenda = _rellenar_agujeros(prenda, img, color_fondo)
    if cfg.get("quitar_color_fondo"):
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB).astype(np.float32)
        fondo_lab = cv2.cvtColor(np.uint8([[color_fondo]]), cv2.COLOR_BGR2LAB)[0, 0].astype(np.float32)
        parecido = cv2.GaussianBlur(np.linalg.norm(lab - fondo_lab, axis=2), (0, 0), 2) < 22
        parecido = cv2.morphologyEx(parecido.astype(np.uint8), cv2.MORPH_OPEN, nucleo) > 0
        prenda = _componente_mayor(prenda & ~parecido)
    # La lupa y los objetos marcados como fondo nunca son prenda (aunque tapen tela)
    for centro, radio in cfg.get("circulos_fondo", []):
        tapa = np.zeros_like(prenda, dtype=np.uint8)
        cv2.circle(tapa, esc(centro), int(radio * e) + 3, 1, -1)
        prenda &= tapa == 0

    # Alfa a tamaño completo, con borde suave de ~1 px
    alfa = cv2.resize(prenda.astype(np.float32), (ancho0, alto0), interpolation=cv2.INTER_LINEAR)
    # Se achica 3 px: el borde de la foto mezcla la tela con el fondo (halo claro) y el
    # recorte se calcula en una imagen más chica
    alfa = cv2.erode((alfa > 0.5).astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
    # Ajuste fino por color: en una franja junto al borde, lo que tiene el color del
    # fondo no es prenda (GrabCut trabaja en una imagen más chica y se pasa un poco)
    franja_borde = (alfa > 0) & ~(cv2.erode(alfa, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))) > 0)
    lab0 = cv2.cvtColor(original, cv2.COLOR_BGR2LAB).astype(np.float32)
    fondo_lab0 = cv2.cvtColor(np.uint8([[color_fondo]]), cv2.COLOR_BGR2LAB)[0, 0].astype(np.float32)
    alfa[franja_borde & (np.linalg.norm(lab0 - fondo_lab0, axis=2) < 20)] = 0
    alfa = cv2.morphologyEx(alfa, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    alfa = cv2.GaussianBlur(alfa.astype(np.float32), (0, 0), 1.0)
    rgba = cv2.cvtColor(original, cv2.COLOR_BGR2BGRA)
    rgba[:, :, 3] = (alfa * 255).astype(np.uint8)

    eje = cfg.get("completar_espejo")
    if cfg.get("rotacion"):
        centro = (ancho0 / 2.0, alto0 / 2.0)
        m = cv2.getRotationMatrix2D(centro, cfg["rotacion"], 1.0)
        cos, sen = abs(m[0, 0]), abs(m[0, 1])
        nuevo_ancho, nuevo_alto = int(alto0 * sen + ancho0 * cos), int(alto0 * cos + ancho0 * sen)
        m[0, 2] += nuevo_ancho / 2.0 - centro[0]
        m[1, 2] += nuevo_alto / 2.0 - centro[1]
        rgba = cv2.warpAffine(rgba, m, (nuevo_ancho, nuevo_alto), flags=cv2.INTER_LINEAR,
                              borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
        if eje is not None:
            eje = tuple(m @ np.array([eje[0], eje[1], 1.0]))
    if eje is not None:
        rgba = completar_con_espejo(rgba, eje[0])
    return rgba


def completar_con_espejo(rgba, eje_x):
    """Rellena lo que falta de un lado de la prenda con el otro lado espejado."""
    alto, ancho = rgba.shape[:2]
    margen = int(max(eje_x, ancho - eje_x)) + 2
    lienzo = cv2.copyMakeBorder(rgba, 0, 0, margen, margen, cv2.BORDER_CONSTANT, value=(0, 0, 0, 0))
    eje = float(eje_x) + margen
    mx = (2 * eje - np.arange(lienzo.shape[1], dtype=np.float32)).astype(np.float32)[None, :].repeat(alto, axis=0)
    my = np.arange(alto, dtype=np.float32)[:, None].repeat(lienzo.shape[1], axis=1)
    espejo = cv2.remap(lienzo, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
    falta = (lienzo[:, :, 3] < 128) & (espejo[:, :, 3] >= 128)
    lienzo[falta] = espejo[falta]
    return lienzo


def _rellenar_todo(mascara):
    """La silueta sin ningún agujero interior."""
    m = mascara.astype(np.uint8)
    relleno = m.copy()
    cv2.floodFill(relleno, np.zeros((m.shape[0] + 2, m.shape[1] + 2), np.uint8), (0, 0), 2)
    return (relleno != 2)


def recortar_bordes(rgba):
    ys, xs = np.where(rgba[:, :, 3] > 10)
    return rgba[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def remera_con_estampado(cfg, base_rgba):
    """Remera lisa de base del color de la remera original + el estampado recortado de la foto."""
    # Silueta llena (sin el hueco de la etiqueta) y sombreado suave: una remera negra
    # tiene mucho contraste en sus pliegues y aclarada se vería manchada
    llena = _rellenar_todo(base_rgba[:, :, 3] > 128)
    base = base_rgba.copy()
    base[:, :, 3] = np.maximum(base[:, :, 3], llena.astype(np.uint8) * 255)
    remera = recolorear(base, cfg["color_remera"], mascara=llena, intensidad=0.35, suavizado=5.0)
    foto = cv2.imread(os.path.join(CARPETA_FOTOS, cfg["foto"]))
    x0, y0, x1, y1 = cfg["estampado"]
    zona = foto[y0:y1, x0:x1].astype(np.float32)
    # El color de la tela alrededor del estampado: lo que se parece a él es transparente
    borde = np.concatenate([zona[:6].reshape(-1, 3), zona[-6:].reshape(-1, 3),
                            zona[:, :6].reshape(-1, 3), zona[:, -6:].reshape(-1, 3)])
    tela = np.median(borde, axis=0)
    lab = cv2.cvtColor(zona.astype(np.uint8), cv2.COLOR_BGR2LAB).astype(np.float32)
    # Color de la tela en CADA lugar (mediana grande: las letras finas no la cambian),
    # así las sombras y la luz despareja de la foto no dejan un "recuadro"
    # Se promedian sólo los píxeles que ya se parecen a la tela: un logo grande no la confunde
    tela_lab = cv2.cvtColor(np.uint8([[tela]]), cv2.COLOR_BGR2LAB)[0, 0].astype(np.float32)
    parece_tela = (np.linalg.norm(lab - tela_lab, axis=2) < 20).astype(np.float32)
    sigma = max(6.0, min(zona.shape[:2]) / 8.0)
    peso = cv2.GaussianBlur(parece_tela, (0, 0), sigma) + 1e-3
    tela_local = cv2.GaussianBlur(lab * parece_tela[:, :, None], (0, 0), sigma) / peso[:, :, None]
    lejos = peso < 0.05  # sin tela cerca: se usa el color general
    tela_local[lejos] = tela_lab
    # Las sombras de los pliegues cambian el brillo, no el color: pesa más el color
    dif = np.sqrt(((lab[:, :, 0] - tela_local[:, :, 0]) * 0.55) ** 2
                  + np.sum((lab[:, :, 1:] - tela_local[:, :, 1:]) ** 2, axis=2))
    alfa = np.clip((dif - 14.0) / 22.0, 0.0, 1.0)
    alfa = cv2.GaussianBlur(alfa, (0, 0), 0.6)

    # Colocar sobre el pecho de la remera
    ys, xs = np.where(remera[:, :, 3] > 128)
    ancho_r = xs.max() - xs.min()
    nuevo_ancho = int(ancho_r * cfg["ancho_relativo"])
    escala = nuevo_ancho / float(zona.shape[1])
    nuevo_alto = int(zona.shape[0] * escala)
    deco = cv2.resize(zona, (nuevo_ancho, nuevo_alto), interpolation=cv2.INTER_AREA)
    alfa = cv2.resize(alfa, (nuevo_ancho, nuevo_alto), interpolation=cv2.INTER_AREA)
    cx = int((xs.min() + xs.max()) / 2)
    cy = int(ys.min() + (ys.max() - ys.min()) * cfg["altura_centro"])
    x, y = cx - nuevo_ancho // 2, cy - nuevo_alto // 2
    region = remera[y:y + nuevo_alto, x:x + nuevo_ancho]
    # El estampado toma las sombras de la tela de base (queda "impreso", no pegado encima)
    gris = cv2.cvtColor(np.ascontiguousarray(region[:, :, :3]), cv2.COLOR_BGR2GRAY).astype(np.float32)
    sombra = np.clip(gris / (np.median(gris) + 1.0), 0.75, 1.15)[:, :, None]
    # El estampado no se aclara: se normaliza respecto del color de tela de su foto
    deco = np.clip(deco * (np.array(hex_a_bgr(cfg["color_remera"]), np.float32) / (tela + 1.0)), 0, 255)
    a = (alfa * (region[:, :, 3] > 128))[:, :, None]
    region[:, :, :3] = (region[:, :, :3] * (1 - a) + deco * sombra * a).astype(np.uint8)
    return remera


def main():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    os.makedirs(CARPETA_PRENDAS, exist_ok=True)
    recortes = {}
    for codigo, cfg in PRENDAS_SUELTAS.items():
        rgba, _ = _escalar(recortar_bordes(recortar_prenda_suelta(cfg)), LADO_MAXIMO_SALIDA)
        recortes[codigo] = rgba
        cv2.imwrite(os.path.join(CARPETA_PRENDAS, f"{codigo}.png"), extender_color_de_la_tela(rgba))
        print(f"[OK] {codigo}: {rgba.shape[1]}x{rgba.shape[0]} desde {cfg['foto']}")

    # Base lisa: la remera sin logo ni etiqueta (se usa el limpiador de la vista de espalda)
    base = cv2.flip(generar_espalda_automatica(recortes[BASE_REMERA_LISA]), 1)
    for codigo, cfg in REMERAS_CON_ESTAMPADO.items():
        rgba = remera_con_estampado(cfg, base)
        cv2.imwrite(os.path.join(CARPETA_PRENDAS, f"{codigo}.png"), extender_color_de_la_tela(rgba))
        print(f"[OK] {codigo}: estampado de {cfg['foto']} sobre remera lisa {cfg['color_remera']}")


if __name__ == "__main__":
    main()
