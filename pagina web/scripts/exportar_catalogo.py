# ==========================================================
# PROYECTO: PROBADOR VIRTUAL INTELIGENTE - PÁGINA WEB
# HERRAMIENTA: EXPORTAR EL CATÁLOGO DEL PROBADOR A LA PÁGINA WEB
# ==========================================================
# Uso (desde la carpeta del proyecto principal, con su entorno de Python):
#     .venv\Scripts\python.exe "pagina web\scripts\exportar_catalogo.py"
#
# 1. Lee el catálogo igual que el probador de escritorio (MySQL + carpeta prendas/),
#    con cada prenda ya recortada y sus 23 puntos de la malla calculados.
# 2. Guarda en pagina web/public/prendas/ una imagen WebP por prenda y por color
#    (los colores que no son el de la foto se tiñen con el mismo algoritmo).
# 3. Escribe pagina web/public/datos/catalogo.json con los datos de cada prenda y
#    los puntos de su malla (el probador web los usa para deformarla sobre el cuerpo).
# 4. Copia tienda.py en pagina web/api/_lib/ para que la API use las mismas reglas
#    de compra, puntos, niveles y cupones que el programa de escritorio.
#
# Volver a correrlo cada vez que se agreguen prendas o se cambien colores.

import json
import os
import re
import shutil
import sys
import unicodedata

RAIZ_WEB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAIZ_PROYECTO = os.path.dirname(RAIZ_WEB)
os.chdir(RAIZ_PROYECTO)
sys.path.insert(0, RAIZ_PROYECTO)

import cv2  # noqa: E402

from catalogo import cargar_catalogo_completo  # noqa: E402
from colores_prenda import recolorear  # noqa: E402

CARPETA_IMAGENES = os.path.join(RAIZ_WEB, "public", "prendas")
ARCHIVO_JSON = os.path.join(RAIZ_WEB, "public", "datos", "catalogo.json")
ALTO_MAXIMO = 760      # px: suficiente para la cámara y liviano para el celular
CALIDAD_WEBP = 88


def nombre_archivo(texto):
    """'Azul Marino' -> 'azul-marino' (sin tildes ni espacios, para las URLs)."""
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", texto.lower()).strip("-") or "color"


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    os.makedirs(CARPETA_IMAGENES, exist_ok=True)
    os.makedirs(os.path.dirname(ARCHIVO_JSON), exist_ok=True)
    for viejo in os.listdir(CARPETA_IMAGENES):
        os.remove(os.path.join(CARPETA_IMAGENES, viejo))

    prendas = []
    for prenda in cargar_catalogo_completo():
        imagen = prenda["imagen_cv"]
        alto, ancho = imagen.shape[:2]
        escala = min(1.0, ALTO_MAXIMO / float(alto))
        if escala < 1.0:
            imagen = cv2.resize(imagen, (int(round(ancho * escala)), int(round(alto * escala))),
                                interpolation=cv2.INTER_AREA)
        colores = prenda.get("colores") or [{"nombre": prenda.get("color", "Original"), "hex": None, "es_foto": True}]
        imagenes = {}
        for color in colores:
            version = imagen if color.get("es_foto") or not color.get("hex") else recolorear(imagen, color["hex"])
            archivo = f"{prenda['id']}__{nombre_archivo(color['nombre'])}.webp"
            cv2.imwrite(os.path.join(CARPETA_IMAGENES, archivo), version, [cv2.IMWRITE_WEBP_QUALITY, CALIDAD_WEBP])
            imagenes[color["nombre"]] = f"prendas/{archivo}"
        stock = prenda.get("stock") or {}
        prendas.append({
            "codigo": prenda["id"],
            "id_prenda": prenda.get("id_prenda"),
            "sku": prenda.get("sku", ""),
            "nombre": prenda["nombre"],
            "descripcion": prenda.get("descripcion", ""),
            "categoria": prenda.get("categoria", "Otros"),
            "genero": prenda.get("genero", "unisex"),
            "calce": prenda.get("calce", "regular"),
            "precio": prenda.get("precio", 0),
            "colores": [{"nombre": c["nombre"], "hex": c.get("hex"), "es_foto": bool(c.get("es_foto"))}
                        for c in colores],
            "talles": prenda.get("talles") or ["M"],
            "medidas_talles": prenda.get("medidas_talles") or {},
            # Stock al momento de exportar: la página lo usa si la API no tiene base
            "stock": {f"{c}|{t}": n for (c, t), n in stock.items()},
            "imagenes": imagenes,
            "ancho": imagen.shape[1],
            "alto": imagen.shape[0],
            "tiene_mangas": bool(prenda.get("tiene_mangas", True)),
            "puntos": {k: [round(float(x) * escala, 1), round(float(y) * escala, 1)]
                       for k, (x, y) in prenda["src_puntos"].items()},
        })
        print(f"[OK] {prenda['nombre']}: {len(imagenes)} color(es)")

    with open(ARCHIVO_JSON, "w", encoding="utf-8") as archivo:
        json.dump({"prendas": prendas}, archivo, ensure_ascii=False, indent=1)

    shutil.copy(os.path.join(RAIZ_PROYECTO, "tienda.py"), os.path.join(RAIZ_WEB, "api", "_lib", "tienda.py"))
    print(f"\n{len(prendas)} prendas exportadas a {ARCHIVO_JSON}")
    print("tienda.py copiado a pagina web/api/_lib/")


if __name__ == "__main__":
    main()
