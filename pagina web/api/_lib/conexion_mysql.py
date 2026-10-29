# ==========================================================
# PROYECTO: PROBADOR VIRTUAL INTELIGENTE - PÁGINA WEB
# MÓDULO: CONEXIÓN CON MYSQL DESDE VERCEL
# ==========================================================
# Versión para la nube de conexion_mysql.py: los datos de conexión vienen SÓLO de
# variables de entorno (se cargan en Vercel > Settings > Environment Variables),
# nunca de un archivo. Son las mismas que acepta el programa de escritorio:
#     PROBADOR_MYSQL_HOST, PROBADOR_MYSQL_PORT, PROBADOR_MYSQL_USER,
#     PROBADOR_MYSQL_PASSWORD, PROBADOR_MYSQL_DATABASE
#     PROBADOR_MYSQL_SSL=1   (las bases en la nube piden conexión cifrada)
# tienda.py (copiado del proyecto) importa de acá conectar() y clave_variante().

import json
import os
from decimal import Decimal

ORDEN_TALLES = ["XXS", "XS", "S", "M", "L", "XL", "XXL", "Único"]
MEDIDAS = ("pecho", "cintura", "cadera", "hombros", "largo")


def hay_base_configurada():
    return bool(os.environ.get("PROBADOR_MYSQL_HOST"))


def conectar():
    import mysql.connector

    datos = {
        "host": os.environ.get("PROBADOR_MYSQL_HOST", "localhost"),
        "port": int(os.environ.get("PROBADOR_MYSQL_PORT", "3306")),
        "user": os.environ.get("PROBADOR_MYSQL_USER", "root"),
        "password": os.environ.get("PROBADOR_MYSQL_PASSWORD", ""),
        "database": os.environ.get("PROBADOR_MYSQL_DATABASE", "probador_virtual"),
    }
    if os.environ.get("PROBADOR_MYSQL_SSL", "0") == "1":
        import certifi
        datos.update(ssl_ca=certifi.where(), ssl_verify_cert=True, ssl_disabled=False)
    return mysql.connector.connect(**datos, charset="utf8mb4", collation="utf8mb4_unicode_ci",
                                   connection_timeout=8, autocommit=False, use_pure=True)


def _json(valor, vacio):
    if valor is None:
        return vacio
    if isinstance(valor, (bytes, bytearray)):
        valor = valor.decode("utf-8")
    return json.loads(valor) if isinstance(valor, str) else valor


def _numero(valor):
    if isinstance(valor, Decimal):
        return int(valor) if valor == valor.to_integral_value() else float(valor)
    return valor


def clave_variante(color, talle):
    """Clave de una variante en la columna prenda.stock: 'Azul Marino|M'."""
    return f"{color}|{talle}"


def leer_prendas():
    """Prendas activas con su precio y stock por variante ({'Color|Talle': unidades})."""
    conexion = conectar()
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute("SELECT id_prenda, codigo, sku, nombre, descripcion, categoria, genero, precio, calce, "
                       "colores, talles, stock FROM prenda WHERE estado = 'activa' ORDER BY categoria, sku, id_prenda")
        filas = cursor.fetchall()
    finally:
        conexion.close()
    prendas = []
    for fila in filas:
        talles = sorted(_json(fila["talles"], []),
                        key=lambda t: ORDEN_TALLES.index(t["talle"]) if t["talle"] in ORDEN_TALLES else 99)
        prendas.append({
            "codigo": fila["codigo"],
            "id_prenda": fila["id_prenda"],
            "sku": fila["sku"] or "",
            "nombre": fila["nombre"],
            "descripcion": fila["descripcion"] or "",
            "categoria": fila["categoria"],
            "genero": fila["genero"],
            "calce": fila["calce"],
            "precio": _numero(fila["precio"]),
            "talles": [t["talle"] for t in talles],
            "medidas_talles": {t["talle"]: {k: int(t[k]) for k in MEDIDAS}
                               for t in talles if all(t.get(k) is not None for k in MEDIDAS)},
            "stock": {clave: int(v.get("stock", 0)) for clave, v in _json(fila["stock"], {}).items()},
        })
    return prendas
