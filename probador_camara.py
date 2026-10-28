# ==========================================================
# PROYECTO: PROBADOR VIRTUAL INTELIGENTE - BOUTIQUE FEMENINA
# MÓDULO: PROBADOR CON CÁMARA (bucle en vivo con OpenCV + MediaPipe)
# ==========================================================

import math
import os
import sys
import time
import cv2
import numpy as np
from tkinter import messagebox

from pose_tracker import PoseTracker
from clothing_geometry import detectar_puntos_clave_prenda
from clothing_warper import deformar_malla_prenda
from body_layering import componer_prenda_con_capas
from catalogo import holgura_de_talle, talle_inicial, obtener_medidas_talle
from ajuste_silueta import ajustar_prenda_completa
from hud import dibujar_medidas, dibujar_hud_probador, punto_en_boton_galeria, dibujar_diagnostico
from recursos import obtener_siguiente_nombre_captura
from colores_prenda import CacheColores
from diseno_rigido import pegar_bloques
from profundidad_3d import envolver_en_torso
from vista_costado import generar_vista_costado
from inercia_tela import InerciaTela
from luz_escena import EstimadorLuz
from segmentador_pelo import SegmentadorPelo
from config import (
    ANCHO_PROCESO,
    ANCHO_PANTALLA,
    ANCHO_MEDIAPIPE,
    CADA_N_CUADROS_MEDIAPIPE,
    MEDIAPIPE_EN_SEGUNDO_PLANO,
    MODEL_FILENAME,
    USAR_PELO_DELANTE,
    MODELO_PELO,
    FACTOR_ANCHO_DEFAULT,
    FACTOR_AJUSTE_PASO,
    SMOOTH_ANTERIOR,
    SMOOTH_DETECTADO,
)


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


# =========================================================================
# MOTOR DEL PROBADOR CON CÁMARA (OPENCV + MEDIAPIPE)
# =========================================================================
def abrir_camara():
    """
    Abre la cámara web. En Windows se prueba primero DirectShow: tolera mejor abrir y
    cerrar la cámara varias veces en la misma sesión (al volver a la galería y elegir
    otra prenda). Si no anda, se usa el sistema por defecto de OpenCV.
    """
    intentos = [cv2.CAP_DSHOW, cv2.CAP_ANY] if sys.platform.startswith("win") else [cv2.CAP_ANY]
    for sistema in intentos:
        cap = cv2.VideoCapture(0, sistema)
        if cap.isOpened():
            # Se pide la imagen al tamaño en que se procesa (ANCHO_PROCESO): pedirla en
            # 1280x720 y achicarla después sólo gastaba tiempo en cada cuadro
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, ANCHO_PROCESO)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(round(ANCHO_PROCESO * 3 / 4)))
            return cap
        cap.release()
    return None


def leer_primer_cuadro(cap, espera_s=4.0):
    """La cámara recién abierta puede tardar en entregar imagen: se espera con calma."""
    limite = time.time() + espera_s
    while time.time() < limite:
        ret, frame = cap.read()
        if ret and frame is not None:
            return frame
        time.sleep(0.1)
    return None


ARCHIVO_DIAGNOSTICO = os.path.join("temp", "diagnostico_pose.csv")


def registrar_diagnostico(prenda, info, deteccion):
    """Agrega una línea con los puntos del cuerpo (sólo coordenadas, nunca imágenes)."""
    os.makedirs("temp", exist_ok=True)
    claves = ("nose", "sh_left", "sh_right", "hip_left", "hip_right")
    encabezado = ("hora,prenda,mangas,orientacion,giro,caderas_visibles,angulo_torso,dist_sh,dist_torso,"
                  "cuello_base_y,medio_cuello,base_cuello,menton_y,medio_cara,"
                  + ",".join(f"{k}_x,{k}_y,{k}_vis" for k in claves) + "\n")
    if os.path.exists(ARCHIVO_DIAGNOSTICO):
        with open(ARCHIVO_DIAGNOSTICO, encoding="utf-8") as archivo:
            anterior = archivo.readline() != encabezado
        if anterior:   # registro de una versión anterior (otras columnas): se aparta
            os.replace(ARCHIVO_DIAGNOSTICO, ARCHIVO_DIAGNOSTICO + ".anterior")
    nuevo = not os.path.exists(ARCHIVO_DIAGNOSTICO)
    with open(ARCHIVO_DIAGNOSTICO, "a", encoding="utf-8") as archivo:
        if nuevo:
            archivo.write(encabezado)
        u = info["u_torso"]
        fila = [time.strftime("%H:%M:%S"), prenda["id"], str(prenda.get("tiene_mangas")), info.get("orientacion", ""),
                f"{info.get('giro', 0):.2f}", str(info.get("caderas_visibles")),
                f"{math.degrees(math.atan2(float(u[0]), float(u[1]))):.1f}", f"{info['dist_sh']:.0f}",
                f"{info['dist_torso']:.0f}"]
        def numero(v):
            return "" if v is None else f"{float(v):.0f}"
        fila += [numero(info["p_neck_base"][1]), numero(info.get("medio_cuello")), numero(info.get("base_cuello")),
                 numero(info["p_menton"][1] if info.get("p_menton") is not None else None),
                 numero(info.get("medio_cara"))]
        for k in claves:
            p = deteccion["p_raw"].get(k) if deteccion else None
            v = deteccion["vis"].get(k, 0.0) if deteccion else 0.0
            fila += [f"{p[0]:.0f}", f"{p[1]:.0f}", f"{v:.2f}"] if p is not None else ["", "", ""]
        archivo.write(",".join(fila) + "\n")


def colores_prenda(prenda):
    return prenda.get("colores") or [{"nombre": prenda.get("color", ""), "hex": None, "es_foto": True}]


def ejecutar_probador_camara(prenda_inicial, catalogo, talle_elegido="M", color_elegido=None):
    """
    color_elegido: nombre del color con que se abre (los colores que no son el de la
    foto se generan tiñendo la prenda). Con [K] se cambia de color en vivo.
    Devuelve (prenda, color) con los que terminó la persona, para volver a su detalle.
    Ejecuta el bucle en vivo de la cámara con detección corporal y calce adaptativo.
    Al cerrar la cámara (G, Q, Esc, el botón "Volver a la galería" o la X de la
    ventana) se vuelve a la galería para elegir otra prenda.
    """
    print(f"\n[+] Iniciando probador para prenda: {prenda_inicial['nombre']}")

    # Inicializar rastreador inteligente con MediaPipe y suavizado EMA
    tracker = PoseTracker(model_path=MODEL_FILENAME, alpha_suavizado=SMOOTH_DETECTADO,
                          ancho_mediapipe=ANCHO_MEDIAPIPE, cada_n_cuadros=CADA_N_CUADROS_MEDIAPIPE,
                          en_segundo_plano=MEDIAPIPE_EN_SEGUNDO_PLANO)
    # Pelo por delante de la prenda (corre en su propio hilo)
    segmentador_pelo = SegmentadorPelo(MODELO_PELO) if USAR_PELO_DELANTE else None

    # Abrir cámara web
    cap = abrir_camara()
    primer_cuadro = leer_primer_cuadro(cap) if cap is not None else None
    if primer_cuadro is None:
        if cap is not None:
            cap.release()
        print("[ERROR] No se pudo acceder a la cámara web.")
        messagebox.showerror("Error de Cámara", "No se pudo acceder a la cámara web. Puede estar en uso por otra app "
                                                "(una videollamada u otra copia del probador). Cerrala y volvé a intentar.")
        tracker.cerrar()
        if segmentador_pelo is not None:
            segmentador_pelo.cerrar()
        return prenda_inicial, color_elegido

    # Índice de la prenda actual dentro del catálogo
    indice_prenda = 0
    for idx, p in enumerate(catalogo):
        if p["id"] == prenda_inicial["id"]:
            indice_prenda = idx
            break

    factor_escala = FACTOR_ANCHO_DEFAULT
    talle = talle_inicial(catalogo[indice_prenda], talle_elegido)
    nombres_color = [c["nombre"] for c in colores_prenda(catalogo[indice_prenda])]
    indice_color = nombres_color.index(color_elegido) if color_elegido in nombres_color else 0
    cache_colores = CacheColores()
    inercia = InerciaTela()  # el ruedo y las mangas se balancean un poco al moverse
    estimador_luz = EstimadorLuz()  # de dónde viene la luz en la cámara
    ver_medidas = False
    diagnostico = False      # tecla I: puntos del cuerpo y registro para encontrar errores
    ultimo_registro = 0.0
    opacidad_prenda = 1.0          # baja a 0 suavemente cuando la persona está de perfil (y sube la de costado)
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

    # Mouse: botón "Volver a la galería" (OpenCV da las coordenadas en píxeles de la
    # imagen mostrada, aunque la ventana esté agrandada o achicada)
    raton = {"x": -1, "y": -1, "click": False, "tam": (1, 1)}

    def al_usar_mouse(evento, x, y, _flags, _param):
        raton["x"], raton["y"] = x, y
        if evento == cv2.EVENT_LBUTTONUP and punto_en_boton_galeria(x, y, *raton["tam"]):
            raton["click"] = True

    cv2.setMouseCallback(nombre_ventana, al_usar_mouse)

    while True:
        if primer_cuadro is not None:
            ret, frame, primer_cuadro = True, primer_cuadro, None
        else:
            ret, frame = cap.read()
        if not ret:
            # Un cuadro perdido no corta la sesión: se espera un poco a que vuelva la imagen
            frame = leer_primer_cuadro(cap, espera_s=2.0)
            ret = frame is not None
            if not ret:
                print("[ERROR] No se pudo capturar imagen de la cámara.")
                messagebox.showerror("Error de Cámara", "La cámara no entrega imagen. Cerrá otras apps que la usen "
                                                        "y volvé a intentar.")
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
        if segmentador_pelo is not None and info_anatomica is not None:
            segmentador_pelo.pedir(frame, info_anatomica)
            info_anatomica["pelo"] = segmentador_pelo.mascara(info_anatomica)
            tracker.mascara_pelo = info_anatomica["pelo"]  # para medir el cuello sin el pelo

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
                # de perfil, la vista de frente se funde con la de costado.
                orientacion = info_anatomica.get("orientacion", "frente")
                de_espaldas = orientacion == "espalda"
                imagen_prenda = prenda_actual.get("imagen_espalda_cv") if de_espaldas else None
                puntos_prenda = prenda_actual.get("src_puntos_espalda") if de_espaldas else None
                bloques = []
                if imagen_prenda is None or puntos_prenda is None:
                    imagen_prenda, puntos_prenda = prenda_actual["imagen_cv"], prenda_actual["src_puntos"]
                    # De frente: se deforma la prenda LISA y el logo / estampado se dibuja
                    # después, rígido, para que nunca se estire ni se tuerza
                    bloques = prenda_actual.get("bloques_diseno") or []
                    if bloques:
                        imagen_prenda = prenda_actual["imagen_lisa_cv"]
                # Color elegido: se tiñe la foto (la forma y los puntos de la malla no cambian)
                lista_colores = colores_prenda(prenda_actual)
                color_actual = lista_colores[indice_color % len(lista_colores)]
                if not color_actual.get("es_foto") and color_actual.get("hex"):
                    imagen_prenda = cache_colores.obtener(prenda_actual["id"], imagen_prenda, color_actual["hex"])
                # Si ESTE cuadro ya se ve de perfil, empezar a desvanecer enseguida
                # (sin esperar a que la vista cambie "oficialmente").
                de_perfil = orientacion == "perfil" or info_anatomica.get("orientacion_cuadro") == "perfil"
                objetivo = 0.0 if de_perfil else 1.0
                opacidad_prenda += (objetivo - opacidad_prenda) * (0.45 if de_perfil else 0.25)
                if orientacion != orientacion_anterior:
                    if orientacion == "perfil":
                        notificacion_texto = "Vista de costado"
                    elif de_espaldas and prenda_actual.get("espalda_automatica", True):
                        notificacion_texto = "Vista de espalda (automatica: sin foto de espalda)"
                    elif de_espaldas:
                        notificacion_texto = "Vista de espalda"
                    elif orientacion_anterior in ("perfil", "espalda"):
                        notificacion_texto = "Vista de frente"
                    notificacion_tiempo = time.time()
                    orientacion_anterior = orientacion

                # Calcular puntos destino adaptados al cuerpo del usuario
                # Calcular puntos destino adaptados a la figura medida del usuario,
                # al talle elegido y al tipo de calce de la prenda
                dst_pts = tracker.calcular_puntos_destino_malla(
                    info_anatomica,
                    tiene_mangas=tiene_mangas,
                    factor_escala=factor_escala,
                    holgura_talle=holgura_de_talle(talle),
                    calce=prenda_actual.get("calce", "regular"),
                    puntos_prenda=puntos_prenda
                )
                # Inercia: los puntos sueltos (ruedo, cadera, puños) siguen al cuerpo con un resorte
                dst_pts = inercia.aplicar(dst_pts, time.time(), prenda_actual.get("calce", "regular"),
                                          float(info_anatomica["dist_torso"]))

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
                        frame_bgr=frame,
                        tiene_mangas=tiene_mangas
                    )
                if parche is not None and bloques:
                    parche = pegar_bloques(parche, xmin, ymin, bloques, puntos_prenda, dst_pts, tiene_mangas)
                # Profundidad 3D: la tela envuelve el torso (y se ve el giro del cuerpo),
                # iluminada desde donde viene la luz en la cámara
                if parche is not None:
                    info_anatomica["luz"] = estimador_luz.estimar(frame, info_anatomica)
                    parche = envolver_en_torso(parche, xmin, ymin, info_anatomica)

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
                        talle=talle, recortar_silueta=recorte_silueta, sombras=True,
                        cuello_por_delante=tiene_mangas and not de_espaldas
                    )
                # Vista de costado: aparece a medida que se va la de frente. La tela sale
                # de la espalda de la prenda (de costado no se ven logos ni botones).
                if opacidad_prenda < 0.98 and not de_espaldas and info_anatomica.get("mascara") is not None:
                    imagen_costado = prenda_actual.get("imagen_espalda_cv")
                    puntos_costado = prenda_actual.get("src_puntos_espalda")
                    if imagen_costado is None or puntos_costado is None:
                        imagen_costado, puntos_costado = prenda_actual["imagen_cv"], prenda_actual["src_puntos"]
                    if not color_actual.get("es_foto") and color_actual.get("hex"):
                        imagen_costado = cache_colores.obtener(prenda_actual["id"], imagen_costado, color_actual["hex"])
                    costado = generar_vista_costado(imagen_costado, puntos_costado, tiene_mangas, info_anatomica,
                                                    info_anatomica["mascara"], holgura_talle=holgura_de_talle(talle))
                    if costado is not None:
                        parche_c, x0_c, y0_c, x1_c, y1_c = costado
                        parche_c[:, :, 3] = (parche_c[:, :, 3].astype(np.float32) * (1.0 - opacidad_prenda)).astype(np.uint8)
                        frame = componer_prenda_con_capas(
                            frame, parche_c, x0_c, y0_c, x1_c, y1_c, info_anatomica,
                            talle=talle, recortar_silueta=False, sombras=True)
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
            if diagnostico:
                dibujar_diagnostico(frame, info_anatomica, tracker._ultima_deteccion)
                if time.time() - ultimo_registro > 0.5:
                    registrar_diagnostico(prenda_actual, info_anatomica, tracker._ultima_deteccion)
                    ultimo_registro = time.time()
        else:
            smooth_quad = None
            inercia.reiniciar()

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
        lista_colores = colores_prenda(prenda_actual)
        # Guía de encuadre (como en los probadores de tienda: el cuerpo entero a la vista)
        if info_anatomica is None:
            aviso_encuadre = "Parate frente a la camara, a unos 2 metros"
        elif not info_anatomica.get("caderas_visibles", True):
            aviso_encuadre = "Alejate un poco: que se vea hasta tu cadera"
        else:
            aviso_encuadre = ""
        dibujar_hud_probador(frame, prenda_actual, factor_escala, notificacion_texto,
                             aviso_encuadre=aviso_encuadre,
                             color=lista_colores[indice_color % len(lista_colores)]["nombre"],
                             modo_malla=modo_malla, talle=talle, figura=figura,
                             fps=fps_suave, recorte=recorte_silueta,
                             orientacion=info_anatomica.get("orientacion") if info_anatomica else None,
                             boton_resaltado=punto_en_boton_galeria(raton["x"], raton["y"],
                                                                    frame.shape[1], frame.shape[0]))
        raton["tam"] = (frame.shape[1], frame.shape[0])

        cv2.imshow(nombre_ventana, frame)

        # 4. Manejo interactivo de teclado
        key = cv2.waitKey(1) & 0xFF

        # [G], el botón "Volver a la galería" o cerrar la ventana con la X:
        # volver a la galería sin cerrar el programa
        ventana_cerrada = cv2.getWindowProperty(nombre_ventana, cv2.WND_PROP_VISIBLE) < 1
        if key == ord('g') or key == ord('G') or raton["click"] or ventana_cerrada:
            accion_salida = "galeria"
            break

        # [Q] o [Esc]: cerrar la cámara y volver a la galería para elegir otra prenda
        elif key == ord('q') or key == ord('Q') or key == 27:
            accion_salida = "galeria"
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

        # [K] Cambiar de color (entre los disponibles de la prenda)
        elif key == ord('k') or key == ord('K'):
            lista_colores = colores_prenda(prenda_actual)
            indice_color = (indice_color + 1) % len(lista_colores)
            notificacion_texto = f"Color: {lista_colores[indice_color]['nombre']}"
            notificacion_tiempo = time.time()

        # [R] Activar / desactivar el recorte de la prenda al borde del cuerpo
        elif key == ord('r') or key == ord('R'):
            recorte_silueta = not recorte_silueta
            notificacion_texto = "Prenda pegada a la silueta" if recorte_silueta else "Recorte desactivado"
            notificacion_tiempo = time.time()

        # [I] Modo diagnóstico: puntos del cuerpo en pantalla y registro en temp/diagnostico_pose.csv
        elif key == ord('i') or key == ord('I'):
            diagnostico = not diagnostico
            notificacion_texto = "Diagnostico activo" if diagnostico else "Diagnostico apagado"
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
            indice_color = 0
            inercia.reiniciar()
            smooth_quad = None

        # [P] o [A] Prenda anterior
        elif key == ord('p') or key == ord('P') or key == ord('a') or key == ord('A'):
            indice_prenda = (indice_prenda - 1) % len(catalogo)
            notificacion_texto = f"Prenda: {catalogo[indice_prenda]['nombre']}"
            notificacion_tiempo = time.time()
            tracker.reiniciar()
            talle = talle_inicial(catalogo[indice_prenda], talle)
            indice_color = 0
            inercia.reiniciar()
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
                indice_color = 0
                inercia.reiniciar()
                smooth_quad = None

        # Ajuste fino de holgura (+ y -)
        elif key == ord('+') or key == ord('='):
            factor_escala = min(2.5, factor_escala + FACTOR_AJUSTE_PASO)
        elif key == ord('-') or key == ord('_'):
            factor_escala = max(0.5, factor_escala - FACTOR_AJUSTE_PASO)

    # Limpieza de recursos
    tracker.cerrar()
    if segmentador_pelo is not None:
        segmentador_pelo.cerrar()
    cap.release()
    cv2.destroyAllWindows()
    cv2.waitKey(1)
    time.sleep(0.3)  # Windows libera la cámara un instante después: así la próxima sesión la encuentra libre
    prenda_final = catalogo[indice_prenda]
    lista_colores = colores_prenda(prenda_final)
    return prenda_final, lista_colores[indice_color % len(lista_colores)]["nombre"]
