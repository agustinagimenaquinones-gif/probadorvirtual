# ==========================================================
# PROYECTO: PROBADOR VIRTUAL INTELIGENTE - PÁGINA WEB
# HERRAMIENTA: PASAR EL CATÁLOGO DE MYSQL A SUPABASE
# ==========================================================
# Uso (desde la carpeta del proyecto principal, con su entorno de Python):
#     .venv\Scripts\python.exe "pagina web\scripts\exportar_a_supabase.py"
#
# Lee las prendas y las tiendas del MySQL de la compu y escribe
# pagina web/supabase/catalogo.sql con los INSERT para Supabase (PostgreSQL).
# Ese archivo se ejecuta en Supabase después de esquema.sql (en el SQL Editor del
# panel de Supabase, o pidiéndoselo a Claude con el servidor MCP de Supabase).
#
# Sólo pasa el catálogo (prendas con su stock actual y tiendas): los clientes, las
# pruebas y las compras de la página empiezan de cero. Si una prenda ya está en
# Supabase, actualiza sus datos pero NO su stock (lo vendido en la web se respeta).

import json
import os
import sys

RAIZ_WEB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAIZ_PROYECTO = os.path.dirname(RAIZ_WEB)
os.chdir(RAIZ_PROYECTO)
sys.path.insert(0, RAIZ_PROYECTO)

from conexion_mysql import conectar  # noqa: E402

ARCHIVO_SQL = os.path.join(RAIZ_WEB, "supabase", "catalogo.sql")


def literal(valor):
    """Valor de Python -> literal de PostgreSQL."""
    if valor is None:
        return "NULL"
    if isinstance(valor, bool):
        return "true" if valor else "false"
    if isinstance(valor, (int, float)) or type(valor).__name__ == "Decimal":
        return str(valor)
    if isinstance(valor, (dict, list)):
        valor = json.dumps(valor, ensure_ascii=False)
    if isinstance(valor, (bytes, bytearray)):
        valor = valor.decode("utf-8")
    return "'" + str(valor).replace("'", "''") + "'"


def jsonb(valor):
    if isinstance(valor, (bytes, bytearray)):
        valor = valor.decode("utf-8")
    if isinstance(valor, str):
        valor = json.loads(valor)
    return "NULL" if valor is None else f"{literal(valor)}::jsonb"


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    conexion = conectar()
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute("SELECT * FROM tienda ORDER BY id_tienda")
        tiendas = cursor.fetchall()
        cursor.execute("SELECT * FROM prenda ORDER BY id_prenda")
        prendas = cursor.fetchall()
    finally:
        conexion.close()

    lineas = ["-- Catálogo exportado del MySQL del probador (scripts/exportar_a_supabase.py).",
              "-- Ejecutar después de esquema.sql. Se puede volver a ejecutar: no duplica nada.", "BEGIN;", ""]
    for t in tiendas:
        lineas.append(
            "INSERT INTO tienda (id_tienda, nombre, direccion, ciudad, telefono, email, equipos, estado) VALUES ("
            + ", ".join([literal(t["id_tienda"]), literal(t["nombre"]), literal(t["direccion"]), literal(t["ciudad"]),
                         literal(t["telefono"]), literal(t["email"]), jsonb(t["equipos"]), literal(t["estado"])])
            + ") ON CONFLICT (id_tienda) DO NOTHING;")
    for p in prendas:
        lineas.append(
            "INSERT INTO prenda (id_prenda, codigo, sku, nombre, descripcion, categoria, genero, precio, calce, "
            "imagen_url, ajuste_foto, colores, talles, stock, estado) VALUES ("
            + ", ".join([literal(p["id_prenda"]), literal(p["codigo"]), literal(p["sku"]), literal(p["nombre"]),
                         literal(p["descripcion"]), literal(p["categoria"]), literal(p["genero"]), literal(p["precio"]),
                         literal(p["calce"]), literal(p["imagen_url"]), jsonb(p["ajuste_foto"]), jsonb(p["colores"]),
                         jsonb(p["talles"]), jsonb(p["stock"]), literal(p["estado"])])
            + ") ON CONFLICT (codigo) DO UPDATE SET sku = EXCLUDED.sku, nombre = EXCLUDED.nombre, "
              "descripcion = EXCLUDED.descripcion, categoria = EXCLUDED.categoria, genero = EXCLUDED.genero, "
              "precio = EXCLUDED.precio, calce = EXCLUDED.calce, imagen_url = EXCLUDED.imagen_url, "
              "ajuste_foto = EXCLUDED.ajuste_foto, colores = EXCLUDED.colores, talles = EXCLUDED.talles, "
              "estado = EXCLUDED.estado;")
    lineas += [
        "",
        "-- Los próximos id siguen después de los que se cargaron",
        "SELECT setval(pg_get_serial_sequence('tienda', 'id_tienda'), GREATEST(1, (SELECT max(id_tienda) FROM tienda)));",
        "SELECT setval(pg_get_serial_sequence('prenda', 'id_prenda'), GREATEST(1, (SELECT max(id_prenda) FROM prenda)));",
        "COMMIT;", ""]
    os.makedirs(os.path.dirname(ARCHIVO_SQL), exist_ok=True)
    with open(ARCHIVO_SQL, "w", encoding="utf-8", newline="\n") as archivo:
        archivo.write("\n".join(lineas))
    print(f"[OK] {len(prendas)} prendas y {len(tiendas)} tienda(s) -> {ARCHIVO_SQL}")


if __name__ == "__main__":
    main()
