# ==========================================================
# PROYECTO: PROBADOR VIRTUAL INTELIGENTE
# MÓDULO: LIMPIEZA DE LAS FOTOS DE PRENDAS (SE HACE UNA VEZ, AL CARGAR)
# ==========================================================
# Las fotos de producto se recortan quitando un fondo de color parejo (casi
# siempre blanco). Eso deja dos problemas que se notan mucho en la cámara:
#
#   1. Partes BLANCAS de la prenda borradas junto con el fondo (por ejemplo, el
#      cuello blanco de una chomba): quedan transparentes y sólo se ve su contorno.
#   2. Debajo de la parte transparente sigue el color del fondo. Al deformar y
#      suavizar la prenda, ese color se mezcla con el borde y aparece un "halo"
#      blanco (o negro) alrededor del cuello, las mangas y el ruedo.
#
# recuperar_partes_borradas() arregla el punto 1 y extender_color_de_la_tela()
# el punto 2. La foto original en 'prendas/' no se modifica.

import numpy as np
import cv2

# Diferencia mínima con el color del fondo para considerar que un píxel es tela
UMBRAL_DIFERENCIA_FONDO = 12
# Una parte recuperada tiene que ser al menos esta fracción de la prenda
AREA_MINIMA_RECUPERADA = 0.002
# ... y tocar la prenda en al menos esta fracción de su contorno (una sombra o
# una mancha del fondo casi no la toca; un cuello borrado sí)
CONTACTO_MINIMO = 0.12


def recuperar_partes_borradas(img_rgba):
    """
    Devuelve una copia con el alfa reparado: las zonas transparentes cuyo color es
    claramente distinto del fondo y que están pegadas a la prenda vuelven a ser tela.
    Si el fondo no es de un color parejo, no cambia nada.
    """
    if img_rgba is None or img_rgba.ndim != 3 or img_rgba.shape[2] != 4:
        return img_rgba
    alfa = img_rgba[:, :, 3]
    transparente = alfa == 0
    tela = alfa > 25
    if transparente.sum() < 500 or tela.sum() < 500:
        return img_rgba

    bgr = img_rgba[:, :, :3].astype(np.int16)
    muestra = bgr[transparente][::7]  # una muestra alcanza para conocer el fondo
    fondo = np.median(muestra, axis=0)
    # El fondo tiene que ser parejo: si no, no se puede distinguir de la tela
    if float(np.percentile(np.abs(muestra - fondo).max(axis=1), 90)) > 6:
        return img_rgba
    # Debajo de lo transparente está el color de la misma tela (ver extender_color_de_la_tela):
    # esa foto ya se limpió y no hay fondo con el que comparar. Si se "recuperara" algo, se
    # taparía el hueco entre la manga y el torso.
    if float(np.abs(fondo - np.median(bgr[alfa > 200][::7], axis=0)).max()) <= UMBRAL_DIFERENCIA_FONDO:
        return img_rgba

    distinto = (np.abs(bgr - fondo).max(axis=2) > UMBRAL_DIFERENCIA_FONDO) & transparente
    nucleo = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    candidatos = cv2.morphologyEx(distinto.astype(np.uint8), cv2.MORPH_OPEN, nucleo)
    n, etiquetas, stats, _ = cv2.connectedComponentsWithStats(candidatos, connectivity=8)
    if n <= 1:
        return img_rgba

    cerca_tela = cv2.dilate(tela.astype(np.uint8), nucleo) > 0
    area_tela = float(tela.sum())
    recuperado = np.zeros_like(transparente)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] < area_tela * AREA_MINIMA_RECUPERADA:
            continue
        parte = etiquetas == i
        contorno = parte & ~cv2.erode(parte.astype(np.uint8), nucleo).astype(bool)
        if float(np.mean(cerca_tela[contorno])) >= CONTACTO_MINIMO:
            recuperado |= parte
    if not recuperado.any():
        return img_rgba

    # Cerrar los huecos de 1 o 2 píxeles entre la parte recuperada y la tela
    alfa_nuevo = np.maximum(alfa, recuperado.astype(np.uint8) * 255)
    cerrado = cv2.morphologyEx(alfa_nuevo, cv2.MORPH_CLOSE, nucleo)
    resultado = img_rgba.copy()
    resultado[:, :, 3] = np.where(cv2.dilate(recuperado.astype(np.uint8), nucleo) > 0, cerrado, alfa_nuevo)
    return resultado


def extender_color_de_la_tela(img_rgba, alfa_solido=250):
    """
    Reemplaza el color de los píxeles transparentes y semitransparentes por el color
    de la tela más cercana. El alfa no cambia: la prenda se ve igual, pero al
    deformarla y suavizar los bordes ya no aparece el color del fondo.
    """
    if img_rgba is None or img_rgba.ndim != 3 or img_rgba.shape[2] != 4:
        return img_rgba
    solido = (img_rgba[:, :, 3] >= alfa_solido).astype(np.float32)
    if solido.sum() < 50:
        return img_rgba
    bgr = img_rgba[:, :, :3].astype(np.float32)
    pendiente = solido < 1.0
    color = bgr.copy()
    # Promedio ponderado por la tela, de cerca hacia lejos: cada píxel toma el color
    # de la tela más próxima que alcance el desenfoque. Sólo importa una franja de
    # unos pocos píxeles alrededor de la prenda (lo que alcanzan a mezclar la
    # deformación y el suavizado); más lejos se usa el color promedio.
    for sigma in (1.5, 4.0):
        if not pendiente.any():
            break
        peso = cv2.GaussianBlur(solido, (0, 0), sigma)
        suma = cv2.GaussianBlur(bgr * solido[:, :, None], (0, 0), sigma)
        listo = pendiente & (peso > 0.02)
        color[listo] = suma[listo] / peso[listo][:, None]
        pendiente &= ~listo
    if pendiente.any():
        color[pendiente] = bgr[solido > 0].mean(axis=0)
    resultado = img_rgba.copy()
    resultado[:, :, :3] = np.clip(color, 0, 255).astype(np.uint8)
    return resultado


def enderezar_prenda(img_rgba, ventana_ancho=0.08, ventana_centro=0.30):
    """
    Foto tomada sobre una modelo torcida o de costado: la prenda sale con el eje inclinado,
    un lado más ancho que el otro y el cuello corrido. Fila por fila, lleva la tela a un eje
    vertical y a un ancho parejo a los dos lados. Un cuello alto queda como un tubo recto
    (las puntas que asoman arriba se recortan). Sirve para prendas lisas: un estampado se
    movería junto con la tela.
    """
    alfa = img_rgba[:, :, 3] > 128
    filas = np.where(alfa.any(axis=1))[0]
    if len(filas) < 20:
        return img_rgba
    y0, y1 = int(filas[0]), int(filas[-1]) + 1
    alto = y1 - y0
    izq = np.array([np.argmax(alfa[y]) for y in range(y0, y1)], dtype=np.float32)
    der = np.array([alfa.shape[1] - 1 - np.argmax(alfa[y, ::-1]) for y in range(y0, y1)], dtype=np.float32)

    # Cuello: las filas de arriba tan angostas como el tubo. Se mide debajo de las puntas
    a, b = int(alto * 0.05), int(alto * 0.10)
    medio_cuello = float(np.median((der - izq)[a:b])) * 0.5
    centro_cuello = float(np.median((der + izq)[a:b])) * 0.5
    fin_cuello = b
    while fin_cuello < alto // 2 and (der[fin_cuello] - izq[fin_cuello]) * 0.5 < medio_cuello * 1.12:
        fin_cuello += 1
    izq[:fin_cuello] = centro_cuello - medio_cuello
    der[:fin_cuello] = centro_cuello + medio_cuello

    # El borde de arriba suele ser curvo (se ve la piel del cuello en el medio, con puntas
    # a los lados): el cuello empieza donde ya hay tela de lado a lado, y queda parejo
    c0, c1 = int(centro_cuello - medio_cuello * 0.8), int(centro_cuello + medio_cuello * 0.8)
    corte = 0
    while corte < fin_cuello - 1 and alfa[y0 + corte, c0:c1].mean() < 0.98:
        corte += 1
    y0, alto = y0 + corte, alto - corte
    izq, der = izq[corte:], der[corte:]
    fin_cuello -= corte

    def suave(v, ventana):
        k = max(3, int(alto * ventana) | 1)
        return cv2.GaussianBlur(v[:, None], (1, k), 0, borderType=cv2.BORDER_REPLICATE)[:, 0]

    medio = suave((der - izq) * 0.5, ventana_ancho)
    medio[:fin_cuello] = medio_cuello
    # Del cuello al pecho, sin escalón
    rampa = min(alto - fin_cuello, max(3, int(alto * 0.03)))
    t = np.linspace(0.0, 1.0, rampa, dtype=np.float32)
    medio[fin_cuello:fin_cuello + rampa] = medio_cuello + (medio[fin_cuello:fin_cuello + rampa] - medio_cuello) * t

    ancho = int(np.ceil(medio.max())) * 2 + 6
    eje = ancho * 0.5
    xs = np.arange(ancho, dtype=np.float32)[None, :]
    relativo = (xs - eje) / np.maximum(1.0, medio[:, None])     # -1 y 1 son los bordes de la tela
    map_x = (izq[:, None] + (relativo + 1.0) * 0.5 * (der - izq)[:, None]).astype(np.float32)
    map_x[np.abs(relativo) > 1.0] = -1.0
    map_y = np.repeat(np.arange(y0, y1, dtype=np.float32)[:, None], ancho, axis=1)
    return cv2.remap(img_rgba, map_x, map_y, interpolation=cv2.INTER_LINEAR,
                     borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
