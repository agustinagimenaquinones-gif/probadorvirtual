# ==========================================================
# PROYECTO: PROBADOR VIRTUAL INTELIGENTE
# HERRAMIENTA: REGISTRAR EN MYSQL LAS PRENDAS NUEVAS DE 'prendas/'
# ==========================================================
# El catálogo vive en MySQL. Cuando se copia un PNG nuevo en 'prendas/', este
# script lo registra con datos por defecto (precio, talles S/M/L, calce regular),
# que después se corrigen en MySQL Workbench. Las prendas que ya están en la base
# no se tocan.
#
# Uso (desde la carpeta del proyecto):
#     .venv\Scripts\python.exe cargar_prendas_mysql.py
#
#   --crear-tablas  ejecuta antes base_datos/probador_virtual_mysql.sql
#                   (no borra nada: sólo crea lo que falta).
#   --stock N       stock inicial de cada talle nuevo (por defecto 0).

import argparse
import glob
import os
import sys

from catalogo import CARPETA_PRENDAS, definicion_automatica
from conexion_mysql import conectar, crear_tablas, guardar_prenda, leer_configuracion
from vista_espalda import es_archivo_espalda

SCRIPT_SQL = os.path.join("base_datos", "probador_virtual_mysql.sql")

# Categoría según cómo empieza el nombre del archivo
CATEGORIAS = {"polo": "Chombas", "remera": "Remeras", "top": "Tops"}


def categoria_de(prenda):
    nombre = os.path.splitext(os.path.basename(prenda["archivo"]))[0]
    prefijo = nombre.split("_")[0].lower()
    return CATEGORIAS.get(prefijo, "Otros")


def rutas_registradas(cursor):
    """Rutas de imagen de todas las prendas de la base (activas o no)."""
    cursor.execute("SELECT imagen_url FROM prendas")
    return {os.path.abspath(fila[0]) for fila in cursor.fetchall()}


def prendas_nuevas_de_la_carpeta(registradas):
    """Los PNG de 'prendas/' que todavía no están en la base."""
    return [
        definicion_automatica(ruta)
        for ruta in sorted(glob.glob(os.path.join(CARPETA_PRENDAS, "*.png")))
        if os.path.abspath(ruta) not in registradas and not es_archivo_espalda(ruta)
    ]


def main():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    parser = argparse.ArgumentParser(description="Registra en MySQL las prendas nuevas de 'prendas/'.")
    parser.add_argument("--crear-tablas", action="store_true")
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

    nuevas = 0
    try:
        cursor = conexion.cursor()
        for prenda in prendas_nuevas_de_la_carpeta(rutas_registradas(cursor)):
            if guardar_prenda(cursor, prenda, categoria_de(prenda), stock=args.stock) == "nueva":
                nuevas += 1
                print(f"  [nueva] {prenda['id']} - {prenda['nombre']}")
        conexion.commit()
    except Exception as error:
        conexion.rollback()
        print(f"[ERROR] No se guardó ningún cambio: {error}")
        return 1
    finally:
        conexion.close()

    print(f"[OK] Prendas nuevas registradas: {nuevas}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
