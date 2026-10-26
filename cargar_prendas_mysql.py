# ==========================================================
# PROYECTO: PROBADOR VIRTUAL INTELIGENTE
# HERRAMIENTA: CARGAR EL CATÁLOGO EN MYSQL
# ==========================================================
# Uso (desde la carpeta del proyecto):
#     .venv\Scripts\python.exe cargar_prendas_mysql.py --crear-tablas
#
# 1. Carga las prendas de base_datos/catalogo_inicial.json (con sus colores, SKU,
#    talles, medidas y stock inicial) que todavía no estén en la base.
# 2. Saca del catálogo las prendas listadas en RETIRADAS (si se vendieron, quedan
#    'inactivas' para conservar el historial de ventas).
# 3. Registra con datos por defecto cualquier PNG nuevo de 'prendas/' que no esté
#    en el catálogo (después se corrigen en MySQL Workbench).
#
#   --crear-tablas    ejecuta antes base_datos/probador_virtual_mysql.sql (no borra
#                     nada: crea las tablas que falten).
#   --actualizar      pisa los datos de las prendas (nombre, precio, colores...) con
#                     los del JSON. El stock vendido NO se toca.
#   --reponer-stock   lleva a 'stock_por_variante' las variantes que tengan menos.

import argparse
import glob
import json
import os
import sys

from catalogo import CARPETA_PRENDAS, definicion_automatica
from conexion_mysql import (conectar, crear_tablas, guardar_prenda, leer_configuracion, borrar_prenda,
                            quitar_variantes_sobrantes)
from vista_espalda import es_archivo_espalda

SCRIPT_SQL = os.path.join("base_datos", "probador_virtual_mysql.sql")
CATALOGO_JSON = os.path.join("base_datos", "catalogo_inicial.json")

# Remeras dibujadas por programa (sin diseño real): fuera del catálogo
RETIRADAS = ["remera", "remera_azul", "remera_blanca", "remera_negra", "remera_roja"]

# Categoría según cómo empieza el nombre del archivo (prendas sin datos en el JSON)
CATEGORIAS = {"polo": "Chombas", "chomba": "Chombas", "remera": "Remeras", "top": "Tops", "buzo": "Buzos"}


def categoria_de(ruta):
    nombre = os.path.splitext(os.path.basename(ruta))[0]
    return CATEGORIAS.get(nombre.split("_")[0].lower(), "Otros")


def leer_catalogo_json():
    with open(CATALOGO_JSON, encoding="utf-8") as archivo:
        datos = json.load(archivo)
    tablas = datos.get("tablas_medidas", {})
    for prenda in datos["prendas"]:
        if "medidas_talles" not in prenda and prenda.get("medidas") in tablas:
            prenda["medidas_talles"] = {t: tablas[prenda["medidas"]][t] for t in prenda["talles"]}
    return datos


def reponer_stock(cursor, unidades):
    """Lleva a 'unidades' cada variante que tenga menos. Devuelve cuántas repuso."""
    cursor.execute("SELECT id_prenda, stock FROM prenda WHERE estado = 'activa' FOR UPDATE")
    repuestas = 0
    for id_prenda, stock in cursor.fetchall():
        variantes = json.loads(stock)
        bajas = [v for v in variantes.values() if v["stock"] < unidades]
        for variante in bajas:
            variante["stock"] = unidades
        if bajas:
            cursor.execute("UPDATE prenda SET stock = %s WHERE id_prenda = %s",
                           (json.dumps(variantes, ensure_ascii=False), id_prenda))
            repuestas += len(bajas)
    return repuestas


def main():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    parser = argparse.ArgumentParser(description="Carga el catálogo de prendas en MySQL.")
    parser.add_argument("--crear-tablas", action="store_true")
    parser.add_argument("--actualizar", action="store_true")
    parser.add_argument("--reponer-stock", action="store_true")
    args = parser.parse_args()

    datos = leer_configuracion()
    print(f"Conectando a MySQL en {datos['host']}:{datos['port']} como '{datos['user']}'...")
    try:
        if args.crear_tablas:
            crear_tablas(SCRIPT_SQL)
            print(f"[OK] Tablas creadas o actualizadas ({SCRIPT_SQL}).")
        conexion = conectar()
    except Exception as error:
        print(f"[ERROR] {error}")
        print("Revisá base_datos/mysql.ini (copiá mysql.ini.ejemplo y completá la contraseña).")
        return 1

    catalogo = leer_catalogo_json()
    stock_inicial = int(catalogo.get("stock_por_variante", 5))
    contadores = {"nueva": 0, "actualizada": 0, "existente": 0}
    try:
        cursor = conexion.cursor()
        for codigo in RETIRADAS:
            estado = borrar_prenda(cursor, codigo)
            if estado:
                print(f"  [{estado}] {codigo}")

        codigos_json = set()
        for prenda in catalogo["prendas"]:
            codigos_json.add(prenda["codigo"])
            resultado = guardar_prenda(cursor, prenda, stock=stock_inicial, actualizar=args.actualizar)
            borradas = quitar_variantes_sobrantes(cursor, prenda["codigo"], [c["nombre"] for c in prenda["colores"]])
            contadores[resultado] += 1
            extra = f" ({borradas} variantes de colores viejos quitadas)" if borradas else ""
            print(f"  [{resultado}] {prenda['sku']} {prenda['nombre']}{extra}")

        # PNG nuevos que no están ni en el JSON ni en la base
        cursor.execute("SELECT imagen_url FROM prenda")
        registradas = {os.path.abspath(f[0]) for f in cursor.fetchall()}
        for ruta in sorted(glob.glob(os.path.join(CARPETA_PRENDAS, "*.png"))):
            codigo = os.path.splitext(os.path.basename(ruta))[0]
            if (os.path.abspath(ruta) in registradas or codigo in codigos_json or codigo in RETIRADAS
                    or es_archivo_espalda(ruta)):
                continue
            prenda = definicion_automatica(ruta)
            prenda.update({"codigo": prenda["id"], "categoria": categoria_de(ruta),
                           "colores": [{"nombre": "Colección", "hex": None}], "color_foto": "Colección"})
            guardar_prenda(cursor, prenda, stock=stock_inicial)
            contadores["nueva"] += 1
            print(f"  [nueva, datos por defecto] {prenda['codigo']}")

        if args.reponer_stock:
            print(f"  [stock] {reponer_stock(cursor, stock_inicial)} variantes repuestas a {stock_inicial} unidades")
        conexion.commit()
    except Exception as error:
        conexion.rollback()
        print(f"[ERROR] No se guardó ningún cambio: {error}")
        return 1
    finally:
        conexion.close()

    print(f"[OK] Nuevas: {contadores['nueva']}, actualizadas: {contadores['actualizada']}, "
          f"sin cambios: {contadores['existente']}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
