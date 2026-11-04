# ==========================================================
# PROYECTO: PROBADOR VIRTUAL INTELIGENTE
# MÓDULO: PLIEGUES Y CAÍDA DE LA TELA, SEGÚN LA POSE
# ==========================================================
# La foto de la prenda es lisa y la ropa de la persona no puede prestarle sus pliegues
# (pasarían también sus dibujos, y parecería transparente). Por eso los pliegues se
# generan: tiran de la axila hacia el pecho, se juntan en la cintura, caen rectos por la
# gravedad hacia el ruedo y se arrugan en el codo. Están atados a los puntos de la malla,
# así que se mueven con el cuerpo y no parpadean.
#
# No es una simulación física de la tela: es una aproximación visual.

import numpy as np
import cv2

# Cuánto oscurece un pliegue y cuánta luz suma su lado claro (niveles de 0 a 255)
INTENSIDAD_SOMBRA = 0.30
LUZ_TELA_OSCURA = 24.0
LUZ_TELA_CLARA = 0.10
# Trazar las curvas es lo más caro y un cuadro de atraso no se nota: se trazan un cuadro sí y otro no
_recuerdo = {"cuadro": 0, "mapa": None}


def _curva(a, b, comba, pasos=10):
    """Curva suave de a hasta b, con una panza lateral de 'comba' píxeles."""
    a, b = np.asarray(a, np.float32), np.asarray(b, np.float32)
    normal = np.array([-(b - a)[1], (b - a)[0]], np.float32)
    normal = normal / max(1e-6, float(np.linalg.norm(normal)))
    medio = (a + b) * 0.5 + normal * comba
    t = np.linspace(0.0, 1.0, pasos, dtype=np.float32)[:, None]
    return (1 - t) ** 2 * a + 2 * (1 - t) * t * medio + t ** 2 * b


def lista_de_pliegues(dst, dist_sh, manga_larga=False):
    """Cada pliegue: (puntos, peso). El lado claro se dibuja al lado del oscuro."""
    p = {k: np.asarray(v, np.float32) for k, v in dst.items()}
    pliegues = []

    def tramo(a, b, fraccion):
        return a + (b - a) * fraccion

    for lado, signo in (("l", 1.0), ("r", -1.0)):
        axila, cintura, cadera = p[f"armpit_{lado}"], p[f"waist_{lado}"], p[f"high_hip_{lado}"]
        # La tela tira de la axila hacia el pecho
        pliegues.append((_curva(axila, tramo(axila, p["chest_mid"], 0.62) + np.array([0, dist_sh * 0.05]), signo * dist_sh * 0.03), 1.0))
        pliegues.append((_curva(tramo(axila, cintura, 0.30), tramo(axila, p["torso_mid"], 0.55), signo * dist_sh * 0.03), 0.75))
        # Se junta en la cintura
        pliegues.append((_curva(cintura, tramo(cintura, p["torso_mid"], 0.50), -signo * dist_sh * 0.02), 0.85))
        pliegues.append((_curva(tramo(cintura, cadera, 0.45), tramo(cadera, p["torso_mid"], 0.42), signo * dist_sh * 0.02), 0.6))
    # La gravedad: caen casi rectos hacia el ruedo
    for t, peso in ((0.20, 0.7), (0.42, 0.5), (0.63, 0.6), (0.82, 0.7)):
        arriba = tramo(p["waist_l"], p["waist_r"], t)
        abajo = tramo(p["hem_l"], p["hem_r"], t)
        pliegues.append((_curva(tramo(arriba, abajo, 0.45), tramo(arriba, abajo, 0.98), (t - 0.5) * dist_sh * 0.06), peso))
    if manga_larga:
        for lado in ("l", "r"):
            afuera, adentro = p[f"bicep_out_{lado}"], p[f"bicep_in_{lado}"]
            # Arrugas del codo, cruzadas a la manga
            pliegues.append((_curva(tramo(afuera, adentro, 0.08), tramo(afuera, adentro, 0.92), dist_sh * 0.025), 1.0))
            codo = (afuera + adentro) * 0.5
            puno = (p[f"sleeve_cuff_out_{lado}"] + p[f"sleeve_cuff_in_{lado}"]) * 0.5
            eje = (puno - codo) * 0.16
            pliegues.append((_curva(tramo(afuera, adentro, 0.15) + eje, tramo(afuera, adentro, 0.85) + eje, dist_sh * 0.02), 0.65))
            pliegues.append((_curva(tramo(afuera, adentro, 0.15) - eje, tramo(afuera, adentro, 0.85) - eje, -dist_sh * 0.02), 0.65))
            # Pliegue del hombro hacia la axila
            pliegues.append((_curva(tramo(p[f"shoulder_{lado}"], p[f"armpit_{lado}"], 0.25), p[f"armpit_{lado}"], dist_sh * 0.02), 0.7))
    return pliegues


def mapa_pliegues(alto, ancho, xmin, ymin, dst, dist_sh, manga_larga=False):
    """Mapa a un cuarto del tamaño del parche: negativo donde hay sombra, positivo en el lado con luz."""
    if not all(k in dst for k in ("armpit_l", "armpit_r", "waist_l", "waist_r", "high_hip_l", "high_hip_r", "hem_l", "hem_r",
                                  "chest_mid", "torso_mid")):
        return None
    escala = 0.25   # chico: se dibuja por cuadro y no necesita detalle (después se desenfoca)
    h, w = max(4, int(alto * escala)), max(4, int(ancho * escala))
    mapa = np.zeros((h, w), np.float32)
    origen = np.array([xmin, ymin], np.float32)
    grosor = max(1, int(dist_sh * 0.012 * escala))
    desvio = dist_sh * 0.012 * escala
    for puntos, peso in lista_de_pliegues(dst, dist_sh, manga_larga):
        pares = ((puntos - origen) * escala)
        linea = np.int32(np.round(pares))[None, :, :]
        cv2.polylines(mapa, linea, False, -float(peso), grosor, cv2.LINE_AA)
        cv2.polylines(mapa, linea + np.int32([max(1, int(desvio * 2.2)), max(1, int(desvio))]), False, float(peso) * 0.75,
                      grosor, cv2.LINE_AA)
    return cv2.GaussianBlur(mapa, (0, 0), max(0.8, desvio))


def aplicar_pliegues(parche_rgba, xmin, ymin, dst, dist_sh, manga_larga=False):
    """Dibuja los pliegues sobre la tela. La sombra multiplica; la luz se suma en la tela oscura."""
    if parche_rgba is None or dst is None:
        return parche_rgba
    alto, ancho = parche_rgba.shape[:2]
    _recuerdo["cuadro"] += 1
    mapa = _recuerdo["mapa"]
    if _recuerdo["cuadro"] % 2 == 1 or mapa is None or mapa.shape[:2] != (max(4, int(alto * 0.25)), max(4, int(ancho * 0.25))):
        mapa = mapa_pliegues(alto, ancho, xmin, ymin, dst, dist_sh, manga_larga)
        _recuerdo["mapa"] = mapa
    if mapa is None:
        return parche_rgba
    bgr = np.ascontiguousarray(parche_rgba[:, :, :3])
    # Todas las cuentas se hacen en chico y el resultado se agranda en enteros de 8 bits:
    # así el costo casi no depende del tamaño de la prenda en la cámara
    h, w = mapa.shape[:2]
    claridad = cv2.resize(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), (w, h), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
    sombra, luz = np.minimum(mapa, 0.0), np.maximum(mapa, 0.0)
    factor = np.clip((1.0 + sombra * INTENSIDAD_SOMBRA + luz * LUZ_TELA_CLARA * claridad) * 128.0, 0, 255).astype(np.uint8)
    suma = np.clip(luz * LUZ_TELA_OSCURA * np.clip(1.0 - claridad * 2.0, 0.0, 1.0), 0, 255).astype(np.uint8)
    factor = cv2.resize(factor, (ancho, alto), interpolation=cv2.INTER_LINEAR)
    suma = cv2.resize(suma, (ancho, alto), interpolation=cv2.INTER_LINEAR)
    resultado = parche_rgba.copy()
    tres = cv2.merge([factor, factor, factor])
    resultado[:, :, :3] = cv2.add(cv2.multiply(bgr, tres, scale=1.0 / 128.0, dtype=cv2.CV_8U), cv2.merge([suma, suma, suma]))
    return resultado
