# ==========================================================
# PROYECTO: PROBADOR VIRTUAL INTELIGENTE - PÁGINA WEB
# BACKEND: API DE LA TIENDA (FastAPI, corre como función de Vercel)
# ==========================================================
# Todas las rutas empiezan con /api (vercel.json manda /api/* a este archivo).
# Usa tienda.py, el mismo módulo del programa de escritorio: las reglas de stock,
# niveles, puntos y cupones son idénticas. Si no hay base configurada, la página
# sigue mostrando el catálogo (lo lee de datos/catalogo.json) pero no vende.

import datetime
import os
import sys
from decimal import Decimal
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "_lib"))

import conexion_mysql  # noqa: E402
import tienda  # noqa: E402

app = FastAPI(title="Probador Virtual Inteligente - API", docs_url="/api/docs", openapi_url="/api/openapi.json")


def a_json(valor):
    """Convierte lo que devuelve MySQL / tienda.py (Decimal, fechas, sets) a JSON."""
    if isinstance(valor, dict):
        return {str(k): a_json(v) for k, v in valor.items()
                if k not in ("todos_los_cupones",)}  # los cupones usados no salen de la base
    if isinstance(valor, (list, tuple, set)):
        return [a_json(v) for v in valor]
    if isinstance(valor, Decimal):
        return int(valor) if valor == valor.to_integral_value() else float(valor)
    if isinstance(valor, (datetime.date, datetime.datetime)):
        return valor.isoformat()
    return valor


def sin_base():
    raise HTTPException(503, "La tienda en línea todavía no tiene base de datos configurada.")


def con_la_base(funcion, *args, **kwargs):
    """Corre una función de tienda.py y traduce sus errores a respuestas HTTP."""
    if not conexion_mysql.hay_base_configurada():
        sin_base()
    try:
        return funcion(*args, **kwargs)
    except tienda.ErrorTienda as error:
        raise HTTPException(400, str(error))
    except HTTPException:
        raise
    except Exception as error:
        print(f"[API] Error con la base: {error!r}")
        raise HTTPException(502, "No se pudo conectar con la base de datos. Probá de nuevo en un momento.")


# -------------------------------------------------------------------------
# MODELOS DE LOS PEDIDOS
# -------------------------------------------------------------------------
class Ingreso(BaseModel):
    email: str


class NuevoCliente(BaseModel):
    nombre: str
    email: str
    apellido: str = ""
    telefono: str = ""
    fecha_nacimiento: Optional[datetime.date] = None
    talle_preferido: Optional[str] = None
    acepta_promociones: bool = False


class Favorito(BaseModel):
    id_cliente: int
    id_prenda: int


class Item(BaseModel):
    id_prenda: int
    color: str
    talle: str
    cantidad: int = Field(1, ge=1, le=10)


class Pedido(BaseModel):
    items: List[Item]
    id_cliente: Optional[int] = None
    cupon: Optional[str] = None
    usar_puntos: bool = False
    id_prueba: Optional[int] = None


class Prueba(BaseModel):
    id_prenda: int
    color: str
    talle: str
    segundos: float = Field(0, ge=0, le=86400)
    id_cliente: Optional[int] = None


# -------------------------------------------------------------------------
# RUTAS
# -------------------------------------------------------------------------
@app.get("/api/salud")
def salud():
    """Para saber si la API anda y si tiene base de datos."""
    if not conexion_mysql.hay_base_configurada():
        return {"api": True, "base": False}
    try:
        conexion = conexion_mysql.conectar()
        conexion.close()
        return {"api": True, "base": True}
    except Exception as error:
        print(f"[API] Sin conexión con la base: {error!r}")
        return {"api": True, "base": False}


@app.get("/api/prendas")
def prendas():
    """Precio y stock en vivo de cada prenda (las fotos y la malla están en datos/catalogo.json)."""
    return JSONResponse({"prendas": con_la_base(conexion_mysql.leer_prendas)},
                        headers={"Cache-Control": "no-store"})


@app.get("/api/niveles")
def niveles():
    return [{"nombre": n, "desde": d, "descuento_pct": p, "beneficio": b} for n, d, p, b in tienda.NIVELES]


@app.post("/api/clientes/ingresar")
def ingresar(datos: Ingreso):
    cliente = con_la_base(tienda.buscar_cliente, datos.email)
    if not cliente:
        raise HTTPException(404, "No encontramos una cuenta con ese email. Podés crearla.")
    return a_json(cliente)


@app.get("/api/clientes/{id_cliente}")
def cliente(id_cliente: int):
    def leer():
        conexion = conexion_mysql.conectar()
        try:
            return tienda._leer_cliente(conexion.cursor(dictionary=True), id_cliente)
        finally:
            conexion.close()
    datos = con_la_base(leer)
    if not datos:
        raise HTTPException(404, "Esa cuenta no existe.")
    return a_json(datos)


@app.post("/api/clientes")
def registrar(datos: NuevoCliente):
    return a_json(con_la_base(tienda.registrar_cliente, datos.nombre, datos.email, datos.apellido, datos.telefono,
                              datos.fecha_nacimiento, datos.talle_preferido, datos.acepta_promociones))


@app.post("/api/favoritos")
def favorito(datos: Favorito):
    return {"favorito": con_la_base(tienda.alternar_favorito, datos.id_cliente, datos.id_prenda)}


@app.post("/api/cotizar")
def cotizar(pedido: Pedido):
    """Total con descuentos, sin comprar (para mostrarlo antes de confirmar)."""
    def calcular():
        conexion = conexion_mysql.conectar()
        try:
            cursor = conexion.cursor(dictionary=True)
            subtotal = Decimal(0)
            for item in pedido.items:
                cursor.execute("SELECT precio FROM prenda WHERE id_prenda = %s AND estado = 'activa'", (item.id_prenda,))
                fila = cursor.fetchone()
                if not fila:
                    raise tienda.ErrorTienda("Esa prenda ya no está en el catálogo.")
                subtotal += Decimal(fila["precio"]) * item.cantidad
            cliente_ = tienda._leer_cliente(cursor, pedido.id_cliente) if pedido.id_cliente else None
            cupon = None
            if pedido.cupon and cliente_:
                cupon = next((c for c in cliente_["cupones"] if c["codigo"] == pedido.cupon), None)
            return tienda.calcular_total(subtotal, cliente_, cupon, pedido.usar_puntos)
        finally:
            conexion.close()
    return a_json(con_la_base(calcular))


@app.post("/api/pruebas")
def prueba(datos: Prueba):
    """Guarda que alguien se probó una prenda en el probador web (nunca imágenes)."""
    return {"id_prueba": con_la_base(tienda.registrar_prueba, datos.id_prenda, datos.color, datos.talle,
                                     datos.segundos, datos.id_cliente)}


@app.post("/api/compras")
def comprar(pedido: Pedido):
    items = [item.model_dump() for item in pedido.items]
    return a_json(con_la_base(tienda.comprar, items, pedido.id_cliente, pedido.cupon, pedido.usar_puntos,
                              pedido.id_prueba))
