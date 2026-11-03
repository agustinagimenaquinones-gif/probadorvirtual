# ==========================================================
# PROYECTO: PROBADOR VIRTUAL INTELIGENTE - PÁGINA WEB
# HERRAMIENTA: CARGAR LAS TABLAS Y EL CATÁLOGO EN SUPABASE
# ==========================================================
# Uso (desde la carpeta pagina web, con su entorno de Python):
#     .venv\Scripts\python.exe scripts\cargar_a_supabase.py
#
# Ejecuta supabase/esquema.sql y supabase/catalogo.sql. Pide la contraseña de la base
# sin mostrarla y no la guarda en ningún lado. Se puede repetir sin duplicar nada, y
# no pisa el stock que ya se vendió por la web.

import getpass
import os

import psycopg

SERVIDOR = "aws-1-us-west-2.pooler.supabase.com"
USUARIO = "postgres.nwjvgikunyevmkeuajgu"
PUERTO_SESION = 5432  # modo sesión: el indicado para crear tablas
TABLAS = ("tienda", "prenda", "clientes", "prueba", "compra")
CARPETA_SQL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "supabase")


def contar(cursor):
    """Filas de cada tabla (None si la tabla todavía no existe)."""
    filas = {}
    for tabla in TABLAS:
        cursor.execute("SELECT to_regclass(%s)", (f"public.{tabla}",))
        if cursor.fetchone()[0] is None:
            filas[tabla] = None
        else:
            cursor.execute(f"SELECT count(*) FROM {tabla}")
            filas[tabla] = cursor.fetchone()[0]
    return filas


def ejecutar_archivo(cursor, nombre):
    with open(os.path.join(CARPETA_SQL, nombre), encoding="utf-8") as archivo:
        cursor.execute(archivo.read())
    print(f"[OK] {nombre}")


def main():
    contrasena = getpass.getpass("Contraseña de la base de Supabase (no se ve al escribir): ")
    with psycopg.connect(host=SERVIDOR, port=PUERTO_SESION, dbname="postgres", user=USUARIO, password=contrasena,
                         sslmode="require", connect_timeout=15, autocommit=True) as conexion:
        cursor = conexion.cursor()
        antes = contar(cursor)
        print("Antes:  ", antes)
        if any(antes.values()):
            respuesta = input("La base ya tiene datos. Se actualizan las prendas, sin tocar el stock. ¿Seguir? (s/n): ")
            if respuesta.strip().lower() != "s":
                print("No se cargó nada.")
                return
        ejecutar_archivo(cursor, "esquema.sql")
        ejecutar_archivo(cursor, "catalogo.sql")
        print("Después:", contar(cursor))
        cursor.execute("SELECT count(*) FROM prenda WHERE estado = 'activa'")
        print("Prendas activas:", cursor.fetchone()[0])


if __name__ == "__main__":
    try:
        main()
    except psycopg.OperationalError as error:
        print("[ERROR] No se pudo conectar:", str(error).strip()[:300])
