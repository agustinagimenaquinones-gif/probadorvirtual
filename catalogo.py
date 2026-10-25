# ==========================================================
# PROYECTO: PROBADOR VIRTUAL INTELIGENTE
# MÓDULO: CATÁLOGO DE PRENDAS Y GESTIÓN DE METADATOS
# ==========================================================

import os
import glob
import cv2
import numpy as np
from clothing_geometry import detectar_puntos_clave_prenda
from vista_espalda import cargar_espalda, es_archivo_espalda
from limpieza_prenda import recuperar_partes_borradas, extender_color_de_la_tela
from diseno_rigido import extraer_diseno
from config import USAR_MYSQL

CARPETA_PRENDAS = "prendas"

# -------------------------------------------------------------------------
# TALLES: HOLGURA RESPECTO DEL CUERPO MEDIDO
# -------------------------------------------------------------------------
# 1.00 = la prenda tiene exactamente el ancho de la silueta.
# Un talle chico sobre un cuerpo grande se ve ajustado (deja ver el cuerpo a
# los costados) y un talle grande se ve más suelto y un poco más largo.
HOLGURA_TALLES = {
    "XS": 0.95,
    "S": 1.00,
    "M": 1.05,
    "L": 1.11,
    "XL": 1.18,
    "XXL": 1.25,
}

# Tipo de calce de cada prenda (cómo cae la tela sobre la cintura):
#   "entallado": sigue la curva de la cintura.
#   "regular":   marca un poco la cintura pero cae más recto.
#   "holgado":   cae recto desde el pecho o la cadera (la más ancha).
CALCES_VALIDOS = ("entallado", "regular", "holgado")

# Margen transparente alrededor de cada prenda (en píxeles) para que la malla
# no recorte los bordes de la tela.
MARGEN_TRANSPARENTE = 6

# -------------------------------------------------------------------------
# CATÁLOGO DE PRENDAS
# Los datos de las prendas (nombre, precio, talles, medidas, etc.) están en la
# base MySQL (ver conexion_mysql.py). Para agregar una prenda: copiar el PNG en
# 'prendas/' y ejecutar cargar_prendas_mysql.py.
# -------------------------------------------------------------------------


def obtener_medidas_talle(prenda, talle):
    """
    Retorna un diccionario con las medidas físicas de la prenda para un talle (en cm):
    {'pecho': cm, 'cintura': cm, 'cadera': cm, 'hombros': cm, 'largo': cm}
    """
    talle_str = str(talle).upper()
    if "medidas_talles" in prenda and talle_str in prenda["medidas_talles"]:
        return dict(prenda["medidas_talles"][talle_str])

    # Valores estándar proporcionados si no fueron declarados explícitamente
    escala = HOLGURA_TALLES.get(talle_str, 1.05)
    base_pecho = 94.0
    base_cintura = 76.0 if prenda.get("calce") == "entallado" else 88.0
    base_cadera = 96.0
    base_hombros = 41.0
    base_largo = 66.0

    return {
        "pecho": int(round(base_pecho * escala)),
        "cintura": int(round(base_cintura * escala)),
        "cadera": int(round(base_cadera * escala)),
        "hombros": int(round(base_hombros * (1.0 + (escala - 1.0) * 0.5))),
        "largo": int(round(base_largo * (1.0 + (escala - 1.0) * 0.4))),
    }


def obtener_guia_medidas_completa(prenda):
    """Retorna la tabla completa de medidas de todos los talles de la prenda."""
    talles = prenda.get("talles") or ["S", "M", "L"]
    tabla = []
    for t in talles:
        m = obtener_medidas_talle(prenda, t)
        tabla.append({
            "talle": t,
            "pecho": f"{m['pecho']} cm",
            "cintura": f"{m['cintura']} cm",
            "cadera": f"{m['cadera']} cm",
            "hombros": f"{m['hombros']} cm",
            "largo": f"{m['largo']} cm",
            "calce": prenda.get("calce", "regular").capitalize()
        })
    return tabla


def orientar_prenda(img_rgba, rotacion_grados=0, voltear_horizontal=False, voltear_vertical=False):
    """
    Función para girar o voltear una prenda individual SOLO cuando sea necesario.
    NO se aplica automáticamente a todas las prendas para no alterar las correctas.
    """
    if img_rgba is None:
        return None

    res = img_rgba.copy()
    if rotacion_grados == 90:
        res = cv2.rotate(res, cv2.ROTATE_90_CLOCKWISE)
    elif rotacion_grados == 180:
        res = cv2.rotate(res, cv2.ROTATE_180)
    elif rotacion_grados == 270:
        res = cv2.rotate(res, cv2.ROTATE_90_COUNTERCLOCKWISE)

    if voltear_horizontal:
        res = cv2.flip(res, 1)
    if voltear_vertical:
        res = cv2.flip(res, 0)

    return res


def recortar_bordes_alfa(img_rgba):
    """
    Recorta automáticamente los márgenes 100% transparentes alrededor de la prenda.
    Garantiza que las esquinas y proporciones de la prenda correspondan exactamente a los
    extremos reales de la tela.
    """
    if img_rgba is None or img_rgba.shape[2] != 4:
        return img_rgba

    alpha = img_rgba[:, :, 3]
    pos = np.where(alpha > 10)
    if len(pos[0]) == 0 or len(pos[1]) == 0:
        return img_rgba

    ymin, ymax = np.min(pos[0]), np.max(pos[0])
    xmin, xmax = np.min(pos[1]), np.max(pos[1])

    return img_rgba[ymin:ymax + 1, xmin:xmax + 1].copy()


def agregar_margen_transparente(img_rgba, margen=MARGEN_TRANSPARENTE):
    """Agrega un borde 100% transparente para que la tela no toque el límite de la imagen."""
    if img_rgba is None:
        return None
    return cv2.copyMakeBorder(img_rgba, margen, margen, margen, margen,
                              cv2.BORDER_CONSTANT, value=(0, 0, 0, 0))


def preparar_imagen_prenda(img_rgba):
    """
    Deja la foto lista para el probador: recupera las partes de la prenda que se
    borraron junto con el fondo (por ejemplo, un cuello blanco), recorta los márgenes,
    agrega el borde transparente y pone el color de la tela debajo de la parte
    transparente (así no aparece un halo del color del fondo en los bordes).
    """
    img = recortar_bordes_alfa(recuperar_partes_borradas(img_rgba))
    return extender_color_de_la_tela(agregar_margen_transparente(img))


def holgura_de_talle(talle):
    """Factor de holgura de un talle (M si el talle no es conocido)."""
    return HOLGURA_TALLES.get(str(talle).upper(), HOLGURA_TALLES["M"])


def talle_inicial(prenda, preferido="M"):
    """Devuelve el talle preferido si la prenda lo tiene; si no, el más cercano."""
    talles = prenda.get("talles") or ["M"]
    if preferido in talles:
        return preferido
    orden = list(HOLGURA_TALLES.keys())
    pos = orden.index(preferido) if preferido in orden else orden.index("M")
    return min(talles, key=lambda t: abs((orden.index(t) if t in orden else pos) - pos))


def _agregar_espalda(item, ruta):
    """Agrega a la prenda su vista de espalda (foto propia o automática) y sus puntos de malla."""
    espalda, automatica = cargar_espalda(ruta, item["imagen_cv"], preparar_imagen_prenda)
    src_espalda, _ = detectar_puntos_clave_prenda(espalda)
    if src_espalda is None:
        espalda, src_espalda = item["imagen_cv"], item["src_puntos"]
    item["imagen_espalda_cv"] = espalda
    item["src_puntos_espalda"] = src_espalda
    item["espalda_automatica"] = automatica
    return item


def definicion_automatica(ruta):
    """Datos por defecto de un PNG de 'prendas/' que no está declarado en el catálogo."""
    nombre_archivo = os.path.splitext(os.path.basename(ruta))[0]
    return {
        "id": nombre_archivo,
        "nombre": nombre_archivo.replace("_", " ").title(),
        "precio": 18000,
        "color": "Colección",
        "talles": ["S", "M", "L"],
        "archivo": ruta,
        "descripcion": "Prenda de la colección boutique atelier.",
        "margen_hombros": 0.38,
        "margen_cuello": 0.20,
        "calce": "regular",
    }


def obtener_definiciones():
    """
    Devuelve los datos de las prendas guardados en MySQL. Si MySQL no responde,
    devuelve una lista vacía y las prendas de 'prendas/' se muestran con datos
    por defecto (precio, talles y medidas genéricos), así el probador no se cae.
    """
    if not USAR_MYSQL:
        print("[Catálogo] MySQL desactivado en config.py: las prendas usan datos por defecto.")
        return []
    try:
        from conexion_mysql import leer_prendas
        prendas = leer_prendas()
        if prendas:
            print(f"[Catálogo] {len(prendas)} prendas leídas de MySQL.")
        else:
            print("[Catálogo] La base MySQL no tiene prendas: ejecutá cargar_prendas_mysql.py.")
        return prendas
    except Exception as error:
        print(f"[Catálogo] No se pudo leer MySQL ({error}). "
              "Las prendas de 'prendas/' usan datos por defecto.")
        return []


def cargar_catalogo_completo():
    """
    Carga el catálogo de MySQL, precalcula los puntos anatómicos de
    la malla y detecta automáticamente cualquier prenda nueva en 'prendas/' sin romper nada.
    """
    catalogo_cargado = []
    rutas_procesadas = set()

    for item in obtener_definiciones():
        ruta = item["archivo"]
        if os.path.exists(ruta):
            img_rgba = cv2.imread(ruta, cv2.IMREAD_UNCHANGED)
            if img_rgba is not None and img_rgba.shape[2] == 4:
                # Aplicar orientación específica si fue declarada
                img_orientada = orientar_prenda(
                    img_rgba,
                    item.get("rotacion", 0),
                    item.get("voltear_horizontal", False),
                    item.get("voltear_vertical", False)
                )
                img_recortada = preparar_imagen_prenda(img_orientada)
                
                # Extraer puntos anatómicos de la prenda para la malla
                src_pts, tiene_mangas = detectar_puntos_clave_prenda(img_recortada)

                item_copia = dict(item)
                item_copia["imagen_cv"] = img_recortada
                item_copia["imagen_original_cv"] = img_orientada
                item_copia["src_puntos"] = src_pts
                item_copia["tiene_mangas"] = tiene_mangas
                # Logos y estampados aparte, para dibujarlos rígidos (sin deformarse)
                item_copia["imagen_lisa_cv"], item_copia["bloques_diseno"] = extraer_diseno(img_recortada)
                _agregar_espalda(item_copia, ruta)

                catalogo_cargado.append(item_copia)
                rutas_procesadas.add(os.path.abspath(ruta))

    # Auto-detección de prendas extras colocadas en la carpeta prendas/
    todas_rutas = glob.glob(os.path.join(CARPETA_PRENDAS, "*.png"))
    for ruta in todas_rutas:
        if os.path.abspath(ruta) not in rutas_procesadas and not es_archivo_espalda(ruta):
            img_rgba = cv2.imread(ruta, cv2.IMREAD_UNCHANGED)
            if img_rgba is not None and img_rgba.shape[2] == 4:
                img_recortada = preparar_imagen_prenda(img_rgba)
                src_pts, tiene_mangas = detectar_puntos_clave_prenda(img_recortada)

                catalogo_cargado.append({
                    **definicion_automatica(ruta),
                    "imagen_cv": img_recortada,
                    "imagen_original_cv": img_rgba,
                    "src_puntos": src_pts,
                    "tiene_mangas": tiene_mangas
                })
                catalogo_cargado[-1]["imagen_lisa_cv"], catalogo_cargado[-1]["bloques_diseno"] =                     extraer_diseno(img_recortada)
                _agregar_espalda(catalogo_cargado[-1], ruta)

    return catalogo_cargado
