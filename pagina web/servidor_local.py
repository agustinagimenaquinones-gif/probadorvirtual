# ==========================================================
# PROYECTO: PROBADOR VIRTUAL INTELIGENTE - PÁGINA WEB
# HERRAMIENTA: PROBAR LA PÁGINA EN LA COMPU ANTES DE SUBIRLA A VERCEL
# ==========================================================
# Uso (desde la carpeta "pagina web"):
#     .venv\Scripts\python.exe servidor_local.py
# y abrir http://localhost:8000 en el navegador.
#
# Sirve la misma API que Vercel (api/index.py) y los archivos de public/. La base es
# la de la variable DATABASE_URL (la de Supabase, o un PostgreSQL de prueba). Sin esa
# variable la página funciona en modo vidriera (sin compras).
#     $env:DATABASE_URL="postgresql://..."; .venv\Scripts\python.exe servidor_local.py

import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, AQUI)

import uvicorn  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from api.index import app  # noqa: E402

app.mount("/", StaticFiles(directory=os.path.join(AQUI, "public"), html=True), name="public")

if __name__ == "__main__":
    puerto = int(os.environ.get("PORT", "8000"))
    print(f"Página web en http://localhost:{puerto}  (API en /api, documentación en /api/docs)")
    uvicorn.run(app, host="127.0.0.1", port=puerto)
