# ==========================================================
# PROYECTO: PROBADOR VIRTUAL INTELIGENTE
# HERRAMIENTA DE PRUEBA: SILUETAS SINTÉTICAS DE DISTINTAS FIGURAS
# ==========================================================
# Genera personas "de mentira" (silueta + puntos corporales) con
# distintas proporciones de pecho, cintura y cadera, para probar
# el calce de la prenda sin necesidad de una cámara.

import math
import numpy as np
import cv2

# Medidas relativas al ancho entre hombros (articulaciones).
# Cada valor es el ANCHO TOTAL de la silueta a esa altura.
FIGURAS_PRUEBA = {
    "rectangulo":          {"pecho": 0.96, "cintura": 0.90, "cadera": 0.98, "brazo": 0.22},
    "reloj_de_arena":      {"pecho": 1.00, "cintura": 0.70, "cadera": 1.02, "brazo": 0.22},
    "pera":                {"pecho": 0.86, "cintura": 0.74, "cadera": 1.22, "brazo": 0.22},
    "triangulo_invertido": {"pecho": 1.08, "cintura": 0.84, "cadera": 0.84, "brazo": 0.24},
    "ovalada":             {"pecho": 1.08, "cintura": 1.18, "cadera": 1.10, "brazo": 0.30},
}


class _LM:
    def __init__(self, x_px, y_px, z, ancho, alto, vis=0.99):
        self.x = x_px / float(ancho)
        self.y = y_px / float(alto)
        self.z = z
        self.visibility = vis


def crear_persona_sintetica(figura, ancho=1280, alto=720, cx=640, cy=200,
                            ancho_hombros=220, largo_torso=280,
                            angulo_brazos_deg=12.0, color_piel=(150, 175, 215),
                            angulo_brazo_izq_deg=None, angulo_brazo_der_deg=None,
                            inclinacion_cadera_deg=0.0, giro=0.0):
    """
    Devuelve (frame_bgr, mascara_float, landmarks, puntos) de una persona sintética
    vista de frente, con la figura indicada (ver FIGURAS_PRUEBA o un dict propio).

    Opciones de movimiento:
      angulo_brazo_izq_deg / angulo_brazo_der_deg: 0 = brazo abajo, 90 = horizontal, 150 = arriba.
      inclinacion_cadera_deg: inclina la línea de caderas (la izquierda de pantalla baja si es > 0).
      giro: torso girado (-1 a 1); > 0 aleja el lado derecho de la pantalla (cambia la Z
            de hombros y caderas y achica ese lado de la silueta).
    """
    f = FIGURAS_PRUEBA[figura] if isinstance(figura, str) else figura
    d = float(ancho_hombros)

    p_neck = np.array([cx, cy], dtype=np.float32)
    p_sh_l = p_neck + np.array([-d / 2, 0], dtype=np.float32)   # izquierda de pantalla
    p_sh_r = p_neck + np.array([d / 2, 0], dtype=np.float32)
    p_hip_mid = p_neck + np.array([0, largo_torso], dtype=np.float32)
    # Articulaciones de cadera: un poco más adentro que el borde de la silueta
    medio_cadera_art = d * f["cadera"] * 0.30
    p_hip_l = p_hip_mid + np.array([-medio_cadera_art, 0], dtype=np.float32)
    p_hip_r = p_hip_mid + np.array([medio_cadera_art, 0], dtype=np.float32)

    # Inclinación de la cadera: rota los puntos de cadera alrededor del centro
    def rotar_cadera(p):
        ang = math.radians(-inclinacion_cadera_deg)
        rel = p - p_hip_mid
        c, s_ = math.cos(ang), math.sin(ang)
        return p_hip_mid + np.array([c * rel[0] - s_ * rel[1], s_ * rel[0] + c * rel[1]], dtype=np.float32)
    p_hip_l, p_hip_r = rotar_cadera(p_hip_l), rotar_cadera(p_hip_r)

    # Brazos
    largo_brazo = d * 0.72
    a_l = math.radians(angulo_brazos_deg if angulo_brazo_izq_deg is None else angulo_brazo_izq_deg)
    a_r = math.radians(angulo_brazos_deg if angulo_brazo_der_deg is None else angulo_brazo_der_deg)
    dir_l = np.array([-math.sin(a_l), math.cos(a_l)], dtype=np.float32)
    dir_r = np.array([math.sin(a_r), math.cos(a_r)], dtype=np.float32)
    p_elb_l = p_sh_l + dir_l * largo_brazo
    p_wri_l = p_elb_l + dir_l * largo_brazo * 0.95
    p_elb_r = p_sh_r + dir_r * largo_brazo
    p_wri_r = p_elb_r + dir_r * largo_brazo * 0.95

    # --- Silueta: torso por niveles (cuello, hombros, pecho, cintura, cadera, muslos)
    niveles = [
        (-0.10, 0.30), (-0.04, 0.60), (0.04, 1.02), (0.30, f["pecho"]), (0.62, f["cintura"]),
        (1.00, f["cadera"]), (1.40, f["cadera"] * 0.92),
    ]
    izq, der = [], []
    for t, w in niveles:
        y = cy + t * largo_torso
        w_l = w * d / 2 * (1.0 + 0.30 * giro)   # el lado que se acerca se ve más ancho
        w_r = w * d / 2 * (1.0 - 0.30 * giro)
        pl = np.array([cx - w_l, y], dtype=np.float32)
        pr = np.array([cx + w_r, y], dtype=np.float32)
        if t >= 0.6 and inclinacion_cadera_deg:
            mezcla = min(1.0, (t - 0.6) / 0.4)
            pl = pl * (1 - mezcla) + rotar_cadera(pl) * mezcla
            pr = pr * (1 - mezcla) + rotar_cadera(pr) * mezcla
        izq.append(tuple(pl))
        der.append(tuple(pr))
    poly = np.array(izq + der[::-1], dtype=np.int32)

    mask = np.zeros((alto, ancho), dtype=np.uint8)
    cv2.fillPoly(mask, [poly], 255)
    # Cuello y cabeza
    cv2.rectangle(mask, (int(cx - d * 0.13), int(cy - d * 0.35)), (int(cx + d * 0.13), int(cy + 5)), 255, -1)
    cv2.ellipse(mask, (cx, int(cy - d * 0.55)), (int(d * 0.21), int(d * 0.27)), 0, 0, 360, 255, -1)
    # Brazos (cápsulas)
    grosor = max(4, int(d * f["brazo"]))
    for a_, b_ in [(p_sh_l, p_elb_l), (p_elb_l, p_wri_l), (p_sh_r, p_elb_r), (p_elb_r, p_wri_r)]:
        cv2.line(mask, tuple(np.int32(a_)), tuple(np.int32(b_)), 255, grosor)
    mask = cv2.GaussianBlur(mask, (5, 5), 0)

    # --- Imagen: fondo gris + silueta color piel (sirve para ver el calce)
    frame = np.full((alto, ancho, 3), (236, 236, 240), dtype=np.uint8)
    m3 = (mask.astype(np.float32) / 255.0)[:, :, None]
    piel = np.full_like(frame, color_piel)
    frame = (frame * (1 - m3) + piel * m3).astype(np.uint8)

    # --- Landmarks estilo MediaPipe (vista espejo: el LM11 queda a la derecha de pantalla)
    z_sh = -0.5
    z_sh_izq_pantalla = z_sh - 0.12 * giro   # giro > 0: el lado izquierdo se acerca
    z_sh_der_pantalla = z_sh + 0.12 * giro
    lms = [_LM(cx, cy - d * 0.55, z_sh, ancho, alto)] * 33
    lms[0] = _LM(cx, cy - d * 0.55, z_sh, ancho, alto)
    lms[11] = _LM(*p_sh_r, z_sh_der_pantalla, ancho, alto)
    lms[12] = _LM(*p_sh_l, z_sh_izq_pantalla, ancho, alto)
    lms[13] = _LM(*p_elb_r, z_sh, ancho, alto)
    lms[14] = _LM(*p_elb_l, z_sh, ancho, alto)
    lms[15] = _LM(*p_wri_r, -0.4, ancho, alto)
    lms[16] = _LM(*p_wri_l, -0.4, ancho, alto)
    lms[23] = _LM(*p_hip_r, 0.12 * giro, ancho, alto)
    lms[24] = _LM(*p_hip_l, -0.12 * giro, ancho, alto)

    puntos = {
        "nose": np.array([cx, cy - d * 0.55], dtype=np.float32),
        "sh_left": p_sh_r, "sh_right": p_sh_l,
        "elb_left": p_elb_r, "elb_right": p_elb_l,
        "wri_left": p_wri_r, "wri_right": p_wri_l,
        "hip_left": p_hip_r, "hip_right": p_hip_l,
    }
    z = {k: 0.0 for k in puntos}
    z["sh_left"], z["sh_right"] = z_sh_der_pantalla, z_sh_izq_pantalla
    z["hip_left"], z["hip_right"] = 0.12 * giro, -0.12 * giro
    puntos_z = z
    crear_persona_sintetica.ultima_z = puntos_z  # profundidad Z para las pruebas
    return frame, mask.astype(np.float32) / 255.0, lms, puntos


def persona_cerca_con_brazos_arriba(ancho_hombros=220.0, color_piel=(150, 175, 215)):
    """
    Persona cerca de la cámara con los brazos levantados: la cara se ve grande y los
    hombros (como los marca MediaPipe) suben hacia el mentón. Incluye orejas y boca.
    Devuelve (frame, mascara, puntos); la Z queda en crear_persona_sintetica.ultima_z y
    la parte de abajo de la cara (para medir si la tapa algo) en .cara.
    """
    d = float(ancho_hombros)
    cx, cy = 640, 260
    frame, mascara, _, puntos = crear_persona_sintetica("rectangulo", ancho_hombros=d, cy=cy,
                                                        angulo_brazos_deg=150.0, color_piel=color_piel)
    centro = (cx, int(cy - d * 0.45))
    ejes = (int(d * 0.34), int(d * 0.40))
    m = (mascara * 255).astype(np.uint8)
    cv2.ellipse(m, centro, ejes, 0, 0, 360, 255, -1)
    frame = frame.copy()
    cara_color = tuple(int(c * 1.04) for c in color_piel)   # la cara, un poco distinta del cuello
    cv2.ellipse(frame, centro, ejes, 0, 0, 360, cara_color, -1)
    nariz = np.array([cx, cy - d * 0.45], np.float32)
    puntos = dict(puntos)
    puntos["nose"] = nariz
    puntos["ear_left"] = nariz + np.float32([d * 0.34, -d * 0.02])
    puntos["ear_right"] = nariz + np.float32([-d * 0.34, -d * 0.02])
    puntos["mouth_left"] = nariz + np.float32([d * 0.08, d * 0.17])
    puntos["mouth_right"] = nariz + np.float32([-d * 0.08, d * 0.17])
    for k in ("sh_left", "sh_right"):          # los hombros suben con los brazos
        puntos[k] = puntos[k] + np.float32([0, -d * 0.16])
    # Parte de abajo de la cara: de la boca al mentón
    zona = np.zeros(m.shape, np.uint8)
    cv2.ellipse(zona, centro, (ejes[0] - 3, ejes[1] - 3), 0, 0, 360, 255, -1)
    zona[: int(nariz[1] + d * 0.12)] = 0
    persona_cerca_con_brazos_arriba.cara = zona > 0
    # Alrededor del mentón (donde va el cuello de la prenda): una franja debajo de la cara
    # y a sus costados, entre los hombros
    alrededor = np.zeros(m.shape, np.uint8)
    menton_y = int(centro[1] + ejes[1])
    cv2.rectangle(alrededor, (int(cx - d * 0.40), menton_y - int(d * 0.06)),
                  (int(cx + d * 0.40), menton_y + int(d * 0.08)), 255, -1)
    cv2.ellipse(alrededor, centro, (ejes[0] + 2, ejes[1] + 2), 0, 0, 360, 0, -1)
    persona_cerca_con_brazos_arriba.alrededor_del_menton = alrededor > 0
    return frame, m.astype(np.float32) / 255.0, puntos


def cruzar_brazos(frame, mascara, puntos, z, color_piel, largo_torso=280, altura_codos=0.42):
    """
    Agrega a una persona sintética de frente los brazos cruzados delante del torso: los
    codos a los costados y las muñecas cruzadas, más cerca de la cámara que los hombros.
    Devuelve (frame, mascara, puntos, z) nuevos y los segmentos de los antebrazos.
    """
    sh_izq, sh_der = puntos["sh_right"], puntos["sh_left"]   # izquierda y derecha de pantalla
    d = float(np.linalg.norm(sh_der - sh_izq))
    L = float(largo_torso)
    codo_izq = sh_izq + np.float32([d * 0.05, L * altura_codos])
    codo_der = sh_der + np.float32([-d * 0.05, L * altura_codos])
    muneca_izq = codo_der + np.float32([-d * 0.10, -L * 0.08])   # el antebrazo izquierdo cruza a la derecha
    muneca_der = codo_izq + np.float32([d * 0.10, -L * 0.14])
    p = dict(puntos)
    p.update({"elb_right": codo_izq, "wri_right": muneca_izq, "elb_left": codo_der, "wri_left": muneca_der})
    zz = dict(z)
    zz.update({"wri_left": -0.95, "wri_right": -0.95, "elb_left": -0.6, "elb_right": -0.6})
    frame = frame.copy()
    m = (mascara * 255).astype(np.uint8)
    grosor = int(d * 0.22)
    for a, b in ((sh_izq, codo_izq), (codo_izq, muneca_izq), (sh_der, codo_der), (codo_der, muneca_der)):
        cv2.line(frame, tuple(np.int32(a)), tuple(np.int32(b)), tuple(int(c) for c in color_piel), grosor)
        cv2.line(m, tuple(np.int32(a)), tuple(np.int32(b)), 255, grosor)
    return frame, m.astype(np.float32) / 255.0, p, zz, [(codo_izq, muneca_izq), (codo_der, muneca_der)]


def crear_persona_de_perfil(ancho=1280, alto=720, cx=640, cy=200, largo_torso=280,
                            mira_a_la_derecha=True, angulo_brazo_deg=8.0, color_piel=(150, 175, 215)):
    """
    Devuelve (frame_bgr, mascara_float, landmarks, puntos) de una persona sintética de
    PERFIL: los hombros casi se superponen, el pecho sobresale hacia donde mira y el
    brazo del lado de la cámara cuelga sobre el torso. La Z queda en .ultima_z.
    angulo_brazo_deg: 0 = brazo colgando, > 0 = hacia adelante.
    """
    L = float(largo_torso)
    adelante = 1.0 if mira_a_la_derecha else -1.0
    p_neck = np.array([cx, cy], dtype=np.float32)
    # Hombros: casi en el mismo lugar (el de atrás un poco corrido y más lejos)
    p_sh_cerca = p_neck + np.array([adelante * L * 0.02, 0], dtype=np.float32)
    p_sh_lejos = p_neck - np.array([adelante * L * 0.05, 0], dtype=np.float32)
    p_hip_cerca = p_neck + np.array([adelante * L * 0.01, L], dtype=np.float32)
    p_hip_lejos = p_neck + np.array([-adelante * L * 0.03, L], dtype=np.float32)

    # Brazo del lado de la cámara: colgando sobre el costado del torso
    a = math.radians(angulo_brazo_deg)
    direccion = np.array([adelante * math.sin(a), math.cos(a)], dtype=np.float32)
    largo_brazo = L * 0.56
    p_elb = p_sh_cerca + direccion * largo_brazo
    p_wri = p_elb + direccion * largo_brazo * 0.95

    # Silueta de costado: espalda (detrás) y pecho / panza (adelante), por niveles
    niveles = [(-0.06, 0.10, 0.12), (0.0, 0.20, 0.22), (0.25, 0.22, 0.30), (0.45, 0.20, 0.26),
               (0.65, 0.20, 0.22), (1.00, 0.24, 0.22), (1.40, 0.20, 0.20)]
    frente_pts, espalda_pts = [], []
    for t, atras, adel in niveles:
        y = cy + t * L
        frente_pts.append((cx + adelante * adel * L, y))
        espalda_pts.append((cx - adelante * atras * L, y))
    poly = np.array(frente_pts + espalda_pts[::-1], dtype=np.int32)
    mask = np.zeros((alto, ancho), dtype=np.uint8)
    cv2.fillPoly(mask, [poly], 255)
    # Cuello y cabeza (la cara mira hacia adelante)
    cv2.rectangle(mask, (int(cx - L * 0.07), int(cy - L * 0.25)), (int(cx + L * 0.07), int(cy + 5)), 255, -1)
    p_nariz = np.array([cx + adelante * L * 0.17, cy - L * 0.40], dtype=np.float32)
    cv2.ellipse(mask, (cx + int(adelante * L * 0.04), int(cy - L * 0.40)), (int(L * 0.15), int(L * 0.19)),
                0, 0, 360, 255, -1)
    grosor = max(4, int(L * 0.13))
    for a_, b_ in [(p_sh_cerca, p_elb), (p_elb, p_wri)]:
        cv2.line(mask, tuple(np.int32(a_)), tuple(np.int32(b_)), 255, grosor)
    mask = cv2.GaussianBlur(mask, (5, 5), 0)

    frame = np.full((alto, ancho, 3), (236, 236, 240), dtype=np.uint8)
    m3 = (mask.astype(np.float32) / 255.0)[:, :, None]
    frame = (frame * (1 - m3) + np.full_like(frame, color_piel) * m3).astype(np.uint8)
    # El brazo un poco más oscuro que el torso (como en la cámara), para verlo en las imágenes
    brazo = np.zeros((alto, ancho), dtype=np.uint8)
    for a_, b_ in [(p_sh_cerca, p_elb), (p_elb, p_wri)]:
        cv2.line(brazo, tuple(np.int32(a_)), tuple(np.int32(b_)), 255, grosor - 4)
    frame[brazo > 0] = (frame[brazo > 0].astype(np.float32) * 0.86).astype(np.uint8)

    # "sh_left" es el hombro del lado de la cámara y "sh_right" el de atrás: para la vista
    # de costado lo que importa es cuál está más cerca (Z más chico).
    puntos = {
        "nose": p_nariz,
        "sh_left": p_sh_cerca, "sh_right": p_sh_lejos,
        "elb_left": p_elb, "elb_right": p_sh_lejos + np.array([0, largo_brazo], dtype=np.float32),
        "wri_left": p_wri, "wri_right": p_sh_lejos + np.array([0, largo_brazo * 1.95], dtype=np.float32),
        "hip_left": p_hip_cerca, "hip_right": p_hip_lejos,
    }
    z = {k: 0.0 for k in puntos}
    z.update({"sh_left": -0.45, "sh_right": -0.15, "elb_left": -0.45, "elb_right": -0.10,
              "wri_left": -0.45, "wri_right": -0.10, "hip_left": -0.10, "hip_right": 0.10})
    lms = [_LM(*p_nariz, -0.5, ancho, alto)] * 33
    for indice, clave in ((11, "sh_left"), (12, "sh_right"), (13, "elb_left"), (14, "elb_right"),
                          (15, "wri_left"), (16, "wri_right"), (23, "hip_left"), (24, "hip_right")):
        lms[indice] = _LM(*puntos[clave], z[clave], ancho, alto)
    crear_persona_de_perfil.ultima_z = z
    return frame, mask.astype(np.float32) / 255.0, lms, puntos


def poner_de_espaldas(puntos, z=None):
    """
    Convierte los puntos de una persona de frente en los de una persona DE ESPALDAS:
    el hombro izquierdo real queda a la izquierda de la pantalla (orden invertido)
    y la cara no se ve (nariz y orejas con visibilidad baja).
    Devuelve (puntos, z, visibilidades).
    """
    intercambio = [("sh_left", "sh_right"), ("elb_left", "elb_right"),
                   ("wri_left", "wri_right"), ("hip_left", "hip_right")]
    p = dict(puntos)
    zz = dict(z or {k: 0.0 for k in puntos})
    for a, b in intercambio:
        p[a], p[b] = puntos[b], puntos[a]
        zz[a], zz[b] = zz.get(b, 0.0), zz.get(a, 0.0)
    vis = {k: 0.99 for k in p}
    vis.update({"nose": 0.05, "ear_left": 0.10, "ear_right": 0.10})
    return p, zz, vis
