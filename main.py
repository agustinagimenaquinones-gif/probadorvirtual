# ==========================================================
# PROYECTO: PROBADOR VIRTUAL INTELIGENTE - BOUTIQUE FEMENINA
# Flujo: Galería Visual -> Elección -> Confirmación -> Cámara en Vivo -> Calce Realista
# ==========================================================

import os
import sys
import glob
import time
import urllib.request
from datetime import datetime
import cv2
import numpy as np
from PIL import Image, ImageTk
import tkinter as tk
from tkinter import ttk, messagebox
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

# Importar generadores y gestores modulares
from crear_prendas import (
    generar_catalogo_inicial,
    procesar_top_champagne_si_existe,
    procesar_polo_azul_marino_si_existe,
    procesar_polo_ralph_lauren_si_existe,
    procesar_top_asimetrico_negro_si_existe
)
from pose_tracker import PoseTracker
from clothing_geometry import TRIANGULOS_ESTRUCTURADOS, detectar_puntos_clave_prenda
from clothing_warper import deformar_malla_prenda
from body_layering import componer_prenda_con_capas
from catalogo import (
    CATALOGO_PRENDAS,
    cargar_catalogo_completo,
    orientar_prenda,
    recortar_bordes_alfa,
    holgura_de_talle,
    talle_inicial,
    obtener_medidas_talle,
    obtener_guia_medidas_completa
)
from body_measure import ancho_total
from ajuste_silueta import ajustar_prenda_completa

# Rendimiento: todo el cálculo se hace sobre una imagen de este ancho y después se
# agranda para mostrarla. En notebooks lentas es la mejora de velocidad más grande.
ANCHO_PROCESO = 640
ANCHO_PANTALLA = 1280
# MediaPipe es la etapa más lenta: se corre sobre una imagen de este ancho y sólo
# 1 de cada N cuadros (en los demás se predice la pose con la velocidad del cuerpo).
ANCHO_MEDIAPIPE = 480
CADA_N_CUADROS_MEDIAPIPE = 2

# -------------------------------------------------------------------------
# CONSTANTES Y CONFIGURACIÓN DEL SISTEMA
# -------------------------------------------------------------------------
MODEL_FILENAME = "pose_landmarker_lite.task"
MODEL_URL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task"
CARPETA_PRENDAS = "prendas"
CARPETA_CAPTURAS = "capturas"

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


# =========================================================================
# FUNCIONES AUXILIARES Y GESTIÓN DE RECURSOS
# =========================================================================
def asegurar_recursos():
    """Verifica y asegura la existencia del modelo MediaPipe y las carpetas."""
    if not os.path.exists(MODEL_FILENAME):
        print("[+] Descargando modelo MediaPipe Pose Landmarker...")
        try:
            urllib.request.urlretrieve(MODEL_URL, MODEL_FILENAME)
            print("[OK] Modelo descargado exitosamente.")
        except Exception as e:
            print(f"[ERROR] No se pudo descargar el modelo: {e}")
            sys.exit(1)

    os.makedirs(CARPETA_PRENDAS, exist_ok=True)
    os.makedirs(CARPETA_CAPTURAS, exist_ok=True)

    # Verificar y preparar prendas
    pngs = glob.glob(os.path.join(CARPETA_PRENDAS, "*.png"))
    if len(pngs) < 3:
        print("[+] Generando catálogo base de prendas...")
        generar_catalogo_inicial()
    else:
        procesar_polo_azul_marino_si_existe()
        procesar_polo_ralph_lauren_si_existe()
        procesar_top_champagne_si_existe()
        procesar_top_asimetrico_negro_si_existe()





def obtener_siguiente_nombre_captura():
    """Genera un nombre secuencial automático para capturas: capturas/prueba_001.png"""
    os.makedirs(CARPETA_CAPTURAS, exist_ok=True)
    archivos = glob.glob(os.path.join(CARPETA_CAPTURAS, "prueba_*.png"))
    numeros = []
    for a in archivos:
        base = os.path.splitext(os.path.basename(a))[0]
        num_str = base.replace("prueba_", "")
        if num_str.isdigit():
            numeros.append(int(num_str))
    siguiente = (max(numeros) + 1) if numeros else 1
    return os.path.join(CARPETA_CAPTURAS, f"prueba_{siguiente:03d}.png"), f"prueba_{siguiente:03d}.png"


# =========================================================================
# LÓGICA DE CALCE ANATÓMICO Y DEFORMACIÓN (WARP PERSPECTIVE)
# =========================================================================
def calcular_cuadrilatero_torso(landmarks, ancho, alto, factor_escala=1.0, margen_h=0.38, margen_c=0.20):
    """
    Calcula el cuadrilátero anatómico del torso a partir de los landmarks corporales:
      - 11: Hombro izquierdo
      - 12: Hombro derecho
      - 23: Cadera izquierda
      - 24: Cadera derecha

    Garantiza estrictamente:
      - Cuello arriba (menor Y)
      - Cintura y ruedo abajo (mayor Y)
      - Frente hacia el usuario (hombro derecho a la izquierda en pantalla espejo)
      - Proporciones adaptativas al ancho y alto del torso.
    """
    # 1. Puntos anatómicos en píxeles
    hombro_izq = landmarks[11]
    hombro_der = landmarks[12]
    cadera_izq = landmarks[23]
    cadera_der = landmarks[24]

    p11 = np.array([hombro_izq.x * ancho, hombro_izq.y * alto], dtype=np.float32)
    p12 = np.array([hombro_der.x * ancho, hombro_der.y * alto], dtype=np.float32)
    p23 = np.array([cadera_izq.x * ancho, cadera_izq.y * alto], dtype=np.float32)
    p24 = np.array([cadera_der.x * ancho, cadera_der.y * alto], dtype=np.float32)

    # En pantalla en espejo, el hombro a la izquierda de la pantalla es p_sh_der_pantalla (menor X)
    # y el hombro a la derecha de la pantalla es p_sh_izq_pantalla (mayor X).
    if p12[0] <= p11[0]:
        p_sh_der = p12
        p_sh_izq = p11
    else:
        p_sh_der = p11
        p_sh_izq = p12

    if p24[0] <= p23[0]:
        p_hip_der = p24
        p_hip_izq = p23
    else:
        p_hip_der = p23
        p_hip_izq = p24

    # 2. Vector horizontal de hombros (apunta hacia la derecha: X positivo)
    v_sh = p_sh_izq - p_sh_der
    dist_sh = float(np.linalg.norm(v_sh))
    if dist_sh < 10.0:
        dist_sh = 10.0
    u_sh = v_sh / dist_sh

    # Vector vertical perpendicular hacia arriba (hacia el cuello/cabeza)
    # En pantalla (Y crece hacia abajo), rotar u_sh 90° antihorario es (u_sh[1], -u_sh[0])
    u_up = np.array([u_sh[1], -u_sh[0]], dtype=np.float32)
    if u_up[1] > 0:  # Debe apuntar hacia arriba (Y negativo)
        u_up = -u_up

    # 3. Puntos medios y vector hacia el torso inferior
    p_sh_mid = (p_sh_der + p_sh_izq) * 0.5
    p_hip_mid = (p_hip_der + p_hip_izq) * 0.5

    v_torso = p_hip_mid - p_sh_mid
    dist_torso = float(np.linalg.norm(v_torso))

    # Si las caderas no son visibles o están demasiado cerca/arriba, proyectar torso proporcional
    if dist_torso < 25.0 or v_torso[1] <= 0 or hombro_izq.visibility < 0.3 or hombro_der.visibility < 0.3:
        dist_torso = dist_sh * 1.35
        u_down = -u_up
        p_hip_der = p_sh_der + u_down * dist_torso
        p_hip_izq = p_sh_izq + u_down * dist_torso
    else:
        u_down = v_torso / dist_torso
        if u_down[1] < 0:  # Debe apuntar hacia abajo (Y positivo)
            u_down = -u_down

    # 4. Vector de caderas
    v_hip = p_hip_izq - p_hip_der
    dist_hip = float(np.linalg.norm(v_hip))
    if dist_hip < 10.0:
        dist_hip = dist_sh * 0.80
        u_hip = u_sh
    else:
        u_hip = v_hip / dist_hip
        if u_hip[0] < 0:
            u_hip = -u_hip

    # 5. Holguras y proporciones anatómicas
    margen_hombro = dist_sh * margen_h * factor_escala
    margen_cuello = dist_sh * margen_c * factor_escala
    margen_cadera = dist_hip * 0.30 * factor_escala
    margen_ruedo  = dist_torso * 0.16 * factor_escala

    # 6. Cuadrilátero ordenado:
    # 0: Top-Left (Hombro derecho de la persona / izquierda de pantalla)
    pt_tl = p_sh_der - (u_sh * margen_hombro) + (u_up * margen_cuello)
    # 1: Top-Right (Hombro izquierdo de la persona / derecha de pantalla)
    pt_tr = p_sh_izq + (u_sh * margen_hombro) + (u_up * margen_cuello)
    # 2: Bottom-Right (Cadera izquierda de la persona / derecha de pantalla)
    pt_br = p_hip_izq + (u_hip * margen_cadera) + (u_down * margen_ruedo)
    # 3: Bottom-Left (Cadera derecha de la persona / izquierda de pantalla)
    pt_bl = p_hip_der - (u_hip * margen_cadera) + (u_down * margen_ruedo)

    # 7. Salvaguarda estricta anti-inversión (cuello arriba, cintura abajo)
    if pt_tl[1] > pt_bl[1]:
        pt_tl[1], pt_bl[1] = pt_bl[1], pt_tl[1]
        pt_tr[1], pt_br[1] = pt_br[1], pt_tr[1]

    if pt_tl[0] > pt_tr[0]:
        pt_tl[0], pt_tr[0] = pt_tr[0], pt_tl[0]
        pt_bl[0], pt_br[0] = pt_br[0], pt_bl[0]

    return np.array([pt_tl, pt_tr, pt_br, pt_bl], dtype=np.float32)


def deformar_y_superponer_prenda(fondo, prenda_rgba, dst_quad):
    """
    Deforma suavemente la prenda utilizando una matriz de perspectiva de 4 puntos
    y realiza la fusión Alfa de alta precisión sobre el cuerpo en el cuadro de la cámara.
    """
    h_prenda, w_prenda = prenda_rgba.shape[:2]
    alto_fondo, ancho_fondo = fondo.shape[:2]

    if w_prenda <= 0 or h_prenda <= 0:
        return fondo

    # Puntos de origen: las 4 esquinas de la imagen recortada
    src_pts = np.float32([
        [0, 0],
        [w_prenda, 0],
        [w_prenda, h_prenda],
        [0, h_prenda]
    ])

    dst_pts = np.float32(dst_quad)

    try:
        matriz = cv2.getPerspectiveTransform(src_pts, dst_pts)
    except Exception:
        return fondo

    # Deformar imagen sobre el espacio del cuadro
    prenda_deformada = cv2.warpPerspective(
        prenda_rgba,
        matriz,
        (ancho_fondo, alto_fondo),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0, 0)
    )

    # Separar canales BGR y Alfa
    b_def, g_def, r_def, a_def = cv2.split(prenda_deformada)
    mascara_alfa = a_def > 0

    if not np.any(mascara_alfa):
        return fondo

    # Fusión Alfa pixel a pixel
    alpha = (a_def[mascara_alfa] / 255.0)[:, np.newaxis]
    rgb_prenda = np.stack([b_def[mascara_alfa], g_def[mascara_alfa], r_def[mascara_alfa]], axis=1)
    rgb_fondo = fondo[mascara_alfa]

    fondo[mascara_alfa] = ((1.0 - alpha) * rgb_fondo + alpha * rgb_prenda).astype(np.uint8)
    return fondo


def dibujar_medidas(frame, info_anatomica):
    """Dibuja las líneas de pecho, cintura y cadera medidas sobre la silueta (tecla V)."""
    medidas = (info_anatomica or {}).get("medidas") or {}
    if not medidas:
        return
    u_torso = info_anatomica["u_torso"]
    lateral = np.array([-u_torso[1], u_torso[0]], dtype=np.float32)
    if float(lateral @ info_anatomica["u_sh"]) < 0:
        lateral = -lateral
    colores = {"pecho": (255, 200, 80), "cintura": (120, 230, 120), "cadera": (210, 140, 255)}
    d_sh = max(10.0, float(info_anatomica.get("dist_sh", 200.0)))

    for nivel, color in colores.items():
        centro = medidas.get(f"{nivel}_centro")
        izq, der = medidas.get(f"{nivel}_l"), medidas.get(f"{nivel}_r")
        if centro is None or izq is None or der is None:
            continue
        a = tuple(np.int32(centro - lateral * izq))
        b = tuple(np.int32(centro + lateral * der))
        cv2.line(frame, a, b, color, 2, cv2.LINE_AA)
        cv2.circle(frame, a, 5, color, -1)
        cv2.circle(frame, b, 5, color, -1)
        ancho_px = ancho_total(medidas, nivel)
        # Estimación en cm de contorno (relación biométrica promedio basada en ancho de hombros estándar de 42 cm)
        cm_est = int(round((ancho_px / d_sh) * 42.0 * 2.15))
        cv2.putText(frame, f"{nivel.capitalize()}: {int(ancho_px)}px (~{cm_est}cm)", (b[0] + 10, b[1] + 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)


NOMBRES_ORIENTACION = {"frente": "De frente", "girada": "Girada", "perfil": "De perfil", "espalda": "De espaldas"}


def dibujar_hud_probador(frame, prenda_info, factor_escala, mensaje_notif="", modo_malla=True,
                         talle="M", figura="", fps=None, recorte=True, orientacion=None):
    """Dibuja la interfaz visual limpia y elegante requerida sobre la cámara."""
    alto, ancho, _ = frame.shape

    # Barra superior semi-transparente
    # Oscurecer sólo las dos barras (más rápido que copiar toda la imagen)
    color_barra = np.array([25, 23, 22], dtype=np.float32)
    for y0, y1 in ((0, 65), (alto - 45, alto)):
        barra = frame[y0:y1]
        barra[:] = (barra.astype(np.float32) * 0.30 + color_barra * 0.70).astype(np.uint8)

    # Título superior
    cv2.putText(frame, "PROBADOR VIRTUAL INTELIGENTE", (25, 28), cv2.FONT_HERSHEY_DUPLEX, 0.75, (255, 255, 255), 1, cv2.LINE_AA)

    # Indicador de modo de adaptación
    modo_texto = "Modo: Calce Automatico (Malla 3D + Mangas)" if modo_malla else "Modo: Basico (Perspectiva 4 Puntos)"
    if fps is not None:
        modo_texto += f"   |   {fps:.0f} FPS"
    if not recorte:
        modo_texto += "   |   Recorte OFF"
    if orientacion:
        modo_texto = f"Vista: {NOMBRES_ORIENTACION.get(orientacion, orientacion)}   |   " + modo_texto
    (ancho_texto, _), _ = cv2.getTextSize(modo_texto, cv2.FONT_HERSHEY_SIMPLEX, 0.50, 1)
    cv2.putText(frame, modo_texto, (max(420, ancho - ancho_texto - 20), 28), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (140, 230, 255), 1, cv2.LINE_AA)

    # Información de la prenda elegida
    precio_formateado = f"${prenda_info['precio']:,}".replace(',', '.')
    texto_prenda = f"Prenda: {prenda_info['nombre']}   |   Precio: {precio_formateado}"
    cv2.putText(frame, texto_prenda, (25, 52), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (210, 180, 120), 1, cv2.LINE_AA)

    # Talle elegido, sus medidas y figura estimada
    meds_t = obtener_medidas_talle(prenda_info, talle)
    calce_txt = prenda_info.get('calce', 'regular').capitalize()
    texto_talle = f"Talle: {talle} (Pecho: {meds_t['pecho']}cm · Cintura: {meds_t['cintura']}cm)   |   Calce: {calce_txt}"
    if figura:
        texto_talle += f"   |   Figura: {figura}"
    cv2.putText(frame, texto_talle, (ancho - 740, 52), cv2.FONT_HERSHEY_SIMPLEX, 0.46, (200, 235, 200), 1, cv2.LINE_AA)

    # Controles inferiores limpios y claros
    controles = "[G] Galeria | [C] Foto | [1..9 / N] Prenda | [T] Talle | [V] Medidas | [R] Recorte | [M] Modo | [+/-] Calce | [Q] Salir"
    cv2.putText(frame, controles, (25, alto - 18), cv2.FONT_HERSHEY_SIMPLEX, 0.46, (220, 220, 220), 1, cv2.LINE_AA)

    # Notificación temporal en el centro (por ejemplo al sacar una foto o cambiar prenda/talle)
    if mensaje_notif:
        cv2.putText(frame, mensaje_notif, (ancho // 2 - 250, alto - 65), cv2.FONT_HERSHEY_DUPLEX, 0.72, (80, 255, 140), 2, cv2.LINE_AA)


# =========================================================================
# MOTOR DEL PROBADOR CON CÁMARA (OPENCV + MEDIAPIPE)
# =========================================================================
def ejecutar_probador_camara(prenda_inicial, catalogo, talle_elegido="M"):
    """
    Ejecuta el bucle en vivo de la cámara con detección corporal y calce adaptativo.
    Retorna 'galeria' si el usuario presiona G, o 'salir' si presiona Q.
    """
    print(f"\n[+] Iniciando probador para prenda: {prenda_inicial['nombre']}")

    # Inicializar rastreador inteligente con MediaPipe y suavizado EMA
    tracker = PoseTracker(model_path=MODEL_FILENAME, alpha_suavizado=SMOOTH_DETECTADO,
                          ancho_mediapipe=ANCHO_MEDIAPIPE, cada_n_cuadros=CADA_N_CUADROS_MEDIAPIPE)

    # Abrir cámara web
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("[ERROR] No se pudo acceder a la cámara web.")
        messagebox.showerror("Error de Cámara", "No se pudo acceder a la cámara web. Verifica que no esté en uso por otra app.")
        tracker.cerrar()
        return "galeria"

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    # Índice de la prenda actual dentro del catálogo
    indice_prenda = 0
    for idx, p in enumerate(catalogo):
        if p["id"] == prenda_inicial["id"]:
            indice_prenda = idx
            break

    factor_escala = FACTOR_ANCHO_DEFAULT
    talle = talle_inicial(catalogo[indice_prenda], talle_elegido)
    ver_medidas = False
    opacidad_prenda = 1.0          # baja a 0 suavemente cuando la persona está de perfil
    orientacion_anterior = "frente"
    recorte_silueta = True   # prenda pegada a la silueta: escáner + recorte (tecla R)
    memoria_ajuste = {}      # suavizado del escáner entre cuadros
    fps_suave = None
    t_cuadro_anterior = time.time()
    modo_malla = True  # True: Deformación por Malla 3D; False: Clásico cuadrilátero
    smooth_quad = None
    notificacion_texto = "¡Calce automático adaptativo activo!"
    notificacion_tiempo = time.time()
    accion_salida = "galeria"

    nombre_ventana = "Probador Virtual Inteligente - Boutique Atelier"
    cv2.namedWindow(nombre_ventana, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(nombre_ventana, 1100, 680)

    while True:
        ret, frame = cap.read()
        if not ret:
            print("[ERROR] No se pudo capturar imagen de la cámara.")
            break

        # 1. Efecto espejo para interacción natural de probador
        frame = cv2.flip(frame, 1)
        # Reducir la imagen para procesarla rápido (se agranda al mostrarla)
        if frame.shape[1] > ANCHO_PROCESO:
            escala_proc = ANCHO_PROCESO / float(frame.shape[1])
            frame = cv2.resize(frame, (ANCHO_PROCESO, int(round(frame.shape[0] * escala_proc))),
                               interpolation=cv2.INTER_AREA)
        alto, ancho, _ = frame.shape

        prenda_actual = catalogo[indice_prenda]

        # 2. Detección y seguimiento corporal inteligente
        landmarks, info_anatomica = tracker.procesar_frame(frame)

        # Cuadro limpio para capturas (sin los textos del HUD)
        frame_limpio_con_prenda = frame.copy()

        if info_anatomica is not None:
            if modo_malla:
                # =========================================================
                # MODO 1 (PRINCIPAL): ADAPTACIÓN POR MALLA (MESH WARPING)
                # =========================================================
                # Asegurar puntos origen de la prenda
                if "src_puntos" not in prenda_actual or prenda_actual["src_puntos"] is None:
                    src_pts, tiene_mangas = detectar_puntos_clave_prenda(prenda_actual["imagen_cv"])
                    prenda_actual["src_puntos"] = src_pts
                    prenda_actual["tiene_mangas"] = tiene_mangas

                tiene_mangas = prenda_actual.get("tiene_mangas", True)

                # Hacia dónde mira la persona: de espaldas se usa la vista de espalda;
                # de perfil la prenda se desvanece (no hay foto de costado).
                orientacion = info_anatomica.get("orientacion", "frente")
                de_espaldas = orientacion == "espalda"
                imagen_prenda = prenda_actual.get("imagen_espalda_cv") if de_espaldas else None
                puntos_prenda = prenda_actual.get("src_puntos_espalda") if de_espaldas else None
                if imagen_prenda is None or puntos_prenda is None:
                    imagen_prenda, puntos_prenda = prenda_actual["imagen_cv"], prenda_actual["src_puntos"]
                # Si ESTE cuadro ya se ve de perfil, empezar a desvanecer enseguida
                # (sin esperar a que la vista cambie "oficialmente").
                de_perfil = orientacion == "perfil" or info_anatomica.get("orientacion_cuadro") == "perfil"
                objetivo = 0.0 if de_perfil else 1.0
                opacidad_prenda += (objetivo - opacidad_prenda) * (0.45 if de_perfil else 0.25)
                if orientacion != orientacion_anterior:
                    if orientacion == "perfil":
                        notificacion_texto = "Gira un poco hacia la camara para ver la prenda"
                    elif de_espaldas and prenda_actual.get("espalda_automatica", True):
                        notificacion_texto = "Vista de espalda (automatica: sin foto de espalda)"
                    elif de_espaldas:
                        notificacion_texto = "Vista de espalda"
                    elif orientacion_anterior in ("perfil", "espalda"):
                        notificacion_texto = "Vista de frente"
                    notificacion_tiempo = time.time()
                    orientacion_anterior = orientacion
                if orientacion == "perfil":
                    notificacion_tiempo = time.time()  # el aviso queda mientras siga de perfil

                # Calcular puntos destino adaptados al cuerpo del usuario
                # Calcular puntos destino adaptados a la figura medida del usuario,
                # al talle elegido y al tipo de calce de la prenda
                dst_pts = tracker.calcular_puntos_destino_malla(
                    info_anatomica,
                    tiene_mangas=tiene_mangas,
                    factor_escala=factor_escala,
                    holgura_talle=holgura_de_talle(talle),
                    calce=prenda_actual.get("calce", "regular")
                )

                # Deformación anatómica por malla elástica (sub-malla por regiones)
                parche, xmin, ymin, xmax, ymax = deformar_malla_prenda(
                    imagen_prenda,
                    puntos_prenda,
                    dst_pts,
                    ancho,
                    alto,
                    tiene_mangas=tiene_mangas
                )

                # Ajuste tipo ESCÁNER: la tela copia el borde de la silueta fila por fila
                if parche is not None and recorte_silueta and info_anatomica.get("mascara") is not None:
                    # (hombros columna por columna, mangas y torso fila por fila)
                    parche = ajustar_prenda_completa(
                        parche, xmin, ymin, info_anatomica["mascara"], info_anatomica,
                        holgura=holgura_de_talle(talle) * factor_escala,
                        calce=prenda_actual.get("calce", "regular"),
                        memoria=memoria_ajuste,
                        frame_bgr=frame
                    )

                # Integración visual multicapa (cuello, torso, y brazos al frente)
                if parche is not None and opacidad_prenda < 0.98:
                    parche = parche.copy()
                    parche[:, :, 3] = (parche[:, :, 3].astype(np.float32) * opacidad_prenda).astype(np.uint8)
                if de_espaldas:
                    # De espaldas, las manos "al frente" quedan detrás del cuerpo
                    info_anatomica = dict(info_anatomica, brazos_al_frente=False)
                if parche is not None and opacidad_prenda > 0.02:
                    frame = componer_prenda_con_capas(
                        frame, parche, xmin, ymin, xmax, ymax, info_anatomica,
                        talle=talle, recortar_silueta=recorte_silueta, sombras=True
                    )
            else:
                # =========================================================
                # MODO 2 (DEPURACIÓN / COMPARACIÓN): CUADRILÁTERO CLÁSICO
                # =========================================================
                quad_actual = calcular_cuadrilatero_torso(
                    landmarks, ancho, alto, factor_escala,
                    margen_h=prenda_actual.get("margen_hombros", 0.38),
                    margen_c=prenda_actual.get("margen_cuello", 0.20)
                )
                if smooth_quad is None:
                    smooth_quad = quad_actual.copy()
                else:
                    smooth_quad = (smooth_quad * SMOOTH_ANTERIOR) + (quad_actual * SMOOTH_DETECTADO)
                frame = deformar_y_superponer_prenda(frame, prenda_actual["imagen_cv"], smooth_quad)

            frame_limpio_con_prenda = frame.copy()
            if ver_medidas:
                dibujar_medidas(frame, info_anatomica)
        else:
            smooth_quad = None

        # Cuadros por segundo (promedio suave)
        ahora = time.time()
        dt = max(1e-3, ahora - t_cuadro_anterior)
        t_cuadro_anterior = ahora
        fps_suave = (1.0 / dt) if fps_suave is None else fps_suave * 0.9 + (1.0 / dt) * 0.1

        # Expiración del mensaje temporal
        if notificacion_texto and time.time() - notificacion_tiempo > 2.5:
            notificacion_texto = ""

        # Agrandar para mostrar (el HUD se dibuja en alta resolución para que se lea bien)
        if frame.shape[1] < ANCHO_PANTALLA:
            tam = (ANCHO_PANTALLA, int(round(frame.shape[0] * ANCHO_PANTALLA / float(frame.shape[1]))))
            frame = cv2.resize(frame, tam, interpolation=cv2.INTER_LINEAR)
            frame_limpio_con_prenda = cv2.resize(frame_limpio_con_prenda, tam, interpolation=cv2.INTER_LINEAR)

        # 3. Dibujar Interfaz HUD requerida
        figura = info_anatomica.get("figura", "") if info_anatomica else ""
        dibujar_hud_probador(frame, prenda_actual, factor_escala, notificacion_texto,
                             modo_malla=modo_malla, talle=talle, figura=figura,
                             fps=fps_suave, recorte=recorte_silueta,
                             orientacion=info_anatomica.get("orientacion") if info_anatomica else None)

        cv2.imshow(nombre_ventana, frame)

        # 4. Manejo interactivo de teclado
        key = cv2.waitKey(1) & 0xFF

        # [G] Volver a la galería sin cerrar el programa
        if key == ord('g') or key == ord('G'):
            accion_salida = "galeria"
            break

        # [Q] Salir de la aplicación
        elif key == ord('q') or key == ord('Q') or key == 27:
            accion_salida = "salir"
            break

        # [C] Capturar foto y guardar en capturas/prueba_xxx.png
        elif key == ord('c') or key == ord('C') or key == 32:
            ruta_foto, nombre_foto = obtener_siguiente_nombre_captura()
            cv2.imwrite(ruta_foto, frame_limpio_con_prenda)
            notificacion_texto = f"¡Foto guardada: {nombre_foto}!"
            notificacion_tiempo = time.time()
            print(f"[OK] Fotografía guardada: {ruta_foto}")

        # [T] Cambiar de talle (entre los disponibles de la prenda)
        elif key == ord('t') or key == ord('T'):
            talles = prenda_actual.get("talles") or ["M"]
            pos = talles.index(talle) if talle in talles else -1
            talle = talles[(pos + 1) % len(talles)]
            m_t = obtener_medidas_talle(prenda_actual, talle)
            notificacion_texto = f"Talle: {talle} (Pecho: {m_t['pecho']}cm · Cintura: {m_t['cintura']}cm)"
            notificacion_tiempo = time.time()

        # [R] Activar / desactivar el recorte de la prenda al borde del cuerpo
        elif key == ord('r') or key == ord('R'):
            recorte_silueta = not recorte_silueta
            notificacion_texto = "Prenda pegada a la silueta" if recorte_silueta else "Recorte desactivado"
            notificacion_tiempo = time.time()

        # [V] Mostrar / ocultar las medidas de la silueta
        elif key == ord('v') or key == ord('V'):
            ver_medidas = not ver_medidas
            notificacion_texto = "Medidas visibles" if ver_medidas else "Medidas ocultas"
            notificacion_tiempo = time.time()

        # [M] Alternar modo de adaptación (Malla 3D vs Cuadrilátero Clásico)
        elif key == ord('m') or key == ord('M'):
            modo_malla = not modo_malla
            nombre_modo = "Malla 3D Adaptativa" if modo_malla else "Clasico 4 Puntos"
            notificacion_texto = f"Modo: {nombre_modo}"
            notificacion_tiempo = time.time()
            smooth_quad = None

        # [N] o [D] Prenda siguiente
        elif key == ord('n') or key == ord('N') or key == ord('d') or key == ord('D'):
            indice_prenda = (indice_prenda + 1) % len(catalogo)
            notificacion_texto = f"Prenda: {catalogo[indice_prenda]['nombre']}"
            notificacion_tiempo = time.time()
            tracker.reiniciar()
            talle = talle_inicial(catalogo[indice_prenda], talle)
            smooth_quad = None

        # [P] o [A] Prenda anterior
        elif key == ord('p') or key == ord('P') or key == ord('a') or key == ord('A'):
            indice_prenda = (indice_prenda - 1) % len(catalogo)
            notificacion_texto = f"Prenda: {catalogo[indice_prenda]['nombre']}"
            notificacion_tiempo = time.time()
            tracker.reiniciar()
            talle = talle_inicial(catalogo[indice_prenda], talle)
            smooth_quad = None

        # Selección directa con teclas numéricas 1 a 9
        elif ord('1') <= key <= ord('9'):
            num_idx = key - ord('1')
            if num_idx < len(catalogo):
                indice_prenda = num_idx
                notificacion_texto = f"Prenda: {catalogo[indice_prenda]['nombre']}"
                notificacion_tiempo = time.time()
                tracker.reiniciar()
                talle = talle_inicial(catalogo[indice_prenda], talle)
                smooth_quad = None

        # Ajuste fino de holgura (+ y -)
        elif key == ord('+') or key == ord('='):
            factor_escala = min(2.5, factor_escala + FACTOR_AJUSTE_PASO)
        elif key == ord('-') or key == ord('_'):
            factor_escala = max(0.5, factor_escala - FACTOR_AJUSTE_PASO)

    # Limpieza de recursos
    tracker.cerrar()
    cap.release()
    cv2.destroyAllWindows()
    return accion_salida


# =========================================================================
# INTERFAZ GRÁFICA TKINTER: BOUTIQUE FEMENINA & GALERÍA DE PRENDAS
# =========================================================================
class BoutiqueVirtualApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Probador Virtual Inteligente - Boutique Atelier")
        self.root.geometry("1200x800")
        self.root.minsize(1000, 700)
        self.root.configure(bg=COLOR_BG_APP)

        # Centrar ventana en pantalla
        self.centrar_ventana(1200, 800)

        # Asegurar recursos y cargar prendas
        asegurar_recursos()
        self.catalogo = cargar_catalogo_completo()
        self.fotos_tk_cache = {}  # Cache para evitar recolección de basura de PhotoImage
        self.prenda_seleccionada = None
        self.talle_seleccionado = tk.StringVar(value="M")

        # Contenedor principal que alternará entre Galería y Confirmación
        self.contenedor_principal = tk.Frame(self.root, bg=COLOR_BG_APP)
        self.contenedor_principal.pack(fill=tk.BOTH, expand=True)

        # Iniciar mostrando la Galería
        self.mostrar_galeria()

    def centrar_ventana(self, ancho, alto):
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = max(0, (sw - ancho) // 2)
        y = max(0, (sh - alto) // 2)
        self.root.geometry(f"{ancho}x{alto}+{x}+{y}")

    def limpiar_contenedor(self):
        for widget in self.contenedor_principal.winfo_children():
            widget.destroy()

    def obtener_imagen_tk(self, ruta_archivo, tamano=(190, 190)):
        """Carga y reescala con alta calidad una imagen para mostrarla en Tkinter."""
        clave = f"{ruta_archivo}_{tamano[0]}x{tamano[1]}"
        if clave in self.fotos_tk_cache:
            return self.fotos_tk_cache[clave]

        try:
            img = Image.open(ruta_archivo)
            img.thumbnail(tamano, Image.Resampling.LANCZOS)

            # Fondo blanco para la tarjeta
            canvas_img = Image.new("RGBA", tamano, (255, 255, 255, 0))
            offset_x = (tamano[0] - img.width) // 2
            offset_y = (tamano[1] - img.height) // 2
            canvas_img.paste(img, (offset_x, offset_y), img if img.mode == 'RGBA' else None)

            foto_tk = ImageTk.PhotoImage(canvas_img)
            self.fotos_tk_cache[clave] = foto_tk
            return foto_tk
        except Exception as e:
            print(f"[AVISO] Error cargando imagen para Tkinter: {e}")
            return None

    # ---------------------------------------------------------------------
    # VISTA 1: GALERÍA DE PRENDAS (TIENDA ONLINE FEMENINA)
    # ---------------------------------------------------------------------
    def mostrar_galeria(self):
        self.limpiar_contenedor()

        # 1. Cabecera estilo Atelier de Moda Femenina
        header_frame = tk.Frame(self.contenedor_principal, bg=COLOR_HEADER_BG, pady=18)
        header_frame.pack(fill=tk.X, side=tk.TOP)

        lbl_marca = tk.Label(
            header_frame,
            text="✨   B O U T I Q U E   A T E L I E R   ✨",
            font=("Segoe UI", 10, "bold"),
            fg=COLOR_GOLD,
            bg=COLOR_HEADER_BG
        )
        lbl_marca.pack()

        lbl_titulo = tk.Label(
            header_frame,
            text="Vestidor Virtual de Moda Femenina",
            font=("Georgia", 22, "bold"),
            fg=COLOR_TEXT_MAIN,
            bg=COLOR_HEADER_BG,
            pady=4
        )
        lbl_titulo.pack()

        lbl_sub = tk.Label(
            header_frame,
            text="Explora la colección exclusiva y prueba cada prenda en vivo adaptada a tu cuerpo",
            font=("Segoe UI", 11),
            fg=COLOR_TEXT_MUTED,
            bg=COLOR_HEADER_BG
        )
        lbl_sub.pack()

        # Línea divisoria suave
        div = tk.Frame(header_frame, height=1, bg=COLOR_CARD_BORDER)
        div.pack(fill=tk.X, pady=(12, 0))

        # 2. Área desplazable (Canvas + Scrollbar) para las tarjetas de prendas
        canvas_contenedor = tk.Frame(self.contenedor_principal, bg=COLOR_BG_APP)
        canvas_contenedor.pack(fill=tk.BOTH, expand=True, padx=25, pady=15)

        canvas = tk.Canvas(canvas_contenedor, bg=COLOR_BG_APP, highlightthickness=0)
        scrollbar = ttk.Scrollbar(canvas_contenedor, orient=tk.VERTICAL, command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=COLOR_BG_APP)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")

        def al_redimensionar(event):
            canvas.itemconfig(canvas_window, width=event.width)

        canvas.bind("<Configure>", al_redimensionar)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Soporte para rueda del ratón
        def on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", on_mousewheel)

        # 3. Cuadrícula de Tarjetas de Prendas
        columnas = 3
        pad_x, pad_y = 12, 14

        grid_frame = tk.Frame(scrollable_frame, bg=COLOR_BG_APP)
        grid_frame.pack(anchor="center", pady=10)

        for idx, prenda in enumerate(self.catalogo):
            fila = idx // columnas
            col = idx % columnas
            self.crear_tarjeta_prenda(grid_frame, prenda, fila, col, pad_x, pad_y)

    def crear_tarjeta_prenda(self, parent, prenda, fila, col, pad_x, pad_y):
        """Crea una tarjeta individual moderna, limpia y femenina con botón PROBAR."""
        card = tk.Frame(
            parent,
            bg=COLOR_CARD_BG,
            highlightbackground=COLOR_CARD_BORDER,
            highlightthickness=1,
            padx=18,
            pady=16,
            width=290
        )
        card.grid(row=fila, column=col, padx=pad_x, pady=pad_y, sticky="nsew")

        # Efecto hover sobre la tarjeta
        def on_enter(e):
            card.config(highlightbackground=COLOR_CARD_HOVER, highlightthickness=2)
        def on_leave(e):
            card.config(highlightbackground=COLOR_CARD_BORDER, highlightthickness=1)
        card.bind("<Enter>", on_enter)
        card.bind("<Leave>", on_leave)

        # Imagen real de la prenda
        foto_tk = self.obtener_imagen_tk(prenda["archivo"], tamano=(180, 180))
        if foto_tk:
            lbl_img = tk.Label(card, image=foto_tk, bg=COLOR_CARD_BG)
            lbl_img.image = foto_tk
            lbl_img.pack(pady=(4, 10))

        # Nombre de la prenda
        lbl_nombre = tk.Label(
            card,
            text=prenda["nombre"],
            font=("Segoe UI", 12, "bold"),
            fg=COLOR_TEXT_MAIN,
            bg=COLOR_CARD_BG,
            wraplength=250
        )
        lbl_nombre.pack(anchor="center", pady=(0, 2))

        # Precio con formato elegante
        precio_str = f"${prenda['precio']:,}".replace(',', '.')
        lbl_precio = tk.Label(
            card,
            text=precio_str,
            font=("Segoe UI", 14, "bold"),
            fg=COLOR_GOLD,
            bg=COLOR_CARD_BG
        )
        lbl_precio.pack(anchor="center", pady=(0, 4))

        # Color
        lbl_color = tk.Label(
            card,
            text=f"Color: {prenda['color']}",
            font=("Segoe UI", 10),
            fg=COLOR_TEXT_MUTED,
            bg=COLOR_CARD_BG
        )
        lbl_color.pack(anchor="center", pady=(0, 2))

        # Talles disponibles y calce
        talles_str = " · ".join(prenda["talles"])
        calce_str = prenda.get("calce", "regular").capitalize()
        lbl_talles = tk.Label(
            card,
            text=f"Talles: {talles_str}  ·  Calce {calce_str}",
            font=("Segoe UI", 9, "bold"),
            fg="#9E786B",
            bg=COLOR_TAG_BG,
            padx=8,
            pady=2
        )
        lbl_talles.pack(anchor="center", pady=(2, 12))

        # Botón PROBAR
        btn_probar = tk.Button(
            card,
            text="PROBAR",
            font=("Segoe UI", 10, "bold"),
            fg="#FFFFFF",
            bg=COLOR_ROSE,
            activeforeground="#FFFFFF",
            activebackground=COLOR_ROSE_HOVER,
            relief=tk.FLAT,
            bd=0,
            padx=25,
            pady=7,
            cursor="hand2",
            command=lambda p=prenda: self.mostrar_confirmacion(p)
        )
        btn_probar.pack(anchor="center", fill=tk.X, pady=(4, 2))

        # Efecto hover del botón
        btn_probar.bind("<Enter>", lambda e, b=btn_probar: b.config(bg=COLOR_ROSE_HOVER))
        btn_probar.bind("<Leave>", lambda e, b=btn_probar: b.config(bg=COLOR_ROSE))

    # ---------------------------------------------------------------------
    # VISTA 2: PANTALLA DE DETALLE Y CONFIRMACIÓN ("Elegiste: ...")
    # ---------------------------------------------------------------------
    def mostrar_confirmacion(self, prenda):
        """Muestra la pantalla de confirmación y selección de talle con sus medidas reales."""
        self.prenda_seleccionada = prenda
        self.limpiar_contenedor()

        contenedor_detalle = tk.Frame(self.contenedor_principal, bg=COLOR_BG_APP)
        contenedor_detalle.pack(expand=True, fill=tk.BOTH, padx=25, pady=20)

        # Tarjeta central flotante de confirmación (dos columnas: foto y medidas)
        tarjeta_detalle = tk.Frame(
            contenedor_detalle,
            bg=COLOR_CARD_BG,
            highlightbackground=COLOR_CARD_BORDER,
            highlightthickness=1,
            padx=35,
            pady=22
        )
        tarjeta_detalle.pack(anchor="center", expand=True)

        lbl_sub = tk.Label(
            tarjeta_detalle,
            text="✨ VESTIDOR VIRTUAL · ELECCIÓN Y MEDIDAS ✨",
            font=("Segoe UI", 10, "bold"),
            fg=COLOR_GOLD,
            bg=COLOR_CARD_BG
        )
        lbl_sub.pack(pady=(0, 2))

        lbl_elegiste = tk.Label(
            tarjeta_detalle,
            text=f"Elegiste: {prenda['nombre']}",
            font=("Georgia", 19, "bold"),
            fg=COLOR_TEXT_MAIN,
            bg=COLOR_CARD_BG
        )
        lbl_elegiste.pack(pady=(0, 10))

        # Panel de dos columnas
        panel_columnas = tk.Frame(tarjeta_detalle, bg=COLOR_CARD_BG)
        panel_columnas.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # --- COLUMNA IZQUIERDA: Imagen y Ficha Rápida ---
        col_izq = tk.Frame(panel_columnas, bg=COLOR_CARD_BG)
        col_izq.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 25))

        foto_grande = self.obtener_imagen_tk(prenda["archivo"], tamano=(230, 230))
        if foto_grande:
            marco_foto = tk.Frame(col_izq, bg="#F9F6F3", highlightbackground=COLOR_CARD_BORDER, highlightthickness=1, padx=6, pady=6)
            marco_foto.pack(pady=(0, 8))
            lbl_foto = tk.Label(marco_foto, image=foto_grande, bg="#F9F6F3")
            lbl_foto.image = foto_grande
            lbl_foto.pack()

        precio_str = f"${prenda['precio']:,}".replace(',', '.')
        lbl_precio = tk.Label(
            col_izq,
            text=precio_str,
            font=("Segoe UI", 17, "bold"),
            fg=COLOR_GOLD,
            bg=COLOR_CARD_BG
        )
        lbl_precio.pack(pady=(0, 2))

        lbl_color = tk.Label(
            col_izq,
            text=f"Color: {prenda['color']}",
            font=("Segoe UI", 10),
            fg=COLOR_TEXT_MUTED,
            bg=COLOR_CARD_BG
        )
        lbl_color.pack(pady=(0, 2))

        calce_str = prenda.get("calce", "regular").capitalize()
        lbl_calce_tag = tk.Label(
            col_izq,
            text=f"Calce: {calce_str}",
            font=("Segoe UI", 9, "bold"),
            fg="#8B5E3C",
            bg=COLOR_TAG_BG,
            padx=10,
            pady=3
        )
        lbl_calce_tag.pack(pady=(4, 0))

        # --- COLUMNA DERECHA: Descripción, Selección de Talle y Medidas Reales ---
        col_der = tk.Frame(panel_columnas, bg=COLOR_CARD_BG)
        col_der.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        lbl_desc = tk.Label(
            col_der,
            text=prenda.get("descripcion", ""),
            font=("Segoe UI", 10, "italic"),
            fg=COLOR_TEXT_MUTED,
            bg=COLOR_CARD_BG,
            wraplength=480,
            justify="left"
        )
        lbl_desc.pack(anchor="w", pady=(0, 10))

        # 1. Selector de Talle
        self.talle_seleccionado.set(talle_inicial(prenda, self.talle_seleccionado.get()))

        lbl_sel_tit = tk.Label(
            col_der,
            text="1. Elegí tu Talle con sus Medidas:",
            font=("Segoe UI", 11, "bold"),
            fg=COLOR_TEXT_MAIN,
            bg=COLOR_CARD_BG
        )
        lbl_sel_tit.pack(anchor="w", pady=(0, 6))

        talles_bar = tk.Frame(col_der, bg=COLOR_CARD_BG)
        talles_bar.pack(anchor="w", pady=(0, 10))

        # 2. Caja de Medidas Reales Dinámicas
        medidas_box = tk.Frame(
            col_der,
            bg="#FAF6F0",
            highlightbackground="#E2D5C8",
            highlightthickness=1,
            padx=14,
            pady=10
        )
        medidas_box.pack(fill=tk.X, pady=(0, 10))

        lbl_medidas_tit = tk.Label(
            medidas_box,
            text="📐 Medidas de la Prenda para el Talle Elegido (en cm):",
            font=("Segoe UI", 10, "bold"),
            fg="#7E5835",
            bg="#FAF6F0"
        )
        lbl_medidas_tit.pack(anchor="w", pady=(0, 6))

        grid_medidas = tk.Frame(medidas_box, bg="#FAF6F0")
        grid_medidas.pack(fill=tk.X)

        val_pecho = tk.StringVar()
        val_cintura = tk.StringVar()
        val_cadera = tk.StringVar()
        val_hombros = tk.StringVar()
        val_largo = tk.StringVar()
        val_holgura = tk.StringVar()

        def crear_item_medida(parent, r, c, icono, etiqueta, var):
            f_item = tk.Frame(parent, bg="#FAF6F0")
            f_item.grid(row=r, column=c, sticky="w", padx=10, pady=3)
            tk.Label(f_item, text=f"{icono} {etiqueta}:", font=("Segoe UI", 9, "bold"), fg=COLOR_TEXT_MAIN, bg="#FAF6F0").pack(side=tk.LEFT)
            tk.Label(f_item, textvariable=var, font=("Segoe UI", 9, "bold"), fg="#A35848", bg="#FAF6F0").pack(side=tk.LEFT, padx=(4, 0))

        crear_item_medida(grid_medidas, 0, 0, "📏", "Pecho/Busto", val_pecho)
        crear_item_medida(grid_medidas, 0, 1, "📐", "Cintura", val_cintura)
        crear_item_medida(grid_medidas, 0, 2, "👗", "Cadera", val_cadera)
        crear_item_medida(grid_medidas, 1, 0, "👔", "Hombros", val_hombros)
        crear_item_medida(grid_medidas, 1, 1, "↕️", "Largo Total", val_largo)
        crear_item_medida(grid_medidas, 1, 2, "🏷️", "Holgura", val_holgura)

        def actualizar_ficha_medidas():
            t_sel = self.talle_seleccionado.get()
            m = obtener_medidas_talle(prenda, t_sel)
            lbl_medidas_tit.config(text=f"📐 Medidas de la Prenda para el Talle Elegido (TALLE {t_sel}):")
            val_pecho.set(f"{m['pecho']} cm")
            val_cintura.set(f"{m['cintura']} cm")
            val_cadera.set(f"{m['cadera']} cm")
            val_hombros.set(f"{m['hombros']} cm")
            val_largo.set(f"{m['largo']} cm")
            h_pct = int(round((holgura_de_talle(t_sel) - 1.0) * 100))
            h_signo = f"+{h_pct}%" if h_pct >= 0 else f"{h_pct}%"
            val_holgura.set(f"{h_signo} ({calce_str})")

        for t in prenda["talles"]:
            rb = tk.Radiobutton(
                talles_bar, text=t, value=t, variable=self.talle_seleccionado,
                indicatoron=False, width=5, font=("Segoe UI", 11, "bold"),
                fg=COLOR_TEXT_MAIN, bg=COLOR_TAG_BG, selectcolor=COLOR_ROSE,
                activebackground=COLOR_CARD_HOVER, relief=tk.FLAT, bd=0, pady=5, cursor="hand2",
                command=actualizar_ficha_medidas
            )
            rb.pack(side=tk.LEFT, padx=3)

        btn_tabla_modal = tk.Button(
            talles_bar,
            text="📏 Ver Guía Completa de Medidas",
            font=("Segoe UI", 9, "bold"),
            fg="#7E5835",
            bg="#F0E5D8",
            activebackground="#E5D6C5",
            relief=tk.FLAT,
            bd=0,
            padx=12,
            pady=6,
            cursor="hand2",
            command=lambda p=prenda: self.mostrar_tabla_medidas_modal(p)
        )
        btn_tabla_modal.pack(side=tk.LEFT, padx=(12, 0))

        actualizar_ficha_medidas()

        lbl_tip = tk.Label(
            col_der,
            text="💡 Al abrir la cámara, el sistema medirá tu silueta real (pecho, cintura y cadera) y adaptará la prenda a tu figura y al talle seleccionado.",
            font=("Segoe UI", 9),
            fg="#8C7F79",
            bg=COLOR_TAG_BG,
            padx=12,
            pady=7,
            wraplength=480,
            justify="left"
        )
        lbl_tip.pack(anchor="w", pady=(0, 14))

        # Botones de Acción
        botones_frame = tk.Frame(col_der, bg=COLOR_CARD_BG)
        botones_frame.pack(anchor="w")

        btn_abrir_cam = tk.Button(
            botones_frame,
            text="⭐ PROBAR PRENDA EN CÁMARA",
            font=("Segoe UI", 11, "bold"),
            fg="#FFFFFF",
            bg=COLOR_GOLD,
            activeforeground="#FFFFFF",
            activebackground="#A8853F",
            relief=tk.FLAT,
            bd=0,
            padx=28,
            pady=9,
            cursor="hand2",
            command=self.lanzar_camara
        )
        btn_abrir_cam.grid(row=0, column=0, padx=(0, 12))

        btn_abrir_cam.bind("<Enter>", lambda e, b=btn_abrir_cam: b.config(bg="#B59048"))
        btn_abrir_cam.bind("<Leave>", lambda e, b=btn_abrir_cam: b.config(bg=COLOR_GOLD))

        btn_volver = tk.Button(
            botones_frame,
            text="← VOLVER A LA GALERÍA",
            font=("Segoe UI", 11),
            fg=COLOR_TEXT_MAIN,
            bg="#F2EBE5",
            activebackground="#E5DCD4",
            relief=tk.FLAT,
            bd=0,
            padx=18,
            pady=9,
            cursor="hand2",
            command=self.mostrar_galeria
        )
        btn_volver.grid(row=0, column=1)

        btn_volver.bind("<Enter>", lambda e, b=btn_volver: b.config(bg="#E5DCD4"))
        btn_volver.bind("<Leave>", lambda e, b=btn_volver: b.config(bg="#F2EBE5"))

    def mostrar_tabla_medidas_modal(self, prenda):
        """Abre un modal elegante con la tabla comparativa de medidas de todos los talles de la prenda."""
        modal = tk.Toplevel(self.root)
        modal.title(f"Guía y Tabla de Medidas - {prenda['nombre']}")
        modal.geometry("680x500")
        modal.minsize(600, 440)
        modal.configure(bg=COLOR_BG_APP)
        modal.transient(self.root)
        modal.grab_set()

        mw, mh = 680, 500
        rx = self.root.winfo_x() + (self.root.winfo_width() - mw) // 2
        ry = self.root.winfo_y() + (self.root.winfo_height() - mh) // 2
        modal.geometry(f"{mw}x{mh}+{max(0, rx)}+{max(0, ry)}")

        f = tk.Frame(modal, bg=COLOR_CARD_BG, padx=25, pady=18)
        f.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)

        tk.Label(f, text="📏 TABLA DE MEDIDAS Y GUÍA DE CALCE", font=("Segoe UI", 11, "bold"),
                 fg=COLOR_GOLD, bg=COLOR_CARD_BG).pack()
        tk.Label(f, text=prenda["nombre"], font=("Georgia", 16, "bold"),
                 fg=COLOR_TEXT_MAIN, bg=COLOR_CARD_BG, pady=3).pack()
        tk.Label(f, text=f"Calce: {prenda.get('calce', 'regular').capitalize()}  ·  Color: {prenda.get('color')}",
                 font=("Segoe UI", 10), fg=COLOR_TEXT_MUTED, bg=COLOR_CARD_BG).pack(pady=(0, 14))

        tabla_frame = tk.Frame(f, bg=COLOR_CARD_BORDER, padx=1, pady=1)
        tabla_frame.pack(fill=tk.X, pady=(0, 14))

        cabeceras = ["Talle", "Pecho / Busto", "Cintura", "Cadera", "Hombros", "Largo Total", "Calce"]
        filas = obtener_guia_medidas_completa(prenda)

        for col_idx, h in enumerate(cabeceras):
            tk.Label(tabla_frame, text=h, font=("Segoe UI", 10, "bold"),
                     bg="#EAE0D6", fg=COLOR_TEXT_MAIN, padx=8, pady=7).grid(row=0, column=col_idx, sticky="nsew", padx=1, pady=1)

        talle_actual = self.talle_seleccionado.get()
        for row_idx, fila in enumerate(filas, start=1):
            es_sel = (fila["talle"] == talle_actual)
            bg_fila = "#F5E6E0" if es_sel else ("#FFFFFF" if row_idx % 2 == 1 else "#FAF7F5")
            fg_fila = COLOR_TEXT_MAIN

            vals = [fila["talle"] + (" ★" if es_sel else ""), fila["pecho"], fila["cintura"], fila["cadera"],
                    fila["hombros"], fila["largo"], fila["calce"]]
            for col_idx, val in enumerate(vals):
                font_weight = "bold" if es_sel or col_idx == 0 else "normal"
                lbl = tk.Label(tabla_frame, text=val, font=("Segoe UI", 9, font_weight),
                               bg=bg_fila, fg=fg_fila, padx=8, pady=6)
                lbl.grid(row=row_idx, column=col_idx, sticky="nsew", padx=1, pady=1)

        for i in range(len(cabeceras)):
            tabla_frame.columnconfigure(i, weight=1)

        tips_frame = tk.Frame(f, bg=COLOR_TAG_BG, padx=14, pady=9)
        tips_frame.pack(fill=tk.X, pady=(0, 14))
        tk.Label(tips_frame, text="💡 ¿Cómo tomar tus medidas con cinta métrica?",
                 font=("Segoe UI", 9, "bold"), fg="#7A5230", bg=COLOR_TAG_BG).pack(anchor="w")
        tk.Label(tips_frame, text="• Pecho/Busto: medir horizontalmente rodeando el contorno más ancho del torso.\n• Cintura: medir en el punto más estrecho del torso natural (a la altura del ombligo).\n• Cadera: medir de pie con los talones juntos en la parte más amplia.",
                 font=("Segoe UI", 9), fg=COLOR_TEXT_MUTED, bg=COLOR_TAG_BG, justify="left").pack(anchor="w", pady=(2, 0))

        btn_cerrar = tk.Button(f, text="ENTENDIDO / CERRAR", font=("Segoe UI", 10, "bold"),
                               bg=COLOR_ROSE, fg="#FFFFFF", relief=tk.FLAT, bd=0, padx=22, pady=7,
                               cursor="hand2", command=modal.destroy)
        btn_cerrar.pack()

    # ---------------------------------------------------------------------
    # VISTA 3: APERTURA Y CONTROL DE LA CÁMARA
    # ---------------------------------------------------------------------
    def lanzar_camara(self):
        """Oculta la ventana de la galería e inicia la cámara en vivo."""
        if not self.prenda_seleccionada:
            return

        # 1. Ocultar ventana de la galería
        self.root.withdraw()

        # 2. Ejecutar probador en vivo con OpenCV y MediaPipe
        resultado = ejecutar_probador_camara(self.prenda_seleccionada, self.catalogo,
                                             talle_elegido=self.talle_seleccionado.get())

        # 3. Retorno del probador:
        # Si presionó 'G' vuelve a la galería, si presionó 'Q' cierra la app.
        if resultado == "galeria":
            self.root.deiconify()
            self.mostrar_galeria()
        else:
            self.root.destroy()


# =========================================================================
# PUNTO DE ENTRADA PRINCIPAL
# =========================================================================
def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # tildes bien aunque se redirija la salida
    except Exception:
        pass
    root = tk.Tk()
    app = BoutiqueVirtualApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
