# ==========================================================
# PROYECTO: PROBADOR VIRTUAL INTELIGENTE
# MÓDULO: TIENDA (CLIENTES, FIDELIDAD, CUPONES, COMPRAS Y STOCK EN MYSQL)
# ==========================================================
# Reglas del programa de fidelidad:
#   * Al registrarse, el cliente recibe un cupón de bienvenida del 15%.
#   * Cada compra suma 1 punto por cada $100 pagados; cada punto vale $1 en la
#     próxima compra (se pueden usar hasta cubrir el 30% del pedido).
#   * Según lo gastado en total sube de nivel (Bronce, Plata, Oro, Diamante) y
#     cada nivel tiene un descuento fijo en todas sus compras.
#   * En el mes de su cumpleaños recibe un cupón del 20%.
#
# Una compra es una sola transacción: se bloquea el stock de cada variante, se
# verifica que alcance, se descuenta, se registran el pedido, sus prendas, los
# movimientos de stock, los puntos y el cupón usado. Si algo falla, no se guarda nada.

import datetime
import random
import re
import string
from decimal import Decimal, ROUND_HALF_UP

from conexion_mysql import conectar

CUPON_BIENVENIDA_PCT = 15
CUPON_CUMPLEANOS_PCT = 20
PESOS_POR_PUNTO = 100          # 1 punto cada $100 pagados
VALOR_PUNTO = Decimal("1")     # cada punto vale $1
TOPE_PUNTOS_PCT = Decimal("0.30")
VIGENCIA_CUPON_DIAS = 60


class ErrorTienda(Exception):
    """Error de negocio con un mensaje para mostrarle al cliente (sin stock, cupón vencido...)."""


def _dinero(valor):
    return Decimal(valor).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def email_valido(email):
    return re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email or "") is not None


def _codigo_cupon(prefijo):
    return f"{prefijo}-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


# -------------------------------------------------------------------------
# CLIENTES
# -------------------------------------------------------------------------
def _leer_cliente(cursor, id_cliente):
    cursor.execute(
        "SELECT c.id_cliente, c.nombre, c.apellido, c.email, c.telefono, c.fecha_nacimiento, c.talle_preferido, "
        "c.acepta_promociones, c.puntos, c.total_gastado, n.id_nivel, n.nombre AS nivel, n.descuento_pct, "
        "n.beneficio FROM clientes c JOIN niveles_fidelidad n ON n.id_nivel = c.id_nivel WHERE c.id_cliente = %s",
        (id_cliente,))
    cliente = cursor.fetchone()
    if not cliente:
        return None
    cursor.execute("SELECT nombre, gasto_minimo FROM niveles_fidelidad WHERE gasto_minimo > %s "
                   "ORDER BY gasto_minimo LIMIT 1", (cliente["total_gastado"],))
    siguiente = cursor.fetchone()
    cliente["siguiente_nivel"] = siguiente["nombre"] if siguiente else None
    cliente["falta_para_siguiente"] = (siguiente["gasto_minimo"] - cliente["total_gastado"]) if siguiente else 0
    cursor.execute("SELECT id_cupon, codigo, descripcion, tipo, valor, compra_minima, vence FROM cupones "
                   "WHERE id_cliente = %s AND usado = FALSE AND (vence IS NULL OR vence >= CURDATE()) "
                   "ORDER BY vence", (id_cliente,))
    cliente["cupones"] = cursor.fetchall()
    cursor.execute("SELECT p.codigo FROM favoritos f JOIN prendas p ON p.id_prenda = f.id_prenda "
                   "WHERE f.id_cliente = %s", (id_cliente,))
    cliente["favoritos"] = {f["codigo"] for f in cursor.fetchall()}
    return cliente


def _dar_cupon_cumpleanos(cursor, cliente):
    """Si es el mes de su cumpleaños y todavía no recibió el cupón este año, se lo da."""
    nacimiento = cliente.get("fecha_nacimiento")
    hoy = datetime.date.today()
    if not nacimiento or nacimiento.month != hoy.month:
        return False
    cursor.execute("SELECT COUNT(*) AS n FROM cupones WHERE id_cliente = %s AND codigo LIKE 'CUMPLE-%%' "
                   "AND YEAR(fecha_creacion) = %s", (cliente["id_cliente"], hoy.year))
    if cursor.fetchone()["n"]:
        return False
    cursor.execute("INSERT INTO cupones (codigo, id_cliente, descripcion, tipo, valor, vence) "
                   "VALUES (%s, %s, %s, 'porcentaje', %s, %s)",
                   (_codigo_cupon("CUMPLE"), cliente["id_cliente"], f"¡Feliz cumpleaños! {CUPON_CUMPLEANOS_PCT}% OFF",
                    CUPON_CUMPLEANOS_PCT, hoy + datetime.timedelta(days=30)))
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
        cliente = _leer_cliente(cursor, fila["id_cliente"])
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
        cursor.execute(
            "INSERT INTO clientes (nombre, apellido, email, telefono, fecha_nacimiento, talle_preferido, "
            "acepta_promociones, id_nivel, ultima_visita) VALUES (%s, %s, %s, %s, %s, %s, %s, 1, NOW())",
            (nombre.strip(), (apellido or "").strip(), email, (telefono or "").strip() or None, fecha_nacimiento,
             talle_preferido or None, bool(acepta_promociones)))
        id_cliente = cursor.lastrowid
        cursor.execute("INSERT INTO cupones (codigo, id_cliente, descripcion, tipo, valor, vence) "
                       "VALUES (%s, %s, %s, 'porcentaje', %s, %s)",
                       (_codigo_cupon("BIENVENIDA"), id_cliente, f"Bienvenida: {CUPON_BIENVENIDA_PCT}% OFF en tu primera compra",
                        CUPON_BIENVENIDA_PCT, datetime.date.today() + datetime.timedelta(days=VIGENCIA_CUPON_DIAS)))
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
        cursor.execute("DELETE FROM favoritos WHERE id_cliente = %s AND id_prenda = %s", (id_cliente, id_prenda))
        quedo = cursor.rowcount == 0
        if quedo:
            cursor.execute("INSERT INTO favoritos (id_cliente, id_prenda) VALUES (%s, %s)", (id_cliente, id_prenda))
        conexion.commit()
        return quedo
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
    pct_nivel = Decimal(cliente["descuento_pct"]) if cliente else Decimal(0)
    desc_nivel = _dinero(subtotal * pct_nivel / 100)
    resto = subtotal - desc_nivel
    desc_cupon = Decimal(0)
    if cupon:
        if subtotal < Decimal(cupon["compra_minima"]):
            raise ErrorTienda(f"El cupón {cupon['codigo']} pide una compra mínima de ${cupon['compra_minima']:,.0f}.")
        valor = Decimal(cupon["valor"])
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


def comprar(items, id_cliente=None, id_cupon=None, usar_puntos=False):
    """
    Registra una compra. items: [{"id_prenda", "color", "talle", "cantidad"}].
    Devuelve {"id_pedido", "detalle", "nivel_nuevo", "cliente"}; si no hay stock o el
    cupón no sirve, lanza ErrorTienda y no se guarda nada.
    """
    if not items:
        raise ErrorTienda("El carrito está vacío.")
    conexion = conectar()
    try:
        cursor = conexion.cursor(dictionary=True)
        conexion.start_transaction()
        lineas, subtotal = [], Decimal(0)
        for item in items:
            cantidad = int(item.get("cantidad", 1))
            if cantidad <= 0:
                raise ErrorTienda("La cantidad tiene que ser mayor que cero.")
            # FOR UPDATE: otra compra al mismo tiempo espera; así nunca se vende de más
            cursor.execute(
                "SELECT i.id_inventario, i.stock, i.sku, p.precio, p.nombre FROM inventario i "
                "JOIN prendas p ON p.id_prenda = i.id_prenda JOIN colores c ON c.id_color = i.id_color "
                "JOIN talles t ON t.id_talle = i.id_talle "
                "WHERE i.id_prenda = %s AND c.nombre = %s AND t.nombre = %s AND p.estado = 'activa' FOR UPDATE",
                (item["id_prenda"], item["color"], item["talle"]))
            variante = cursor.fetchone()
            if not variante:
                raise ErrorTienda(f"No existe esa combinación de color {item['color']} y talle {item['talle']}.")
            if variante["stock"] < cantidad:
                quedan = variante["stock"]
                raise ErrorTienda(f"{variante['nombre']} ({item['color']}, {item['talle']}): "
                                  + (f"sólo quedan {quedan}." if quedan else "sin stock."))
            lineas.append((variante, cantidad))
            subtotal += Decimal(variante["precio"]) * cantidad

        cliente = _leer_cliente(cursor, id_cliente) if id_cliente else None
        cupon = None
        if id_cupon:
            cursor.execute("SELECT * FROM cupones WHERE id_cupon = %s FOR UPDATE", (id_cupon,))
            cupon = cursor.fetchone()
            hoy = datetime.date.today()
            if (not cupon or cupon["usado"] or (cupon["vence"] and cupon["vence"] < hoy)
                    or (cupon["id_cliente"] is not None and cupon["id_cliente"] != id_cliente)):
                raise ErrorTienda("El cupón no es válido o ya se usó.")
        detalle = calcular_total(subtotal, cliente, cupon, usar_puntos)

        cursor.execute(
            "INSERT INTO pedidos (id_cliente, id_cupon, subtotal, descuento_nivel, descuento_cupon, descuento_puntos, "
            "total, puntos_usados, puntos_ganados, estado) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'pagado')",
            (id_cliente, id_cupon, detalle["subtotal"], detalle["descuento_nivel"], detalle["descuento_cupon"],
             detalle["descuento_puntos"], detalle["total"], detalle["puntos_usados"], detalle["puntos_ganados"]))
        id_pedido = cursor.lastrowid
        for variante, cantidad in lineas:
            nuevo_stock = variante["stock"] - cantidad
            cursor.execute("UPDATE inventario SET stock = %s WHERE id_inventario = %s",
                           (nuevo_stock, variante["id_inventario"]))
            cursor.execute("INSERT INTO compras (id_pedido, id_inventario, cantidad, precio_unitario, estado) "
                           "VALUES (%s, %s, %s, %s, 'pagada')",
                           (id_pedido, variante["id_inventario"], cantidad, variante["precio"]))
            cursor.execute("INSERT INTO movimientos_stock (id_inventario, cantidad, motivo, id_pedido, stock_resultante) "
                           "VALUES (%s, %s, 'venta', %s, %s)", (variante["id_inventario"], -cantidad, id_pedido, nuevo_stock))
        if cupon:
            cursor.execute("UPDATE cupones SET usado = TRUE, fecha_uso = NOW() WHERE id_cupon = %s", (id_cupon,))

        nivel_nuevo = None
        if cliente:
            cursor.execute("UPDATE clientes SET puntos = puntos - %s + %s, total_gastado = total_gastado + %s, "
                           "ultima_visita = NOW() WHERE id_cliente = %s",
                           (detalle["puntos_usados"], detalle["puntos_ganados"], detalle["total"], id_cliente))
            cursor.execute("SELECT n.id_nivel, n.nombre FROM niveles_fidelidad n JOIN clientes c ON c.id_cliente = %s "
                           "WHERE n.gasto_minimo <= c.total_gastado ORDER BY n.gasto_minimo DESC LIMIT 1", (id_cliente,))
            nivel = cursor.fetchone()
            if nivel and nivel["id_nivel"] != cliente["id_nivel"]:
                cursor.execute("UPDATE clientes SET id_nivel = %s WHERE id_cliente = %s", (nivel["id_nivel"], id_cliente))
                nivel_nuevo = nivel["nombre"]
        conexion.commit()
        return {"id_pedido": id_pedido, "detalle": detalle, "nivel_nuevo": nivel_nuevo,
                "cliente": _leer_cliente(cursor, id_cliente) if id_cliente else None}
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()
