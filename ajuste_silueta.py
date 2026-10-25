# ==========================================================
# PROYECTO: PROBADOR VIRTUAL INTELIGENTE
# MÓDULO: AJUSTE TIPO "ESCÁNER" — LA PRENDA COPIA LA SILUETA FILA POR FILA
# ==========================================================
# La malla coloca la prenda usando unos pocos puntos del cuerpo. Entre esos puntos
# la tela sale recta, aunque el cuerpo sea curvo. Este módulo lo corrige:
#
#   1. Para cada fila de píxeles del torso, mide dónde empieza y dónde termina el
#      cuerpo en la silueta de MediaPipe (sin contar los brazos).
#   2. Mide dónde empieza y dónde termina la tela de la prenda en esa misma fila.
#   3. Estira o encoge la tela de esa fila para que sus bordes queden sobre los
#      bordes del cuerpo, más la holgura del talle.
#
# Resultado: la prenda sigue la forma real del cuerpo en TODA la altura del torso,
# como si se hubiera "escaneado" el cuerpo.

import numpy as np
import cv2


def _es_piel(bgr):
    """Píxeles con color de piel (rango amplio en YCrCb)."""
    ycrcb = cv2.cvtColor(bgr, cv2.COLOR_BGR2YCrCb)
    return (ycrcb[:, :, 1] >= 130) & (ycrcb[:, :, 1] <= 180) & (ycrcb[:, :, 2] >= 75) & (ycrcb[:, :, 2] <= 135)


def _mascara_torso_sin_brazos(mascara_roi, info, xmin, ymin, alto, ancho, frame_roi=None):
    """
    Silueta de la persona en la zona de la prenda, quitando los brazos.
    Si se pasa la imagen (frame_roi), dentro de la zona del brazo sólo se quita lo que
    tiene color de piel: así, si el brazo cuelga pegado al cuerpo, la ropa de al lado
    sigue contando como torso. El centro del brazo se quita siempre.
    """
    cuerpo = (mascara_roi > 0.5).astype(np.uint8)
    d_sh = float(info["dist_sh"])
    medidas = info.get("medidas") or {}
    # un poco más angosto que el brazo medido: si el brazo cuelga pegado al cuerpo,
    # así no se "come" el costado del torso
    grosor_medido = (medidas.get("brazo") or d_sh * 0.22)
    grosor = int(max(6, grosor_medido * (1.0 if frame_roi is not None else 0.80)))
    grosor_centro = int(max(4, grosor_medido * 0.45))
    brazos = np.zeros((alto, ancho), dtype=np.uint8)
    centro_brazos = np.zeros((alto, ancho), dtype=np.uint8)
    offset = np.array([xmin, ymin], dtype=np.float32)
    for hombro, codo, muneca in (("p_sh_l", "p_elb_l", "p_wri_l"), ("p_sh_r", "p_elb_r", "p_wri_r")):
        p_sh, p_elb, p_wri = (np.asarray(info[k], dtype=np.float32) - offset for k in (hombro, codo, muneca))
        eje = p_elb - p_sh
        largo = float(np.linalg.norm(eje))
        if largo < 1.0:
            continue
        # el brazo empieza un poco más abajo del hombro (en el hombro, brazo y torso son uno)
        inicio = p_sh + eje / largo * min(largo, d_sh * 0.30)
        for a, b in ((inicio, p_elb), (p_elb, p_wri)):
            cv2.line(brazos, tuple(np.int32(a)), tuple(np.int32(b)), 1, grosor)
            cv2.line(centro_brazos, tuple(np.int32(a)), tuple(np.int32(b)), 1, grosor_centro)
    if frame_roi is not None and frame_roi.shape[:2] == (alto, ancho):
        quitar = (centro_brazos > 0) | ((brazos > 0) & _es_piel(frame_roi))
    else:
        quitar = brazos > 0
    return (cuerpo > 0) & ~quitar


def _bordes_desde_centro(filas_bool, centros):
    """
    Para cada fila: el primer píxel 'falso' a cada lado de su centro.
    Procesa todas las filas juntas (mucho más rápido que fila por fila).
    Devuelve (izq, der, ok); ok es False donde no se pudo medir.
    """
    n_filas, n = filas_bool.shape
    c = np.round(centros).astype(np.int64)
    ok = (c > 0) & (c < n - 1)
    ok &= filas_bool[np.arange(n_filas), np.clip(c, 0, n - 1)]
    cols = np.arange(n)[None, :]
    fuera = ~filas_bool
    falso_izq = np.where(fuera & (cols < c[:, None]), cols, -1).max(axis=1)
    falso_der = np.where(fuera & (cols >= c[:, None]), cols, n).min(axis=1)
    ok &= (falso_izq >= 0) & (falso_der < n)  # si el cuerpo toca el borde de la zona, no se puede medir
    return (falso_izq + 1).astype(np.float32), (falso_der - 1).astype(np.float32), ok


def _suavizar(valores, validos, ventana):
    """Promedio móvil que ignora filas no válidas y rellena huecos interpolando."""
    n = len(valores)
    idx = np.arange(n)
    if validos.sum() < 2:
        return None
    v = np.interp(idx, idx[validos], valores[validos])
    k = max(1, int(ventana) | 1)
    nucleo = np.ones(k, dtype=np.float32) / k
    pad = k // 2
    return np.convolve(np.pad(v, pad, mode="edge"), nucleo, mode="valid")


def ajustar_prenda_a_silueta(parche_rgba, xmin, ymin, mascara, info, holgura=1.05, calce="regular",
                             memoria=None, frame_bgr=None):
    """
    Ajusta la prenda (ya deformada por la malla) al borde real del cuerpo, fila por fila.

    parche_rgba: la prenda deformada (RGBA) que empieza en (xmin, ymin) del cuadro.
    mascara: silueta de MediaPipe del cuadro completo (0 a 1).
    holgura: 1.00 = pegada a la piel; el talle la aumenta (ver catalogo.HOLGURA_TALLES).
    calce: "holgado" no se mete en la cintura; "entallado" y "regular" sí.
    memoria: dict opcional para suavizar entre cuadros (evita que el borde tiemble).

    Devuelve el parche ajustado (o el original si no se pudo medir bien).
    """
    if parche_rgba is None or mascara is None or info is None:
        return parche_rgba
    alto, ancho = parche_rgba.shape[:2]
    mascara_roi = mascara[ymin:ymin + alto, xmin:xmin + ancho]
    if mascara_roi.shape[:2] != (alto, ancho) or alto < 10 or ancho < 10:
        return parche_rgba

    frame_roi = frame_bgr[ymin:ymin + alto, xmin:xmin + ancho] if frame_bgr is not None else None
    torso = _mascara_torso_sin_brazos(mascara_roi, info, xmin, ymin, alto, ancho, frame_roi)
    tela = parche_rgba[:, :, 3] > 100

    # Eje del torso: centro de cada fila
    p_neck = np.asarray(info["p_neck_base"], dtype=np.float32) - np.array([xmin, ymin], dtype=np.float32)
    u_torso = np.asarray(info["u_torso"], dtype=np.float32)
    d_torso = float(info["dist_torso"])
    pendiente = float(u_torso[0] / u_torso[1]) if abs(u_torso[1]) > 1e-3 else 0.0

    # Hasta dónde llegan las mangas (cuando los brazos cuelgan, la manga está al lado
    # del torso y no hay que estirarla)
    off = np.array([xmin, ymin], dtype=np.float32)
    fin_mangas = 0.0
    for hombro, eje in (("p_sh_l", "u_arm_l"), ("p_sh_r", "u_arm_r")):
        punto = (np.asarray(info[hombro], dtype=np.float32) - off
                 + np.asarray(info[eje], dtype=np.float32) * float(info["dist_sh"]) * 0.62)
        fin_mangas = max(fin_mangas, float(punto[1]))

    # Zona que se ajusta: desde debajo de las axilas (y de las mangas) hasta el final de la prenda
    y_inicio = int(max(p_neck[1] + d_torso * 0.30, min(fin_mangas + d_torso * 0.02, p_neck[1] + d_torso * 0.55)))
    y_rampa = int(d_torso * 0.12)  # transición suave para no cortar las mangas
    filas = np.arange(max(0, y_inicio), alto)
    if len(filas) < 8:
        return parche_rgba

    n = len(filas)
    centros_exactos = p_neck[0] + (filas - p_neck[1]) * pendiente
    centros = centros_exactos.astype(np.float32)
    tela_izq, tela_der, ok_tela = _bordes_desde_centro(tela[filas], centros_exactos)
    cuerpo_izq, cuerpo_der, ok_cuerpo = _bordes_desde_centro(torso[filas], centros_exactos)
    tela_izq[~ok_tela] = 0; tela_der[~ok_tela] = 0
    cuerpo_izq[~ok_cuerpo] = 0; cuerpo_der[~ok_cuerpo] = 0

    # Sólo filas donde hay tela Y cuerpo, con anchos razonables (evita errores de la silueta)
    ancho_tela = tela_der - tela_izq
    ancho_cuerpo = cuerpo_der - cuerpo_izq
    validas = ok_tela & ok_cuerpo & (ancho_cuerpo > ancho_tela * 0.45) & (ancho_cuerpo < ancho_tela * 1.8)
    if validas.sum() < max(6, n * 0.25):
        return parche_rgba

    ventana = max(5, int(d_torso * 0.06))
    medio_izq = _suavizar(centros - cuerpo_izq, validas, ventana)
    medio_der = _suavizar(cuerpo_der - centros, validas, ventana)
    if medio_izq is None or medio_der is None:
        return parche_rgba

    # Suavizado entre cuadros (por posición relativa en el torso)
    if memoria is not None:
        clave = "ajuste_silueta"
        anterior = memoria.get(clave)
        rel = (filas - p_neck[1]) / max(1.0, d_torso)
        if anterior is not None:
            prev_izq = np.interp(rel, anterior[0], anterior[1])
            prev_der = np.interp(rel, anterior[0], anterior[2])
            medio_izq = prev_izq * 0.5 + medio_izq * 0.5
            medio_der = prev_der * 0.5 + medio_der * 0.5
        memoria[clave] = (rel, medio_izq.copy(), medio_der.copy())

    objetivo_izq = centros - medio_izq * holgura
    objetivo_der = centros + medio_der * holgura

    orig_izq = np.where(ok_tela, tela_izq, objetivo_izq)
    orig_der = np.where(ok_tela, tela_der, objetivo_der)
    if calce == "holgado":
        # La tela cae recta: nunca más angosta que la prenda original en esa fila
        objetivo_izq = np.minimum(objetivo_izq, orig_izq)
        objetivo_der = np.maximum(objetivo_der, orig_der)
    elif calce == "regular":
        # Sigue el cuerpo, pero si la prenda es más ancha cae un poco más recta
        objetivo_izq = np.minimum(objetivo_izq, 0.55 * objetivo_izq + 0.45 * orig_izq)
        objetivo_der = np.maximum(objetivo_der, 0.55 * objetivo_der + 0.45 * orig_der)

    objetivo_izq = np.clip(objetivo_izq, 0, ancho - 1)
    objetivo_der = np.clip(objetivo_der, 0, ancho - 1)

    # Si alguna fila todavía incluye mangas pegadas al torso, no se ajusta
    ancho_objetivo = objetivo_der - objetivo_izq
    con_mangas = (filas < fin_mangas) & (ancho_tela > ancho_objetivo * 1.30)

    # Construir el mapa de píxeles: en cada fila, los bordes de la tela van a los bordes del cuerpo
    map_x = np.tile(np.arange(ancho, dtype=np.float32), (alto, 1))
    map_y = np.repeat(np.arange(alto, dtype=np.float32)[:, None], ancho, axis=1)
    xs = np.arange(ancho, dtype=np.float32)[None, :]
    # Todas las filas a la vez: cada columna de 'xs' es un píxel, cada fila una fila de la prenda
    peso = np.clip((filas - y_inicio) / max(1, y_rampa), 0.0, 1.0)
    gl, gr = tela_izq, tela_der
    tl = gl + (objetivo_izq - gl) * peso
    tr = gr + (objetivo_der - gr) * peso
    usar = ok_tela & ~con_mangas & (tr - tl >= 4)
    if usar.any():
        gl, gr, tl, tr = (v[usar][:, None] for v in (gl, gr, tl, tr))
        tramo = (xs >= np.minimum(gl, tl)) & (xs <= np.maximum(gr, tr))
        dentro = (xs >= tl) & (xs <= tr)
        estirada = gl + (xs - tl) * (gr - gl) / (tr - tl)
        y_usar = filas[usar]
        map_x[y_usar] = np.where(tramo & dentro, estirada,
                                 np.where(tramo, -1.0, map_x[y_usar]))  # donde la tela sobraba, queda vacío

    return cv2.remap(parche_rgba, map_x, map_y, interpolation=cv2.INTER_LINEAR,
                     borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))


# -------------------------------------------------------------------------
# HOMBROS Y MANGAS
# -------------------------------------------------------------------------

def _suavizar_simple(v, k):
    k = max(1, int(k) | 1)
    pad = k // 2
    return np.convolve(np.pad(v, pad, mode="edge"), np.ones(k, np.float32) / k, mode="valid")


def ajustar_hombros(parche_rgba, xmin, ymin, mascara, info, holgura=1.05):
    """
    Columna por columna, entre el cuello y la punta de cada hombro: sube o baja la
    línea de arriba de la prenda para que se apoye sobre la línea real del hombro.
    El pelo que cae sobre los hombros también es parte de la silueta, por eso el
    cambio está limitado (la prenda no se 'trepa' al pelo).
    """
    if parche_rgba is None or mascara is None:
        return parche_rgba
    alto, ancho = parche_rgba.shape[:2]
    m = mascara[ymin:ymin + alto, xmin:xmin + ancho]
    if m.shape[:2] != (alto, ancho):
        return parche_rgba
    cuerpo = m > 0.5
    tela = parche_rgba[:, :, 3] > 100
    off = np.array([xmin, ymin], dtype=np.float32)
    d_sh = float(info["dist_sh"])
    d_torso = float(info["dist_torso"])
    neck = np.asarray(info["p_neck_base"], np.float32) - off
    sh_l = np.asarray(info["p_sh_l"], np.float32) - off
    sh_r = np.asarray(info["p_sh_r"], np.float32) - off
    medio_cuello = float(info.get("medio_cuello", d_sh * 0.20))
    centro_x = float(np.asarray(info.get("p_cuello", info["p_neck_base"]), np.float32)[0] - off[0])

    y_busqueda0 = int(max(0, neck[1] - d_sh * 0.45))
    y_ancla = int(min(alto - 1, neck[1] + d_torso * 0.30))  # axilas: aquí no se mueve nada
    if y_ancla - y_busqueda0 < 10:
        return parche_rgba
    max_subir = d_sh * 0.10
    max_bajar = d_sh * 0.12
    margen = d_sh * 0.015 * (holgura / 1.05)  # la tela queda apenas por encima de la piel

    map_x = np.tile(np.arange(ancho, dtype=np.float32), (alto, 1))
    map_y = np.repeat(np.arange(alto, dtype=np.float32)[:, None], ancho, axis=1)
    cambio = False
    for lado, punta in ((-1, sh_l), (1, sh_r)):
        x_ini = centro_x + lado * medio_cuello * 1.15
        x_fin = punta[0] + lado * d_sh * 0.18
        cols = np.arange(int(min(x_ini, x_fin)), int(max(x_ini, x_fin)) + 1)
        cols = cols[(cols >= 0) & (cols < ancho)]
        if len(cols) < 6:
            continue
        # Primera fila con tela y con cuerpo en cada columna (todas las columnas juntas)
        zona_t = tela[y_busqueda0:y_ancla][:, cols]
        zona_c = cuerpo[y_busqueda0:y_ancla][:, cols]
        top_tela = np.where(zona_t.any(axis=0), y_busqueda0 + np.argmax(zona_t, axis=0), np.nan).astype(np.float32)
        top_cuerpo = np.where(zona_c.any(axis=0), y_busqueda0 + np.argmax(zona_c, axis=0), np.nan).astype(np.float32)
        ok = ~np.isnan(top_tela) & ~np.isnan(top_cuerpo)
        if ok.sum() < len(cols) * 0.4:
            continue
        idx = np.arange(len(cols))
        tt = np.interp(idx, idx[ok], top_tela[ok])
        tc = np.interp(idx, idx[ok], top_cuerpo[ok])
        objetivo = np.clip(tc - margen, tt - max_subir, tt + max_bajar)
        objetivo = _suavizar_simple(objetivo, max(5, len(cols) // 8))
        # Transición suave en los extremos (cuello y punta del hombro)
        rampa = max(3, len(cols) // 6)
        peso = np.minimum(1.0, np.minimum(idx + 1, len(cols) - idx) / float(rampa))
        objetivo = tt + (objetivo - tt) * peso
        mover = (np.abs(tt - objetivo) >= 0.5) & (y_ancla - objetivo >= 4)
        if mover.any():
            yo, yn = tt[mover][None, :], objetivo[mover][None, :]
            ys = np.arange(0, y_ancla, dtype=np.float32)[:, None]
            # filas entre la nueva línea y el ancla se estiran desde la línea original
            map_y[:y_ancla, cols[mover]] = np.where(
                ys >= yn, yo + (ys - yn) * (y_ancla - yo) / np.maximum(1.0, (y_ancla - yn)), -1.0)
            cambio = True
    if not cambio:
        return parche_rgba
    return cv2.remap(parche_rgba, map_x, map_y, interpolation=cv2.INTER_LINEAR,
                     borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))


def ajustar_mangas(parche_rgba, xmin, ymin, mascara, info, holgura=1.05):
    """
    Fila por fila, en la altura de las mangas: lleva el borde de AFUERA de la manga
    hasta el borde de afuera del brazo (más la holgura). El borde de adentro no se toca.
    """
    if parche_rgba is None or mascara is None:
        return parche_rgba
    alto, ancho = parche_rgba.shape[:2]
    m = mascara[ymin:ymin + alto, xmin:xmin + ancho]
    if m.shape[:2] != (alto, ancho):
        return parche_rgba
    cuerpo = m > 0.5
    tela = parche_rgba[:, :, 3] > 100
    off = np.array([xmin, ymin], dtype=np.float32)
    d_sh = float(info["dist_sh"])
    ventana = int(d_sh * 0.15)

    map_x = np.tile(np.arange(ancho, dtype=np.float32), (alto, 1))
    map_y = np.repeat(np.arange(alto, dtype=np.float32)[:, None], ancho, axis=1)
    xs = np.arange(ancho, dtype=np.float32)
    cambio = False
    for lado, hombro, eje in ((-1, "p_sh_l", "u_arm_l"), (1, "p_sh_r", "u_arm_r")):
        p_sh = np.asarray(info[hombro], np.float32) - off
        u_arm = np.asarray(info[eje], np.float32)
        fin = p_sh + u_arm * d_sh * 0.55
        if abs(u_arm[1]) < 0.5:
            continue  # brazo muy levantado u horizontal: la manga ya sigue al brazo por la malla
        y0 = int(max(0, p_sh[1] - d_sh * 0.02))
        y1 = int(min(alto - 1, fin[1]))
        if y1 - y0 < 6:
            continue
        filas = np.arange(y0, y1)
        # Borde de afuera de la tela en cada fila, y del cuerpo cerca de ese borde (todas las filas juntas)
        zona_t, zona_c = tela[filas], cuerpo[filas]
        cols = np.arange(ancho)[None, :]
        hay_tela = zona_t.any(axis=1)
        bt_filas = np.argmax(zona_t, axis=1) if lado < 0 else ancho - 1 - np.argmax(zona_t[:, ::-1], axis=1)
        a = np.maximum(0, bt_filas - ventana)[:, None]
        b = np.minimum(ancho, bt_filas + ventana + 1)[:, None]
        en_ventana = zona_c & (cols >= a) & (cols < b)
        if lado < 0:
            bc_filas = np.where(en_ventana, cols, ancho).min(axis=1)
        else:
            bc_filas = np.where(en_ventana, cols, -1).max(axis=1)
        ok = hay_tela & en_ventana.any(axis=1)
        borde_tela = np.where(ok, bt_filas, np.nan).astype(np.float32)
        borde_cuerpo = np.where(ok, bc_filas, np.nan).astype(np.float32)
        if ok.sum() < len(filas) * 0.5:
            continue
        idx = np.arange(len(filas))
        bt = np.interp(idx, idx[ok], borde_tela[ok])
        bc = np.interp(idx, idx[ok], borde_cuerpo[ok])
        holg = d_sh * 0.03 * (holgura / 1.05)
        objetivo = _suavizar_simple(bc + lado * holg, max(5, len(filas) // 6))
        peso = np.minimum(1.0, np.minimum(idx + 1, len(filas) - idx) / max(3.0, len(filas) / 5.0))
        objetivo = bt + (objetivo - bt) * peso
        mover = np.abs(objetivo - bt) >= 0.5
        if mover.any():
            # Estirar sólo el tramo exterior de la manga (un cuarto del ancho de hombros)
            nuevo, viejo = objetivo[mover][:, None], bt[mover][:, None]
            interior = viejo - lado * d_sh * 0.25
            x2 = xs[None, :]
            if lado < 0:
                sel = (x2 >= np.minimum(nuevo, viejo)) & (x2 <= interior)
                valor = np.where(x2 >= nuevo,
                                 viejo + (x2 - nuevo) * (interior - viejo) / np.maximum(1.0, interior - nuevo), -1.0)
            else:
                sel = (x2 <= np.maximum(nuevo, viejo)) & (x2 >= interior)
                valor = np.where(x2 <= nuevo,
                                 interior + (x2 - interior) * (viejo - interior) / np.maximum(1.0, nuevo - interior), -1.0)
            y_mover = filas[mover]
            map_x[y_mover] = np.where(sel, valor, map_x[y_mover])
            cambio = True
    if not cambio:
        return parche_rgba
    return cv2.remap(parche_rgba, map_x, map_y, interpolation=cv2.INTER_LINEAR,
                     borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))


def ajustar_prenda_completa(parche_rgba, xmin, ymin, mascara, info, holgura=1.05, calce="regular", memoria=None,
                            frame_bgr=None, tiene_mangas=True):
    """
    Escáner completo: hombros, mangas y torso. frame_bgr (opcional) mejora la separación brazo / torso.
    Sin mangas (top halter, musculosa) no se ajustan hombros ni mangas: las tiras no se
    apoyan en la línea del hombro y estirarlas hasta ahí deforma el diseño.
    """
    p = parche_rgba
    if tiene_mangas:
        p = ajustar_hombros(p, xmin, ymin, mascara, info, holgura)
        p = ajustar_mangas(p, xmin, ymin, mascara, info, holgura)
    return ajustar_prenda_a_silueta(p, xmin, ymin, mascara, info, holgura=holgura, calce=calce, memoria=memoria,
                                    frame_bgr=frame_bgr)
