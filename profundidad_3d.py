# ==========================================================
# PROYECTO: PROBADOR VIRTUAL INTELIGENTE
# MÓDULO: PROFUNDIDAD 3D (LA TELA ENVUELVE EL TORSO)
# ==========================================================
# La cámara ve un cuerpo redondo, pero la foto de la prenda es plana. Si se la pega
# tal cual, el estampado y la trama se ven igual de anchos en el centro que en los
# costados, y al girar sólo "se corre". Aquí el torso se modela como un cilindro:
#
#   * La tela cubre un arco del frente del cuerpo (de -ARCO_FRENTE a +ARCO_FRENTE).
#     Proyectada en la cámara, se ve más ancha en el centro y comprimida hacia los
#     costados, donde la tela "da la vuelta".
#   * El giro del torso (calculado con la profundidad Z de MediaPipe en hombros y
#     caderas) rota el cilindro: el lado que se aleja se comprime más, el centro de la
#     prenda (botones, logo) se corre hacia ese lado y lo que queda detrás no se ve.
#   * La luz llega desde donde viene en la cámara (info["luz"]; de frente si no se
#     sabe): la tela que mira hacia la luz se ve más clara y la que le da la espalda,
#     más oscura. Si la luz viene de arriba, los hombros quedan más claros que la cintura.
#
# Los bordes de la tela no se mueven (siguen pegados a la silueta medida): sólo se
# redistribuye la tela entre ellos, fila por fila.

import math
import numpy as np
import cv2

from ajuste_silueta import _bordes_desde_centro, _suavizar

# Medio arco del cuerpo que cubre el frente de la prenda (grados)
ARCO_FRENTE = 62.0
# Giro del torso: el valor 'giro' de pose_tracker (-0.7 a 0.7) pasado a grados
GRADOS_POR_GIRO = 50.0
# Cuánto se oscurecen los costados por la curva del cuerpo (0 = nada)
INTENSIDAD_LUZ_3D = 0.22
# Dirección de la luz estimada en la cámara (info["luz"], ver luz_escena.py):
# cuántos grados se corre la luz hacia un costado, y cuánto más claros quedan los
# hombros que la cintura cuando la luz viene de arriba
GRADOS_LUZ_LATERAL = 45.0
INTENSIDAD_LUZ_VERTICAL = 0.16


def envolver_en_torso(parche_rgba, xmin, ymin, info, arco=ARCO_FRENTE, intensidad_luz=INTENSIDAD_LUZ_3D):
    """Devuelve el parche con la tela envuelta en el torso y la luz según su curva."""
    if parche_rgba is None or info is None:
        return parche_rgba
    alto, ancho = parche_rgba.shape[:2]
    tela = parche_rgba[:, :, 3] > 40
    if tela.sum() < 100:
        return parche_rgba

    p_neck = np.asarray(info["p_neck_base"], np.float32) - np.array([xmin, ymin], np.float32)
    u_torso = np.asarray(info["u_torso"], np.float32)
    d_torso = float(info["dist_torso"])
    pendiente = float(u_torso[0] / u_torso[1]) if abs(u_torso[1]) > 1e-3 else 0.0

    # Filas del torso: desde un poco debajo de los hombros (arriba están las mangas,
    # que tienen su propia forma) con una transición suave
    y_inicio = p_neck[1] + d_torso * 0.12
    y_pleno = p_neck[1] + d_torso * 0.32
    filas = np.arange(max(0, int(y_inicio)), alto)
    if len(filas) < 4:
        return parche_rgba
    centros = p_neck[0] + (filas - p_neck[1]) * pendiente
    izq, der, ok = _bordes_desde_centro(tela[filas], centros)
    ok &= (der - izq) > 8
    if ok.sum() < 4:
        return parche_rgba
    # Bordes suaves de fila a fila: si cada fila se envolviera con bordes distintos,
    # las letras de un estampado se cortarían en franjas
    medio_izq, medio_der = centros - izq, der - centros
    # Donde empiezan las mangas la fila es mucho más ancha: se envuelve sólo el torso
    tope = float(np.percentile(np.minimum(medio_izq, medio_der)[ok], 60)) * 1.15
    medio_izq, medio_der = np.minimum(medio_izq, tope), np.minimum(medio_der, tope)
    ventana = max(5, int(d_torso * 0.10))
    medio_izq, medio_der = _suavizar(medio_izq, ok, ventana), _suavizar(medio_der, ok, ventana)
    if medio_izq is None or medio_der is None:
        return parche_rgba
    izq, der = centros - medio_izq, centros + medio_der
    peso = np.clip((filas - y_inicio) / max(1.0, y_pleno - y_inicio), 0.0, 1.0)

    # Cilindro: posición en pantalla X = sin(phi + giro) para la tela en el ángulo phi
    giro = math.radians(float(np.clip(info.get("giro", 0.0), -0.7, 0.7)) * GRADOS_POR_GIRO)
    a = math.radians(arco)
    x_min = math.sin(max(-a + giro, -math.radians(89)))
    x_max = math.sin(min(a + giro, math.radians(89)))

    # Sólo se trabaja en el recuadro del torso (filas y columnas que se envuelven)
    c0 = int(max(0, np.floor(izq[ok].min())))
    c1 = int(min(ancho, np.ceil(der[ok].max()) + 1))
    f0 = int(filas[0])
    if c1 - c0 < 4:
        return parche_rgba
    xs = np.arange(c0, c1, dtype=np.float32)[None, :]
    l, r = izq[:, None], der[:, None]
    t = np.clip((xs - l) / np.maximum(1.0, r - l), 0.0, 1.0)   # 0..1 a lo ancho de la tela visible
    phi = np.arcsin(np.clip(x_min + t * (x_max - x_min), -1.0, 1.0)) - giro  # ángulo de la tela que se ve
    origen = l + (phi + a) / (2.0 * a) * (r - l)                # misma tela, en la foto plana
    w = (peso * ok)[:, None]
    dentro = (xs >= l) & (xs <= r)
    map_x = np.where(dentro, xs + w * (origen - xs), xs).astype(np.float32)
    map_y = np.repeat(filas.astype(np.float32)[:, None], c1 - c0, axis=1)
    resultado = parche_rgba.copy()
    zona = cv2.remap(parche_rgba, map_x, map_y, interpolation=cv2.INTER_LINEAR,
                     borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))

    if intensidad_luz > 0:
        # Luz: proporcional a cuánto mira la tela hacia la fuente de luz
        luz_lateral, luz_vertical = info.get("luz", (0.0, 0.0))
        angulo_luz = math.radians(float(luz_lateral) * GRADOS_LUZ_LATERAL)
        mirada = np.cos(phi + giro - angulo_luz).clip(0.0, 1.0) ** 0.6
        altura = ((filas - y_inicio) / max(1.0, float(filas[-1]) - y_inicio))[:, None]  # 0 arriba, 1 abajo
        vertical = 1.0 + INTENSIDAD_LUZ_VERTICAL * float(luz_vertical) * (0.5 - altura)
        factor = np.where(dentro, (1.0 - intensidad_luz * w * (1.0 - mirada)) * (1.0 + (vertical - 1.0) * w),
                          1.0).astype(np.float32)
        zona[:, :, :3] = cv2.multiply(np.ascontiguousarray(zona[:, :, :3]), cv2.merge([factor, factor, factor]),
                                      dtype=cv2.CV_8U)
    resultado[f0:f0 + len(filas), c0:c1] = zona
    return resultado
