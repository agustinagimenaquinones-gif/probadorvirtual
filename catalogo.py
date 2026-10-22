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
# -------------------------------------------------------------------------
# CATÁLOGO DE PRENDAS (ESTRUCTURA MODULAR Y EXTENSIBLE)
# Puedes agregar aquí fácilmente nuevas prendas sin modificar la lógica del código.
# -------------------------------------------------------------------------
CATALOGO_PRENDAS = [
    {
        "id": "polo_ralph_lauren",
        "calce": "regular",
        "nombre": "Chomba Polo Ralph Lauren",
        "precio": 38500,
        "color": "Azul Marino y Blanco",
        "talles": ["S", "M", "L", "XL"],
        "archivo": "prendas/polo_ralph_lauren.png",
        "descripcion": "Chomba clásica Ralph Lauren azul marino con cuello estructurado, icónico Big Pony blanco, escudo '20' y número '3' bordado en la manga.",
        "margen_hombros": 0.38,
        "margen_cuello": 0.20,
        "voltear_horizontal": False,
        "rotacion": 0,
        "medidas_talles": {
            "S":  {"pecho": 94, "cintura": 86, "cadera": 94, "hombros": 43, "largo": 69},
            "M":  {"pecho": 100, "cintura": 92, "cadera": 100, "hombros": 45, "largo": 72},
            "L":  {"pecho": 106, "cintura": 98, "cadera": 106, "hombros": 47, "largo": 75},
            "XL": {"pecho": 112, "cintura": 104, "cadera": 112, "hombros": 49, "largo": 78},
        }
    },
    {
        "id": "top_asimetrico_negro",
        "calce": "entallado",
        "nombre": "Top Asimétrico Drapeado Negro",
        "precio": 34000,
        "color": "Negro Seda",
        "talles": ["S", "M", "L"],
        "archivo": "prendas/top_asimetrico_negro.png",
        "descripcion": "Exclusivo diseño de alta costura con escote halter drapeado, un hombro al descubierto y elegante fular lateral en satén negro profundo.",
        "margen_hombros": 0.16,
        "margen_cuello": 0.25,
        "voltear_horizontal": False,
        "rotacion": 0,
        "medidas_talles": {
            "S": {"pecho": 86, "cintura": 66, "cadera": 90, "hombros": 36, "largo": 76},
            "M": {"pecho": 92, "cintura": 72, "cadera": 96, "hombros": 38, "largo": 79},
            "L": {"pecho": 98, "cintura": 78, "cadera": 102, "hombros": 40, "largo": 82},
        }
    },
    {
        "id": "polo_azul_marino",
        "calce": "regular",
        "nombre": "Chomba Polo Azul Marino",
        "precio": 28500,
        "color": "Azul Marino y Blanco",
        "talles": ["S", "M", "L", "XL"],
        "archivo": "prendas/polo_azul_marino.png",
        "descripcion": "Chomba tipo polo azul marino con cuello blanco estructurado, tapeta y ribete en mangas.",
        "margen_hombros": 0.38,
        "margen_cuello": 0.20,
        "voltear_horizontal": False,
        "rotacion": 0,
        "medidas_talles": {
            "S":  {"pecho": 92, "cintura": 84, "cadera": 92, "hombros": 42, "largo": 68},
            "M":  {"pecho": 98, "cintura": 90, "cadera": 98, "hombros": 44, "largo": 71},
            "L":  {"pecho": 104, "cintura": 96, "cadera": 104, "hombros": 46, "largo": 74},
            "XL": {"pecho": 110, "cintura": 102, "cadera": 110, "hombros": 48, "largo": 77},
        }
    },
    {
        "id": "remera_blanca",
        "calce": "entallado",
        "nombre": "Remera Básica Blanca",
        "precio": 18000,
        "color": "Blanco",
        "talles": ["S", "M", "L"],
        "archivo": "prendas/remera_blanca.png",
        "descripcion": "Remera de algodón peinado con escote femenino suave, fresca y combinable.",
        "margen_hombros": 0.38,
        "margen_cuello": 0.20,
        "voltear_horizontal": False,
        "rotacion": 0,
        "medidas_talles": {
            "S": {"pecho": 88, "cintura": 70, "cadera": 92, "hombros": 39, "largo": 64},
            "M": {"pecho": 94, "cintura": 76, "cadera": 98, "hombros": 41, "largo": 66},
            "L": {"pecho": 100, "cintura": 82, "cadera": 104, "hombros": 43, "largo": 68},
        }
    },
    {
        "id": "remera_azul",
        "calce": "entallado",
        "nombre": "Remera Clásica Azul",
        "precio": 18000,
        "color": "Azul",
        "talles": ["S", "M", "L"],
        "archivo": "prendas/remera_azul.png",
        "descripcion": "Tono azul cobalto intenso de corte estilizado para un look diario impecable.",
        "margen_hombros": 0.38,
        "margen_cuello": 0.20,
        "voltear_horizontal": False,
        "rotacion": 0,
        "medidas_talles": {
            "S": {"pecho": 88, "cintura": 70, "cadera": 92, "hombros": 39, "largo": 64},
            "M": {"pecho": 94, "cintura": 76, "cadera": 98, "hombros": 41, "largo": 66},
            "L": {"pecho": 100, "cintura": 82, "cadera": 104, "hombros": 43, "largo": 68},
        }
    },
    {
        "id": "remera_negra",
        "calce": "entallado",
        "nombre": "Remera Urbana Negra",
        "precio": 19500,
        "color": "Negro",
        "talles": ["S", "M", "L", "XL"],
        "archivo": "prendas/remera_negra.png",
        "descripcion": "Prenda básica en negro profundo, entalle sofisticado y textura aterciopelada.",
        "margen_hombros": 0.38,
        "margen_cuello": 0.20,
        "voltear_horizontal": False,
        "rotacion": 0,
        "medidas_talles": {
            "S":  {"pecho": 88, "cintura": 70, "cadera": 92, "hombros": 39, "largo": 64},
            "M":  {"pecho": 94, "cintura": 76, "cadera": 98, "hombros": 41, "largo": 66},
            "L":  {"pecho": 100, "cintura": 82, "cadera": 104, "hombros": 43, "largo": 68},
            "XL": {"pecho": 106, "cintura": 88, "cadera": 110, "hombros": 45, "largo": 70},
        }
    },
    {
        "id": "remera_roja",
        "calce": "entallado",
        "nombre": "Remera Coral Roja",
        "precio": 18500,
        "color": "Rojo",
        "talles": ["S", "M", "L"],
        "archivo": "prendas/remera_roja.png",
        "descripcion": "Diseño en rojo frambuesa con escote femenino y costuras reforzadas.",
        "margen_hombros": 0.38,
        "margen_cuello": 0.20,
        "voltear_horizontal": False,
        "rotacion": 0,
        "medidas_talles": {
            "S": {"pecho": 88, "cintura": 70, "cadera": 92, "hombros": 39, "largo": 64},
            "M": {"pecho": 94, "cintura": 76, "cadera": 98, "hombros": 41, "largo": 66},
            "L": {"pecho": 100, "cintura": 82, "cadera": 104, "hombros": 43, "largo": 68},
        }
    },
    {
        "id": "top_satin",
        "calce": "entallado",
        "nombre": "Top Satinado Champagne",
        "precio": 24000,
        "color": "Champagne",
        "talles": ["S", "M"],
        "archivo": "prendas/top_satin_champagne.png",
        "descripcion": "Exclusivo top halter de satén de seda drapeado con cuello alto de alta costura.",
        "margen_hombros": 0.16,
        "margen_cuello": 0.26,
        "voltear_horizontal": False,
        "rotacion": 0,
        "medidas_talles": {
            "S": {"pecho": 86, "cintura": 68, "cadera": 90, "hombros": 36, "largo": 62},
            "M": {"pecho": 92, "cintura": 74, "cadera": 96, "hombros": 38, "largo": 65},
        }
    }
]


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
    preparar = lambda img: agregar_margen_transparente(recortar_bordes_alfa(img))
    espalda, automatica = cargar_espalda(ruta, item["imagen_cv"], preparar)
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
    Devuelve los datos de las prendas: de MySQL si está activado y responde,
    o del catálogo escrito en este archivo si no.
    """
    if USAR_MYSQL:
        try:
            from conexion_mysql import leer_prendas
            prendas = leer_prendas()
            if prendas:
                print(f"[Catálogo] {len(prendas)} prendas leídas de MySQL.")
                return prendas
            print("[Catálogo] La base MySQL no tiene prendas: ejecutá cargar_prendas_mysql.py. "
                  "Se usa el catálogo de catalogo.py.")
        except Exception as error:
            print(f"[Catálogo] No se pudo leer MySQL ({error}). Se usa el catálogo de catalogo.py.")
    return CATALOGO_PRENDAS


def cargar_catalogo_completo():
    """
    Carga el catálogo (MySQL o el definido acá), precalcula los puntos anatómicos de
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
                img_recortada = agregar_margen_transparente(recortar_bordes_alfa(img_orientada))
                
                # Extraer puntos anatómicos de la prenda para la malla
                src_pts, tiene_mangas = detectar_puntos_clave_prenda(img_recortada)

                item_copia = dict(item)
                item_copia["imagen_cv"] = img_recortada
                item_copia["imagen_original_cv"] = img_orientada
                item_copia["src_puntos"] = src_pts
                item_copia["tiene_mangas"] = tiene_mangas
                _agregar_espalda(item_copia, ruta)

                catalogo_cargado.append(item_copia)
                rutas_procesadas.add(os.path.abspath(ruta))

    # Auto-detección de prendas extras colocadas en la carpeta prendas/
    todas_rutas = glob.glob(os.path.join(CARPETA_PRENDAS, "*.png"))
    for ruta in todas_rutas:
        if os.path.abspath(ruta) not in rutas_procesadas and not es_archivo_espalda(ruta):
            img_rgba = cv2.imread(ruta, cv2.IMREAD_UNCHANGED)
            if img_rgba is not None and img_rgba.shape[2] == 4:
                img_recortada = agregar_margen_transparente(recortar_bordes_alfa(img_rgba))
                src_pts, tiene_mangas = detectar_puntos_clave_prenda(img_recortada)

                catalogo_cargado.append({
                    **definicion_automatica(ruta),
                    "imagen_cv": img_recortada,
                    "imagen_original_cv": img_rgba,
                    "src_puntos": src_pts,
                    "tiene_mangas": tiene_mangas
                })
                _agregar_espalda(catalogo_cargado[-1], ruta)

    return catalogo_cargado
