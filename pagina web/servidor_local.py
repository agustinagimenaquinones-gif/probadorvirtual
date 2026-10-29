# ==========================================================
# PROYECTO: PROBADOR VIRTUAL INTELIGENTE - PÁGINA WEB
# HERRAMIENTA: PROBAR LA PÁGINA EN LA COMPU ANTES DE SUBIRLA A VERCEL
# ==========================================================
# Uso (desde la carpeta "pagina web"):
#     .venv\Scripts\python.exe servidor_local.py
# y abrir http://localhost:8000 en el navegador.
#
# Sirve la misma API que Vercel (api/index.py) y los archivos de public/. Usa la base
# MySQL de la compu: toma los datos de ../base_datos/mysql.ini (el del probador de
# escritorio) salvo que ya estén las variables PROBADOR_MYSQL_*.

import configparser
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
INI = os.path.join(os.path.dirname(AQUI), "base_datos", "mysql.ini")

if "PROBADOR_MYSQL_HOST" not in os.environ and os.path.exists(INI):
    parser = configparser.ConfigParser()
    parser.read(INI, encoding="utf-8")
    if parser.has_section("mysql"):
        for clave, valor in parser.items("mysql"):
            os.environ.setdefault(f"PROBADOR_MYSQL_{clave.upper()}", valor)
        os.environ.setdefault("PROBADOR_MYSQL_HOST", "localhost")

sys.path.insert(0, AQUI)

import uvicorn  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from api.index import app  # noqa: E402

app.mount("/", StaticFiles(directory=os.path.join(AQUI, "public"), html=True), name="public")

if __name__ == "__main__":
    puerto = int(os.environ.get("PORT", "8000"))
    print(f"Página web en http://localhost:{puerto}  (API en /api, documentación en /api/docs)")
    uvicorn.run(app, host="127.0.0.1", port=puerto)
