# ==========================================================
# PROYECTO: PROBADOR VIRTUAL INTELIGENTE
# MÓDULO: MOTOR DE DEFORMACIÓN GEOMÉTRICA POR MALLA (MESH WARPER)
# ==========================================================

import numpy as np
import cv2
from clothing_geometry import obtener_triangulos_prenda, TRIANGULOS_ESTRUCTURADOS

def _deformar_triangulo_vectorizado(img_src, patch_dst, t_src, t_dst):
    """
    Deforma un triángulo de img_src al parche local patch_dst utilizando
    transformación afín optimizada en NumPy y OpenCV.
    """
    # 1. Comprobar área para evitar triángulos degenerados o colineales
    area_src = abs((t_src[0][0]*(t_src[1][1] - t_src[2][1]) + t_src[1][0]*(t_src[2][1] - t_src[0][1]) + t_src[2][0]*(t_src[0][1] - t_src[1][1])) * 0.5)
    area_dst = abs((t_dst[0][0]*(t_dst[1][1] - t_dst[2][1]) + t_dst[1][0]*(t_dst[2][1] - t_dst[0][1]) + t_dst[2][0]*(t_dst[0][1] - t_dst[1][1])) * 0.5)
    if area_src < 2.0 or area_dst < 2.0:
        return

    r1 = cv2.boundingRect(np.float32([t_src]))
    r2 = cv2.boundingRect(np.float32([t_dst]))

    x1, y1, w1, h1 = r1
    x2, y2, w2, h2 = r2
    if w1 <= 0 or h1 <= 0 or w2 <= 0 or h2 <= 0:
        return

    # Verificar límites dentro de img_src
    if x1 < 0 or y1 < 0 or x1 + w1 > img_src.shape[1] or y1 + h1 > img_src.shape[0]:
        return

    # Límites de destino dentro de patch_dst
    dx_min, dy_min = max(0, x2), max(0, y2)
    dx_max, dy_max = min(patch_dst.shape[1], x2 + w2), min(patch_dst.shape[0], y2 + h2)
    if dx_min >= dx_max or dy_min >= dy_max:
        return

    # Puntos relativos a los rectángulos delimitadores
    t1_rect = [(t_src[i][0] - x1, t_src[i][1] - y1) for i in range(3)]
    t2_rect = [(t_dst[i][0] - x2, t_dst[i][1] - y2) for i in range(3)]

    # Recorte origen
    src_crop = img_src[y1:y1 + h1, x1:x1 + w1]

    # Matriz afín de triángulo a triángulo
    try:
        M = cv2.getAffineTransform(np.float32(t1_rect), np.float32(t2_rect))
    except Exception:
        return

    # Deformar recorte
    warped_crop = cv2.warpAffine(
        src_crop, M, (w2, h2),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REFLECT_101
    )

    # Máscara binaria del triángulo destino
    mask = np.zeros((h2, w2), dtype=np.uint8)
    cv2.fillConvexPoly(mask, np.int32(t2_rect), 255)

    # Recorte del parche válido
    sx_min, sy_min = dx_min - x2, dy_min - y2
    sx_max, sy_max = sx_min + (dx_max - dx_min), sy_min + (dy_max - dy_min)

    patch_bgr = warped_crop[sy_min:sy_max, sx_min:sx_max, :3]
    patch_alpha = warped_crop[sy_min:sy_max, sx_min:sx_max, 3]
    patch_mask = mask[sy_min:sy_max, sx_min:sx_max]

    # Alfa efectivo ponderado por la máscara triangular
    eff_alpha = cv2.multiply(patch_alpha, patch_mask, scale=1.0 / 255.0)

    # Fusión alfa sobre el parche destino
    canvas_crop = patch_dst[dy_min:dy_max, dx_min:dx_max]
    idx = eff_alpha > 5
    if not np.any(idx):
        return

    alpha_norm = (eff_alpha[idx].astype(np.float32) / 255.0)[:, np.newaxis]
    bgr_patch = patch_bgr[idx].astype(np.float32)
    bgr_dst = canvas_crop[idx, :3].astype(np.float32)

    blended = (bgr_dst * (1.0 - alpha_norm) + bgr_patch * alpha_norm).astype(np.uint8)
    canvas_crop[idx, :3] = blended
    canvas_crop[idx, 3] = np.maximum(canvas_crop[idx, 3], eff_alpha[idx])


_CACHE_REDUCIDAS = {}

# Suavizado de la deformación (fracción del lado menor del parche). Entre triángulo y
# triángulo la malla cambia de dirección de golpe (la tela se ve "quebrada"); al
# suavizar el desplazamiento de cada píxel, la tela se curva de forma continua, como
# con una malla muchísimo más fina. 0 = sin suavizado.
SUAVIZADO_MALLA = 0.035


def _zona_triangulo(triangulo):
    """1 = torso, 2 = manga izquierda, 3 = manga derecha (se suavizan por separado)."""
    if any(p.startswith(("sleeve", "bicep")) for p in triangulo):
        return 2 if any(p.endswith("_l") for p in triangulo) else 3
    return 1


def _suavizar_por_zonas(map_x, map_y, zonas, sigma, reduccion=3):
    """
    Promedio gaussiano del mapa de origen, dentro de cada zona (torso, cada manga):
    así la manga y el torso no se mezclan en la axila. Se calcula a un tercio del
    tamaño y sólo dentro del recuadro de cada zona (es lo que lo hace rápido).
    """
    for zona in np.unique(zonas):
        if zona == 0:
            continue
        sel = zonas == zona
        filas = np.flatnonzero(sel.any(axis=1))
        cols = np.flatnonzero(sel.any(axis=0))
        y0, y1, x0, x1 = filas[0], filas[-1] + 1, cols[0], cols[-1] + 1
        sel_z = sel[y0:y1, x0:x1]
        m = sel_z.astype(np.float32)
        chico = (max(2, (x1 - x0) // reduccion), max(2, (y1 - y0) // reduccion))
        s_chico = max(0.8, sigma / reduccion)
        peso = cv2.GaussianBlur(cv2.resize(m, chico, interpolation=cv2.INTER_AREA), (0, 0), s_chico) + 1e-4
        for mapa in (map_x, map_y):
            zona_mapa = mapa[y0:y1, x0:x1]
            suma = cv2.GaussianBlur(cv2.resize(zona_mapa * m, chico, interpolation=cv2.INTER_AREA), (0, 0), s_chico)
            suave = cv2.resize(suma / peso, (x1 - x0, y1 - y0), interpolation=cv2.INTER_LINEAR)
            np.copyto(zona_mapa, suave, where=sel_z)


def _version_reducida(img, src_pts, ancho_destino, alto_destino):
    """Devuelve (imagen, puntos) reducidos si la prenda es mucho más grande que el destino."""
    alto_src, ancho_src = img.shape[:2]
    escala = min(1.0, 1.15 * max(ancho_destino / float(ancho_src), alto_destino / float(alto_src)))
    escala = round(escala, 1)
    if escala >= 0.95:
        return img, src_pts
    clave = (id(img), escala)
    if clave not in _CACHE_REDUCIDAS:
        if len(_CACHE_REDUCIDAS) > 64:
            _CACHE_REDUCIDAS.clear()
        reducida = cv2.resize(img, (max(2, int(ancho_src * escala)), max(2, int(alto_src * escala))),
                              interpolation=cv2.INTER_AREA)
        _CACHE_REDUCIDAS[clave] = (img, reducida)  # se guarda img para que su id no se reutilice
    reducida = _CACHE_REDUCIDAS[clave][1]
    puntos = {k: (float(x) * escala, float(y) * escala) for k, (x, y) in src_pts.items()}
    return reducida, puntos


def _area_triangulo(t):
    a, b, c = t
    return abs(float((b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1]))) * 0.5


def _deformar_en_una_pasada(img_src, src_pts, dst_pts, xmin, ymin, patch_w, patch_h, tiene_mangas):
    """Deforma la prenda completa con un único cv2.remap. Devuelve el parche RGBA o None."""
    triangulos = [t for t in obtener_triangulos_prenda(tiene_mangas)
                  if all(p in src_pts and p in dst_pts for p in t)]
    if not triangulos or len(triangulos) > 250:
        return None
    etiquetas = np.zeros((patch_h, patch_w), dtype=np.uint8)  # 0 = sin tela
    inversas = np.zeros((len(triangulos) + 1, 2, 3), dtype=np.float32)
    zona_de = np.zeros(len(triangulos) + 1, dtype=np.uint8)
    offset = np.array([xmin, ymin], dtype=np.float32)
    for i, (p1, p2, p3) in enumerate(triangulos, start=1):
        t_src = np.float32([src_pts[p1], src_pts[p2], src_pts[p3]])
        t_dst = np.float32([np.asarray(dst_pts[p], dtype=np.float32) - offset for p in (p1, p2, p3)])
        area_src = _area_triangulo(t_src)
        area_dst = _area_triangulo(t_dst)
        if area_src < 2.0 or area_dst < 2.0:
            continue
        try:
            inversas[i] = cv2.getAffineTransform(t_dst, t_src)  # destino -> origen
        except cv2.error:
            continue
        cv2.fillConvexPoly(etiquetas, np.round(t_dst).astype(np.int32), i)
        zona_de[i] = _zona_triangulo((p1, p2, p3))

    if not np.any(etiquetas):
        return None
    ys, xs = np.mgrid[0:patch_h, 0:patch_w].astype(np.float32)
    # La transformación de cada píxel: se busca cada coeficiente por separado (más
    # rápido que armar una tabla de alto x ancho x 2 x 3)
    def coef(fila, col):
        return inversas[:, fila, col][etiquetas]
    map_x = coef(0, 0) * xs + coef(0, 1) * ys + coef(0, 2)
    map_y = coef(1, 0) * xs + coef(1, 1) * ys + coef(1, 2)
    if SUAVIZADO_MALLA > 0:
        sigma = max(1.5, min(patch_w, patch_h) * SUAVIZADO_MALLA)
        _suavizar_por_zonas(map_x, map_y, zona_de[etiquetas], sigma)
    sin_tela = etiquetas == 0
    map_x[sin_tela] = -1.0
    map_y[sin_tela] = -1.0
    return cv2.remap(img_src, map_x, map_y, interpolation=cv2.INTER_LINEAR,
                     borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))


def deformar_malla_prenda(img_prenda_rgba, src_pts_dict, dst_pts_dict, ancho_frame, alto_frame, tiene_mangas=True):
    """
    Deforma suavemente la prenda utilizando la triangulación anatómica.
    Retorna (parche_local_rgba, xmin, ymin, xmax, ymax) listo para componer.
    """
    if img_prenda_rgba is None or src_pts_dict is None or dst_pts_dict is None:
        return None, 0, 0, 0, 0

    # 1. Bounding box de los puntos destino con margen de seguridad
    all_dst = np.array(list(dst_pts_dict.values()), dtype=np.float32)
    xmin = int(np.min(all_dst[:, 0]) - 25)
    ymin = int(np.min(all_dst[:, 1]) - 25)
    xmax = int(np.max(all_dst[:, 0]) + 25)
    ymax = int(np.max(all_dst[:, 1]) + 25)

    xmin = max(0, xmin)
    ymin = max(0, ymin)
    xmax = min(ancho_frame, xmax)
    ymax = min(alto_frame, ymax)

    if xmax <= xmin or ymax <= ymin:
        return None, 0, 0, 0, 0

    patch_w = xmax - xmin
    patch_h = ymax - ymin
    parche_local = np.zeros((patch_h, patch_w, 4), dtype=np.uint8)

    # 1b. Velocidad: si la foto de la prenda es mucho más grande que lo que se va a
    # dibujar, usamos una copia reducida (se calcula una vez y se guarda).
    img_prenda_rgba, src_pts_dict = _version_reducida(img_prenda_rgba, src_pts_dict, patch_w, patch_h)

    # 2. Deformar todos los triángulos en UNA sola pasada (rápido):
    #    se dibuja en un "mapa" qué triángulo cubre cada píxel del destino, y para cada
    #    píxel se calcula de qué lugar de la prenda original viene (transformación afín
    #    inversa de su triángulo). Después cv2.remap copia todos los píxeles juntos.
    parche_rapido = _deformar_en_una_pasada(img_prenda_rgba, src_pts_dict, dst_pts_dict,
                                            xmin, ymin, patch_w, patch_h, tiene_mangas)
    if parche_rapido is not None:
        parche_local = parche_rapido
        if np.any(parche_local[:, :, 3] > 0):
            parche_local[:, :, 3] = cv2.GaussianBlur(parche_local[:, :, 3], (3, 3), 0)
        return parche_local, xmin, ymin, xmax, ymax

    # (Respaldo: método anterior, triángulo por triángulo)
    triangulos = obtener_triangulos_prenda(tiene_mangas)
    offset = np.array([xmin, ymin], dtype=np.float32)
    for p1, p2, p3 in triangulos:
        if p1 not in src_pts_dict or p2 not in src_pts_dict or p3 not in src_pts_dict:
            continue
        if p1 not in dst_pts_dict or p2 not in dst_pts_dict or p3 not in dst_pts_dict:
            continue

        t_src = np.array([src_pts_dict[p1], src_pts_dict[p2], src_pts_dict[p3]], dtype=np.float32)
        t_dst = np.array([
            dst_pts_dict[p1] - offset,
            dst_pts_dict[p2] - offset,
            dst_pts_dict[p3] - offset
        ], dtype=np.float32)

        _deformar_triangulo_vectorizado(img_prenda_rgba, parche_local, t_src, t_dst)

    # Suavizado de bordes del canal alfa para evitar cortes bruscos
    if np.any(parche_local[:, :, 3] > 0):
        alpha_suave = cv2.GaussianBlur(parche_local[:, :, 3], (3, 3), 0)
        parche_local[:, :, 3] = alpha_suave

    return parche_local, xmin, ymin, xmax, ymax
