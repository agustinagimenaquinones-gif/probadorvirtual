# ==========================================================
# PROYECTO: PROBADOR VIRTUAL INTELIGENTE - PÁGINA WEB
# MÓDULO: CONEXIÓN CON LA BASE DE SUPABASE (POSTGRESQL) DESDE VERCEL
# ==========================================================
# La base de la página está en Supabase (PostgreSQL). La conexión se toma de la
# variable de entorno DATABASE_URL (Vercel > Settings > Environment Variables), con la
# cadena del "Transaction pooler" de Supabase:
#     postgresql://postgres.<proyecto>:<contraseña>@aws-0-<región>.pooler.supabase.com:6543/postgres
# La contraseña nunca se escribe en el código.
#
# tienda.py (copiado del programa de escritorio) está escrito para MySQL. Este módulo
# le da lo mismo que le daba conexion_mysql.py: conectar() con cursores que devuelven
# diccionarios, start_transaction() y cursor.lastrowid después de un INSERT. Así las
# reglas de compra, stock, niveles y cupones son exactamente las del programa.

import json
import os
import re
from decimal import Decimal

ORDEN_TALLES = ["XXS", "XS", "S", "M", "L", "XL", "XXL", "Único"]
MEDIDAS = ("pecho", "cintura", "cadera", "hombros", "largo")

# Columna id de cada tabla (para devolver lastrowid como en MySQL)
ID_DE_TABLA = {"tienda": "id_tienda", "prenda": "id_prenda", "clientes": "id_cliente",
               "prueba": "id_prueba", "compra": "id_compra"}
_INSERT = re.compile(r"^\s*INSERT\s+INTO\s+(\w+)", re.IGNORECASE)


def hay_base_configurada():
    return bool(os.environ.get("DATABASE_URL"))


class _Cursor:
    def __init__(self, cursor):
        self._c = cursor
        self.lastrowid = None

    def execute(self, sql, parametros=None):
        tabla = _INSERT.match(sql)
        if tabla and tabla.group(1).lower() in ID_DE_TABLA and "RETURNING" not in sql.upper():
            sql = f"{sql} RETURNING {ID_DE_TABLA[tabla.group(1).lower()]}"
            self._c.execute(sql, parametros)
            fila = self._c.fetchone()
            self.lastrowid = fila[0] if isinstance(fila, (tuple, list)) else next(iter(fila.values()))
            return
        self._c.execute(sql, parametros)

    def fetchone(self):
        return self._c.fetchone()

    def fetchall(self):
        return self._c.fetchall()


class _Conexion:
    def __init__(self, conexion):
        self._c = conexion

    def cursor(self, dictionary=False):
        from psycopg.rows import dict_row
        return _Cursor(self._c.cursor(row_factory=dict_row) if dictionary else self._c.cursor())

    def start_transaction(self):
        pass  # en Postgres la transacción empieza sola con la primera consulta

    def commit(self):
        self._c.commit()

    def rollback(self):
        self._c.rollback()

    def close(self):
        self._c.close()


def conectar():
    import psycopg

    # prepare_threshold=None: el pooler de Supabase (modo transacción) no admite
    # consultas preparadas que queden guardadas entre pedidos
    return _Conexion(psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=8, prepare_threshold=None,
                                     autocommit=False))


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
