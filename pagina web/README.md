# Vestidor Virtual — página web

Versión web del **Probador Virtual Inteligente**, lista para publicar en **Vercel**, con el frontend y el backend en la misma carpeta.

| Parte | Qué es | Dónde está |
|---|---|---|
| Frontend | Tienda (catálogo, cuenta, compra) y probador con cámara. Es HTML, CSS y JavaScript, sin compilar nada. | `public/` |
| Backend | API en Python (FastAPI) que corre como función de Vercel. Usa el mismo `tienda.py` del programa de escritorio. | `api/index.py`, `api/_lib/` |
| Base de datos | MySQL en la nube (Vercel no guarda bases de datos). | Variables de entorno |

### Por qué el probador corre en el navegador

En el programa de escritorio, la cámara la procesan Python, OpenCV y MediaPipe en la compu. En la web eso no puede correr en el servidor: Vercel no tiene cámara, y mandar el video de cada cuadro a un servidor sería lento y poco privado.

Por eso el probador web usa **MediaPipe en su versión para navegador** y la **misma malla de 23 puntos** de cada prenda. El script de exportación calcula esa malla con el código de Python del proyecto. La imagen de la cámara **nunca sale de la compu del cliente**: a la base sólo llega qué prenda se probó, en qué color y talle, y cuánto tiempo.

**Diferencias con el probador de escritorio:**
- La versión web se recorta a la silueta, protege la cara, quita el temblor con el filtro One Euro y respeta el talle y el calce.
- Todavía no tiene el escáner de silueta fila por fila, la inercia de la tela, la luz de la escena, el pelo por delante ni los logos rígidos.

---

## 1. Probarla en la compu

Desde la carpeta `pagina web`:

```bash
python -m venv .venv
```

```bash
.venv\Scripts\python.exe -m pip install -r requirements.txt uvicorn
```

```bash
.venv\Scripts\python.exe servidor_local.py
```

Después abrí <http://localhost:8000>.

- **Base de datos:** el servidor local usa la base MySQL de la compu, con los datos de `../base_datos/mysql.ini`.
- **Documentación de la API:** está en <http://localhost:8000/api/docs>.
- **Modo foto, sin cámara:** abrí `probador.html?foto=mi_foto.jpg`, con la foto dentro de `public/`. Sirve para presentaciones.

## 2. Actualizar el catálogo de la página

Hay que correrlo cada vez que cambian las prendas, los colores o las fotos. Se corre desde la carpeta del proyecto principal, con su entorno de Python:

```bash
.venv\Scripts\python.exe "pagina web\scripts\exportar_catalogo.py"
```

El script genera:
- `public/prendas/*.webp`: una imagen por prenda y por color.
- `public/datos/catalogo.json`: los datos de cada prenda y los puntos de su malla.

Además copia `tienda.py` a `api/_lib/`, para que la web use las mismas reglas de stock, niveles, puntos y cupones.

## 3. Crear la base MySQL en la nube

Vercel no puede usar el MySQL de tu compu. Creá una base MySQL gratuita en un servicio en la nube, por ejemplo **Aiven for MySQL** (plan gratis) o **TiDB Cloud Serverless**. El servicio te va a dar el host, el puerto, el usuario y la contraseña.

Para crear las tablas y cargar el catálogo, usá el mismo programa que ya tenés. En una terminal, en la carpeta del proyecto principal, cargá los datos de la base de la nube y corré el cargador:

```powershell
$env:PROBADOR_MYSQL_HOST="tu-host.aivencloud.com"; $env:PROBADOR_MYSQL_PORT="12345"; $env:PROBADOR_MYSQL_USER="avnadmin"; $env:PROBADOR_MYSQL_PASSWORD="(tu contraseña)"; $env:PROBADOR_MYSQL_DATABASE="probador_virtual"
```

```bash
.venv\Scripts\python.exe cargar_prendas_mysql.py --crear-tablas
```

Esas variables duran sólo mientras esté abierta esa terminal: tu `mysql.ini` local no se toca. La contraseña nunca se escribe en el código ni se sube a GitHub.

## 4. Publicar en Vercel

**Opción A, con GitHub (recomendada):**
1. Subí el proyecto a un repositorio de GitHub.
2. En <https://vercel.com>, entrá a **Add New → Project** e importá el repositorio.
3. En **Root Directory** elegí `pagina web`. El *Framework Preset* queda en **Other**.
4. En **Environment Variables** cargá las variables de `.env.example`, con los datos de la base de la nube y `PROBADOR_MYSQL_SSL=1`.
5. Tocá **Deploy**. Cada vez que subas cambios a GitHub, Vercel publica la versión nueva.

**Opción B, desde la terminal:** dentro de `pagina web`, corré `npx vercel`. Después cargá las variables en el panel del proyecto y publicá con `npx vercel --prod`.

**Si no configurás la base**, la página igual se publica en **modo vidriera**: muestra el catálogo y el probador funciona, pero no se puede comprar.

## Cómo está organizada

```
pagina web/
├── vercel.json          rutas (/api/* → api/index.py) y la carpeta pública
├── requirements.txt     paquetes de Python del backend
├── .env.example         variables que hay que cargar en Vercel
├── servidor_local.py    servidor para probar en la compu
├── api/
│   ├── index.py         API: prendas, clientes, favoritos, cotizar, pruebas, compras
│   └── _lib/            conexion_mysql.py (para la nube) y tienda.py (copiado del proyecto)
├── public/
│   ├── index.html       tienda
│   ├── probador.html    probador con cámara
│   ├── css/estilos.css
│   ├── js/              comun.js, tienda.js, malla.js (geometría), probador.js
│   ├── modelos/         modelo de pose de MediaPipe
│   ├── prendas/         imágenes exportadas
│   └── datos/           catalogo.json exportado
└── scripts/
    └── exportar_catalogo.py
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
