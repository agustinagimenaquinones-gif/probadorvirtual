# Vestidor Virtual — página web

Versión web del **Probador Virtual Inteligente**, lista para publicar en **Vercel**, con el frontend y el backend en la misma carpeta. La base de datos está en **Supabase** (PostgreSQL).

| Parte | Qué es | Dónde está |
|---|---|---|
| Frontend | Tienda (catálogo, cuenta, compra) y probador con cámara. Es HTML, CSS y JavaScript, sin compilar nada. | `public/` |
| Backend | API en Python (FastAPI) que corre como función de Vercel. Usa el mismo `tienda.py` del programa de escritorio. | `api/index.py`, `api/_lib/` |
| Base de datos | Supabase (PostgreSQL), con las mismas 5 tablas que el MySQL del proyecto. | `supabase/` y la variable `DATABASE_URL` |

El programa de escritorio sigue usando el MySQL de la compu. La página web usa Supabase. El catálogo se pasa de uno a otro con un script (paso 3).

### Por qué el probador corre en el navegador

En el programa de escritorio, la cámara la procesan Python, OpenCV y MediaPipe en la compu. En la web eso no puede correr en el servidor: Vercel no tiene cámara, y mandar el video de cada cuadro a un servidor sería lento y poco privado.

Por eso el probador web usa **MediaPipe en su versión para navegador** y la **misma malla de 31 puntos** de cada prenda. El script de exportación calcula esa malla con el código de Python del proyecto. La imagen de la cámara **nunca sale de la compu del cliente**: a la base sólo llega qué prenda se probó, en qué color y talle, y cuánto tiempo.

**Diferencias con el probador de escritorio:**
- La versión web mide la silueta a varias alturas (sin contar los brazos), se recorta a ella, deja los brazos por delante, ancla el cuello de los tops halter, protege la cara, quita el temblor con el filtro One Euro y respeta el talle y el calce.
- Todavía no tiene el escáner de silueta fila por fila, la tela que envuelve el torso, la inercia de la tela, la luz de la escena, el pelo por delante ni los logos rígidos. Con los brazos cruzados, la tela queda por delante.

---

## 1. Crear las tablas en Supabase

En el panel de Supabase, entrá al proyecto y abrí **SQL Editor**. Ejecutá estos dos archivos, en este orden:

1. `supabase/esquema.sql`: crea las 5 tablas. Les activa RLS sin políticas, así nadie las puede tocar con las claves públicas de Supabase.
2. `supabase/catalogo.sql`: carga las 14 prendas con su stock.

Los dos se pueden ejecutar más de una vez sin duplicar nada.

Con el servidor MCP de Supabase conectado (`.mcp.json` en la carpeta del proyecto), también se le puede pedir a Claude que los ejecute.

## 2. Publicar en Vercel

1. En <https://vercel.com>, entrá a **Add New → Project** e importá el repositorio `probadorvirtual` de GitHub.
2. En **Root Directory** elegí `pagina web`. El *Framework Preset* queda en **Other**.
3. En **Environment Variables** agregá `DATABASE_URL`. Para obtenerla:
   - En Supabase, tocá **Connect → Transaction pooler** (puerto 6543).
   - Copiá la cadena y reemplazá `[YOUR-PASSWORD]` por la contraseña de la base.
   - Es la cadena de `.env.example`.
4. Tocá **Deploy**. Cada vez que subas cambios a GitHub (`git push`), Vercel publica la versión nueva.

La contraseña de la base va sólo en Vercel: nunca en el código ni en GitHub. **Si no cargás `DATABASE_URL`**, la página igual se publica en **modo vidriera**: muestra el catálogo y el probador funciona, pero no se puede comprar.

## 3. Actualizar el catálogo

Hay que hacerlo cada vez que cambian las prendas, los colores o las fotos. Los comandos se corren desde la carpeta del proyecto principal:

```bash
.venv\Scripts\python.exe "pagina web\scripts\exportar_catalogo.py"
```

```bash
.venv\Scripts\python.exe "pagina web\scripts\exportar_a_supabase.py"
```

- **El primer comando** genera las imágenes (`public/prendas/*.webp`) y los puntos de la malla (`public/datos/catalogo.json`). Además copia `tienda.py` a `api/_lib/`, con la conexión a Supabase.
- **El segundo comando** genera `supabase/catalogo.sql` desde tu MySQL. Ejecutalo en Supabase: actualiza los datos de las prendas pero no pisa el stock que se vendió por la web.

## 4. Probarla en la compu

Desde la carpeta `pagina web`:

```bash
python -m venv .venv
```

```bash
.venv\Scripts\python.exe -m pip install -r requirements.txt uvicorn
```

Para que compre de verdad, antes cargá `$env:DATABASE_URL="..."` en esa terminal. Sin esa variable, la página anda en modo vidriera.

```bash
.venv\Scripts\python.exe servidor_local.py
```

Después abrí <http://localhost:8000>.

- **Documentación de la API:** está en <http://localhost:8000/api/docs>.
- **Modo foto, sin cámara:** abrí `probador.html?foto=mi_foto.jpg`, con la foto dentro de `public/`. Sirve para presentaciones.

## Cómo está organizada

```
pagina web/
├── vercel.json          carpeta pública y permiso de cámara
├── requirements.txt     paquetes de Python del backend (FastAPI y psycopg)
├── .env.example         la variable que hay que cargar en Vercel
├── servidor_local.py    servidor para probar en la compu
├── api/
│   ├── index.py         API: prendas, clientes, favoritos, cotizar, pruebas, compras
│   └── _lib/            conexion_db.py (Supabase) y tienda.py (copiado del proyecto)
├── supabase/
│   ├── esquema.sql      las 5 tablas en PostgreSQL
│   └── catalogo.sql     las prendas exportadas del MySQL
├── public/
│   ├── index.html       tienda
│   ├── probador.html    probador con cámara
│   ├── css/, js/        estilos; comun.js, tienda.js, malla.js (geometría), probador.js
│   ├── modelos/         modelo de pose de MediaPipe
│   ├── prendas/         imágenes exportadas
│   └── datos/           catalogo.json exportado
└── scripts/
    ├── exportar_catalogo.py
    └── exportar_a_supabase.py
```

## Rutas de la API

| Método | Ruta | Para qué |
|---|---|---|
| GET | `/api/salud` | Saber si la API y la base responden |
| GET | `/api/prendas` | Precio y stock en vivo |
| POST | `/api/clientes` | Crear una cuenta (con cupón de bienvenida) |
| POST | `/api/clientes/ingresar` | Ingresar con el email |
| GET | `/api/clientes/{id}` | Datos actualizados del cliente |
| POST | `/api/favoritos` | Agregar o quitar un favorito |
| POST | `/api/cotizar` | Total con descuentos, sin comprar |
| POST | `/api/pruebas` | Registrar que alguien se probó una prenda |
| POST | `/api/compras` | Comprar (descuenta stock, suma puntos y sube de nivel) |

> **Aviso de seguridad:** igual que en el programa de escritorio, se ingresa sólo con el email, sin contraseña. Para una demostración escolar alcanza. Para una tienda real habría que agregar contraseñas o un ingreso con código por email.
