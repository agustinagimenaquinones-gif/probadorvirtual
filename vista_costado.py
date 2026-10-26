# ==========================================================
# PROYECTO: PROBADOR VIRTUAL INTELIGENTE
# MÓDULO: VISTA DE COSTADO (LA PRENDA CON LA PERSONA DE PERFIL)
# ==========================================================
# De perfil los hombros casi se superponen: la malla del frente se aplasta y la
# prenda se rompe. No hay foto de costado, así que se arma una a partir de lo que
# se sabe:
#
#   * La FORMA es la silueta real de la persona (la máscara de MediaPipe), desde la
#     línea de hombros hasta el ruedo. El largo y la manga son los mismos que usa la
#     malla de frente (pose_tracker.calcular_puntos_destino_malla), así la prenda no
#     cambia de largo al girar. El ancho de hombros es el que la persona tenía de
#     frente (de perfil no se puede medir).
#   * La TELA sale de la franja central de la espalda (sin logos ni botones, que de
#     costado no se ven): cada fila del cuerpo toma la fila de la prenda que le
#     corresponde, estirada de la espalda al pecho. Así se conservan el color, la
#     trama y el estampado (rayas, lunares, animal print). El ruedo queda parejo, al
#     mismo largo que de frente.
#   * La MANGA (si la prenda tiene) cubre el brazo del lado de la cámara, desde el
#     hombro hasta el mismo largo de manga que de frente, por delante del torso.
#   * El brazo que cuelga sobre el torso se ve por delante de la tela (si la prenda
#     no tiene mangas) o desde donde termina la manga.
#   * Volumen: el torso es redondo, así que la tela se oscurece hacia el pecho y la
#     espalda, donde "da la vuelta".

import numpy as np
import cv2

# Parte del ancho de la espalda de la prenda que se ve de costado (de la espalda al pecho)
ANCHO_FRANJA_ESPALDA = 0.55
# Grosor del brazo, en anchos de hombros de frente
GROSOR_BRAZO = 0.30
# Cuánto se oscurecen el pecho y la espalda por la curva del cuerpo (0 = nada)
INTENSIDAD_VOLUMEN_COSTADO = 0.22
# La tela arranca un poco por encima de la línea de hombros (fracción del torso)
INICIO_SOBRE_HOMBROS = 0.04
# Como la malla de frente: ruedo a 1,06 torsos y manga de 0,52 anchos de hombros
LARGO_HASTA_RUEDO = 1.06
LARGO_MANGA = 0.52


def _normal(v):
    v = np.asarray(v, np.float32)
    return v / max(1e-6, float(np.linalg.norm(v)))


def _medidas_prenda(src, tiene_mangas):
    """Ancho de hombros, altura de hombros, largo hasta el ruedo y manga (en la foto)."""
    sh_l, sh_r = np.float32(src["shoulder_l"]), np.float32(src["shoulder_r"])
    ancho = abs(float(sh_r[0] - sh_l[0]))
    y_hombros = float(sh_l[1] + sh_r[1]) * 0.5
    largo = float(src["hem_mid"][1]) - y_hombros
    manga = None
    if tiene_mangas:
        puno = (np.float32(src["sleeve_cuff_out_l"]) + np.float32(src["sleeve_cuff_in_l"])) * 0.5
        medio_ancho = float(np.linalg.norm(np.float32(src["bicep_out_l"]) - np.float32(src["bicep_in_l"]))) * 0.5
        manga = (sh_l, puno, medio_ancho)
    return ancho, (sh_l[0] + sh_r[0]) * 0.5, y_hombros, largo, manga


_telas_completas = {}


def _tela_completa(img_prenda):
    """
    La foto con sus huecos (fondo transparente, sisas, aberturas) rellenos con el color
    promedio de la tela de esa misma fila: de costado cualquier punto de la foto puede
    caer sobre el cuerpo. Se calcula una vez por imagen.
    """
    clave = id(img_prenda)
    if clave in _telas_completas and _telas_completas[clave][0] is img_prenda:
        return _telas_completas[clave][1]
    tela = img_prenda.copy()
    opaca = img_prenda[:, :, 3] > 200
    cuenta = opaca.sum(axis=1)
    suma = (img_prenda[:, :, :3].astype(np.float32) * opaca[:, :, None]).sum(axis=1)
    filas = np.flatnonzero(cuenta > 0)
    if len(filas):
        promedio = suma[filas] / cuenta[filas, None]
        cercana = filas[np.clip(np.searchsorted(filas, np.arange(len(cuenta))), 0, len(filas) - 1)]
        color_fila = promedio[np.searchsorted(filas, cercana)]
        tela[:, :, :3] = np.where(opaca[:, :, None], img_prenda[:, :, :3], color_fila[:, None, :].astype(np.uint8))
    if len(_telas_completas) > 32:
        _telas_completas.clear()
    _telas_completas[clave] = (img_prenda, tela)
    return tela


def _capsula(forma, p_a, p_b, grosor, offset):
    """Máscara de un segmento grueso (brazo) dentro del recuadro."""
    m = np.zeros(forma, np.uint8)
    a = tuple(np.int32(np.round(np.asarray(p_a, np.float32) - offset)))
    b = tuple(np.int32(np.round(np.asarray(p_b, np.float32) - offset)))
    cv2.line(m, a, b, 255, max(2, int(grosor)))
    return m > 0


def generar_vista_costado(img_prenda, src, tiene_mangas, info, mascara, holgura_talle=1.05):
    """
    Arma la prenda vista de costado sobre la silueta de la persona.
    img_prenda / src: la vista de espalda de la prenda (BGRA) y sus puntos de malla.
    holgura_talle: como en la malla de frente (los talles grandes son más largos).
    Devuelve (parche_bgra, xmin, ymin, xmax, ymax) en coordenadas del cuadro, o None.
    """
    if img_prenda is None or src is None or mascara is None or info is None:
        return None
    alto, ancho = mascara.shape[:2]
    d_torso = float(info["dist_torso"])
    d_frente = float(info.get("ancho_hombros_frente", d_torso * 0.75))
    ancho_g, cx_g, y_hombros_g, largo_g, manga = _medidas_prenda(src, tiene_mangas)
    if ancho_g < 5 or largo_g < 5 or d_torso < 10:
        return None
    largo = LARGO_HASTA_RUEDO * d_torso * (1.0 + (float(holgura_talle) - 1.05) * 0.6)
    t_inicio = -INICIO_SOBRE_HOMBROS * d_torso

    p0 = np.asarray(info["p_neck_base"], np.float32)
    u_t = _normal(info["u_torso"])
    u_q = np.float32([-u_t[1], u_t[0]])
    lado = info.get("lado_cercano", "l")
    p_sh, p_elb, p_wri = (np.asarray(info[f"p_{k}_{lado}"], np.float32) for k in ("sh", "elb", "wri"))

    # Recuadro: el torso hasta el ruedo y el brazo del lado de la cámara
    esquinas = [p0 + u_t * t + u_q * q for t in (t_inicio, largo) for q in (-0.9 * d_torso, 0.9 * d_torso)]
    esquinas += [p_sh, p_elb, p_wri]
    esquinas = np.array(esquinas, np.float32)
    x0, y0 = np.floor(esquinas.min(axis=0)).astype(int) - 4
    x1, y1 = np.ceil(esquinas.max(axis=0)).astype(int) + 4
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(ancho, x1), min(alto, y1)
    if x1 - x0 < 8 or y1 - y0 < 8:
        return None
    offset = np.float32([x0, y0])
    forma = (y1 - y0, x1 - x0)
    xs, ys = np.meshgrid(np.arange(x0, x1, dtype=np.float32), np.arange(y0, y1, dtype=np.float32))
    rel_x, rel_y = xs - p0[0], ys - p0[1]
    t = rel_x * u_t[0] + rel_y * u_t[1]
    q = rel_x * u_q[0] + rel_y * u_q[1]
    cuerpo = mascara[y0:y1, x0:x1] > 0.5

    # --- Torso: la silueta entre los hombros y el ruedo, sin el brazo que queda delante
    grosor_brazo = GROSOR_BRAZO * d_frente
    brazo = _capsula(forma, p_sh, p_elb, grosor_brazo, offset) | _capsula(forma, p_elb, p_wri, grosor_brazo, offset)
    torso = cuerpo & (t >= t_inicio) & (t <= largo)
    # Sólo la parte unida al centro del torso (no una mano o un objeto suelto)
    n, etiquetas = cv2.connectedComponents(torso.astype(np.uint8), connectivity=8)
    if n <= 1:
        return None
    centro = np.int32(np.round(p0 + u_t * (largo * 0.5) - offset))
    cx_l, cy_l = int(np.clip(centro[0], 0, forma[1] - 1)), int(np.clip(centro[1], 0, forma[0] - 1))
    etiqueta = etiquetas[cy_l, cx_l]
    if etiqueta == 0:
        conteo = np.bincount(etiquetas.ravel())
        conteo[0] = 0
        etiqueta = int(np.argmax(conteo))
    torso = etiquetas == etiqueta

    # Ancho del cuerpo en cada fila (de la espalda al pecho), suavizado entre filas
    filas = np.clip(np.round(t - t_inicio).astype(np.int32), 0, None)
    n_filas = int(filas[torso].max()) + 1
    q_min = np.full(n_filas, np.inf, np.float32)
    q_max = np.full(n_filas, -np.inf, np.float32)
    np.minimum.at(q_min, filas[torso], q[torso])
    np.maximum.at(q_max, filas[torso], q[torso])
    hay = np.isfinite(q_min)
    indices = np.arange(n_filas)
    q_min = np.interp(indices, indices[hay], q_min[hay]).astype(np.float32)
    q_max = np.interp(indices, indices[hay], q_max[hay]).astype(np.float32)
    k = max(3, int(d_torso * 0.03)) | 1
    q_min = cv2.GaussianBlur(q_min[:, None], (1, k), 0).ravel()
    q_max = cv2.GaussianBlur(q_max[:, None], (1, k), 0).ravel()
    filas_c = np.clip(filas, 0, n_filas - 1)
    s = np.clip((q - q_min[filas_c]) / np.maximum(1.0, q_max[filas_c] - q_min[filas_c]), 0.0, 1.0)

    # Tela: la franja central de la espalda, fila por fila
    medio_franja = ANCHO_FRANJA_ESPALDA * ancho_g * 0.5
    # (desde un poco más abajo de los hombros: arriba están el cuello y sus vivos)
    avance = np.clip(t / max(1.0, largo), 0.0, 1.0)
    map_x = (cx_g - medio_franja + s * 2.0 * medio_franja).astype(np.float32)
    map_y = (y_hombros_g + (0.10 + 0.90 * avance) * largo_g).astype(np.float32)
    tela_llena = _tela_completa(img_prenda)
    tela = cv2.remap(tela_llena, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    alfa = (torso & ~brazo).astype(np.float32)
    luz = 1.0 - INTENSIDAD_VOLUMEN_COSTADO * (1.0 - np.sin(np.pi * s))

    # --- Manga: sobre el brazo del lado de la cámara, por delante del torso
    if manga is not None:
        sh_g, puno_g, medio_ancho_g = manga
        largo_manga = LARGO_MANGA * d_frente
        u_a = _normal(p_elb - p_sh)
        u_b = np.float32([-u_a[1], u_a[0]])
        # Ancho de la manga: el mismo que en la malla de frente (con el brazo medido, si hay)
        holgura = float(holgura_talle)
        salida, adentro = d_frente * 0.08, d_frente * 0.26 * holgura / 1.05
        brazo_medido = (info.get("medidas") or {}).get("brazo")
        if brazo_medido:
            radio = float(brazo_medido) * 0.5
            salida = max(d_frente * 0.08, radio * 1.05 * holgura)
            adentro = max(d_frente * 0.17 * holgura, radio * 1.30 * holgura)
        medio = max((salida + adentro) * 0.5, grosor_brazo * 0.55)
        rx, ry = xs - p_sh[0], ys - p_sh[1]
        a = rx * u_a[0] + ry * u_a[1]
        b = rx * u_b[0] + ry * u_b[1]
        # (la manga no sube más que el torso: arriba de los hombros está el cuello)
        en_manga = (a >= -medio * 0.6) & (a <= largo_manga) & (np.abs(b) <= medio) & (t >= t_inicio)
        if np.any(en_manga):
            eje_g = puno_g - sh_g
            perp_g = _normal([-eje_g[1], eje_g[0]])
            fa = np.clip(a / max(1.0, largo_manga), 0.0, 1.0)
            fb = np.clip(b / medio, -1.0, 1.0)
            mx = (sh_g[0] + fa * eje_g[0] + fb * medio_ancho_g * perp_g[0]).astype(np.float32)
            my = (sh_g[1] + fa * eje_g[1] + fb * medio_ancho_g * perp_g[1]).astype(np.float32)
            tela_manga = cv2.remap(img_prenda, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT,
                                   borderValue=(0, 0, 0, 0))
            # Lo que no es tela en la foto (el hueco de la sisa) se completa con la tela del torso
            peso = (tela_manga[:, :, 3].astype(np.float32) / 255.0)[:, :, None]
            tela_manga = (tela_manga.astype(np.float32) * peso + tela.astype(np.float32) * (1.0 - peso)).astype(np.uint8)
            alfa_manga = np.where(en_manga, np.maximum(peso[:, :, 0], (np.abs(fb) < 0.8) & (fa > 0.08)), 0.0)
            alfa_manga *= np.clip((largo_manga - a) / 3.0, 0.0, 1.0)  # el puño, con borde suave
            tela = np.where((alfa_manga > 0.0)[:, :, None], tela_manga, tela)
            luz = np.where(alfa_manga > 0.0, 1.0 - INTENSIDAD_VOLUMEN_COSTADO * np.abs(fb) ** 2, luz)
            alfa = np.maximum(alfa, alfa_manga)

    if not np.any(alfa > 0.02):
        return None
    alfa = cv2.GaussianBlur(alfa, (0, 0), 1.0)
    parche = np.empty((forma[0], forma[1], 4), np.uint8)
    parche[:, :, :3] = np.clip(tela[:, :, :3].astype(np.float32) * luz[:, :, None], 0, 255).astype(np.uint8)
    parche[:, :, 3] = np.clip(alfa * 255.0, 0, 255).astype(np.uint8)
    return parche, int(x0), int(y0), int(x1), int(y1)
