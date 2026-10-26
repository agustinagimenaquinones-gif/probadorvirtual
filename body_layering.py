# ==========================================================
# PROYECTO: PROBADOR VIRTUAL INTELIGENTE
# MÓDULO: INTEGRACIÓN VISUAL, COMPOSICIÓN POR CAPAS Y OCLUSIÓN
# ==========================================================

import numpy as np
import cv2

# Margen (en píxeles, para un ancho de hombros de 220 px) que la prenda puede
# sobresalir del borde del cuerpo según el talle. Las mangas tienen el doble.
MARGEN_SILUETA_TALLE = {"XS": 1, "S": 2, "M": 4, "L": 7, "XL": 10, "XXL": 13}

# Intensidad máxima de las sombras del cuerpo sobre la prenda (0 = nada, 1 = todo)
INTENSIDAD_SOMBRAS = 0.35

# Luz de la prenda: las fotos de producto son de estudio y, pegadas tal cual sobre la
# cámara, los colores oscuros (azul marino, negro) se ven apagados. Una curva gamma
# menor que 1 levanta las sombras de la tela sin quemar los blancos.
GAMMA_PRENDA = 0.80
# Cuánto toma la prenda del tono de la luz de la escena (0 = nada, 1 = todo)
TONO_ESCENA = 0.40

# Efecto de volumen: cuánto se oscurece la tela hacia los costados del cuerpo
INTENSIDAD_VOLUMEN = 0.10

# Sombra que la tela proyecta sobre el cuerpo en sus bordes (mangas, ruedo, cuello)
INTENSIDAD_SOMBRA_CONTACTO = 0.30


def recortar_prenda_a_silueta(parche_rgba, xmin, ymin, mascara, info_anatomica, talle="M", frame_bgr=None):
    """
    Recorta el canal alfa de la prenda para que no "flote" fuera del cuerpo.
    - Torso: puede sobresalir del borde de la silueta sólo el margen del talle.
    - Mangas: el doble del margen, pero sólo cerca de los brazos.
    Si la silueta parece poco confiable (cubre menos de la mitad de la prenda),
    no recorta nada, para no comerse la prenda por un error de la cámara.
    Devuelve el parche (una copia) con el alfa recortado.
    """
    if parche_rgba is None or mascara is None or info_anatomica is None:
        return parche_rgba
    alto_p, ancho_p = parche_rgba.shape[:2]
    m = mascara[ymin:ymin + alto_p, xmin:xmin + ancho_p]
    if m.shape[:2] != (alto_p, ancho_p):
        return parche_rgba
    cuerpo = (m > 0.5).astype(np.uint8) * 255

    alfa = parche_rgba[:, :, 3]
    tela = alfa > 20
    if not np.any(tela):
        return parche_rgba
    if float(np.mean(cuerpo[tela] > 0)) < 0.50:
        return parche_rgba  # silueta dudosa: mejor no recortar

    escala = float(info_anatomica["dist_sh"]) / 220.0
    margen = max(1, int(round(MARGEN_SILUETA_TALLE.get(str(talle).upper(), 4) * escala)))
    margen_manga = margen * 2 + 2

    def dilatar(img, px):
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * px + 1, 2 * px + 1))
        return cv2.dilate(img, k)

    permitido = dilatar(cuerpo, margen)
    cuerpo_margen_manga = dilatar(cuerpo, margen_manga)  # se usa en hombros y mangas

    # Hombros: la tela se apoya sobre ellos, así que arriba se acepta un margen mayor
    y_axilas = int(max(info_anatomica["p_sh_l"][1], info_anatomica["p_sh_r"][1]) - ymin
                   + float(info_anatomica["dist_torso"]) * 0.20)
    if y_axilas > 0:
        superior = cuerpo_margen_manga.copy()
        superior[min(alto_p, y_axilas):, :] = 0
        permitido = np.maximum(permitido, superior)

    # Zona de brazos: allí se acepta el margen más amplio de las mangas
    zona_brazos = np.zeros_like(cuerpo)
    grosor = max(6, int(float(info_anatomica["dist_sh"]) * 0.55))
    offset = np.array([xmin, ymin], dtype=np.float32)
    for a, b, cuff in (("p_sh_l", "p_elb_l", "u_cuff_l"), ("p_sh_r", "p_elb_r", "u_cuff_r")):
        p_a = info_anatomica[a] - offset
        eje = info_anatomica[b] - info_anatomica[a]
        largo = float(np.linalg.norm(eje))
        if largo < 1.0:
            continue
        # Sólo a lo largo de la manga (no hasta el codo) y sólo del lado de AFUERA
        # del brazo: así no se cuela tela en el hueco entre el brazo y el torso.
        p_b = p_a + eje / largo * min(largo, float(info_anatomica["dist_sh"]) * 0.62)
        afuera = -np.asarray(info_anatomica[cuff], dtype=np.float32)
        poligono = np.array([p_a - eje / largo * grosor * 0.3, p_b,
                             p_b + afuera * grosor, p_a + afuera * grosor - eje / largo * grosor * 0.3],
                            dtype=np.int32)
        cv2.fillConvexPoly(zona_brazos, poligono, 255)
    permitido = np.maximum(permitido, cv2.bitwise_and(cuerpo_margen_manga, zona_brazos))

    # Brazos por DELANTE de la prenda: más allá del largo de la manga, el brazo tapa
    # la tela del torso (por ejemplo, con los brazos colgando al costado del cuerpo).
    d_sh = float(info_anatomica["dist_sh"])
    medidas = info_anatomica.get("medidas") or {}
    grosor_brazo = int(max(6, (medidas.get("brazo") or d_sh * 0.22) * 0.85))
    brazos_delante = np.zeros_like(cuerpo)
    centro_brazos = np.zeros_like(cuerpo)
    grosor_centro = int(max(4, grosor_brazo * 0.5))
    for hombro, codo, muneca in (("p_sh_l", "p_elb_l", "p_wri_l"), ("p_sh_r", "p_elb_r", "p_wri_r")):
        p_sh, p_elb, p_wri = (info_anatomica[k] - offset for k in (hombro, codo, muneca))
        eje = p_elb - p_sh
        largo = float(np.linalg.norm(eje))
        if largo < 1.0:
            continue
        fin_manga = p_sh + eje / largo * min(largo, d_sh * 0.62)
        for a_, b_ in ((fin_manga, p_elb), (p_elb, p_wri)):
            cv2.line(brazos_delante, tuple(np.int32(a_)), tuple(np.int32(b_)), 255, grosor_brazo)
            cv2.line(centro_brazos, tuple(np.int32(a_)), tuple(np.int32(b_)), 255, grosor_centro)
    # Dentro de la franja del brazo, sólo es "brazo" lo que tiene color de piel (más el
    # centro del brazo): así la ropa de la persona junto al brazo no borra la prenda.
    zona = frame_bgr[ymin:ymin + alto_p, xmin:xmin + ancho_p] if frame_bgr is not None else None
    if zona is not None and zona.shape[:2] == (alto_p, ancho_p):
        ycrcb = cv2.cvtColor(zona, cv2.COLOR_BGR2YCrCb)
        piel = ((ycrcb[:, :, 1] >= 130) & (ycrcb[:, :, 1] <= 180) &
                (ycrcb[:, :, 2] >= 75) & (ycrcb[:, :, 2] <= 135)).astype(np.uint8) * 255
        brazos_delante = np.maximum(cv2.bitwise_and(brazos_delante, piel), centro_brazos)
    brazos_delante = cv2.bitwise_and(brazos_delante, cuerpo)
    permitido[brazos_delante > 0] = 0

    # El cuello de la prenda puede apoyarse un poco por encima de la base del cuello
    cuello = np.zeros_like(cuerpo)
    centro = tuple(np.int32(info_anatomica["p_neck_base"] - offset))
    radio = max(4, int(float(info_anatomica["dist_sh"]) * 0.22))
    cv2.circle(cuello, centro, radio, 255, -1)
    permitido = np.maximum(permitido, cuello)

    # Borde suave (sin escalones)
    suave = cv2.GaussianBlur(permitido, (5, 5), 0).astype(np.float32) / 255.0
    resultado = parche_rgba.copy()
    resultado[:, :, 3] = (alfa.astype(np.float32) * suave).astype(np.uint8)
    return resultado


def aplicar_sombras_del_cuerpo(frame_bgr, parche_rgba, xmin, ymin, intensidad=INTENSIDAD_SOMBRAS, solo_factor=False):
    """
    Pasa las luces y sombras del cuerpo (pliegues, volumen) a la prenda: toma la
    luminosidad de la zona del cuerpo bajo la prenda, la suaviza y la multiplica
    suavemente sobre el color de la tela.
    """
    if parche_rgba is None or intensidad <= 0:
        return None if solo_factor else parche_rgba
    alto_p, ancho_p = parche_rgba.shape[:2]
    zona = frame_bgr[ymin:ymin + alto_p, xmin:xmin + ancho_p]
    if zona.shape[:2] != (alto_p, ancho_p):
        return None if solo_factor else parche_rgba
    tela = parche_rgba[:, :, 3] > 20
    if np.count_nonzero(tela) < 50:
        return None if solo_factor else parche_rgba

    # Desenfoque amplio: pasan los pliegues y el volumen, no los estampados de la ropa
    # de la persona. Se calcula en una imagen 4 veces más chica (es mucho más rápido).
    gris = cv2.cvtColor(zona, cv2.COLOR_BGR2GRAY)
    chica = cv2.resize(gris, (max(4, ancho_p // 4), max(4, alto_p // 4)), interpolation=cv2.INTER_AREA)
    k = max(3, (min(chica.shape) // 12) | 1)
    chica = cv2.GaussianBlur(chica.astype(np.float32), (k, k), 0)
    luz = cv2.resize(chica, (ancho_p, alto_p), interpolation=cv2.INTER_LINEAR)
    media = float(cv2.mean(luz, mask=tela.astype(np.uint8))[0]) + 1e-3
    factor = 1.0 + (np.clip(luz / media, 0.60, 1.30) - 1.0) * intensidad
    if solo_factor:
        return factor

    resultado = parche_rgba.copy()
    resultado[:, :, :3] = cv2.multiply(np.ascontiguousarray(parche_rgba[:, :, :3]),
                                       cv2.merge([factor, factor, factor]), dtype=cv2.CV_8U)
    return resultado


def armonizar_con_la_escena(frame_bgr, parche_rgba, gamma=GAMMA_PRENDA, tono=TONO_ESCENA, solo_factor=False):
    """
    Adapta los colores de la prenda a la luz de la cámara: levanta las sombras de la
    tela (curva gamma sobre la luminosidad, así el color no pierde saturación) y le da
    un poco del tono de la escena (balance de blancos por "mundo gris": si la luz es
    verdosa o cálida, la prenda también).
    """
    if parche_rgba is None:
        return parche_rgba
    muestra = cv2.resize(frame_bgr, (64, 36), interpolation=cv2.INTER_AREA).reshape(-1, 3).astype(np.float32)
    muestra = muestra[muestra.max(axis=1) < 245]  # sin zonas quemadas (lámparas, ventanas)
    ganancias = np.ones(3, dtype=np.float32)
    if len(muestra) > 100:
        medias = muestra.mean(axis=0) + 1e-3
        ganancias = np.clip(1.0 + (medias / float(medias.mean()) - 1.0) * tono, 0.85, 1.15)
    # Factor de aclarado según la luminosidad de cada píxel: curva(L) / L
    niveles = np.arange(256, dtype=np.float32)
    aclarado = 255.0 * np.power(niveles / 255.0, gamma) / np.maximum(niveles, 1.0)
    bgr = np.ascontiguousarray(parche_rgba[:, :, :3])
    factor = aclarado[cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)]
    if solo_factor:
        return factor, ganancias
    resultado = parche_rgba.copy()
    resultado[:, :, :3] = cv2.multiply(bgr, cv2.merge([factor * float(g) for g in ganancias]), dtype=cv2.CV_8U)
    return resultado


def sombreado_volumen(parche_rgba, dist_sh, intensidad=INTENSIDAD_VOLUMEN, solo_factor=False):
    """
    Efecto 3D: el cuerpo es redondeado, así que la tela recibe menos luz hacia los
    costados. Oscurece suavemente la prenda cerca de su borde (según la distancia al
    contorno) y la deja igual en el centro del torso.
    """
    if parche_rgba is None or intensidad <= 0:
        return None if solo_factor else parche_rgba
    tela = (parche_rgba[:, :, 3] > 128).astype(np.uint8)
    if not tela.any():
        return None if solo_factor else parche_rgba
    distancia = cv2.distanceTransform(tela, cv2.DIST_L2, 3)
    curva = np.sqrt(np.clip(distancia / max(4.0, dist_sh * 0.20), 0.0, 1.0))
    factor = (1.0 - intensidad) + intensidad * curva
    if solo_factor:
        return factor
    resultado = parche_rgba.copy()
    resultado[:, :, :3] = cv2.multiply(np.ascontiguousarray(parche_rgba[:, :, :3]),
                                       cv2.merge([factor, factor, factor]), dtype=cv2.CV_8U)
    return resultado


def sombra_de_contacto(roi_fondo, parche_alfa, dist_sh, intensidad=INTENSIDAD_SOMBRA_CONTACTO):
    """
    Oscurece un poco el cuerpo justo debajo de los bordes de la tela (la luz viene de
    arriba): así la prenda parece apoyada sobre el cuerpo y no pegada encima.
    Modifica roi_fondo en el lugar.
    """
    if intensidad <= 0:
        return
    alto_p, ancho_p = parche_alfa.shape
    corrimiento = max(1, int(round(dist_sh * 0.02)))
    sigma = max(0.5, dist_sh * 0.0125)  # a mitad de tamaño (más rápido)
    desplazada = np.zeros_like(parche_alfa)
    desplazada[corrimiento:] = parche_alfa[:-corrimiento]
    mitad = cv2.resize(desplazada, (max(2, ancho_p // 2), max(2, alto_p // 2)), interpolation=cv2.INTER_AREA)
    difusa = cv2.resize(cv2.GaussianBlur(mitad, (0, 0), sigma), (ancho_p, alto_p), interpolation=cv2.INTER_LINEAR)
    sombra = difusa * (1.0 - parche_alfa) * intensidad
    # Sólo se tocan los píxeles con sombra (una franja angosta bajo los bordes)
    donde = sombra > 0.01
    if np.any(donde):
        roi_fondo[donde] = (roi_fondo[donde] * (1.0 - sombra[donde])[:, None]).astype(np.uint8)


def ocultar_cara(parche_alfa, xmin, ymin, p_nariz, p_menton, medio_cara):
    """
    Borra la prenda dentro de un óvalo con la forma de la cara: centrado en la nariz,
    tan ancho como la cara y hasta el mentón (con un borde suave de pocos píxeles).
    Modifica parche_alfa en el lugar.
    """
    centro = np.asarray(p_nariz, np.float32) - np.array([xmin, ymin], np.float32)
    medio_alto = float(p_menton[1]) - float(p_nariz[1])
    medio_ancho = float(medio_cara)
    if medio_alto < 4 or medio_ancho < 4:
        return
    alto_p, ancho_p = parche_alfa.shape
    x0, x1 = int(max(0, centro[0] - medio_ancho - 3)), int(min(ancho_p, centro[0] + medio_ancho + 4))
    y0, y1 = int(max(0, centro[1] - medio_alto - 3)), int(min(alto_p, centro[1] + medio_alto + 4))
    if x1 <= x0 or y1 <= y0:
        return
    ys, xs = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    r = np.sqrt(((xs - centro[0]) / medio_ancho) ** 2 + ((ys - centro[1]) / medio_alto) ** 2)
    suave = 3.0 / min(medio_ancho, medio_alto)
    dentro = np.clip((1.0 - r) / suave, 0.0, 1.0)
    parche_alfa[y0:y1, x0:x1] *= 1.0 - dentro


def ocultar_detras_del_cuello(parche_alfa, xmin, ymin, info_anatomica):
    """
    Vista de frente, el cuello de la persona tapa la parte de atrás del cuello de la
    prenda (la tira de tela que rodea la nuca). Borra esa tela en una zona con forma
    de U sobre el cuello: los costados del cuello de la prenda y el escote quedan.
    Modifica parche_alfa en el lugar.
    """
    # Centro real del cuello (si la cabeza está corrida, la U se corre con ella)
    p_neck = (np.asarray(info_anatomica.get("p_cuello", info_anatomica["p_neck_base"]), dtype=np.float32)
              - np.array([xmin, ymin], np.float32))
    u_up = np.asarray(info_anatomica["u_up"], dtype=np.float32)
    u_sh = np.asarray(info_anatomica["u_sh"], dtype=np.float32)
    d_sh = float(info_anatomica["dist_sh"])
    medio = float(info_anatomica.get("medio_cuello", d_sh * 0.20)) * 0.95
    base = d_sh * 0.02          # la U empieza apenas por encima de la base del cuello...
    hondo = medio * 0.35        # ... y en el centro baja un poco más (curva del escote)
    suave = max(2.0, d_sh * 0.015)

    alto_p, ancho_p = parche_alfa.shape
    x0 = int(max(0, p_neck[0] - medio - d_sh * 0.2))
    x1 = int(min(ancho_p, p_neck[0] + medio + d_sh * 0.2))
    y1 = int(min(alto_p, p_neck[1] + d_sh * 0.15))
    if x1 <= x0 or y1 <= 0:
        return
    ys, xs = np.mgrid[0:y1, x0:x1].astype(np.float32)
    rx, ry = xs - p_neck[0], ys - p_neck[1]
    arriba = rx * u_up[0] + ry * u_up[1]       # > 0: por encima de la base del cuello
    lateral = np.abs(rx * u_sh[0] + ry * u_sh[1])
    borde_u = base - hondo * np.sqrt(np.clip(1.0 - (lateral / medio) ** 2, 0.0, 1.0))
    dentro = np.clip((medio - lateral) / suave, 0.0, 1.0) * np.clip((arriba - borde_u) / suave, 0.0, 1.0)
    parche_alfa[0:y1, x0:x1] *= 1.0 - dentro


def componer_prenda_con_capas(frame_bgr, parche_rgba, xmin, ymin, xmax, ymax, info_anatomica,
                              talle="M", recortar_silueta=True, sombras=True, cuello_por_delante=False):
    """
    Integra la prenda sobre el cuerpo en el cuadro de la cámara respetando las capas anatómicas:
      1. Coloca la prenda sobre el torso, con la luz de la escena y una sombra suave en sus bordes.
      2. Protege el cuello y mentón para que el cuello de la prenda no cubra la cara.
         Con cuello_por_delante (prendas con cuello, vistas de frente), el cuello de la
         persona tapa además la parte de atrás del cuello de la prenda.
      3. Conserva los antebrazos y manos por delante cuando la persona cruza los brazos
         o los coloca al frente del torso.
    """
    if parche_rgba is None or xmax <= xmin or ymax <= ymin:
        return frame_bgr

    alto_frame, ancho_frame = frame_bgr.shape[:2]
    resultado = frame_bgr.copy()

    # 0. Prenda pegada al cuerpo: recorte a la silueta y sombras del cuerpo
    mascara = (info_anatomica or {}).get("mascara")
    if recortar_silueta and mascara is not None:
        parche_rgba = recortar_prenda_a_silueta(parche_rgba, xmin, ymin, mascara, info_anatomica, talle, frame_bgr)
    if sombras:
        # Luz de la escena + sombras del cuerpo + volumen, combinados en UNA sola pasada
        # sobre la tela (antes eran tres: es lo que más tiempo se llevaba por cuadro)
        factor, ganancias = armonizar_con_la_escena(frame_bgr, parche_rgba, solo_factor=True)
        for extra in (aplicar_sombras_del_cuerpo(frame_bgr, parche_rgba, xmin, ymin, solo_factor=True),
                      sombreado_volumen(parche_rgba, float((info_anatomica or {}).get("dist_sh", 200.0)),
                                        solo_factor=True) if info_anatomica else None):
            if extra is not None:
                factor = factor * extra
        parche_rgba = parche_rgba.copy()
        parche_rgba[:, :, :3] = cv2.multiply(np.ascontiguousarray(parche_rgba[:, :, :3]),
                                             cv2.merge([factor * float(g) for g in ganancias]), dtype=cv2.CV_8U)

    # 1. Recorte de la región de interés (ROI)
    roi_fondo = resultado[ymin:ymax, xmin:xmax]
    parche_bgr = parche_rgba[:, :, :3]
    parche_alfa = parche_rgba[:, :, 3].astype(np.float32) / 255.0

    # 2. Máscara de protección del mentón y cara
    # El cuello de la prenda nunca debe tapar la mandíbula ni el rostro de la persona
    if info_anatomica and "nose" in info_anatomica and "p_neck_base" in info_anatomica:
        p_nose = info_anatomica["nose"]
        p_neck = info_anatomica["p_neck_base"]
        # Límite inferior del mentón estimado entre nariz y base del cuello
        chin_y = p_nose[1] + (p_neck[1] - p_nose[1]) * 0.70

        # En coordenadas del parche local
        chin_local_y = int(chin_y - ymin)
        if 0 <= chin_local_y < parche_rgba.shape[0]:
            # Suavizar a cero cualquier píxel de la prenda por encima del mentón
            fade_len = max(5, int((p_neck[1] - p_nose[1]) * 0.20))
            # Sólo en una franja alrededor del cuello y la cara: así no se borra
            # una manga cuando la persona levanta el brazo por encima del mentón.
            medio_franja = float(info_anatomica.get("medio_cuello", info_anatomica.get("dist_sh", 200) * 0.2)) * 2.4
            cx_local = float(p_nose[0]) - xmin
            columnas = np.arange(parche_rgba.shape[1], dtype=np.float32)
            en_franja = np.clip(1.0 - (np.abs(columnas - cx_local) - medio_franja) / 12.0, 0.0, 1.0)
            filas_fade = np.arange(max(0, chin_local_y - fade_len), min(parche_rgba.shape[0], chin_local_y + fade_len))
            if len(filas_fade):
                factor = np.clip((filas_fade - (chin_local_y - fade_len)) / float(2 * fade_len), 0.0, 1.0)[:, None]
                parche_alfa[filas_fade, :] *= 1.0 - (1.0 - factor) * en_franja[None, :]
            arriba = slice(0, max(0, chin_local_y - fade_len))
            parche_alfa[arriba, :] *= (1.0 - en_franja)[None, :]
        # La cara entera, con su forma: un óvalo del ancho de la cara (entre las orejas)
        # que baja de la nariz hasta el mentón (estimado con la boca). Con los brazos
        # levantados los hombros suben, la prenda llega a la altura de la mandíbula y la
        # franja de arriba (pensada para el cuello) es más angosta que la cara. El cuello
        # de la prenda que queda alrededor del mentón no se toca.
        if info_anatomica.get("medio_cara") and info_anatomica.get("p_menton") is not None:
            ocultar_cara(parche_alfa, xmin, ymin, p_nose, info_anatomica["p_menton"], info_anatomica["medio_cara"])
    if cuello_por_delante and info_anatomica and "p_neck_base" in info_anatomica:
        ocultar_detras_del_cuello(parche_alfa, xmin, ymin, info_anatomica)

    # 3. Fusión Alfa de la prenda sobre el cuerpo
    # (sobre todo el recuadro de una vez: más rápido que seleccionar píxel por píxel)
    mask_valida = parche_alfa > 0.02
    if sombras and info_anatomica and np.any(mask_valida):
        sombra_de_contacto(roi_fondo, parche_alfa, float(info_anatomica.get("dist_sh", 200.0)))
    if np.any(mask_valida):
        # Mezcla ponderada con OpenCV (mucho más rápida que la cuenta en NumPy)
        alfa32 = np.ascontiguousarray(parche_alfa, dtype=np.float32)
        mezcla = cv2.blendLinear(np.ascontiguousarray(parche_bgr), roi_fondo, alfa32, 1.0 - alfa32)
        np.copyto(roi_fondo, mezcla, where=mask_valida[:, :, np.newaxis])

    # 4. CAPA SUPERIOR: Brazos y Manos al frente (Oclusión realista)
    # Si la persona cruza los brazos o los sostiene frente al pecho:
    if info_anatomica and info_anatomica.get("brazos_al_frente", False):
        p_elb_l = info_anatomica["p_elb_l"]
        p_elb_r = info_anatomica["p_elb_r"]
        p_wri_l = info_anatomica["p_wri_l"]
        p_wri_r = info_anatomica["p_wri_r"]
        d_sh = info_anatomica["dist_sh"]

        # Sólo se trabaja dentro del rectángulo de la prenda (los brazos únicamente
        # importan donde tapan la tela): mucho más rápido que procesar todo el cuadro.
        x0, y0 = max(0, xmin), max(0, ymin)
        x1, y1 = min(ancho_frame, xmax), min(alto_frame, ymax)
        if x1 > x0 and y1 > y0:
            offset = np.array([x0, y0], dtype=np.float32)
            arm_capsule = np.zeros((y1 - y0, x1 - x0), dtype=np.uint8)
            grosor_brazo = max(10, int(d_sh * 0.26))

            # Trazar cápsulas anatómicas de antebrazos (codo a muñeca)
            def pt(p):
                return tuple(np.int32(np.asarray(p, dtype=np.float32) - offset))
            cv2.line(arm_capsule, pt(p_elb_l), pt(p_wri_l), 255, grosor_brazo)
            cv2.line(arm_capsule, pt(p_elb_r), pt(p_wri_r), 255, grosor_brazo)
            # Conexión entre muñecas: SÓLO si las manos están realmente juntas (brazos
            # cruzados). Si no, esta franja cruzaría el torso y taparía la prenda.
            if float(np.linalg.norm(np.asarray(p_wri_l) - np.asarray(p_wri_r))) < d_sh * 0.6:
                cv2.line(arm_capsule, pt(p_wri_l), pt(p_wri_r), 255, int(grosor_brazo * 0.9))

            if np.any(arm_capsule):
                original = frame_bgr[y0:y1, x0:x1]
                # Restringir a tonos de piel y accesorios de la persona en el cuadro original
                ycrcb = cv2.cvtColor(original, cv2.COLOR_BGR2YCrCb)
                skin = (ycrcb[:, :, 1] >= 125) & (ycrcb[:, :, 1] <= 185) & \
                       (ycrcb[:, :, 2] >= 70) & (ycrcb[:, :, 2] <= 140)
                # Accesorios como reloj o pulsera (luminosidad muy baja o muy alta), sólo
                # cerca de las muñecas: así la ropa oscura de la persona no tapa la prenda
                cerca_munecas = np.zeros_like(arm_capsule)
                for p_w in (p_wri_l, p_wri_r):
                    cv2.circle(cerca_munecas, pt(p_w), max(6, int(d_sh * 0.15)), 255, -1)
                accesorios = ((ycrcb[:, :, 0] < 70) | (ycrcb[:, :, 0] > 210)) & (cerca_munecas > 0)
                # Si hay silueta, el brazo también tiene que ser parte de la persona
                mascara = info_anatomica.get("mascara")
                if mascara is not None and mascara.shape[:2] == frame_bgr.shape[:2]:
                    skin &= mascara[y0:y1, x0:x1] > 0.5

                forearm_px = (arm_capsule > 0) & (skin | accesorios)
                kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
                forearm_clean = cv2.morphologyEx(forearm_px.astype(np.uint8) * 255, cv2.MORPH_CLOSE, kernel)
                forearm_alpha = cv2.GaussianBlur(forearm_clean, (5, 5), 0).astype(np.float32) / 255.0

                # Componer antebrazos por encima de la prenda
                idx_arm = forearm_alpha > 0.05
                if np.any(idx_arm):
                    a_arm = forearm_alpha[idx_arm, np.newaxis]
                    zona = resultado[y0:y1, x0:x1]
                    zona[idx_arm] = (zona[idx_arm] * (1.0 - a_arm) + original[idx_arm] * a_arm).astype(np.uint8)

    return resultado
