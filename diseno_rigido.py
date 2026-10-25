# ==========================================================
# PROYECTO: PROBADOR VIRTUAL INTELIGENTE
# MÓDULO: LOGOS Y ESTAMPADOS RÍGIDOS (NUNCA SE DEFORMAN)
# ==========================================================
# Para seguir el cuerpo, la tela se estira y se encoge por zonas (malla + escáner).
# Si el logo o el estampado viajan con la tela, se deforman (letras torcidas, un
# escudo aplastado hacia la axila). Por eso:
#
#   1. Al cargar la prenda se detectan sus diseños (logos, letras, estampados) y se
#      separan: queda una prenda LISA (el diseño se rellena con la tela de alrededor)
#      y cada diseño como un BLOQUE aparte.
#   2. En la cámara se deforma sólo la prenda lisa. Cada bloque se coloca encima con
#      una transformación RÍGIDA: se mueve, rota y cambia de tamaño con el cuerpo,
#      pero nunca se estira ni se tuerce.
#
# Los estampados que cubren toda la tela (leopardo, lunares) y los vivos largos no
# son bloques: son la tela misma y se dejan como están.

import numpy as np
import cv2

from clothing_geometry import obtener_triangulos_prenda

# Un bloque no puede ocupar más que esta fracción del recuadro de la prenda...
AREA_MAXIMA_BLOQUE = 0.30
# ... y si los detalles cubren más que esto de la tela, es un estampado repetido
AREA_MAXIMA_DETALLES = 0.22
MAXIMO_BLOQUES = 6
# Contraste mínimo con la tela para ser diseño (los pliegues y sombras tienen menos)
CONTRASTE_DISENO = 45
# Con más piezas sueltas que esto, es un estampado repetido (lunares, animal print)
MAXIMO_PIEZAS = 35


def _mascara_detalles(img_rgba, escala):
    """Píxeles que se apartan del color de la tela de alrededor (logos, letras, botones)."""
    alto, ancho = img_rgba.shape[:2]
    peq = cv2.resize(img_rgba, (max(8, int(ancho * escala)), max(8, int(alto * escala))), interpolation=cv2.INTER_AREA)
    bgr = peq[:, :, :3]
    tela = peq[:, :, 3] > 200
    k = max(9, (min(bgr.shape[:2]) // 8) | 1)
    base = cv2.medianBlur(bgr, min(k, 255))
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    lab_base = cv2.cvtColor(base, cv2.COLOR_BGR2LAB).astype(np.float32)
    diferencia = np.linalg.norm(lab - lab_base, axis=2)
    detalles = (diferencia > CONTRASTE_DISENO) & tela
    detalles = cv2.morphologyEx(detalles.astype(np.uint8), cv2.MORPH_OPEN, np.ones((2, 2), np.uint8)) > 0
    # El contorno de la prenda no es un detalle
    adentro = cv2.erode(tela.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))) > 0
    return detalles & adentro, tela, peq, diferencia


def extraer_diseno(img_rgba):
    """
    Devuelve (prenda_lisa, bloques). bloques: [{"img": recorte BGRA del diseño,
    "centro": (x, y) en la imagen de la prenda}]. Si la prenda no tiene diseños
    aislados (lisa o con estampado repetido), devuelve (img_rgba, []).
    """
    if img_rgba is None or img_rgba.ndim != 3 or img_rgba.shape[2] != 4:
        return img_rgba, []
    alto, ancho = img_rgba.shape[:2]
    escala = min(1.0, 420.0 / max(alto, ancho))
    detalles, tela, peq, diferencia = _mascara_detalles(img_rgba, escala)
    area_tela = float(tela.sum())
    if area_tela < 100 or detalles.sum() > area_tela * AREA_MAXIMA_DETALLES:
        return img_rgba, []
    ys, xs = np.where(tela)
    ancho_prenda, alto_prenda = xs.max() - xs.min() + 1, ys.max() - ys.min() + 1
    # Estampado repetido: muchas piezas repartidas por casi toda la prenda (un texto
    # largo también tiene muchas piezas, pero juntas en una zona)
    _, _, stats_piezas, centros = cv2.connectedComponentsWithStats(detalles.astype(np.uint8), connectivity=8)
    validas = stats_piezas[1:, cv2.CC_STAT_AREA] >= 4
    if int(validas.sum()) > MAXIMO_PIEZAS:
        c = centros[1:][validas]
        reparto = (np.ptp(c[:, 0]) / ancho_prenda) * (np.ptp(c[:, 1]) / alto_prenda)
        if reparto > 0.45:
            return img_rgba, []
    # Lo que toca el contorno (cuellos, puños, ribetes) es parte de la prenda, no un logo
    banda = max(5, int(min(ancho_prenda, alto_prenda) * 0.06)) | 1
    interior = cv2.erode(tela.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (banda, banda))) > 0

    # Agrupar letras y piezas cercanas en bloques (una palabra, un escudo)
    radio = max(3, int(min(peq.shape[:2]) * 0.03)) | 1
    juntas = cv2.dilate(detalles.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (radio, radio)))
    n, etiquetas, stats, _ = cv2.connectedComponentsWithStats(juntas, connectivity=8)
    area_recuadro = float(ancho_prenda * alto_prenda)
    candidatos = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        relleno = float(np.sum(detalles[etiquetas == i])) / max(1.0, w * h)
        if area < 30 or w * h > area_recuadro * AREA_MAXIMA_BLOQUE:
            continue
        if relleno < 0.04 or (max(w, h) > 8 * min(w, h) and relleno < 0.2):
            continue  # vivos y costuras largas y finas: son parte de la tela
        if float(np.mean(interior[(etiquetas == i) & detalles])) < 0.9:
            continue
        candidatos.append((area, i, x, y, w, h))
    candidatos = sorted(candidatos, reverse=True)[:MAXIMO_BLOQUES]
    if not candidatos:
        return img_rgba, []

    quitar_peq = np.zeros(detalles.shape, np.uint8)
    bloques = []
    margen = 3
    for _, i, x, y, w, h in candidatos:
        # Dentro del bloque se toma también lo de menos contraste (trazos finos de las
        # letras): así no quedan restos del diseño en la prenda lisa
        zona = (etiquetas == i) & (diferencia > CONTRASTE_DISENO * 0.45) & tela
        quitar_peq |= zona.astype(np.uint8)
        # Recorte a tamaño completo, con el diseño como alfa (borde suave)
        x0, y0 = max(0, int((x - margen) / escala)), max(0, int((y - margen) / escala))
        x1, y1 = min(ancho, int((x + w + margen) / escala) + 1), min(alto, int((y + h + margen) / escala) + 1)
        mascara = cv2.resize(zona.astype(np.float32), (ancho, alto), interpolation=cv2.INTER_LINEAR)[y0:y1, x0:x1]
        mascara = cv2.GaussianBlur((mascara > 0.35).astype(np.float32), (0, 0), 0.8)
        recorte = img_rgba[y0:y1, x0:x1].copy()
        recorte[:, :, 3] = (mascara * recorte[:, :, 3]).astype(np.uint8)
        bloques.append({"img": recorte, "centro": ((x0 + x1) / 2.0, (y0 + y1) / 2.0), "caja": (x0, y0, x1, y1)})

    # Bloques cercanos (las palabras y el escudo de un mismo diseño) forman un grupo
    # que se mueve con UNA sola transformación: así no se separan entre sí.
    distancia = (xs.max() - xs.min()) / escala * 0.10
    grupo = list(range(len(bloques)))

    def raiz(i):
        while grupo[i] != i:
            i = grupo[i]
        return i
    for i, a in enumerate(bloques):
        for j in range(i + 1, len(bloques)):
            b = bloques[j]
            sep_x = max(0, max(a["caja"][0], b["caja"][0]) - min(a["caja"][2], b["caja"][2]))
            sep_y = max(0, max(a["caja"][1], b["caja"][1]) - min(a["caja"][3], b["caja"][3]))
            if max(sep_x, sep_y) < distancia:
                grupo[raiz(j)] = raiz(i)
    for i, b in enumerate(bloques):
        miembros = [bloques[k] for k in range(len(bloques)) if raiz(k) == raiz(i)]
        b["centro_grupo"] = (float(np.mean([m["centro"][0] for m in miembros])),
                             float(np.mean([m["centro"][1] for m in miembros])))

    # Prenda lisa: el diseño se rellena con la tela de alrededor
    quitar_peq = cv2.dilate(quitar_peq, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    relleno = cv2.inpaint(np.ascontiguousarray(peq[:, :, :3]), quitar_peq, 5, cv2.INPAINT_TELEA)
    relleno = cv2.resize(relleno, (ancho, alto), interpolation=cv2.INTER_LINEAR)
    quitar = cv2.resize(quitar_peq.astype(np.float32), (ancho, alto), interpolation=cv2.INTER_LINEAR)
    quitar = cv2.GaussianBlur(quitar, (0, 0), 1.0)[:, :, None]
    lisa = img_rgba.copy()
    lisa[:, :, :3] = (img_rgba[:, :, :3] * (1.0 - quitar) + relleno * quitar).astype(np.uint8)
    return lisa, bloques


def _rigida_cerca(punto, src_pts, dst_pts, cantidad=6):
    """
    Transformación rígida (rotación + escala uniforme + traslación) que mejor lleva
    los puntos de la malla más cercanos al diseño desde la foto hasta el cuerpo.
    Usar varios puntos la hace estable: un solo triángulo puede estar torcido.
    """
    claves = [k for k in src_pts if k in dst_pts and not k.startswith(("sleeve", "bicep"))]
    if len(claves) < 3:
        return None
    p = np.asarray(punto, np.float32)
    claves.sort(key=lambda k: float(np.linalg.norm(np.asarray(src_pts[k], np.float32) - p)))
    elegidas = claves[:cantidad]
    src = np.float32([src_pts[k] for k in elegidas])
    dst = np.float32([np.asarray(dst_pts[k], np.float32) for k in elegidas])
    matriz, _ = cv2.estimateAffinePartial2D(src, dst, method=cv2.LMEDS, refineIters=5)
    return matriz


def _afin_en(punto, src_pts, dst_pts, tiene_mangas):
    """Transformación afín del triángulo de la malla que contiene el punto (o el más cercano)."""
    mejor, mejor_dist = None, None
    p = np.asarray(punto, np.float32)
    for t in obtener_triangulos_prenda(tiene_mangas):
        if any(k not in src_pts or k not in dst_pts for k in t):
            continue
        a, b, c = (np.asarray(src_pts[k], np.float32) for k in t)
        m = np.array([[b[0] - a[0], c[0] - a[0]], [b[1] - a[1], c[1] - a[1]]], np.float32)
        if abs(np.linalg.det(m)) < 1e-3:
            continue
        u, v = np.linalg.solve(m, p - a)
        dentro = min(u, v, 1.0 - u - v)
        dist = -dentro if dentro < 0 else 0.0
        if mejor is None or dist < mejor_dist:
            mejor, mejor_dist = t, dist
            if dist == 0.0:
                break
    if mejor is None:
        return None
    src = np.float32([src_pts[k] for k in mejor])
    dst = np.float32([np.asarray(dst_pts[k], np.float32) for k in mejor])
    return cv2.getAffineTransform(src, dst)


def pegar_bloques(parche_rgba, xmin, ymin, bloques, src_pts, dst_pts, tiene_mangas=True):
    """
    Dibuja los bloques de diseño sobre la prenda ya deformada, con una transformación
    rígida (rotación + escala uniforme, sin estirar). Sólo se pintan donde hay tela.
    """
    if parche_rgba is None or not bloques:
        return parche_rgba
    resultado = parche_rgba.copy()
    alto_p, ancho_p = resultado.shape[:2]
    tela = resultado[:, :, 3].astype(np.float32) / 255.0
    transformaciones = {}
    for bloque in bloques:
        ancla = bloque.get("centro_grupo", bloque["centro"])
        if ancla not in transformaciones:  # una sola vez por grupo
            afin = _rigida_cerca(ancla, src_pts, dst_pts)
            transformaciones[ancla] = afin if afin is not None else _afin_en(ancla, src_pts, dst_pts, tiene_mangas)
        afin = transformaciones[ancla]
        if afin is None:
            continue
        # Parte rígida de la transformación local: rotación + escala uniforme
        m = afin[:, :2].astype(np.float64)
        u, s, vt = np.linalg.svd(m)
        rot = u @ vt
        if np.linalg.det(rot) < 0:
            continue  # la malla quedó dada vuelta: mejor no dibujar
        escala = float(np.sqrt(abs(np.linalg.det(m))))
        # El ancla del grupo va donde la lleva la malla; cada bloque guarda su distancia
        # al ancla (girada y escalada), así el diseño completo queda armado
        destino_ancla = afin @ np.array([ancla[0], ancla[1], 1.0]) - np.array([xmin, ymin])
        destino = destino_ancla + escala * rot @ (np.asarray(bloque["centro"], np.float64) - np.asarray(ancla))
        img = bloque["img"]
        h, w = img.shape[:2]
        rigida = escala * rot
        # Mapa del recorte (centro en el medio) al parche
        t = destino - rigida @ np.array([w / 2.0, h / 2.0])
        matriz = np.hstack([rigida, t[:, None]]).astype(np.float32)
        # Sólo la zona del parche que puede tocar el bloque
        esquinas = (matriz[:, :2] @ np.float32([[0, 0], [w, 0], [0, h], [w, h]]).T).T + matriz[:, 2]
        x0, y0 = np.floor(esquinas.min(axis=0)).astype(int)
        x1, y1 = np.ceil(esquinas.max(axis=0)).astype(int)
        x0, y0, x1, y1 = max(0, x0), max(0, y0), min(ancho_p, x1), min(alto_p, y1)
        if x1 <= x0 or y1 <= y0:
            continue
        matriz[:, 2] -= (x0, y0)
        capa = cv2.warpAffine(img, matriz, (x1 - x0, y1 - y0), flags=cv2.INTER_LINEAR,
                              borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
        a = (capa[:, :, 3].astype(np.float32) / 255.0) * tela[y0:y1, x0:x1]
        zona = resultado[y0:y1, x0:x1, :3].astype(np.float32)
        resultado[y0:y1, x0:x1, :3] = (zona * (1.0 - a[:, :, None]) + capa[:, :, :3] * a[:, :, None]).astype(np.uint8)
    return resultado
