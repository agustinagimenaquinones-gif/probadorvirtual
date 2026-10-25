# ==========================================================
# PROYECTO: PROBADOR VIRTUAL INTELIGENTE
# MÓDULO: VARIANTES DE COLOR DE UNA PRENDA
# ==========================================================
# Cada prenda tiene una sola foto, pero se vende en varios colores. Para mostrar
# (y probarse) otro color, se cambia el color de la TELA principal conservando
# sus luces y sombras (pliegues, costuras), y sin tocar los detalles de otro
# color: logos, cuellos en contraste, estampados.

import numpy as np
import cv2

# Cuánto se respetan las luces y sombras originales al cambiar de color
# (1 = todas; menos = tela más pareja)
INTENSIDAD_SOMBREADO = 0.75
# Brillo medio (0-255) por debajo del cual la tela de la foto se considera oscura
TELA_OSCURA = 70


def hex_a_bgr(hex_color):
    """'#1F2A44' -> (68, 42, 31)"""
    h = hex_color.lstrip("#")
    return int(h[4:6], 16), int(h[2:4], 16), int(h[0:2], 16)


def mascara_tela_principal(img_rgba, tolerancia=1.0):
    """
    Píxeles de la tela principal: los de color parecido al color más común de la
    prenda (en Lab). Quedan afuera los logos, estampados y cuellos de otro color.
    Devuelve (mascara_bool, color_lab_medio).
    """
    alfa = img_rgba[:, :, 3]
    tela = alfa > 128
    if tela.sum() < 50:
        return tela, None
    lab = cv2.cvtColor(np.ascontiguousarray(img_rgba[:, :, :3]), cv2.COLOR_BGR2LAB).astype(np.float32)
    # Color de referencia con desenfoque: la textura (rayas, tejido) no lo cambia
    suave = cv2.GaussianBlur(lab, (0, 0), 3)
    ref = np.median(suave[tela], axis=0)
    dif_l = np.abs(suave[:, :, 0] - ref[0])
    dif_ab = np.linalg.norm(suave[:, :, 1:] - ref[1:], axis=2)
    principal = tela & (dif_l < 45 * tolerancia) & (dif_ab < 14 * tolerancia)
    # Sin manchitas sueltas
    nucleo = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    principal = cv2.morphologyEx(principal.astype(np.uint8), cv2.MORPH_OPEN, nucleo) > 0
    return principal, ref


def recolorear(img_rgba, hex_color, mascara=None, intensidad=INTENSIDAD_SOMBREADO, suavizado=0.0):
    """
    Devuelve una copia de la prenda con la tela principal del color indicado.
    La luminosidad de cada píxel respecto de la media de la tela se conserva como
    "sombreado", así los pliegues y costuras siguen viéndose.
    suavizado (px): desenfoca el sombreado (quita manchas y textura muy marcadas).
    """
    if mascara is None:
        mascara, _ = mascara_tela_principal(img_rgba)
    if not mascara.any():
        return img_rgba.copy()
    bgr = np.ascontiguousarray(img_rgba[:, :, :3])
    gris = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    # Tela original muy oscura (negro, azul noche): sus pliegues son enormes en
    # proporción y, llevados a un color claro, la prenda parece satén o metal.
    if float(np.median(gris[mascara])) < TELA_OSCURA:
        intensidad = min(intensidad, 0.35)
        suavizado = max(suavizado, 1.5)
    if suavizado > 0:
        # Desenfoque que sólo promedia tela (el fondo transparente no oscurece los bordes)
        peso_tela = cv2.GaussianBlur(mascara.astype(np.float32), (0, 0), suavizado) + 1e-3
        gris = cv2.GaussianBlur(gris * mascara, (0, 0), suavizado) / peso_tela
    media = float(np.median(gris[mascara])) + 1.0
    sombreado = 1.0 + (gris / media - 1.0) * intensidad
    # En telas muy oscuras el contraste relativo es enorme: se limita
    sombreado = np.clip(sombreado, 0.55, 1.35)
    destino = np.array(hex_a_bgr(hex_color), dtype=np.float32)
    nuevo = np.clip(sombreado[:, :, None] * destino[None, None, :], 0, 255)
    # Borde suave entre la tela recoloreada y los detalles que se conservan
    peso = cv2.GaussianBlur(mascara.astype(np.float32), (0, 0), 1.2)[:, :, None]
    resultado = img_rgba.copy()
    resultado[:, :, :3] = (bgr * (1.0 - peso) + nuevo * peso).astype(np.uint8)
    return resultado


class CacheColores:
    """Guarda las versiones recoloreadas para no recalcularlas en cada cuadro."""

    def __init__(self, maximo=48):
        self.maximo = maximo
        self._datos = {}

    def obtener(self, clave_prenda, img_rgba, hex_color):
        if not hex_color:
            return img_rgba
        clave = (clave_prenda, id(img_rgba), hex_color.upper())
        if clave not in self._datos:
            if len(self._datos) >= self.maximo:
                self._datos.clear()
            self._datos[clave] = (img_rgba, recolorear(img_rgba, hex_color))
        return self._datos[clave][1]
