# ==========================================================
# PROYECTO: PROBADOR VIRTUAL INTELIGENTE
# MÓDULO: DIRECCIÓN DE LA LUZ EN LA CÁMARA
# ==========================================================
# Para que la prenda parezca iluminada por la misma luz que la persona, se estima
# de dónde viene la luz mirando cómo cambia el brillo sobre su cara y su torso:
#
#   * Se ajusta un plano de brillo  L = a + b * lateral + c * vertical  sobre la
#     cara y el torso (en coordenadas del cuerpo, para que funcione aunque la
#     persona esté inclinada). La cara sirve mucho porque la piel es pareja.
#   * b / a dice cuánto más claro es un costado que el otro (luz de la izquierda o de
#     la derecha) y c / a si los hombros están más claros que la cintura (luz de arriba).
#   * La estimación se suaviza en el tiempo: la luz de una habitación no cambia de un
#     cuadro a otro, así la prenda no "titila" cuando la persona se mueve.

import numpy as np
import cv2

SUAVIZADO = 0.08        # peso de la estimación nueva en cada cuadro
GANANCIA = 1.6          # pasa la variación relativa de brillo a dirección (-1 a 1)
REDUCCION = 4           # se trabaja en una imagen 4 veces más chica


class EstimadorLuz:
    def __init__(self):
        self.reiniciar()

    def reiniciar(self):
        self.lateral = 0.0    # > 0: la luz viene del lado DERECHO de la pantalla
        self.vertical = 0.3   # > 0: la luz viene de arriba (lo normal en una habitación)
        self._iniciado = False

    def estimar(self, frame_bgr, info):
        """Actualiza y devuelve (lateral, vertical), cada uno entre -1 y 1."""
        medida = medir_direccion(frame_bgr, info)
        if medida is not None:
            peso = 1.0 if not self._iniciado else SUAVIZADO
            self.lateral += (medida[0] - self.lateral) * peso
            self.vertical += (medida[1] - self.vertical) * peso
            self._iniciado = True
        return self.lateral, self.vertical


def medir_direccion(frame_bgr, info):
    """Dirección de la luz en ESTE cuadro, o None si no se pudo medir."""
    if frame_bgr is None or info is None or info.get("mascara") is None:
        return None
    alto, ancho = frame_bgr.shape[:2]
    chico = cv2.resize(frame_bgr, (ancho // REDUCCION, alto // REDUCCION), interpolation=cv2.INTER_AREA)
    gris = cv2.GaussianBlur(cv2.cvtColor(chico, cv2.COLOR_BGR2GRAY).astype(np.float32), (5, 5), 0)
    mascara = cv2.resize(info["mascara"], (gris.shape[1], gris.shape[0]), interpolation=cv2.INTER_NEAREST) > 0.5

    d_sh = float(info["dist_sh"]) / REDUCCION
    d_torso = float(info["dist_torso"]) / REDUCCION
    cuello = np.asarray(info["p_neck_base"], np.float32) / REDUCCION
    u_torso = np.asarray(info["u_torso"], np.float32)
    u_lat = np.array([-u_torso[1], u_torso[0]], np.float32)
    if float(u_lat @ np.asarray(info["u_sh"], np.float32)) < 0:
        u_lat = -u_lat

    # Zona: cara (círculo alrededor de la nariz) + torso (entre hombros y cintura)
    zona = np.zeros(gris.shape, np.uint8)
    if "nose" in info:
        nariz = np.asarray(info["nose"], np.float32) / REDUCCION
        cv2.circle(zona, tuple(np.int32(nariz)), max(2, int(d_sh * 0.22)), 1, -1)
    medio = d_sh * 0.42
    esquinas = [cuello - u_lat * medio + u_torso * (d_torso * 0.10), cuello + u_lat * medio + u_torso * (d_torso * 0.10),
                cuello + u_lat * medio + u_torso * (d_torso * 0.75), cuello - u_lat * medio + u_torso * (d_torso * 0.75)]
    cv2.fillConvexPoly(zona, np.int32(esquinas), 1)
    sel = (zona > 0) & mascara & (gris > 12) & (gris < 245)  # sin negro puro ni zonas quemadas
    if sel.sum() < 40:
        return None

    ys, xs = np.nonzero(sel)
    rel = np.stack([xs - cuello[0], ys - cuello[1]], axis=1).astype(np.float32)
    lateral = rel @ u_lat / max(1.0, d_sh)        # -0.5..0.5 a lo ancho del torso
    vertical = rel @ u_torso / max(1.0, d_torso)  # 0 en el cuello, 1 en las caderas
    brillo = gris[ys, xs]
    a = np.stack([np.ones_like(lateral), lateral, vertical], axis=1)
    coef, *_ = np.linalg.lstsq(a, brillo, rcond=None)
    base = max(10.0, float(np.median(brillo)))
    return (float(np.clip(coef[1] / base * GANANCIA, -1.0, 1.0)),
            float(np.clip(-coef[2] / base * GANANCIA, -1.0, 1.0)))
