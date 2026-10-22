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
INTENSIDAD_SOMBRAS = 0.25


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


def aplicar_sombras_del_cuerpo(frame_bgr, parche_rgba, xmin, ymin, intensidad=INTENSIDAD_SOMBRAS):
    """
    Pasa las luces y sombras del cuerpo (pliegues, volumen) a la prenda: toma la
    luminosidad de la zona del cuerpo bajo la prenda, la suaviza y la multiplica
    suavemente sobre el color de la tela.
    """
    if parche_rgba is None or intensidad <= 0:
        return parche_rgba
    alto_p, ancho_p = parche_rgba.shape[:2]
    zona = frame_bgr[ymin:ymin + alto_p, xmin:xmin + ancho_p]
    if zona.shape[:2] != (alto_p, ancho_p):
        return parche_rgba
    tela = parche_rgba[:, :, 3] > 20
    if np.count_nonzero(tela) < 50:
        return parche_rgba

    luz = cv2.cvtColor(zona, cv2.COLOR_BGR2GRAY).astype(np.float32)
    k = max(5, (min(alto_p, ancho_p) // 25) | 1)
    luz = cv2.GaussianBlur(luz, (k, k), 0)
    media = float(np.mean(luz[tela])) + 1e-3
    relativa = np.clip(luz / media, 0.70, 1.20)
    factor = 1.0 + (relativa - 1.0) * intensidad

    resultado = parche_rgba.copy()
    color = resultado[:, :, :3].astype(np.float32) * factor[:, :, None]
    resultado[:, :, :3] = np.clip(color, 0, 255).astype(np.uint8)
    return resultado


def componer_prenda_con_capas(frame_bgr, parche_rgba, xmin, ymin, xmax, ymax, info_anatomica,
                              talle="M", recortar_silueta=True, sombras=True):
    """
    Integra la prenda sobre el cuerpo en el cuadro de la cámara respetando las capas anatómicas:
      1. Coloca la prenda sobre el torso.
      2. Protege el cuello y mentón para que el cuello de la prenda no cubra la cara.
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
        parche_rgba = aplicar_sombras_del_cuerpo(frame_bgr, parche_rgba, xmin, ymin)

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

    # 3. Fusión Alfa de la prenda sobre el cuerpo
    # (sobre todo el recuadro de una vez: más rápido que seleccionar píxel por píxel)
    mask_valida = parche_alfa > 0.02
    if np.any(mask_valida):
        alpha_3c = parche_alfa[:, :, np.newaxis]
        mezcla = (roi_fondo * (1.0 - alpha_3c) + parche_bgr * alpha_3c).astype(np.uint8)
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
