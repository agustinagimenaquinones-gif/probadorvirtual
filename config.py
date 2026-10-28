# ==========================================================
# PROYECTO: PROBADOR VIRTUAL INTELIGENTE - BOUTIQUE FEMENINA
# MÓDULO: CONFIGURACIÓN (rendimiento, archivos, suavizado y colores)
# ==========================================================

# Rendimiento: todo el cálculo se hace sobre una imagen de este ancho y después se
# agranda para mostrarla. En notebooks lentas es la mejora de velocidad más grande.
ANCHO_PROCESO = 640
ANCHO_PANTALLA = 1280
# MediaPipe es la etapa más lenta: se corre sobre una imagen de este ancho y sólo
# 1 de cada N cuadros (en los demás se predice la pose con la velocidad del cuerpo).
ANCHO_MEDIAPIPE = 480
CADA_N_CUADROS_MEDIAPIPE = 2
# True: MediaPipe corre en otro hilo, en paralelo con el dibujo de la prenda (aprovecha
# otro núcleo del procesador; CADA_N_CUADROS_MEDIAPIPE no se usa). False: un paso por vez.
MEDIAPIPE_EN_SEGUNDO_PLANO = True

# -------------------------------------------------------------------------
# CONSTANTES Y CONFIGURACIÓN DEL SISTEMA
# -------------------------------------------------------------------------
MODEL_FILENAME = "pose_landmarker_lite.task"
MODEL_URL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task"
# Segmentador de pelo de MediaPipe: el pelo largo queda por DELANTE de la prenda
# (y el pelo rubio no se confunde con el cuello). False lo apaga si la compu va lenta.
USAR_PELO_DELANTE = True
MODELO_PELO = "hair_segmenter.tflite"
MODELO_PELO_URL = "https://storage.googleapis.com/mediapipe-models/image_segmenter/hair_segmenter/float32/latest/hair_segmenter.tflite"
CARPETA_PRENDAS = "prendas"
CARPETA_CAPTURAS = "capturas"

# Base de datos MySQL: si está activada, el catálogo se lee de la tabla 'prendas'.
# Si MySQL no responde, se usa el catálogo escrito en catalogo.py (el probador
# nunca deja de funcionar). Los datos de conexión van en MYSQL_ARCHIVO_CONFIG.
USAR_MYSQL = True
MYSQL_ARCHIVO_CONFIG = "base_datos/mysql.ini"
MYSQL_TIEMPO_ESPERA = 3  # segundos antes de dar por caída la conexión

# Factor multiplicador de holgura por defecto
FACTOR_ANCHO_DEFAULT = 1.0
FACTOR_AJUSTE_PASO = 0.05

# Suavizado de movimiento (EMA) solicitado por el usuario:
# posicion_nueva = posicion_anterior * 0.7 + posicion_detectada * 0.3
SMOOTH_ANTERIOR = 0.70
SMOOTH_DETECTADO = 0.30

# Paleta de colores femenina, moderna y elegante (Boutique Atelier)
COLOR_BG_APP = "#FAF7F5"       # Beige marfil cálido muy suave
COLOR_HEADER_BG = "#FFFFFF"    # Blanco puro para cabecera
COLOR_CARD_BG = "#FFFFFF"      # Blanco para tarjetas de prendas
COLOR_CARD_BORDER = "#EDE5DE"  # Borde sutil beige arena
COLOR_CARD_HOVER = "#E5D8CF"   # Borde al pasar el ratón
COLOR_TEXT_MAIN = "#2C2523"    # Carbón oscuro elegante para títulos
COLOR_TEXT_MUTED = "#786F6B"   # Taupe suave para subtítulos y detalles
COLOR_GOLD = "#C5A059"         # Dorado champagne para precios y acentos
COLOR_ROSE = "#D98880"         # Rosa vintage suave para botones principales
COLOR_ROSE_HOVER = "#C5756D"   # Rosa más intenso al posar el cursor
COLOR_TAG_BG = "#F7EFEA"       # Fondo pastel para etiquetas de talles
