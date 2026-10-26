# ==========================================================
# PROYECTO: PROBADOR VIRTUAL INTELIGENTE
# HERRAMIENTA: PASAR LA BASE DE 16 TABLAS A LAS 5 TABLAS NUEVAS
# ==========================================================
# Uso (desde la carpeta del proyecto, con MySQL encendido):
#     .venv\Scripts\python.exe migrar_a_5_tablas.py
#
# 1. Lee todos los datos de las tablas anteriores.
# 2. Renombra la tabla clientes vieja (la nueva se llama igual) y crea las cinco
#    tablas nuevas (base_datos/probador_virtual_mysql.sql).
# 3. Pasa los datos: tiendas y su equipo -> tienda; prendas, colores, talles, medidas
#    e inventario -> prenda; clientes, niveles, cupones y favoritos -> clientes;
#    sesiones y prendas elegidas -> prueba; pedidos y compras -> compra.
# 4. Verifica que estén todas las prendas, variantes, unidades, clientes y compras.
#    Sólo entonces borra las tablas viejas. Si algo no coincide, no borra nada.
#
# Conviene hacer antes un respaldo (MySQL Workbench > Server > Data Export).

import json
import os
import sys
from collections import defaultdict

from conexion_mysql import conectar, crear_tablas, clave_variante, ORDEN_TALLES

SCRIPT_SQL = os.path.join("base_datos", "probador_virtual_mysql.sql")
TABLAS_VIEJAS = ["movimientos_stock", "compras", "pedidos", "prendas_seleccionadas", "sesiones_prueba", "favoritos",
                 "cupones", "clientes_anterior", "niveles_fidelidad", "dispositivos_tienda", "inventario",
                 "medidas_talle", "talles", "prendas", "colores", "tiendas"]


def _texto(valor):
    return valor.isoformat() if hasattr(valor, "isoformat") else valor


def _existe(cursor, tabla):
    cursor.execute("SELECT COUNT(*) AS n FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() "
                   "AND TABLE_NAME = %s", (tabla,))
    return cursor.fetchone()["n"] > 0


def leer_todo(cursor):
    datos = {}
    for tabla in ("tiendas", "dispositivos_tienda", "colores", "prendas", "talles", "medidas_talle", "inventario",
                  "niveles_fidelidad", "clientes", "cupones", "favoritos", "sesiones_prueba",
                  "prendas_seleccionadas", "pedidos", "compras"):
        cursor.execute(f"SELECT * FROM {tabla}")
        datos[tabla] = cursor.fetchall()
    return datos


def armar_prendas(d):
    color = {c["id_color"]: c for c in d["colores"]}
    talle = {t["id_talle"]: t["nombre"] for t in d["talles"]}
    variantes = defaultdict(list)
    for i in d["inventario"]:
        variantes[i["id_prenda"]].append(i)
    medidas = defaultdict(dict)
    for m in d["medidas_talle"]:
        medidas[m["id_prenda"]][talle[m["id_talle"]]] = m
    inventario_a_variante = {}
    filas = []
    for p in d["prendas"]:
        foto = color[p["id_color_foto"]]["nombre"] if p["id_color_foto"] in color else None
        colores, stock, talles = [], {}, {}
        for i in variantes[p["id_prenda"]]:
            c, t = color[i["id_color"]], talle[i["id_talle"]]
            if all(x["nombre"] != c["nombre"] for x in colores):
                colores.append({"nombre": c["nombre"], "hex": c["hex"], "es_foto": c["nombre"] == foto})
            stock[clave_variante(c["nombre"], t)] = {"sku": i["sku"], "stock": int(i["stock"])}
            talles.setdefault(t, {"talle": t})
            inventario_a_variante[i["id_inventario"]] = (p, c["nombre"], t, i["sku"])
        for t, m in medidas[p["id_prenda"]].items():
            talles.setdefault(t, {"talle": t}).update({k: int(m[k]) for k in ("pecho", "cintura", "cadera",
                                                                                "hombros", "largo")})
        if colores and not any(c["es_foto"] for c in colores):
            colores[0]["es_foto"] = True
        colores.sort(key=lambda c: not c["es_foto"])
        orden = sorted(talles.values(), key=lambda t: ORDEN_TALLES.index(t["talle"]) if t["talle"] in ORDEN_TALLES
                       else len(ORDEN_TALLES))
        ajuste = {"margen_hombros": float(p["margen_hombros"]), "margen_cuello": float(p["margen_cuello"]),
                  "rotacion": int(p["rotacion"]), "voltear_horizontal": bool(p["voltear_horizontal"]),
                  "voltear_vertical": bool(p["voltear_vertical"])}
        filas.append((p["id_prenda"], p["codigo"], p["sku"], p["nombre"], p["descripcion"], p["categoria"], p["genero"],
                      p["precio"], p["calce"], p["imagen_url"], json.dumps(ajuste), json.dumps(colores, ensure_ascii=False),
                      json.dumps(orden, ensure_ascii=False), json.dumps(stock, ensure_ascii=False), p["estado"],
                      p["fecha_creacion"]))
    return filas, inventario_a_variante


def armar_clientes(d):
    nivel = {n["id_nivel"]: n["nombre"] for n in d["niveles_fidelidad"]}
    cupones, sueltos = defaultdict(list), 0
    for c in d["cupones"]:
        if c["id_cliente"] is None:
            sueltos += 1  # cupón general (sin cliente): en el diseño nuevo cada cupón es de un cliente
            continue
        cupones[c["id_cliente"]].append({
            "codigo": c["codigo"], "descripcion": c["descripcion"], "tipo": c["tipo"], "valor": float(c["valor"]),
            "compra_minima": float(c["compra_minima"]), "vence": _texto(c["vence"]), "usado": bool(c["usado"]),
            "fecha_uso": _texto(c["fecha_uso"]), "creado": _texto(c["fecha_creacion"])[:10]})
    favoritos = defaultdict(list)
    for f in d["favoritos"]:
        favoritos[f["id_cliente"]].append(f["id_prenda"])
    filas = [(c["id_cliente"], c["nombre"], c["apellido"], c["email"], c["telefono"], c["fecha_nacimiento"],
              c["talle_preferido"], c["acepta_promociones"], nivel[c["id_nivel"]], c["puntos"], c["total_gastado"],
              json.dumps(cupones[c["id_cliente"]], ensure_ascii=False), json.dumps(favoritos[c["id_cliente"]]),
              c["fecha_alta"], c["ultima_visita"]) for c in d["clientes"]]
    return filas, sueltos


def armar_pruebas(d, inventario_a_variante):
    sesiones = {s["id_sesion"]: s for s in d["sesiones_prueba"]}
    filas = []
    for sel in d["prendas_seleccionadas"]:
        s = sesiones[sel["id_sesion"]]
        p, color, talle, _ = inventario_a_variante[sel["id_inventario"]]
        fin = s["fecha_fin"] or s["fecha_inicio"]
        filas.append((p["id_prenda"], s["id_tienda"], s["tipo_sesion"], color, talle,
                      int((fin - s["fecha_inicio"]).total_seconds()), sel["fecha_seleccion"], sel["id_sesion"]))
    return filas


def armar_compras(d, inventario_a_variante):
    lineas = defaultdict(list)
    for c in d["compras"]:
        p, color, talle, sku = inventario_a_variante[c["id_inventario"]]
        clave = c["id_pedido"] if c["id_pedido"] is not None else f"sin_pedido_{c['id_compra']}"
        lineas[clave].append((c, {"id_prenda": p["id_prenda"], "sku": sku, "nombre": p["nombre"], "color": color,
                                  "talle": talle, "cantidad": int(c["cantidad"]),
                                  "precio": float(c["precio_unitario"])}))
    cupon = {c["id_cupon"]: c["codigo"] for c in d["cupones"]}
    estado = {"pendiente": "pendiente", "pagado": "pagada", "cancelado": "cancelada", "entregado": "entregada"}
    filas = []
    for pe in d["pedidos"]:
        detalle = [linea for _, linea in lineas.pop(pe["id_pedido"], [])]
        filas.append((pe["id_pedido"], pe["id_cliente"], pe["id_tienda"], json.dumps(detalle, ensure_ascii=False),
                      pe["subtotal"], pe["descuento_nivel"], pe["descuento_cupon"], pe["descuento_puntos"], pe["total"],
                      cupon.get(pe["id_cupon"]), pe["puntos_usados"], pe["puntos_ganados"], estado[pe["estado"]],
                      pe["fecha"], pe["id_sesion"]))
    for sueltas in lineas.values():  # compras viejas sin pedido: una compra por cada una
        c, linea = sueltas[0]
        total = linea["precio"] * linea["cantidad"]
        filas.append((None, None, c["id_tienda"], json.dumps([linea], ensure_ascii=False), total, 0, 0, 0, total,
                      None, 0, 0, c["estado"], c["fecha_compra"], c["id_sesion"]))
    return filas


def main():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    conexion = conectar()
    cursor = conexion.cursor(dictionary=True)
    if not _existe(cursor, "prendas"):
        print("[OK] La base ya tiene las 5 tablas nuevas: no hay nada que migrar.")
        return 0
    if _existe(cursor, "prenda"):
        print("[ERROR] Ya existe la tabla 'prenda' junto a las viejas: una migración anterior quedó a medias.\n"
              "Revisá la base en MySQL Workbench antes de seguir (no se cambió nada).")
        return 1

    d = leer_todo(cursor)
    prendas, inventario_a_variante = armar_prendas(d)
    clientes, cupones_sueltos = armar_clientes(d)
    pruebas = armar_pruebas(d, inventario_a_variante)
    compras = armar_compras(d, inventario_a_variante)
    print(f"Leído: {len(prendas)} prendas ({len(d['inventario'])} variantes), {len(clientes)} clientes, "
          f"{len(d['cupones'])} cupones, {len(pruebas)} pruebas, {len(compras)} compras.")

    cursor.execute("RENAME TABLE clientes TO clientes_anterior")
    conexion.commit()
    conexion.close()
    crear_tablas(SCRIPT_SQL)
    conexion = conectar()
    cursor = conexion.cursor(dictionary=True)
    try:
        for t in d["tiendas"]:
            equipos = [{"tipo": e["tipo"], "ubicacion": e["ubicacion"], "estado": e["estado"],
                        "fecha_instalacion": _texto(e["fecha_instalacion"])}
                       for e in d["dispositivos_tienda"] if e["id_tienda"] == t["id_tienda"]]
            cursor.execute("INSERT INTO tienda (id_tienda, nombre, direccion, ciudad, telefono, email, equipos, estado, "
                           "fecha_creacion) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                           (t["id_tienda"], t["nombre"], t["direccion"], t["ciudad"], t["telefono"], t["email"],
                            json.dumps(equipos, ensure_ascii=False), t["estado"], t["fecha_creacion"]))
        cursor.executemany(
            "INSERT INTO prenda (id_prenda, codigo, sku, nombre, descripcion, categoria, genero, precio, calce, "
            "imagen_url, ajuste_foto, colores, talles, stock, estado, fecha_creacion) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)", prendas)
        cursor.executemany(
            "INSERT INTO clientes (id_cliente, nombre, apellido, email, telefono, fecha_nacimiento, talle_preferido, "
            "acepta_promociones, nivel, puntos, total_gastado, cupones, favoritos, fecha_alta, ultima_visita) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)", clientes)
        prueba_de_sesion = {}
        for id_prenda, id_tienda, tipo, color, talle, segundos, fecha, id_sesion in pruebas:
            cursor.execute("INSERT INTO prueba (id_prenda, id_tienda, tipo, color, talle, segundos, fecha) "
                           "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                           (id_prenda, id_tienda, tipo, color, talle, segundos, fecha))
            prueba_de_sesion.setdefault(id_sesion, cursor.lastrowid)
        for *fila, id_sesion in compras:
            id_prueba = prueba_de_sesion.get(id_sesion)
            cursor.execute(
                "INSERT INTO compra (id_compra, id_cliente, id_tienda, detalle, subtotal, descuento_nivel, "
                "descuento_cupon, descuento_puntos, total, cupon, puntos_usados, puntos_ganados, estado, fecha, "
                "id_prueba) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)", (*fila, id_prueba))
            if id_prueba:
                cursor.execute("UPDATE prueba SET compro = TRUE WHERE id_prueba = %s", (id_prueba,))

        # Verificación: todo lo que había tiene que estar
        cursor.execute("SELECT stock FROM prenda")
        variantes = [v for f in cursor.fetchall() for v in json.loads(f["stock"]).values()]
        controles = [
            ("prendas", len(d["prendas"]), "SELECT COUNT(*) AS n FROM prenda"),
            ("clientes", len(d["clientes"]), "SELECT COUNT(*) AS n FROM clientes"),
            ("compras", len(compras), "SELECT COUNT(*) AS n FROM compra"),
            ("pruebas", len(pruebas), "SELECT COUNT(*) AS n FROM prueba"),
            ("tiendas", len(d["tiendas"]), "SELECT COUNT(*) AS n FROM tienda"),
        ]
        errores = []
        for nombre, esperado, consulta in controles:
            cursor.execute(consulta)
            if cursor.fetchone()["n"] != esperado:
                errores.append(nombre)
        if len(variantes) != len(d["inventario"]):
            errores.append("variantes")
        if sum(v["stock"] for v in variantes) != sum(int(i["stock"]) for i in d["inventario"]):
            errores.append("unidades en stock")
        cursor.execute("SELECT COALESCE(SUM(JSON_LENGTH(cupones)), 0) AS n FROM clientes")
        if int(cursor.fetchone()["n"]) != len(d["cupones"]) - cupones_sueltos:
            errores.append("cupones")
        if errores:
            raise RuntimeError("no coinciden: " + ", ".join(errores))
        conexion.commit()
    except Exception as error:
        conexion.rollback()
        print(f"[ERROR] {error}. Las tablas nuevas quedaron vacías y las viejas no se tocaron "
              "(la tabla clientes vieja se llama ahora clientes_anterior).")
        return 1

    cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
    cursor.execute("DROP VIEW IF EXISTS vista_stock")
    for disparador in ("trg_sesiones_validar_insert", "trg_sesiones_validar_update"):
        cursor.execute(f"DROP TRIGGER IF EXISTS {disparador}")
    for tabla in TABLAS_VIEJAS:
        cursor.execute(f"DROP TABLE IF EXISTS {tabla}")
    cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
    conexion.commit()
    conexion.close()
    print(f"[OK] Base migrada a 5 tablas: {len(prendas)} prendas con {len(variantes)} variantes y "
          f"{sum(v['stock'] for v in variantes)} unidades, {len(clientes)} clientes, {len(compras)} compras, "
          f"{len(pruebas)} pruebas.")
    if cupones_sueltos:
        print(f"  [aviso] {cupones_sueltos} cupones sin cliente no se pasaron (en el diseño nuevo cada cupón es de "
              "un cliente).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
