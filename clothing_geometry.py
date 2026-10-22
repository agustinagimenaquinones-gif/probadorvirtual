# ==========================================================
# PROYECTO: PROBADOR VIRTUAL INTELIGENTE
# MÓDULO: GEOMETRÍA Y PUNTOS CLAVE DE PRENDAS
# ==========================================================

import numpy as np
import cv2

# Triangulación anatómica estructurada:
# Separa mangas, cuello y torso para permitir movimiento independiente sin deformaciones cruzadas.
# Ahora incluye curvas intermedias: axila -> bajo busto -> cintura -> cadera alta -> ruedo,
# y mangas articuladas en el bíceps para evitar que se quiebren al mover los brazos.
TRIANGULOS_TORSO = [
    # Zona Cuello, Escote y Canesú superior
    ("collar_top_mid", "collar_top_l", "collar_tip_l"),
    ("collar_top_mid", "collar_top_r", "collar_tip_r"),
    ("collar_top_mid", "collar_tip_l", "neck_v"),
    ("collar_top_mid", "collar_tip_r", "neck_v"),
    ("collar_top_l", "shoulder_l", "collar_tip_l"),
    ("collar_top_r", "shoulder_r", "collar_tip_r"),
    ("collar_tip_l", "shoulder_l", "chest_mid"),
    ("collar_tip_r", "shoulder_r", "chest_mid"),
    ("collar_tip_l", "neck_v", "chest_mid"),
    ("collar_tip_r", "neck_v", "chest_mid"),

    # Torso Superior, Axilas y Pecho
    ("shoulder_l", "armpit_l", "chest_mid"),
    ("shoulder_r", "armpit_r", "chest_mid"),

    # Curvatura Bajo Busto (sigue la silueta entre axila y cintura)
    ("armpit_l", "underbust_l", "chest_mid"),
    ("armpit_r", "underbust_r", "chest_mid"),
    ("underbust_l", "waist_l", "chest_mid"),
    ("underbust_r", "waist_r", "chest_mid"),
    ("chest_mid", "waist_l", "torso_mid"),
    ("chest_mid", "waist_r", "torso_mid"),

    # Curvatura Cadera Alta (sigue la silueta entre cintura y ruedo)
    ("waist_l", "high_hip_l", "torso_mid"),
    ("waist_r", "high_hip_r", "torso_mid"),
    ("high_hip_l", "hem_l", "torso_mid"),
    ("high_hip_r", "hem_r", "torso_mid"),

    # Ruedo Inferior
    ("torso_mid", "hem_l", "hem_mid"),
    ("torso_mid", "hem_r", "hem_mid"),
]

TRIANGULOS_MANGAS = [
    # Manga Izquierda (articulada en bíceps para doblar de forma realista con el brazo)
    ("shoulder_l", "sleeve_top_l", "bicep_out_l"),
    ("shoulder_l", "bicep_out_l", "bicep_in_l"),
    ("shoulder_l", "bicep_in_l", "armpit_l"),
    ("bicep_out_l", "sleeve_cuff_out_l", "bicep_in_l"),
    ("bicep_in_l", "sleeve_cuff_out_l", "sleeve_cuff_in_l"),

    # Manga Derecha (articulada en bíceps para doblar de forma realista con el brazo)
    ("shoulder_r", "sleeve_top_r", "bicep_out_r"),
    ("shoulder_r", "bicep_out_r", "bicep_in_r"),
    ("shoulder_r", "bicep_in_r", "armpit_r"),
    ("bicep_out_r", "sleeve_cuff_out_r", "bicep_in_r"),
    ("bicep_in_r", "sleeve_cuff_out_r", "sleeve_cuff_in_r"),
]

TRIANGULOS_ESTRUCTURADOS = TRIANGULOS_TORSO + TRIANGULOS_MANGAS

def obtener_triangulos_prenda(tiene_mangas=True):
    """Retorna la lista de triángulos adecuada según la prenda tenga o no mangas."""
    if tiene_mangas:
        return TRIANGULOS_ESTRUCTURADOS
    return TRIANGULOS_TORSO


def detectar_puntos_clave_prenda(img_rgba):
    """
    Analiza de forma automática cualquier prenda PNG con canal alfa y extrae
    sus 23 puntos anatómicos clave:
    - Cuello: borde superior, base de cuello, puntas de cuello/escote.
    - Hombros: costura exterior.
    - Mangas: curvatura superior, puños exteriores e interiores.
    - Axilas y laterales del torso.
    - Pecho central (logotipos y botones).
    - Cintura y ruedo inferior.
    
    Retorna (puntos_clave_dict, tiene_mangas).
    """
    if img_rgba is None or img_rgba.shape[2] != 4:
        return None, False

    alpha = img_rgba[:, :, 3]
    h, w = alpha.shape
    pos = np.where(alpha > 25)
    if len(pos[0]) == 0:
        return None, False

    ymin, ymax = int(np.min(pos[0])), int(np.max(pos[0]))
    xmin, xmax = int(np.min(pos[1])), int(np.max(pos[1]))
    gw = float(max(1, xmax - xmin))
    gh = float(max(1, ymax - ymin))
    cx = (xmin + xmax) / 2.0

    # 1. Análisis del escote / cuello
    x_c1, x_c2 = int(cx - gw * 0.15), int(cx + gw * 0.15)
    top_y = []
    for x in range(x_c1, x_c2):
        ys = np.where(alpha[:, x] > 25)[0]
        if len(ys) > 0:
            top_y.append(ys[0])

    if len(top_y) > 0:
        collar_mid_y = float(np.min(top_y))
        neck_v_y = float(np.max(top_y))
    else:
        collar_mid_y = ymin + gh * 0.02
        neck_v_y = ymin + gh * 0.18

    # Si el escote es poco profundo, asignar valor proporcional
    if neck_v_y - collar_mid_y < gh * 0.05:
        neck_v_y = collar_mid_y + gh * 0.16

    # 2. Detección de mangas (relación de ancho hombros vs torso)
    y_sh = int(ymin + gh * 0.18)
    xs_sh = np.where(alpha[y_sh, :] > 25)[0]
    y_torso = int(ymin + gh * 0.55)
    xs_torso = np.where(alpha[y_torso, :] > 25)[0]

    tiene_mangas = True
    if len(xs_sh) > 0 and len(xs_torso) > 0:
        ancho_sh = xs_sh[-1] - xs_sh[0]
        ancho_torso = xs_torso[-1] - xs_torso[0]
        if ancho_sh < ancho_torso * 1.05 and (gw / gh) < 0.75:
            tiene_mangas = False

    pts = {
        "collar_top_mid": (cx, collar_mid_y),
        "collar_top_l": (cx - gw * 0.16, ymin + gh * 0.02),
        "collar_top_r": (cx + gw * 0.16, ymin + gh * 0.02),
        "collar_tip_l": (cx - gw * 0.13, neck_v_y * 0.85 + collar_mid_y * 0.15),
        "collar_tip_r": (cx + gw * 0.13, neck_v_y * 0.85 + collar_mid_y * 0.15),
        "neck_v": (cx, neck_v_y),
        "chest_mid": (cx, ymin + gh * 0.38),
        "torso_mid": (cx, ymin + gh * 0.65),
        "hem_mid": (cx, ymax),
    }

    if tiene_mangas:
        # Prenda con mangas (remera, chomba polo, camisa, buzo)
        pts.update({
            "shoulder_l": (xmin + gw * 0.19, ymin + gh * 0.10),
            "shoulder_r": (xmax - gw * 0.19, ymin + gh * 0.10),
            "sleeve_top_l": (xmin + gw * 0.05, ymin + gh * 0.22),
            "sleeve_top_r": (xmax - gw * 0.05, ymin + gh * 0.22),
            "bicep_out_l": (xmin + gw * 0.02, ymin + gh * 0.32),
            "bicep_out_r": (xmax - gw * 0.02, ymin + gh * 0.32),
            "bicep_in_l": (xmin + gw * 0.20, ymin + gh * 0.42),
            "bicep_in_r": (xmax - gw * 0.20, ymin + gh * 0.42),
            "sleeve_cuff_out_l": (xmin, ymin + gh * 0.42),
            "sleeve_cuff_out_r": (xmax, ymin + gh * 0.42),
            "sleeve_cuff_in_l": (xmin + gw * 0.16, ymin + gh * 0.46),
            "sleeve_cuff_in_r": (xmax - gw * 0.16, ymin + gh * 0.46),
            "armpit_l": (xmin + gw * 0.25, ymin + gh * 0.38),
            "armpit_r": (xmax - gw * 0.25, ymin + gh * 0.38),
            "underbust_l": (xmin + gw * 0.255, ymin + gh * 0.50),
            "underbust_r": (xmax - gw * 0.255, ymin + gh * 0.50),
            "waist_l": (xmin + gw * 0.26, ymin + gh * 0.65),
            "waist_r": (xmax - gw * 0.26, ymin + gh * 0.65),
            "high_hip_l": (xmin + gw * 0.255, ymin + gh * 0.82),
            "high_hip_r": (xmax - gw * 0.255, ymin + gh * 0.82),
            "hem_l": (xmin + gw * 0.25, ymax),
            "hem_r": (xmax - gw * 0.25, ymax),
        })
    else:
        # Prenda sin mangas (top halter, musculosa, strapless)
        pts.update({
            "shoulder_l": (cx - gw * 0.30, ymin + gh * 0.20),
            "shoulder_r": (cx + gw * 0.30, ymin + gh * 0.20),
            "sleeve_top_l": (cx - gw * 0.32, ymin + gh * 0.25),
            "sleeve_top_r": (cx + gw * 0.32, ymin + gh * 0.25),
            "bicep_out_l": (cx - gw * 0.33, ymin + gh * 0.30),
            "bicep_out_r": (cx + gw * 0.33, ymin + gh * 0.30),
            "bicep_in_l": (cx - gw * 0.35, ymin + gh * 0.35),
            "bicep_in_r": (cx + gw * 0.35, ymin + gh * 0.35),
            "sleeve_cuff_out_l": (cx - gw * 0.35, ymin + gh * 0.35),
            "sleeve_cuff_out_r": (cx + gw * 0.35, ymin + gh * 0.35),
            "sleeve_cuff_in_l": (cx - gw * 0.35, ymin + gh * 0.35),
            "sleeve_cuff_in_r": (cx + gw * 0.35, ymin + gh * 0.35),
            "armpit_l": (cx - gw * 0.38, ymin + gh * 0.38),
            "armpit_r": (cx + gw * 0.38, ymin + gh * 0.38),
            "underbust_l": (cx - gw * 0.37, ymin + gh * 0.50),
            "underbust_r": (cx + gw * 0.37, ymin + gh * 0.50),
            "waist_l": (cx - gw * 0.36, ymin + gh * 0.65),
            "waist_r": (cx + gw * 0.36, ymin + gh * 0.65),
            "high_hip_l": (cx - gw * 0.37, ymin + gh * 0.82),
            "high_hip_r": (cx + gw * 0.37, ymin + gh * 0.82),
            "hem_l": (cx - gw * 0.38, ymax),
            "hem_r": (cx + gw * 0.38, ymax),
        })

    if tiene_mangas:
        pts = _ajustar_puntos_al_contorno(alpha > 25, pts, xmin, xmax, ymin, ymax)

    return pts, tiene_mangas


# -------------------------------------------------------------------------
# AJUSTE FINO: PUNTOS SOBRE EL CONTORNO REAL DE LA PRENDA
# -------------------------------------------------------------------------
# Los porcentajes de arriba son una aproximación. Si un punto del borde queda
# "adentro" de la tela, la parte de tela que queda afuera de la malla se pierde
# (aparecen cortes y "pestañas" en axilas y hombros) y el borde de la prenda no
# coincide con el borde del cuerpo. Por eso buscamos cada punto sobre el
# contorno verdadero de la prenda.

def _tramos(xs):
    """Agrupa columnas consecutivas en tramos [(inicio, fin), ...]."""
    if len(xs) == 0:
        return []
    cortes = np.where(np.diff(xs) > 1)[0]
    inicios = np.concatenate(([xs[0]], xs[cortes + 1]))
    fines = np.concatenate((xs[cortes], [xs[-1]]))
    return list(zip(inicios.tolist(), fines.tolist()))


def _puntos_lado_izquierdo(mask, xmin, xmax, ymin, ymax):
    """
    Busca en la mitad izquierda de la imagen: axila, bajo busto, puño exterior e interior,
    bíceps, borde superior de la manga, hombro, costado a la cintura, cadera alta y ruedo.
    Devuelve un dict o None si la prenda no tiene la forma esperada.
    """
    gw, gh = float(xmax - xmin), float(ymax - ymin)
    cx = int((xmin + xmax) / 2)
    mitad = mask[:, :cx]

    # 1. Axila: primera fila (de arriba hacia abajo) donde manga y torso se separan
    axila = None
    for y in range(int(ymin + gh * 0.10), int(ymin + gh * 0.65)):
        tramos = _tramos(np.where(mitad[y])[0])
        if len(tramos) >= 2 and tramos[-1][0] - tramos[-2][1] >= 2:
            axila = (float(tramos[-1][0]), float(y))
            break
    if axila is None:
        return None

    def borde_torso(y):
        tramos = _tramos(np.where(mitad[int(y)])[0])
        return float(tramos[-1][0]) if tramos else None

    # 2. Puño exterior: el punto más a la izquierda de toda la prenda
    columnas = np.where(mitad.any(axis=0))[0]
    x_ext = int(columnas[0])
    ys_ext = np.where(mitad[:, x_ext])[0]
    puno_ext = (float(x_ext), float(np.mean(ys_ext)))

    # 3. Puño interior: el punto más bajo de la manga (a la izquierda de la axila)
    puno_int = None
    for y in range(int(ymax), int(axila[1]), -1):
        tramos = _tramos(np.where(mitad[y])[0])
        tramos_manga = [t for t in tramos[:-1] if t[1] < axila[0] - 1] if len(tramos) >= 2 else []
        if tramos_manga:
            puno_int = (float(tramos_manga[-1][1]), float(y))
            break
    if puno_int is None:
        return None

    # 4. Hombro y borde superior de la manga: sobre el contorno de arriba
    def borde_superior(x):
        ys = np.where(mask[:, int(x)])[0]
        return float(ys[0]) if len(ys) else None

    x_hombro = xmin + gw * 0.19
    y_hombro = borde_superior(x_hombro)
    x_manga = x_ext + (x_hombro - x_ext) * 0.35
    y_manga = borde_superior(x_manga)
    if y_hombro is None or y_manga is None:
        return None

    # 5. Costado: bajo busto, cintura, cadera alta y ruedo
    y_cintura = ymin + gh * 0.65
    x_cintura = borde_torso(y_cintura)

    y_underbust = ymin + gh * 0.50
    x_underbust = borde_torso(y_underbust)
    if x_underbust is None and x_cintura is not None:
        x_underbust = (axila[0] + x_cintura) * 0.5

    y_ruedo = ymax - 2
    x_ruedo = borde_torso(y_ruedo)

    y_high_hip = ymin + gh * 0.82
    x_high_hip = borde_torso(y_high_hip)
    if x_high_hip is None and x_cintura is not None and x_ruedo is not None:
        x_high_hip = (x_cintura + x_ruedo) * 0.5

    if x_cintura is None or x_ruedo is None or x_underbust is None or x_high_hip is None:
        return None

    # 6. Bíceps intermedio (outer e inner) para evitar quiebre de manga
    bicep_out = (float((puno_ext[0] + x_manga) * 0.5), float((puno_ext[1] + y_manga) * 0.5))
    bicep_in = (float((puno_int[0] + axila[0]) * 0.5), float((puno_int[1] + axila[1]) * 0.5))

    return {
        "armpit": axila,
        "underbust": (float(x_underbust), float(y_underbust)),
        "waist": (x_cintura, float(y_cintura)),
        "high_hip": (float(x_high_hip), float(y_high_hip)),
        "hem": (x_ruedo, float(ymax)),
        "sleeve_cuff_out": puno_ext,
        "sleeve_cuff_in": puno_int,
        "shoulder": (float(x_hombro), y_hombro),
        "sleeve_top": (float(x_manga), y_manga),
        "bicep_out": bicep_out,
        "bicep_in": bicep_in,
    }


def _ajustar_puntos_al_contorno(mask, pts, xmin, xmax, ymin, ymax):
    alto, ancho = mask.shape
    izquierda = _puntos_lado_izquierdo(mask, xmin, xmax, ymin, ymax)
    # El lado derecho se mide espejando la imagen
    espejo = mask[:, ::-1]
    derecha = _puntos_lado_izquierdo(espejo, ancho - 1 - xmax, ancho - 1 - xmin, ymin, ymax)
    if izquierda is None or derecha is None:
        return pts  # forma inesperada: se conservan los porcentajes

    nuevos = dict(pts)
    for nombre, (x, y) in izquierda.items():
        nuevos[f"{nombre}_l"] = (x, y)
    for nombre, (x, y) in derecha.items():
        nuevos[f"{nombre}_r"] = (ancho - 1 - x, y)

    # Control de sentido común: la axila debe quedar entre hombro y cintura,
    # y los puntos deben descender en orden natural
    for lado in ("l", "r"):
        sh_y = nuevos[f"shoulder_{lado}"][1]
        arm_y = nuevos[f"armpit_{lado}"][1]
        ub_y = nuevos[f"underbust_{lado}"][1]
        w_y = nuevos[f"waist_{lado}"][1]
        hh_y = nuevos[f"high_hip_{lado}"][1]
        h_y = nuevos[f"hem_{lado}"][1]
        if not (sh_y < arm_y < ub_y < w_y < hh_y < h_y):
            return pts
    return nuevos
