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


def _puntos_sin_mangas_desde_contorno(alpha, pts, xmin, xmax, ymin, ymax):
    """
    Prenda sin mangas: apoya los puntos en el contorno REAL de la foto (no en porcentajes
    fijos), así la tira del cuello queda medida. Si hay algo que cae más abajo del ruedo
    (un pañuelo), agrega 'ruedo_cuerpo': dónde termina de verdad el cuerpo de la prenda.
    """
    gw = float(max(1, xmax - xmin))
    margen = gw * 0.015

    anchos = (alpha > 25).sum(axis=1)
    filas_cuerpo = np.where(anchos >= anchos.max() * 0.5)[0]
    y_cuerpo = int(filas_cuerpo[-1]) if len(filas_cuerpo) else ymax
    gh = float(max(1, y_cuerpo - ymin))

    def borde(y):
        y = int(np.clip(y, ymin, ymax))
        xs = np.where(alpha[y, :] > 25)[0]
        return (float(xs[0]) - margen, float(xs[-1]) + margen) if len(xs) else (float(xmin), float(xmax))

    izq, der = borde(ymin + gh * 0.02)
    pts["collar_top_l"], pts["collar_top_r"] = (izq, float(ymin)), (der, float(ymin))
    pts["collar_top_mid"] = ((izq + der) * 0.5, float(ymin))
    for clave, fraccion in (("shoulder", 0.20), ("armpit", 0.38), ("underbust", 0.50), ("waist", 0.65),
                            ("high_hip", 0.82)):
        izq, der = borde(ymin + gh * fraccion)
        pts[f"{clave}_l"], pts[f"{clave}_r"] = (izq, ymin + gh * fraccion), (der, ymin + gh * fraccion)
    izq, der = borde(y_cuerpo - gh * 0.01)
    pts["hem_l"], pts["hem_r"] = (izq, float(ymax)), (der, float(ymax))
    cx = (pts["armpit_l"][0] + pts["armpit_r"][0]) * 0.5
    pts["chest_mid"] = (cx, ymin + gh * 0.38)
    pts["torso_mid"] = (cx, ymin + gh * 0.65)
    pts["hem_mid"] = (cx, float(ymax))
    if ymax - y_cuerpo > gh * 0.05:
        pts["ruedo_cuerpo"] = (cx, float(y_cuerpo))
    return pts


def es_cuello_halter(puntos):
    """Top halter: arriba, la tela es mucho más angosta que el pecho (una tira que rodea el cuello)."""
    if not all(k in puntos for k in ("collar_top_l", "collar_top_r", "armpit_l", "armpit_r")):
        return False
    ancho_pecho = abs(float(puntos["armpit_r"][0]) - float(puntos["armpit_l"][0]))
    ancho_cuello = abs(float(puntos["collar_top_r"][0]) - float(puntos["collar_top_l"][0]))
    return ancho_pecho > 1.0 and ancho_cuello / ancho_pecho < 0.60


def es_manga_larga(puntos):
    """Manga larga: el puño cae bastante más abajo que la mitad entre el hombro y el ruedo."""
    if not all(k in puntos for k in ("shoulder_l", "sleeve_cuff_out_l", "hem_mid")):
        return False
    y_hombro = float(puntos["shoulder_l"][1])
    return float(puntos["sleeve_cuff_out_l"][1]) - y_hombro > (float(puntos["hem_mid"][1]) - y_hombro) * 0.60


def _puntos_manga_larga(alpha, pts, xmin, xmax, ymin, ymax):
    """
    Buzo o campera de frente: las mangas cuelgan pegadas al cuerpo y no se ve la axila. El
    costado del torso se toma del ruedo (cae casi recto) y la manga es lo que queda afuera.
    Devuelve los puntos, o None si la foto no tiene esa forma (por ejemplo, manga corta).
    """
    mask = alpha > 25
    gw, gh = float(xmax - xmin), float(ymax - ymin)
    # Manga larga: en la mitad de abajo hay filas con tela separada a los dos costados (las
    # mangas). En un top, cada fila es una sola pieza.
    cx = int((xmin + xmax) / 2)
    centro = np.where(mask[:, max(0, cx - 2):cx + 3].any(axis=1))[0]
    y_ruedo = int(centro[-1])
    limite_izq, limite_der = xmin + gw * 0.40, xmax - gw * 0.40
    con_mangas = 0
    bordes_torso = []
    for y in range(int(ymin + gh * 0.50), int(ymax)):
        tramos = _tramos(np.where(mask[y])[0])
        if tramos and tramos[0][1] < limite_izq and tramos[-1][0] > limite_der:
            con_mangas += 1
            if y < y_ruedo:
                bordes_torso += [t for t in tramos if t[0] <= cx <= t[1] and t[1] - t[0] < gw * 0.80]
    if con_mangas < gh * 0.03:
        return None

    # Costado del torso: donde se separa de las mangas o, si se tocan, el ruedo
    if len(bordes_torso) < gh * 0.03:
        for y in range(int(y_ruedo - gh * 0.05), y_ruedo - 1):
            bordes_torso += [t for t in _tramos(np.where(mask[y])[0]) if t[0] <= cx <= t[1]]
    if not bordes_torso:
        return None
    x_izq, x_der = float(np.median([t[0] for t in bordes_torso])), float(np.median([t[1] for t in bordes_torso]))
    if x_der - x_izq > gw * 0.80:
        return None
    ancho_torso = x_der - x_izq

    def arriba(x):
        ys = np.where(mask[:, int(np.clip(x, 0, mask.shape[1] - 1))])[0]
        return float(ys[0]) if len(ys) else float(ymin)

    y_hombro = max(arriba(x_izq), arriba(x_der))
    y_axila = y_hombro + (y_ruedo - y_hombro) * 0.28
    nuevos = dict(pts)

    def nivel(fraccion):
        return y_axila + (y_ruedo - y_axila) * fraccion

    for lado, x_torso in (("l", x_izq), ("r", x_der)):
        afuera = -1 if lado == "l" else 1
        visible = mask[:, :int(x_torso)] if lado == "l" else mask[:, int(x_torso) + 1:]
        desde = 0 if lado == "l" else int(x_torso) + 1
        filas = np.where(visible.any(axis=1))[0]
        y_puno = int(filas[-1])
        # Puño: unas filas arriba de su final, donde tiene el ancho completo
        y_medida = int(y_puno - gh * 0.02)
        # (sólo la pieza de más afuera: el ruedo puede asomar pasando el costado del torso)
        piezas = _tramos(np.where(visible[y_medida])[0] + desde)
        if not piezas:
            return None
        pieza = piezas[0] if lado == "l" else piezas[-1]
        puno_afuera, puno_adentro = (float(pieza[0]), float(pieza[1])) if lado == "l" else (float(pieza[1]), float(pieza[0]))
        y_codo = int(y_hombro + (y_puno - y_hombro) * 0.50)
        xs_codo = np.where(visible[y_codo])[0] + desde
        codo_afuera = float(xs_codo[0] if lado == "l" else xs_codo[-1]) if len(xs_codo) else puno_afuera
        x_manga = x_torso + afuera * gw * 0.10
        nuevos[f"shoulder_{lado}"] = (x_torso, arriba(x_torso))
        nuevos[f"sleeve_top_{lado}"] = (x_manga, arriba(x_manga))
        nuevos[f"bicep_out_{lado}"] = (codo_afuera, float(y_codo))
        nuevos[f"bicep_in_{lado}"] = ((x_torso + puno_adentro) * 0.5, float(y_codo))
        nuevos[f"sleeve_cuff_out_{lado}"] = (puno_afuera, float(y_puno))
        nuevos[f"sleeve_cuff_in_{lado}"] = (puno_adentro, float(y_puno))
        nuevos[f"armpit_{lado}"] = (x_torso, y_axila)
        nuevos[f"underbust_{lado}"] = (x_torso, nivel(0.25))
        nuevos[f"waist_{lado}"] = (x_torso, nivel(0.50))
        nuevos[f"high_hip_{lado}"] = (x_torso, nivel(0.78))
        nuevos[f"hem_{lado}"] = (x_torso, float(y_ruedo))

    # Cuello o capucha, medidos con el ancho del torso (no con el de toda la foto). La foto
    # tiene el cuello abierto: en el centro, lo primero que hay es el borde de adelante.
    y_escote = arriba(cx)
    paso = max(2.0, ancho_torso * 0.01)

    def borde_escote(lado):
        # Hacia el costado, el contorno sube: ahí termina el hueco del cuello
        x = float(cx)
        while abs(x - cx) < ancho_torso * 0.35:
            if arriba(x) < y_escote - gh * 0.015:
                return x
            x += lado * paso
        return cx + lado * ancho_torso * 0.20

    def union_capucha(lado, x_escote):
        # Una capucha sube de golpe desde el hombro: el cuello empieza donde el contorno se empina
        x, anterior = cx + lado * ancho_torso * 0.48, None
        while abs(x - cx) > abs(x_escote - cx):
            y = arriba(x)
            if anterior is not None and anterior - y > paso * 1.5:
                return float(x + lado * paso), anterior
            anterior = y
            x -= lado * paso
        x_cuello = x_escote + lado * paso * 2.0
        return float(x_cuello), arriba(x_cuello)

    for lado_txt, lado in (("l", -1), ("r", 1)):
        x_escote = borde_escote(lado)
        nuevos[f"collar_tip_{lado_txt}"] = (float(x_escote), arriba(x_escote))
        nuevos[f"collar_top_{lado_txt}"] = union_capucha(lado, x_escote)
    y_arriba = min(nuevos["collar_top_l"][1], nuevos["collar_top_r"][1], nuevos["collar_tip_l"][1], nuevos["collar_tip_r"][1])
    nuevos["collar_top_mid"] = (float(cx), float(y_arriba))
    nuevos["neck_v"] = (float(cx), y_escote)
    nuevos["chest_mid"] = (float(cx), y_axila)
    nuevos["torso_mid"] = (float(cx), nivel(0.50))
    nuevos["hem_mid"] = (float(cx), float(y_ruedo))
    return nuevos


def detectar_puntos_clave_prenda(img_rgba):
    """
    Analiza de forma automática cualquier prenda PNG con canal alfa y extrae
    sus 31 puntos anatómicos clave:
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

    # Con mangas, a la altura de los hombros la prenda es más ancha que en el torso;
    # un top halter o una musculosa es igual o más angosta arriba.
    tiene_mangas = True
    if len(xs_sh) > 0 and len(xs_torso) > 0:
        ancho_sh = xs_sh[-1] - xs_sh[0]
        ancho_torso = xs_torso[-1] - xs_torso[0]
        if ancho_sh < ancho_torso * 1.04:
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

    larga = _puntos_manga_larga(alpha, pts, xmin, xmax, ymin, ymax)
    if larga is not None:
        return larga, True
    if tiene_mangas:
        pts = _ajustar_puntos_al_contorno(alpha > 25, pts, xmin, xmax, ymin, ymax)
    else:
        pts = _puntos_sin_mangas_desde_contorno(alpha, pts, xmin, xmax, ymin, ymax)

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
        # (el torso es el tramo ancho: un pedacito suelto al lado del cuello no es la axila)
        if len(tramos) >= 2 and tramos[-1][0] - tramos[-2][1] >= 2 and tramos[-1][1] - tramos[-1][0] >= gw * 0.15:
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

    y_ruedo = ymax - max(2.0, gh * 0.03)   # un poco más arriba: las puntas del ruedo pueden ser redondeadas
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
