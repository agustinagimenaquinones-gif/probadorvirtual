# ==========================================================
# PROYECTO: PROBADOR VIRTUAL INTELIGENTE
# MÓDULO: TIENDA (CLIENTES, FIDELIDAD, CUPONES, PRUEBAS Y COMPRAS EN MYSQL)
# ==========================================================
# Reglas del programa de fidelidad:
#   * Al registrarse, el cliente recibe un cupón de bienvenida del 15%.
#   * Cada compra suma 1 punto por cada $100 pagados; cada punto vale $1 en la
#     próxima compra (se pueden usar hasta cubrir el 30% del pedido).
#   * Según lo gastado en total sube de nivel (Bronce, Plata, Oro, Diamante) y
#     cada nivel tiene un descuento fijo en todas sus compras.
#   * En el mes de su cumpleaños recibe un cupón del 20%.
# Los cupones y los favoritos de cada cliente se guardan en su fila (columnas JSON).
#
# Una compra es una sola transacción: se bloquea la fila de cada prenda, se verifica
# que alcance el stock de la variante, se descuenta, se registra la compra con sus
# prendas, los puntos, el cupón usado y, si vino de una prueba, que terminó en compra.
# Si algo falla, no se guarda nada.

import datetime
import json
import random
import re
import string
from decimal import Decimal, ROUND_HALF_UP

from conexion_mysql import conectar, clave_variante

CUPON_BIENVENIDA_PCT = 15
CUPON_CUMPLEANOS_PCT = 20
PESOS_POR_PUNTO = 100          # 1 punto cada $100 pagados
VALOR_PUNTO = Decimal("1")     # cada punto vale $1
TOPE_PUNTOS_PCT = Decimal("0.30")
VIGENCIA_CUPON_DIAS = 60

# Niveles de fidelidad: (nombre, gasto acumulado mínimo, % de descuento, beneficio)
NIVELES = [
    ("Bronce", 0, 0, "Cupón de bienvenida del 15% y 1 punto por cada $100"),
    ("Plata", 80000, 5, "5% de descuento en todas tus compras"),
    ("Oro", 200000, 10, "10% de descuento y acceso anticipado a nuevas colecciones"),
    ("Diamante", 400000, 15, "15% de descuento, regalo de cumpleaños y asesoría de estilo"),
]


class ErrorTienda(Exception):
    """Error de negocio con un mensaje para mostrarle al cliente (sin stock, cupón vencido...)."""


def _dinero(valor):
    return Decimal(str(valor)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def email_valido(email):
    return re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email or "") is not None


def _codigo_cupon(prefijo):
    return f"{prefijo}-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


def _json(valor, vacio):
    if valor is None:
        return vacio
    if isinstance(valor, (bytes, bytearray)):
        valor = valor.decode("utf-8")
    return json.loads(valor) if isinstance(valor, str) else valor


def nivel_para(total_gastado):
    """El nivel que corresponde a lo gastado: (nombre, mínimo, %, beneficio)."""
    return [n for n in NIVELES if Decimal(str(total_gastado)) >= n[1]][-1]


def _nuevo_cupon(prefijo, descripcion, valor, dias):
    hoy = datetime.date.today()
    return {"codigo": _codigo_cupon(prefijo), "descripcion": descripcion, "tipo": "porcentaje", "valor": valor,
            "compra_minima": 0, "vence": (hoy + datetime.timedelta(days=dias)).isoformat(), "usado": False,
            "creado": hoy.isoformat()}


def _cupon_vigente(cupon, hoy=None):
    hoy = hoy or datetime.date.today()
    return not cupon.get("usado") and (not cupon.get("vence") or datetime.date.fromisoformat(cupon["vence"]) >= hoy)


# -------------------------------------------------------------------------
# CLIENTES
# -------------------------------------------------------------------------
def _leer_cliente(cursor, id_cliente, bloquear=False):
    cursor.execute(
        "SELECT id_cliente, nombre, apellido, email, telefono, fecha_nacimiento, talle_preferido, acepta_promociones, "
        "nivel, puntos, total_gastado, cupones, favoritos FROM clientes WHERE id_cliente = %s"
        + (" FOR UPDATE" if bloquear else ""), (id_cliente,))
    cliente = cursor.fetchone()
    if not cliente:
        return None
    nombre, minimo, pct, beneficio = next(n for n in NIVELES if n[0] == cliente["nivel"])
    cliente["descuento_pct"], cliente["beneficio"] = pct, beneficio
    siguiente = next((n for n in NIVELES if n[1] > cliente["total_gastado"]), None)
    cliente["siguiente_nivel"] = siguiente[0] if siguiente else None
    cliente["falta_para_siguiente"] = (siguiente[1] - cliente["total_gastado"]) if siguiente else 0
    cliente["todos_los_cupones"] = _json(cliente["cupones"], [])
    # Cupones que se pueden usar, con la fecha como fecha (la galería la muestra dd/mm/aaaa)
    cliente["cupones"] = sorted(
        (dict(c, vence=datetime.date.fromisoformat(c["vence"]) if c.get("vence") else None)
         for c in cliente["todos_los_cupones"] if _cupon_vigente(c)),
        key=lambda c: c["vence"] or datetime.date.max)
    ids_favoritos = _json(cliente["favoritos"], [])
    cliente["ids_favoritos"] = ids_favoritos
    cliente["favoritos"] = set()
    if ids_favoritos:
        marcas = ", ".join(["%s"] * len(ids_favoritos))
        cursor.execute(f"SELECT codigo FROM prenda WHERE id_prenda IN ({marcas})", tuple(ids_favoritos))
        cliente["favoritos"] = {f["codigo"] for f in cursor.fetchall()}
    return cliente


def _guardar_cupones(cursor, id_cliente, cupones):
    cursor.execute("UPDATE clientes SET cupones = %s WHERE id_cliente = %s",
                   (json.dumps(cupones, ensure_ascii=False), id_cliente))


def _dar_cupon_cumpleanos(cursor, cliente):
    """Si es el mes de su cumpleaños y todavía no recibió el cupón este año, se lo da."""
    nacimiento = cliente.get("fecha_nacimiento")
    hoy = datetime.date.today()
    if not nacimiento or nacimiento.month != hoy.month:
        return False
    cupones = cliente["todos_los_cupones"]
    if any(c["codigo"].startswith("CUMPLE-") and c.get("creado", "")[:4] == str(hoy.year) for c in cupones):
        return False
    cupones.append(_nuevo_cupon("CUMPLE", f"¡Feliz cumpleaños! {CUPON_CUMPLEANOS_PCT}% OFF", CUPON_CUMPLEANOS_PCT, 30))
    _guardar_cupones(cursor, cliente["id_cliente"], cupones)
    return True


def buscar_cliente(email):
    """Busca al cliente por email; registra su visita y su cupón de cumpleaños. None si no existe."""
    conexion = conectar()
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute("SELECT id_cliente FROM clientes WHERE email = %s", (email.strip().lower(),))
        fila = cursor.fetchone()
        if not fila:
            return None
        cursor.execute("UPDATE clientes SET ultima_visita = NOW() WHERE id_cliente = %s", (fila["id_cliente"],))
        cliente = _leer_cliente(cursor, fila["id_cliente"], bloquear=True)
        _dar_cupon_cumpleanos(cursor, cliente)
        conexion.commit()
        return _leer_cliente(cursor, fila["id_cliente"])
    finally:
        conexion.close()


def registrar_cliente(nombre, email, apellido="", telefono="", fecha_nacimiento=None, talle_preferido=None,
                      acepta_promociones=False):
    """Crea el cliente (nivel Bronce) con su cupón de bienvenida. Devuelve el cliente."""
    email = (email or "").strip().lower()
    if not nombre or not nombre.strip():
        raise ErrorTienda("Ingresá tu nombre.")
    if not email_valido(email):
        raise ErrorTienda("El email no es válido.")
    conexion = conectar()
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute("SELECT id_cliente FROM clientes WHERE email = %s", (email,))
        if cursor.fetchone():
            raise ErrorTienda("Ya hay un cliente con ese email: ingresá con él.")
        bienvenida = _nuevo_cupon("BIENVENIDA", f"Bienvenida: {CUPON_BIENVENIDA_PCT}% OFF en tu primera compra",
                                  CUPON_BIENVENIDA_PCT, VIGENCIA_CUPON_DIAS)
        cursor.execute(
            "INSERT INTO clientes (nombre, apellido, email, telefono, fecha_nacimiento, talle_preferido, "
            "acepta_promociones, nivel, cupones, favoritos, ultima_visita) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, 'Bronce', %s, '[]', NOW())",
            (nombre.strip(), (apellido or "").strip(), email, (telefono or "").strip() or None, fecha_nacimiento,
             talle_preferido or None, bool(acepta_promociones), json.dumps([bienvenida], ensure_ascii=False)))
        id_cliente = cursor.lastrowid
        cliente = _leer_cliente(cursor, id_cliente)
        _dar_cupon_cumpleanos(cursor, cliente)
        conexion.commit()
        return _leer_cliente(cursor, id_cliente)
    finally:
        conexion.close()


def alternar_favorito(id_cliente, id_prenda):
    """Agrega o quita una prenda de favoritos. Devuelve True si quedó como favorita."""
    conexion = conectar()
    try:
        cursor = conexion.cursor()
        cursor.execute("SELECT favoritos FROM clientes WHERE id_cliente = %s FOR UPDATE", (id_cliente,))
        favoritos = _json(cursor.fetchone()[0], [])
        quedo = id_prenda not in favoritos
        favoritos = favoritos + [id_prenda] if quedo else [f for f in favoritos if f != id_prenda]
        cursor.execute("UPDATE clientes SET favoritos = %s WHERE id_cliente = %s", (json.dumps(favoritos), id_cliente))
        conexion.commit()
        return quedo
    finally:
        conexion.close()


# -------------------------------------------------------------------------
# PRUEBAS
# -------------------------------------------------------------------------
def registrar_prueba(id_prenda, color, talle, segundos, id_cliente=None, id_tienda=None):
    """Guarda que alguien se probó una prenda (nunca imágenes). Devuelve el id de la prueba."""
    conexion = conectar()
    try:
        cursor = conexion.cursor()
        cursor.execute(
            "INSERT INTO prueba (id_prenda, id_cliente, id_tienda, tipo, color, talle, segundos) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (id_prenda, id_cliente, id_tienda, "tienda" if id_tienda else "online", color, talle,
             max(0, int(round(segundos)))))
        conexion.commit()
        return cursor.lastrowid
    finally:
        conexion.close()


# -------------------------------------------------------------------------
# PRECIOS Y COMPRA
# -------------------------------------------------------------------------
def calcular_total(subtotal, cliente=None, cupon=None, usar_puntos=False):
    """
    Devuelve el detalle del precio: subtotal, descuento del nivel, del cupón, de los
    puntos, total y puntos que se ganan. No toca la base.
    """
    subtotal = _dinero(subtotal)
    pct_nivel = Decimal(str(cliente["descuento_pct"])) if cliente else Decimal(0)
    desc_nivel = _dinero(subtotal * pct_nivel / 100)
    resto = subtotal - desc_nivel
    desc_cupon = Decimal(0)
    if cupon:
        minima = Decimal(str(cupon.get("compra_minima") or 0))
        if subtotal < minima:
            raise ErrorTienda(f"El cupón {cupon['codigo']} pide una compra mínima de ${minima:,.0f}.")
        valor = Decimal(str(cupon["valor"]))
        desc_cupon = _dinero(resto * valor / 100) if cupon["tipo"] == "porcentaje" else min(resto, _dinero(valor))
    resto -= desc_cupon
    puntos_usados = 0
    if cliente and usar_puntos:
        puntos_usados = int(min(cliente["puntos"], (resto * TOPE_PUNTOS_PCT) // VALOR_PUNTO))
    desc_puntos = _dinero(puntos_usados * VALOR_PUNTO)
    total = max(Decimal(0), resto - desc_puntos)
    return {
        "subtotal": subtotal, "descuento_nivel": desc_nivel, "descuento_cupon": desc_cupon,
        "descuento_puntos": desc_puntos, "total": total, "puntos_usados": puntos_usados,
        "puntos_ganados": int(total // PESOS_POR_PUNTO) if cliente else 0,
    }


def comprar(items, id_cliente=None, codigo_cupon=None, usar_puntos=False, id_prueba=None, id_tienda=None):
    """
    Registra una compra. items: [{"id_prenda", "color", "talle", "cantidad"}].
    codigo_cupon: un cupón vigente del cliente. id_prueba: la prueba de la que salió.
    Devuelve {"id_compra", "detalle", "nivel_nuevo", "cliente"}; si no hay stock o el
    cupón no sirve, lanza ErrorTienda y no se guarda nada.
    """
    if not items:
        raise ErrorTienda("El carrito está vacío.")
    conexion = conectar()
    try:
        cursor = conexion.cursor(dictionary=True)
        conexion.start_transaction()
        prendas, lineas, subtotal = {}, [], Decimal(0)
        for item in items:
            cantidad = int(item.get("cantidad", 1))
            if cantidad <= 0:
                raise ErrorTienda("La cantidad tiene que ser mayor que cero.")
            id_prenda = item["id_prenda"]
            if id_prenda not in prendas:
                # FOR UPDATE: otra compra de la misma prenda espera; así nunca se vende de más
                cursor.execute("SELECT id_prenda, nombre, precio, stock FROM prenda "
                               "WHERE id_prenda = %s AND estado = 'activa' FOR UPDATE", (id_prenda,))
                fila = cursor.fetchone()
                if not fila:
                    raise ErrorTienda("Esa prenda ya no está en el catálogo.")
                fila["stock"] = _json(fila["stock"], {})
                prendas[id_prenda] = fila
            prenda = prendas[id_prenda]
            variante = prenda["stock"].get(clave_variante(item["color"], item["talle"]))
            if variante is None:
                raise ErrorTienda(f"No existe esa combinación de color {item['color']} y talle {item['talle']}.")
            if variante["stock"] < cantidad:
                quedan = variante["stock"]
                raise ErrorTienda(f"{prenda['nombre']} ({item['color']}, {item['talle']}): "
                                  + (f"sólo quedan {quedan}." if quedan else "sin stock."))
            variante["stock"] -= cantidad
            lineas.append({"id_prenda": id_prenda, "sku": variante.get("sku"), "nombre": prenda["nombre"],
                           "color": item["color"], "talle": item["talle"], "cantidad": cantidad,
                           "precio": float(prenda["precio"])})
            subtotal += Decimal(prenda["precio"]) * cantidad

        cliente = _leer_cliente(cursor, id_cliente, bloquear=True) if id_cliente else None
        cupon = None
        if codigo_cupon:
            cupones = cliente["todos_los_cupones"] if cliente else []
            cupon = next((c for c in cupones if c["codigo"] == codigo_cupon), None)
            if not cupon or not _cupon_vigente(cupon):
                raise ErrorTienda("El cupón no es válido o ya se usó.")
        detalle = calcular_total(subtotal, cliente, cupon, usar_puntos)

        for prenda in prendas.values():
            cursor.execute("UPDATE prenda SET stock = %s WHERE id_prenda = %s",
                           (json.dumps(prenda["stock"], ensure_ascii=False), prenda["id_prenda"]))
        cursor.execute(
            "INSERT INTO compra (id_cliente, id_tienda, id_prueba, detalle, subtotal, descuento_nivel, descuento_cupon, "
            "descuento_puntos, total, cupon, puntos_usados, puntos_ganados, estado) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pagada')",
            (id_cliente, id_tienda, id_prueba, json.dumps(lineas, ensure_ascii=False), detalle["subtotal"],
             detalle["descuento_nivel"], detalle["descuento_cupon"], detalle["descuento_puntos"], detalle["total"],
             codigo_cupon if cupon else None, detalle["puntos_usados"], detalle["puntos_ganados"]))
        id_compra = cursor.lastrowid
        if id_prueba:
            cursor.execute("UPDATE prueba SET compro = TRUE WHERE id_prueba = %s", (id_prueba,))

        nivel_nuevo = None
        if cliente:
            if cupon:
                cupon.update(usado=True, fecha_uso=datetime.datetime.now().isoformat(timespec="seconds"))
                _guardar_cupones(cursor, id_cliente, cliente["todos_los_cupones"])
            total_gastado = Decimal(cliente["total_gastado"]) + detalle["total"]
            nivel = nivel_para(total_gastado)[0]
            cursor.execute("UPDATE clientes SET puntos = puntos - %s + %s, total_gastado = %s, nivel = %s, "
                           "ultima_visita = NOW() WHERE id_cliente = %s",
                           (detalle["puntos_usados"], detalle["puntos_ganados"], total_gastado, nivel, id_cliente))
            if nivel != cliente["nivel"]:
                nivel_nuevo = nivel
        conexion.commit()
        return {"id_compra": id_compra, "detalle": detalle, "nivel_nuevo": nivel_nuevo,
                "cliente": _leer_cliente(cursor, id_cliente) if id_cliente else None}
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()
