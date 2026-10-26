# ==========================================================
# PROYECTO: PROBADOR VIRTUAL INTELIGENTE
# MÓDULO: CONEXIÓN CON LA BASE DE DATOS MYSQL
# ==========================================================
# Los datos de conexión se leen de base_datos/mysql.ini (copiar mysql.ini.ejemplo)
# o de las variables de entorno PROBADOR_MYSQL_HOST, _PORT, _USER, _PASSWORD y
# _DATABASE, que tienen prioridad. La contraseña nunca se guarda en el código.

import configparser
import json
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


def crear_tablas(ruta_sql):
    """Crea la base y las cinco tablas si no existen (no borra nada)."""
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
# Orden en que se muestran los talles
ORDEN_TALLES = ["XXS", "XS", "S", "M", "L", "XL", "XXL", "Único"]
MEDIDAS = ("pecho", "cintura", "cadera", "hombros", "largo")


def _numero(valor):
    """Convierte los DECIMAL de MySQL: 18000.00 -> 18000 y 0.38 -> 0.38."""
    if isinstance(valor, Decimal):
        return int(valor) if valor == valor.to_integral_value() else float(valor)
    return valor


def _json(valor, vacio):
    """Las columnas JSON llegan como texto: se convierten a listas / diccionarios."""
    if valor is None:
        return vacio
    if isinstance(valor, (bytes, bytearray)):
        valor = valor.decode("utf-8")
    return json.loads(valor) if isinstance(valor, str) else valor


def clave_variante(color, talle):
    """Clave de una variante en la columna prenda.stock: 'Azul Marino|M'."""
    return f"{color}|{talle}"


def _orden_talle(talle):
    return ORDEN_TALLES.index(talle) if talle in ORDEN_TALLES else len(ORDEN_TALLES)


def _stock_por_variante(stock_json):
    """{'Negro|M': {'sku', 'stock'}} -> ({('Negro', 'M'): unidades}, {('Negro', 'M'): sku})."""
    stock, skus = {}, {}
    for clave, datos in stock_json.items():
        color, _, talle = clave.rpartition("|")
        stock[(color, talle)] = int(datos.get("stock", 0))
        skus[(color, talle)] = datos.get("sku")
    return stock, skus


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
            "SELECT id_prenda, codigo, sku, nombre, descripcion, categoria, genero, precio, calce, imagen_url, "
            "ajuste_foto, colores, talles, stock FROM prenda WHERE estado = 'activa' "
            "ORDER BY categoria, sku, id_prenda")
        filas = cursor.fetchall()
    finally:
        conexion.close()

    prendas = []
    for fila in filas:
        ajuste = _json(fila["ajuste_foto"], {})
        lista_colores = _json(fila["colores"], [])
        if lista_colores and not any(c.get("es_foto") for c in lista_colores):
            lista_colores[0]["es_foto"] = True
        lista_colores.sort(key=lambda c: not c.get("es_foto"))  # el color de la foto va primero
        talles = sorted(_json(fila["talles"], []), key=lambda t: _orden_talle(t["talle"]))
        stock, skus = _stock_por_variante(_json(fila["stock"], {}))
        medidas = {t["talle"]: {k: int(t[k]) for k in MEDIDAS}
                   for t in talles if all(t.get(k) is not None for k in MEDIDAS)}
        prendas.append({
            "id": fila["codigo"],
            "id_prenda": fila["id_prenda"],
            "sku": fila["sku"] or "",
            "categoria": fila["categoria"],
            "genero": fila["genero"],
            "calce": fila["calce"],
            "nombre": fila["nombre"],
            "precio": _numero(fila["precio"]),
            "colores": lista_colores,
            "color": " / ".join(c["nombre"] for c in lista_colores) or "Colección",
            "talles": [t["talle"] for t in talles] or ["S", "M", "L"],
            "stock": stock,
            "skus": skus,
            "archivo": fila["imagen_url"],
            "descripcion": fila["descripcion"] or "",
            "margen_hombros": ajuste.get("margen_hombros", 0.38),
            "margen_cuello": ajuste.get("margen_cuello", 0.20),
            "voltear_horizontal": bool(ajuste.get("voltear_horizontal", False)),
            "voltear_vertical": bool(ajuste.get("voltear_vertical", False)),
            "rotacion": int(ajuste.get("rotacion", 0)),
            "medidas_talles": medidas,
        })
    return prendas


def leer_stock(id_prenda):
    """Stock actual de una prenda: {(color, talle): unidades} (para refrescar la galería)."""
    conexion = conectar()
    try:
        cursor = conexion.cursor()
        cursor.execute("SELECT stock FROM prenda WHERE id_prenda = %s", (id_prenda,))
        fila = cursor.fetchone()
        return _stock_por_variante(_json(fila[0], {}))[0] if fila else {}
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


def _se_vendio(cursor, sku=None, id_prenda=None):
    """True si alguna compra incluye esa variante (por SKU) o esa prenda."""
    candidato = {"sku": sku} if sku else {"id_prenda": id_prenda}
    cursor.execute("SELECT COUNT(*) FROM compra WHERE JSON_CONTAINS(detalle, %s)", (json.dumps(candidato),))
    return cursor.fetchone()[0] > 0


def guardar_prenda(cursor, prenda, stock=0, actualizar=False):
    """
    Guarda una prenda con sus colores, sus talles y medidas y el stock de cada
    variante (color x talle). prenda usa las claves de base_datos/catalogo_inicial.json.

    - Prenda nueva: se crea con 'stock' unidades por variante.
    - Prenda existente: con actualizar=True se actualizan sus datos; en ambos casos se
      agregan las variantes que falten (con 'stock' unidades) y se completan los SKU.
      El stock de las variantes que ya existían NO se toca (no se pisan las ventas).
    Devuelve 'nueva', 'actualizada' o 'existente'.
    """
    cursor.execute("SELECT id_prenda, colores, talles, stock FROM prenda WHERE codigo = %s FOR UPDATE",
                   (prenda["codigo"],))
    fila = cursor.fetchone()
    colores = prenda.get("colores") or [{"nombre": prenda.get("color_foto", "Colección"), "hex": None}]
    foto = prenda.get("color_foto") or colores[0]["nombre"]
    colores_json = [{"nombre": c["nombre"], "hex": c.get("hex"), "es_foto": c["nombre"] == foto} for c in colores]
    archivo = (prenda.get("archivo") or f"prendas/{prenda['codigo']}.png").replace("\\", "/")
    ajuste = {
        "margen_hombros": prenda.get("margen_hombros", 0.38), "margen_cuello": prenda.get("margen_cuello", 0.20),
        "rotacion": prenda.get("rotacion", 0), "voltear_horizontal": bool(prenda.get("voltear_horizontal", False)),
        "voltear_vertical": bool(prenda.get("voltear_vertical", False)),
    }

    # Stock: las variantes que ya existían conservan sus unidades
    stock_json = _json(fila[3], {}) if fila else {}
    for color in colores:
        for talle in prenda.get("talles") or []:
            clave = clave_variante(color["nombre"], talle)
            sku = sku_variante(prenda["sku"], color["nombre"], talle) if prenda.get("sku") else None
            if clave in stock_json:
                stock_json[clave]["sku"] = stock_json[clave].get("sku") or sku
            else:
                stock_json[clave] = {"sku": sku, "stock": int(stock)}

    # Talles con sus medidas (las del JSON pisan las guardadas)
    talles_json = {t["talle"]: t for t in (_json(fila[2], []) if fila else [])}
    medidas = prenda.get("medidas_talles") or {}
    for talle in prenda.get("talles") or []:
        talles_json.setdefault(talle, {"talle": talle})
    for talle, m in medidas.items():
        talles_json.setdefault(talle, {"talle": talle}).update({k: int(m[k]) for k in MEDIDAS})
    talles_json = sorted(talles_json.values(), key=lambda t: _orden_talle(t["talle"]))

    datos = (
        prenda.get("sku"), prenda["nombre"], prenda.get("descripcion", ""), prenda.get("categoria", "Otros"),
        prenda.get("genero", "unisex"), prenda.get("precio", 0), prenda.get("calce", "regular"), archivo,
        json.dumps(ajuste), json.dumps(colores_json, ensure_ascii=False),
    )
    if fila is None:
        cursor.execute(
            "INSERT INTO prenda (sku, nombre, descripcion, categoria, genero, precio, calce, imagen_url, ajuste_foto, "
            "colores, talles, stock, codigo) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            datos + (json.dumps(talles_json, ensure_ascii=False), json.dumps(stock_json, ensure_ascii=False),
                     prenda["codigo"]))
        return "nueva"
    id_prenda = fila[0]
    if actualizar:
        cursor.execute(
            "UPDATE prenda SET sku = %s, nombre = %s, descripcion = %s, categoria = %s, genero = %s, precio = %s, "
            "calce = %s, imagen_url = %s, ajuste_foto = %s, colores = %s, talles = %s, stock = %s, "
            "estado = 'activa' WHERE id_prenda = %s",
            datos + (json.dumps(talles_json, ensure_ascii=False), json.dumps(stock_json, ensure_ascii=False),
                     id_prenda))
        return "actualizada"
    # Sin actualizar: sólo se agregan variantes, talles y colores que falten
    conocidos = {c["nombre"] for c in _json(fila[1], [])}
    colores_viejos = _json(fila[1], []) + [c for c in colores_json if c["nombre"] not in conocidos]
    cursor.execute("UPDATE prenda SET colores = %s, talles = %s, stock = %s WHERE id_prenda = %s",
                   (json.dumps(colores_viejos, ensure_ascii=False), json.dumps(talles_json, ensure_ascii=False),
                    json.dumps(stock_json, ensure_ascii=False), id_prenda))
    return "existente"


def quitar_variantes_sobrantes(cursor, codigo, colores_validos):
    """
    Quita de una prenda las variantes cuyo color ya no está en el catálogo, sólo si
    nunca se vendieron. Devuelve cuántas quitó.
    """
    if not colores_validos:
        return 0
    cursor.execute("SELECT id_prenda, colores, stock FROM prenda WHERE codigo = %s FOR UPDATE", (codigo,))
    fila = cursor.fetchone()
    if not fila:
        return 0
    stock_json = _json(fila[2], {})
    quitar = [clave for clave, datos in stock_json.items()
              if clave.rpartition("|")[0] not in colores_validos
              and not (datos.get("sku") and _se_vendio(cursor, sku=datos["sku"]))]
    if not quitar:
        return 0
    for clave in quitar:
        del stock_json[clave]
    con_stock = {clave.rpartition("|")[0] for clave in stock_json}
    colores = [c for c in _json(fila[1], []) if c["nombre"] in colores_validos or c["nombre"] in con_stock]
    cursor.execute("UPDATE prenda SET colores = %s, stock = %s WHERE id_prenda = %s",
                   (json.dumps(colores, ensure_ascii=False), json.dumps(stock_json, ensure_ascii=False), fila[0]))
    return len(quitar)


def borrar_prenda(cursor, codigo):
    """
    Saca una prenda del catálogo. Si nunca se vendió, se borra (con sus pruebas y de los
    favoritos de los clientes); si tiene ventas, se marca 'inactiva' para conservar el
    historial. Devuelve 'borrada', 'inactiva' o None si no existía.
    """
    cursor.execute("SELECT id_prenda FROM prenda WHERE codigo = %s", (codigo,))
    fila = cursor.fetchone()
    if not fila:
        return None
    id_prenda = fila[0]
    if _se_vendio(cursor, id_prenda=id_prenda):
        cursor.execute("UPDATE prenda SET estado = 'inactiva' WHERE id_prenda = %s", (id_prenda,))
        return "inactiva"
    cursor.execute("SELECT id_cliente, favoritos FROM clientes WHERE JSON_CONTAINS(favoritos, %s)", (str(id_prenda),))
    for id_cliente, favoritos in cursor.fetchall():
        restantes = [f for f in _json(favoritos, []) if f != id_prenda]
        cursor.execute("UPDATE clientes SET favoritos = %s WHERE id_cliente = %s", (json.dumps(restantes), id_cliente))
    cursor.execute("DELETE FROM prenda WHERE id_prenda = %s", (id_prenda,))  # sus pruebas: ON DELETE CASCADE
    return "borrada"
