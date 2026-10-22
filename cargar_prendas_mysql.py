# ==========================================================
# PROYECTO: PROBADOR VIRTUAL INTELIGENTE
# HERRAMIENTA: CARGAR LAS PRENDAS DE 'prendas/' EN MYSQL
# ==========================================================
# Uso (desde la carpeta del proyecto):
#     .venv\Scripts\python.exe cargar_prendas_mysql.py --crear-tablas
#
#   --crear-tablas  ejecuta antes base_datos/probador_virtual_mysql.sql
#                   (no borra nada: sólo crea lo que falta).
#   --actualizar    pisa los datos de las prendas que ya estaban en la base
#                   con los de catalogo.py (por defecto se dejan como están).
#   --stock N       stock inicial de cada talle nuevo (por defecto 0).

import argparse
import glob
import os
import sys

from catalogo import CARPETA_PRENDAS, CATALOGO_PRENDAS, definicion_automatica
from conexion_mysql import conectar, crear_tablas, guardar_prenda, leer_configuracion
from vista_espalda import es_archivo_espalda

SCRIPT_SQL = os.path.join("base_datos", "probador_virtual_mysql.sql")

# Categoría según cómo empieza el nombre del archivo
CATEGORIAS = {"polo": "Chombas", "remera": "Remeras", "top": "Tops"}


def categoria_de(prenda):
    nombre = os.path.splitext(os.path.basename(prenda["archivo"]))[0]
    prefijo = nombre.split("_")[0].lower()
    return CATEGORIAS.get(prefijo, "Otros")


def prendas_de_la_carpeta():
    """Las prendas declaradas en catalogo.py más cualquier PNG nuevo de 'prendas/'."""
    prendas = [p for p in CATALOGO_PRENDAS if os.path.exists(p["archivo"])]
    declaradas = {os.path.abspath(p["archivo"]) for p in prendas}
    for ruta in sorted(glob.glob(os.path.join(CARPETA_PRENDAS, "*.png"))):
        if os.path.abspath(ruta) not in declaradas and not es_archivo_espalda(ruta):
            prendas.append(definicion_automatica(ruta))
    return prendas


def main():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    parser = argparse.ArgumentParser(description="Carga las prendas de 'prendas/' en MySQL.")
    parser.add_argument("--crear-tablas", action="store_true")
    parser.add_argument("--actualizar", action="store_true")
    parser.add_argument("--stock", type=int, default=0)
    args = parser.parse_args()
    if args.stock < 0:
        parser.error("--stock no puede ser negativo")

    datos = leer_configuracion()
    print(f"Conectando a MySQL en {datos['host']}:{datos['port']} como '{datos['user']}'...")
    try:
        if args.crear_tablas:
            crear_tablas(SCRIPT_SQL)
            print(f"[OK] Tablas creadas o ya existentes ({SCRIPT_SQL}).")
        conexion = conectar()
    except Exception as error:
        print(f"[ERROR] {error}")
        print("Revisá base_datos/mysql.ini (copiá mysql.ini.ejemplo y completá la contraseña).")
        return 1

    contadores = {"nueva": 0, "actualizada": 0, "existente": 0}
    try:
        cursor = conexion.cursor()
        for prenda in prendas_de_la_carpeta():
            resultado = guardar_prenda(cursor, prenda, categoria_de(prenda),
                                       stock=args.stock, actualizar=args.actualizar)
            contadores[resultado] += 1
            print(f"  [{resultado}] {prenda['id']} - {prenda['nombre']}")
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
