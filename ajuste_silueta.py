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


def _bordes_desde_centro(fila_bool, centro):
    """Primer píxel 'falso' a cada lado del centro. Devuelve (izq, der) o None."""
    n = len(fila_bool)
    c = int(round(centro))
    if c <= 0 or c >= n - 1 or not fila_bool[c]:
        return None
    izq_trozo = fila_bool[:c][::-1]
    der_trozo = fila_bool[c:]
    fuera_izq = np.argmin(izq_trozo) if not izq_trozo.all() else None
    fuera_der = np.argmin(der_trozo) if not der_trozo.all() else None
    if fuera_izq is None or fuera_der is None:
        return None  # el cuerpo toca el borde de la zona: no se puede medir
    return float(c - fuera_izq), float(c + fuera_der - 1)


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
    tela_izq = np.zeros(n, np.float32); tela_der = np.zeros(n, np.float32)
    cuerpo_izq = np.zeros(n, np.float32); cuerpo_der = np.zeros(n, np.float32)
    centros = np.zeros(n, np.float32)
    ok_tela = np.zeros(n, bool); ok_cuerpo = np.zeros(n, bool)

    for i, y in enumerate(filas):
        c = p_neck[0] + (y - p_neck[1]) * pendiente
        centros[i] = c
        b_tela = _bordes_desde_centro(tela[y], c)
        if b_tela is not None:
            tela_izq[i], tela_der[i] = b_tela
            ok_tela[i] = True
        b_cuerpo = _bordes_desde_centro(torso[y], c)
        if b_cuerpo is not None:
            cuerpo_izq[i], cuerpo_der[i] = b_cuerpo
            ok_cuerpo[i] = True

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
    xs = np.arange(ancho, dtype=np.float32)
    for i, y in enumerate(filas):
        if not ok_tela[i] or con_mangas[i]:
            continue
        peso = float(np.clip((y - y_inicio) / max(1, y_rampa), 0.0, 1.0))
        gl, gr = tela_izq[i], tela_der[i]
        tl = gl + (objetivo_izq[i] - gl) * peso
        tr = gr + (objetivo_der[i] - gr) * peso
        if tr - tl < 4:
            continue
        a = min(gl, tl); b = max(gr, tr)
        tramo = (xs >= a) & (xs <= b)
        dentro = (xs >= tl) & (xs <= tr)
        fila = map_x[y]
        fila[tramo & dentro] = gl + (xs[tramo & dentro] - tl) * (gr - gl) / (tr - tl)
        fila[tramo & ~dentro] = -1.0  # donde la tela sobraba, queda vacío

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
        x_ini = neck[0] + lado * medio_cuello * 1.15
        x_fin = punta[0] + lado * d_sh * 0.18
        cols = np.arange(int(min(x_ini, x_fin)), int(max(x_ini, x_fin)) + 1)
        cols = cols[(cols >= 0) & (cols < ancho)]
        if len(cols) < 6:
            continue
        top_tela = np.full(len(cols), np.nan, np.float32)
        top_cuerpo = np.full(len(cols), np.nan, np.float32)
        for i, x in enumerate(cols):
            col_t = tela[y_busqueda0:y_ancla, x]
            col_c = cuerpo[y_busqueda0:y_ancla, x]
            if col_t.any():
                top_tela[i] = y_busqueda0 + np.argmax(col_t)
            if col_c.any():
                top_cuerpo[i] = y_busqueda0 + np.argmax(col_c)
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
        for i, x in enumerate(cols):
            yo, yn = tt[i], objetivo[i]
            if abs(yo - yn) < 0.5 or y_ancla - yn < 4:
                continue
            ys = np.arange(0, y_ancla, dtype=np.float32)
            col = map_y[:y_ancla, x]
            # filas entre la nueva línea y el ancla se estiran desde la línea original
            col[:] = np.where(ys >= yn, yo + (ys - yn) * (y_ancla - yo) / max(1.0, (y_ancla - yn)), -1.0)
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
        borde_tela = np.full(len(filas), np.nan, np.float32)
        borde_cuerpo = np.full(len(filas), np.nan, np.float32)
        for i, y in enumerate(filas):
            xt = np.where(tela[y])[0]
            if len(xt) == 0:
                continue
            bt = float(xt.min() if lado < 0 else xt.max())
            a, b = int(max(0, bt - ventana)), int(min(ancho, bt + ventana + 1))
            xc = np.where(cuerpo[y, a:b])[0]
            if len(xc) == 0:
                continue
            borde_tela[i] = bt
            borde_cuerpo[i] = a + float(xc.min() if lado < 0 else xc.max())
        ok = ~np.isnan(borde_tela)
        if ok.sum() < len(filas) * 0.5:
            continue
        idx = np.arange(len(filas))
        bt = np.interp(idx, idx[ok], borde_tela[ok])
        bc = np.interp(idx, idx[ok], borde_cuerpo[ok])
        holg = d_sh * 0.03 * (holgura / 1.05)
        objetivo = _suavizar_simple(bc + lado * holg, max(5, len(filas) // 6))
        peso = np.minimum(1.0, np.minimum(idx + 1, len(filas) - idx) / max(3.0, len(filas) / 5.0))
        objetivo = bt + (objetivo - bt) * peso
        for i, y in enumerate(filas):
            if abs(objetivo[i] - bt[i]) < 0.5:
                continue
            # Estirar sólo el tramo exterior de la manga (un cuarto del ancho de hombros)
            interior = bt[i] - lado * d_sh * 0.25
            nuevo, viejo = objetivo[i], bt[i]
            fila = map_x[y]
            if lado < 0:
                sel = (xs >= min(nuevo, viejo)) & (xs <= interior)
                fila[sel] = np.where(xs[sel] >= nuevo,
                                     viejo + (xs[sel] - nuevo) * (interior - viejo) / max(1.0, interior - nuevo), -1.0)
            else:
                sel = (xs <= max(nuevo, viejo)) & (xs >= interior)
                fila[sel] = np.where(xs[sel] <= nuevo,
                                     interior + (xs[sel] - interior) * (viejo - interior) / max(1.0, nuevo - interior), -1.0)
            cambio = True
    if not cambio:
        return parche_rgba
    return cv2.remap(parche_rgba, map_x, map_y, interpolation=cv2.INTER_LINEAR,
                     borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))


def ajustar_prenda_completa(parche_rgba, xmin, ymin, mascara, info, holgura=1.05, calce="regular", memoria=None,
                            frame_bgr=None):
    """Escáner completo: hombros, mangas y torso. frame_bgr (opcional) mejora la separación brazo / torso."""
    p = ajustar_hombros(parche_rgba, xmin, ymin, mascara, info, holgura)
    p = ajustar_mangas(p, xmin, ymin, mascara, info, holgura)
    return ajustar_prenda_a_silueta(p, xmin, ymin, mascara, info, holgura=holgura, calce=calce, memoria=memoria,
                                    frame_bgr=frame_bgr)
