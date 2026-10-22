# ==========================================================
# PROYECTO: PROBADOR VIRTUAL INTELIGENTE
# MÓDULO: CONEXIÓN CON LA BASE DE DATOS MYSQL
# ==========================================================
# Los datos de conexión se leen de base_datos/mysql.ini (copiar mysql.ini.ejemplo)
# o de las variables de entorno PROBADOR_MYSQL_HOST, _PORT, _USER, _PASSWORD y
# _DATABASE, que tienen prioridad. La contraseña nunca se guarda en el código.

import configparser
import os
import re
from decimal import Decimal

from config import MYSQL_ARCHIVO_CONFIG, MYSQL_TIEMPO_ESPERA

CONFIG_POR_DEFECTO = {
    "host": "localhost",
    "port": "3306",
    "user": "root",
    "password": "",
    "database": "probador_virtual",
}


def leer_configuracion():
    """Combina los valores por defecto, el archivo mysql.ini y las variables de entorno."""
    datos = dict(CONFIG_POR_DEFECTO)
    if os.path.exists(MYSQL_ARCHIVO_CONFIG):
        parser = configparser.ConfigParser()
        parser.read(MYSQL_ARCHIVO_CONFIG, encoding="utf-8")
        if parser.has_section("mysql"):
            datos.update({k: v for k, v in parser.items("mysql") if k in datos})
    for clave in datos:
        valor = os.environ.get(f"PROBADOR_MYSQL_{clave.upper()}")
        if valor is not None:
            datos[clave] = valor
    datos["port"] = int(datos["port"])
    return datos


def conectar(usar_base=True):
    """Abre una conexión. Con usar_base=False no elige base (sirve para crearla)."""
    import mysql.connector  # se importa acá para que el probador funcione sin el paquete

    datos = leer_configuracion()
    if not usar_base:
        datos.pop("database")
    return mysql.connector.connect(
        **datos,
        charset="utf8mb4",
        collation="utf8mb4_unicode_ci",
        connection_timeout=MYSQL_TIEMPO_ESPERA,
        autocommit=False,
    )


# -------------------------------------------------------------------------
# CREACIÓN DE TABLAS A PARTIR DEL SCRIPT .SQL
# -------------------------------------------------------------------------
def dividir_script_sql(texto):
    """
    Separa un script en sentencias sueltas respetando los bloques DELIMITER
    (los usan los triggers, que tienen ';' adentro). Ignora los comentarios '--'.
    """
    sentencias = []
    delimitador = ";"
    actual = []
    for linea in texto.splitlines():
        limpia = linea.strip()
        if limpia.startswith("--") or (not actual and not limpia):
            continue
        cambio = re.match(r"(?i)^DELIMITER\s+(\S+)$", limpia)
        if cambio:
            delimitador = cambio.group(1)
            continue
        actual.append(linea)
        if limpia.endswith(delimitador):
            sentencia = "\n".join(actual).rstrip()[: -len(delimitador)].strip()
            if sentencia:
                sentencias.append(sentencia)
            actual = []
    resto = "\n".join(actual).strip()
    if resto:
        sentencias.append(resto)
    return sentencias


def crear_tablas(ruta_sql):
    """Ejecuta el script que crea la base, las tablas, los triggers y los talles."""
    with open(ruta_sql, encoding="utf-8") as archivo:
        sentencias = dividir_script_sql(archivo.read())
    conexion = conectar(usar_base=False)
    try:
        cursor = conexion.cursor()
        for sentencia in sentencias:
            cursor.execute(sentencia)
        conexion.commit()
    finally:
        conexion.close()


# -------------------------------------------------------------------------
# LECTURA DEL CATÁLOGO
# -------------------------------------------------------------------------
def _numero(valor):
    """Convierte los DECIMAL de MySQL: 18000.00 -> 18000 y 0.38 -> 0.38."""
    if isinstance(valor, Decimal):
        return int(valor) if valor == valor.to_integral_value() else float(valor)
    return valor


def leer_prendas():
    """
    Devuelve las prendas activas con la misma forma que catalogo.CATALOGO_PRENDAS
    (id, nombre, precio, color, talles, archivo, medidas_talles, etc.).
    """
    conexion = conectar()
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute(
            "SELECT id_prenda, codigo, nombre, descripcion, precio, imagen_url, calce, "
            "margen_hombros, margen_cuello, rotacion, voltear_horizontal, voltear_vertical "
            "FROM prendas WHERE estado = 'activa' ORDER BY id_prenda"
        )
        filas = cursor.fetchall()

        # Talles y colores de cada prenda, según su inventario
        cursor.execute(
            "SELECT i.id_prenda, t.nombre AS talle, t.orden, c.nombre AS color "
            "FROM inventario i "
            "JOIN talles t ON t.id_talle = i.id_talle "
            "JOIN colores c ON c.id_color = i.id_color "
            "ORDER BY t.orden, c.nombre"
        )
        talles, colores = {}, {}
        for fila in cursor.fetchall():
            lista_t = talles.setdefault(fila["id_prenda"], [])
            if fila["talle"] not in lista_t:
                lista_t.append(fila["talle"])
            lista_c = colores.setdefault(fila["id_prenda"], [])
            if fila["color"] not in lista_c:
                lista_c.append(fila["color"])

        cursor.execute(
            "SELECT m.id_prenda, t.nombre AS talle, m.pecho, m.cintura, m.cadera, m.hombros, m.largo "
            "FROM medidas_talle m JOIN talles t ON t.id_talle = m.id_talle ORDER BY t.orden"
        )
        medidas = {}
        for fila in cursor.fetchall():
            medidas.setdefault(fila["id_prenda"], {})[fila["talle"]] = {
                k: int(fila[k]) for k in ("pecho", "cintura", "cadera", "hombros", "largo")
            }
    finally:
        conexion.close()

    prendas = []
    for fila in filas:
        id_prenda = fila["id_prenda"]
        medidas_prenda = medidas.get(id_prenda, {})
        prendas.append({
            "id": fila["codigo"],
            "id_prenda": id_prenda,
            "calce": fila["calce"],
            "nombre": fila["nombre"],
            "precio": _numero(fila["precio"]),
            "color": " / ".join(colores.get(id_prenda, [])) or "Colección",
            "talles": talles.get(id_prenda) or list(medidas_prenda) or ["S", "M", "L"],
            "archivo": fila["imagen_url"],
            "descripcion": fila["descripcion"] or "",
            "margen_hombros": _numero(fila["margen_hombros"]),
            "margen_cuello": _numero(fila["margen_cuello"]),
            "voltear_horizontal": bool(fila["voltear_horizontal"]),
            "voltear_vertical": bool(fila["voltear_vertical"]),
            "rotacion": int(fila["rotacion"]),
            "medidas_talles": medidas_prenda,
        })
    return prendas


# -------------------------------------------------------------------------
# CARGA DE PRENDAS
# -------------------------------------------------------------------------
def _id_por_nombre(cursor, tabla, columna_id, nombre, crear=False):
    cursor.execute(f"SELECT {columna_id} FROM {tabla} WHERE nombre = %s", (nombre,))
    fila = cursor.fetchone()
    if fila:
        return fila[0]
    if not crear:
        raise ValueError(f"No existe '{nombre}' en la tabla {tabla}")
    cursor.execute(f"INSERT INTO {tabla} (nombre) VALUES (%s)", (nombre,))
    return cursor.lastrowid


def guardar_prenda(cursor, prenda, categoria, stock=0, actualizar=False):
    """
    Guarda una prenda con su color, sus talles en el inventario y sus medidas.
    Devuelve 'nueva', 'actualizada' o 'existente'. Si la prenda ya está y
    actualizar es False, no se toca (para no pisar cambios hechos en la base).
    """
    cursor.execute("SELECT id_prenda FROM prendas WHERE codigo = %s", (prenda["id"],))
    fila = cursor.fetchone()
    if fila and not actualizar:
        return "existente"

    valores = (
        prenda["nombre"], prenda.get("descripcion", ""), categoria, prenda.get("precio", 0),
        prenda["archivo"].replace("\\", "/"), prenda.get("calce", "regular"),
        prenda.get("margen_hombros", 0.38), prenda.get("margen_cuello", 0.20),
        prenda.get("rotacion", 0), bool(prenda.get("voltear_horizontal", False)),
        bool(prenda.get("voltear_vertical", False)),
    )
    if fila:
        id_prenda = fila[0]
        cursor.execute(
            "UPDATE prendas SET nombre = %s, descripcion = %s, categoria = %s, precio = %s, "
            "imagen_url = %s, calce = %s, margen_hombros = %s, margen_cuello = %s, "
            "rotacion = %s, voltear_horizontal = %s, voltear_vertical = %s "
            "WHERE id_prenda = %s",
            valores + (id_prenda,),
        )
        resultado = "actualizada"
    else:
        cursor.execute(
            "INSERT INTO prendas (nombre, descripcion, categoria, precio, imagen_url, calce, "
            "margen_hombros, margen_cuello, rotacion, voltear_horizontal, voltear_vertical, codigo) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            valores + (prenda["id"],),
        )
        id_prenda = cursor.lastrowid
        resultado = "nueva"

    id_color = _id_por_nombre(cursor, "colores", "id_color", prenda.get("color", "Colección"), crear=True)
    for talle in prenda.get("talles") or []:
        id_talle = _id_por_nombre(cursor, "talles", "id_talle", talle)
        # Si la variante ya existe se conserva su stock.
        cursor.execute(
            "INSERT IGNORE INTO inventario (id_prenda, id_talle, id_color, stock) "
            "VALUES (%s, %s, %s, %s)",
            (id_prenda, id_talle, id_color, stock),
        )
    for talle, m in (prenda.get("medidas_talles") or {}).items():
        id_talle = _id_por_nombre(cursor, "talles", "id_talle", talle)
        cursor.execute(
            "INSERT INTO medidas_talle (id_prenda, id_talle, pecho, cintura, cadera, hombros, largo) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) AS nueva "
            "ON DUPLICATE KEY UPDATE pecho = nueva.pecho, cintura = nueva.cintura, "
            "cadera = nueva.cadera, hombros = nueva.hombros, largo = nueva.largo",
            (id_prenda, id_talle, m["pecho"], m["cintura"], m["cadera"], m["hombros"], m["largo"]),
        )
    return resultado
