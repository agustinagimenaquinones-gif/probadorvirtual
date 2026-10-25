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
import unicodedata
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
# CREACIÓN Y ACTUALIZACIÓN DE TABLAS
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


# Columnas agregadas después de la primera versión de la base. Las de ANTES se
# agregan antes de correr el script (la vista vista_stock las usa); las de DESPUÉS,
# cuando ya existen las tablas nuevas a las que apuntan.
COLUMNAS_ANTES = [
    ("colores", "hex", "ALTER TABLE colores ADD COLUMN hex CHAR(7) NULL"),
    ("prendas", "sku", "ALTER TABLE prendas ADD COLUMN sku VARCHAR(20) NULL UNIQUE AFTER codigo"),
    ("prendas", "id_color_foto",
     "ALTER TABLE prendas ADD COLUMN id_color_foto INT NULL AFTER imagen_url, "
     "ADD CONSTRAINT fk_prendas_color_foto FOREIGN KEY (id_color_foto) REFERENCES colores(id_color) "
     "ON UPDATE CASCADE ON DELETE SET NULL"),
    ("inventario", "sku", "ALTER TABLE inventario ADD COLUMN sku VARCHAR(40) NULL UNIQUE AFTER id_color"),
]
COLUMNAS_DESPUES = [
    ("compras", "id_pedido",
     "ALTER TABLE compras ADD COLUMN id_pedido INT NULL AFTER id_compra, "
     "ADD CONSTRAINT fk_compras_pedido FOREIGN KEY (id_pedido) REFERENCES pedidos(id_pedido) "
     "ON UPDATE CASCADE ON DELETE CASCADE"),
]


def _agregar_columnas_faltantes(cursor, base, columnas):
    for tabla, columna, alter in columnas:
        cursor.execute("SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s",
                       (base, tabla))
        if cursor.fetchone()[0] == 0:
            continue  # la tabla todavía no existe: el script la crea completa
        cursor.execute("SELECT COUNT(*) FROM information_schema.COLUMNS "
                       "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND COLUMN_NAME = %s", (base, tabla, columna))
        if cursor.fetchone()[0] == 0:
            cursor.execute(alter)
            print(f"  [migración] {tabla}.{columna} agregada")


def crear_tablas(ruta_sql):
    """
    Crea la base, las tablas, los triggers, los talles y los niveles de fidelidad.
    Si la base ya existía, le agrega las columnas nuevas sin borrar datos.
    """
    with open(ruta_sql, encoding="utf-8") as archivo:
        sentencias = dividir_script_sql(archivo.read())
    base = leer_configuracion()["database"]
    conexion = conectar(usar_base=False)
    try:
        cursor = conexion.cursor()
        cursor.execute("SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = %s", (base,))
        if cursor.fetchone()[0]:
            cursor.execute(f"USE `{base}`")
            _agregar_columnas_faltantes(cursor, base, COLUMNAS_ANTES)
        for sentencia in sentencias:
            cursor.execute(sentencia)
        _agregar_columnas_faltantes(cursor, base, COLUMNAS_DESPUES)
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
    Devuelve las prendas activas como diccionarios que usa el probador
    (id, sku, nombre, precio, colores, talles, stock, archivo, medidas_talles, etc.).

    colores: [{"nombre", "hex", "es_foto"}] — el primero es el de la foto.
    stock: {(color, talle): unidades}
    """
    conexion = conectar()
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute(
            "SELECT p.id_prenda, p.codigo, p.sku, p.nombre, p.descripcion, p.categoria, p.genero, p.precio, "
            "p.imagen_url, p.calce, p.margen_hombros, p.margen_cuello, p.rotacion, p.voltear_horizontal, "
            "p.voltear_vertical, cf.nombre AS color_foto "
            "FROM prendas p LEFT JOIN colores cf ON cf.id_color = p.id_color_foto "
            "WHERE p.estado = 'activa' ORDER BY p.categoria, p.sku, p.id_prenda"
        )
        filas = cursor.fetchall()

        # Talles, colores y stock de cada prenda, según su inventario
        cursor.execute(
            "SELECT i.id_prenda, i.sku, i.stock, t.nombre AS talle, t.orden, c.nombre AS color, c.hex "
            "FROM inventario i "
            "JOIN talles t ON t.id_talle = i.id_talle "
            "JOIN colores c ON c.id_color = i.id_color "
            "ORDER BY i.id_inventario"
        )
        talles, colores, stock, skus = {}, {}, {}, {}
        for fila in cursor.fetchall():
            idp = fila["id_prenda"]
            talles.setdefault(idp, {})[fila["talle"]] = fila["orden"]
            lista_c = colores.setdefault(idp, [])
            if all(c["nombre"] != fila["color"] for c in lista_c):
                lista_c.append({"nombre": fila["color"], "hex": fila["hex"]})
            stock.setdefault(idp, {})[(fila["color"], fila["talle"])] = int(fila["stock"])
            skus.setdefault(idp, {})[(fila["color"], fila["talle"])] = fila["sku"]

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
        lista_colores = colores.get(id_prenda, [])
        # El color de la foto va primero; los demás se generan tiñendo la foto
        foto = fila["color_foto"]
        lista_colores.sort(key=lambda c: c["nombre"] != foto)
        for c in lista_colores:
            c["es_foto"] = c["nombre"] == foto or (foto is None and c is lista_colores[0])
        orden_talles = talles.get(id_prenda, {})
        prendas.append({
            "id": fila["codigo"],
            "id_prenda": id_prenda,
            "sku": fila["sku"] or "",
            "categoria": fila["categoria"],
            "genero": fila["genero"],
            "calce": fila["calce"],
            "nombre": fila["nombre"],
            "precio": _numero(fila["precio"]),
            "colores": lista_colores,
            "color": " / ".join(c["nombre"] for c in lista_colores) or "Colección",
            "talles": sorted(orden_talles, key=orden_talles.get) or list(medidas_prenda) or ["S", "M", "L"],
            "stock": stock.get(id_prenda, {}),
            "skus": skus.get(id_prenda, {}),
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


def leer_stock(id_prenda):
    """Stock actual de una prenda: {(color, talle): unidades} (para refrescar la galería)."""
    conexion = conectar()
    try:
        cursor = conexion.cursor()
        cursor.execute(
            "SELECT c.nombre, t.nombre, i.stock FROM inventario i "
            "JOIN talles t ON t.id_talle = i.id_talle JOIN colores c ON c.id_color = i.id_color "
            "WHERE i.id_prenda = %s", (id_prenda,))
        return {(color, talle): int(st) for color, talle, st in cursor.fetchall()}
    finally:
        conexion.close()


# -------------------------------------------------------------------------
# CARGA DEL CATÁLOGO
# -------------------------------------------------------------------------
def abreviatura_color(nombre):
    """'Negro' -> NEG, 'Azul Marino' -> AZM, 'Blanco con Lunares' -> BLL (para los SKU)."""
    sin_tildes = "".join(ch for ch in unicodedata.normalize("NFD", nombre) if unicodedata.category(ch) != "Mn")
    palabras = [p for p in re.split(r"[^A-Za-z]+", sin_tildes.upper()) if p and p not in ("CON", "DE", "Y")]
    if not palabras:
        return "COL"
    if len(palabras) == 1:
        return palabras[0][:3]
    return palabras[0][:2] + palabras[-1][0]


def sku_variante(sku_prenda, color, talle):
    talle_sku = "U" if talle == "Único" else talle
    return f"{sku_prenda}-{abreviatura_color(color)}-{talle_sku}"


def _id_por_nombre(cursor, tabla, columna_id, nombre, crear=False, hex_color=None):
    cursor.execute(f"SELECT {columna_id} FROM {tabla} WHERE nombre = %s", (nombre,))
    fila = cursor.fetchone()
    if fila:
        if hex_color and tabla == "colores":
            cursor.execute("UPDATE colores SET hex = COALESCE(hex, %s) WHERE id_color = %s", (hex_color, fila[0]))
        return fila[0]
    if not crear:
        raise ValueError(f"No existe '{nombre}' en la tabla {tabla}")
    if tabla == "colores":
        cursor.execute("INSERT INTO colores (nombre, hex) VALUES (%s, %s)", (nombre, hex_color))
    else:
        cursor.execute(f"INSERT INTO {tabla} (nombre) VALUES (%s)", (nombre,))
    return cursor.lastrowid


def guardar_prenda(cursor, prenda, stock=0, actualizar=False):
    """
    Guarda una prenda con sus colores, sus variantes (color x talle) en el inventario
    y sus medidas. prenda usa las claves de base_datos/catalogo_inicial.json.

    - Prenda nueva: se crea con 'stock' unidades por variante.
    - Prenda existente: con actualizar=True se actualizan sus datos; en ambos casos se
      agregan las variantes que falten (con 'stock' unidades) y se completan los SKU.
      El stock de las variantes que ya existían NO se toca (no se pisan las ventas).
    Devuelve 'nueva', 'actualizada' o 'existente'.
    """
    cursor.execute("SELECT id_prenda FROM prendas WHERE codigo = %s", (prenda["codigo"],))
    fila = cursor.fetchone()
    colores = prenda.get("colores") or [{"nombre": prenda.get("color_foto", "Colección"), "hex": None}]
    ids_color = {c["nombre"]: _id_por_nombre(cursor, "colores", "id_color", c["nombre"], crear=True,
                                             hex_color=c.get("hex")) for c in colores}
    id_color_foto = ids_color.get(prenda.get("color_foto"), ids_color[colores[0]["nombre"]])
    archivo = prenda.get("archivo") or f"prendas/{prenda['codigo']}.png"
    valores = (
        prenda.get("sku"), prenda["nombre"], prenda.get("descripcion", ""), prenda.get("categoria", "Otros"),
        prenda.get("genero", "unisex"), prenda.get("precio", 0), archivo.replace("\\", "/"), id_color_foto,
        prenda.get("calce", "regular"), prenda.get("margen_hombros", 0.38), prenda.get("margen_cuello", 0.20),
        prenda.get("rotacion", 0), bool(prenda.get("voltear_horizontal", False)),
        bool(prenda.get("voltear_vertical", False)),
    )
    if fila is None:
        cursor.execute(
            "INSERT INTO prendas (sku, nombre, descripcion, categoria, genero, precio, imagen_url, id_color_foto, "
            "calce, margen_hombros, margen_cuello, rotacion, voltear_horizontal, voltear_vertical, codigo) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            valores + (prenda["codigo"],))
        id_prenda, resultado = cursor.lastrowid, "nueva"
    else:
        id_prenda = fila[0]
        if actualizar:
            cursor.execute(
                "UPDATE prendas SET sku = %s, nombre = %s, descripcion = %s, categoria = %s, genero = %s, "
                "precio = %s, imagen_url = %s, id_color_foto = %s, calce = %s, margen_hombros = %s, "
                "margen_cuello = %s, rotacion = %s, voltear_horizontal = %s, voltear_vertical = %s, "
                "estado = 'activa' WHERE id_prenda = %s", valores + (id_prenda,))
            resultado = "actualizada"
        else:
            resultado = "existente"

    for color in colores:
        for talle in prenda.get("talles") or []:
            id_talle = _id_por_nombre(cursor, "talles", "id_talle", talle)
            sku = sku_variante(prenda["sku"], color["nombre"], talle) if prenda.get("sku") else None
            cursor.execute("SELECT id_inventario FROM inventario WHERE id_prenda = %s AND id_talle = %s AND id_color = %s",
                           (id_prenda, id_talle, ids_color[color["nombre"]]))
            existente = cursor.fetchone()
            if existente:
                cursor.execute("UPDATE inventario SET sku = COALESCE(sku, %s) WHERE id_inventario = %s",
                               (sku, existente[0]))
                continue
            cursor.execute("INSERT INTO inventario (id_prenda, id_talle, id_color, sku, stock) VALUES (%s, %s, %s, %s, %s)",
                           (id_prenda, id_talle, ids_color[color["nombre"]], sku, stock))
            if stock:
                cursor.execute("INSERT INTO movimientos_stock (id_inventario, cantidad, motivo, stock_resultante) "
                               "VALUES (%s, %s, 'carga_inicial', %s)", (cursor.lastrowid, stock, stock))

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


def quitar_variantes_sobrantes(cursor, codigo, colores_validos):
    """
    Borra las variantes de una prenda cuyo color ya no está en el catálogo, sólo si
    nunca se vendieron ni se eligieron en una sesión. Devuelve cuántas borró.
    """
    if not colores_validos:
        return 0
    marcas = ", ".join(["%s"] * len(colores_validos))
    cursor.execute(
        f"SELECT i.id_inventario FROM inventario i JOIN prendas p ON p.id_prenda = i.id_prenda "
        f"JOIN colores c ON c.id_color = i.id_color WHERE p.codigo = %s AND c.nombre NOT IN ({marcas}) "
        f"AND NOT EXISTS (SELECT 1 FROM compras co WHERE co.id_inventario = i.id_inventario) "
        f"AND NOT EXISTS (SELECT 1 FROM prendas_seleccionadas ps WHERE ps.id_inventario = i.id_inventario)",
        (codigo, *colores_validos))
    ids = [f[0] for f in cursor.fetchall()]
    for id_inv in ids:
        cursor.execute("DELETE FROM movimientos_stock WHERE id_inventario = %s", (id_inv,))
        cursor.execute("DELETE FROM inventario WHERE id_inventario = %s", (id_inv,))
    return len(ids)


def borrar_prenda(cursor, codigo):
    """
    Saca una prenda del catálogo. Si nunca se vendió, se borra (con su inventario y
    medidas); si tiene ventas, se marca 'inactiva' para conservar el historial.
    Devuelve 'borrada', 'inactiva' o None si no existía.
    """
    cursor.execute("SELECT id_prenda FROM prendas WHERE codigo = %s", (codigo,))
    fila = cursor.fetchone()
    if not fila:
        return None
    id_prenda = fila[0]
    cursor.execute("SELECT COUNT(*) FROM compras co JOIN inventario i ON i.id_inventario = co.id_inventario "
                   "WHERE i.id_prenda = %s", (id_prenda,))
    if cursor.fetchone()[0]:
        cursor.execute("UPDATE prendas SET estado = 'inactiva' WHERE id_prenda = %s", (id_prenda,))
        return "inactiva"
    cursor.execute("DELETE ps FROM prendas_seleccionadas ps JOIN inventario i ON i.id_inventario = ps.id_inventario "
                   "WHERE i.id_prenda = %s", (id_prenda,))
    cursor.execute("DELETE ms FROM movimientos_stock ms JOIN inventario i ON i.id_inventario = ms.id_inventario "
                   "WHERE i.id_prenda = %s", (id_prenda,))
    cursor.execute("DELETE FROM inventario WHERE id_prenda = %s", (id_prenda,))
    cursor.execute("DELETE FROM favoritos WHERE id_prenda = %s", (id_prenda,))
    cursor.execute("DELETE FROM prendas WHERE id_prenda = %s", (id_prenda,))  # medidas: ON DELETE CASCADE
    return "borrada"
