# ==========================================================
# PROYECTO: PROBADOR VIRTUAL INTELIGENTE
# MÓDULO: DETECCIÓN CORPORAL INTELIGENTE Y SEGUIMIENTO SUAVE
# ==========================================================

import os
import math
import time
import numpy as np
import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

from body_measure import medir_silueta, estimar_figura, MedidasSuavizadas, ancho_total, OneEuroFilter

class PoseTracker:
    """
    Gestiona la detección en tiempo real con MediaPipe Pose Landmarker en modo VIDEO,
    el seguimiento adaptativo mediante filtros One Euro (1€ Filter) y el cálculo
    de medidas corporales dinámicas.
    """
    def __init__(self, model_path="pose_landmarker_lite.task", alpha_suavizado=0.30,
                 ancho_mediapipe=480, cada_n_cuadros=2):
        self.model_path = model_path
        # Rendimiento: MediaPipe es lo más lento del probador (~80 ms por cuadro en una
        # notebook). Se corre sobre una imagen de 'ancho_mediapipe' px y sólo 1 de cada
        # 'cada_n_cuadros' cuadros; en los otros se predicen los puntos con la velocidad
        # del cuerpo y se corre la silueta anterior (ver _predecir_cuadro).
        self.ancho_mediapipe = ancho_mediapipe
        self.cada_n_cuadros = max(1, int(cada_n_cuadros))
        self._ultima_deteccion = None   # puntos, Z, visibilidad, máscara y tiempo de la última detección
        self._velocidad = {}            # px/s de cada punto entre las dos últimas detecciones
        self._cuadros_desde_deteccion = 0
        self.alpha_suavizado = alpha_suavizado
        self.smooth_anterior = 1.0 - alpha_suavizado  # 0.70 por defecto
        
        # Puntos anatómicos suavizados con One Euro Filter
        self.puntos_suavizados = None
        self.z_suavizados = {}
        self.filtros_puntos = {}
        self.filtros_z = {}
        self._ultimo_timestamp_ms = 0
        self.frames_perdidos = 0
        self.max_frames_hold = 12  # Cuadros de gracia antes de desvanecer

        # Medidas de la silueta (pecho, cintura, cadera, brazo) suavizadas
        self.medidas = MedidasSuavizadas(alpha=0.20)
        self.ultima_mascara = None

        # Orientación de la persona (frente / girada / perfil / espalda) con "histéresis":
        # sólo cambia si el nuevo estado se mantiene varios cuadros seguidos.
        self.orientacion = "frente"
        self._orientacion_candidata = "frente"
        self._cuadros_candidata = 0
        self.cuadros_para_cambiar = 4

        # Inicializar modelo de MediaPipe Pose en modo VIDEO para máximo seguimiento temporal
        base_options = python.BaseOptions(model_asset_path=self.model_path)
        options = vision.PoseLandmarkerOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.VIDEO,
            min_pose_detection_confidence=0.5,
            min_pose_presence_confidence=0.5,
            min_tracking_confidence=0.5,
            # Pedimos también la silueta de la persona para medir su figura real
            output_segmentation_masks=True
        )
        self.detector = vision.PoseLandmarker.create_from_options(options)

    def reiniciar(self):
        """Reinicia el estado de suavizado y filtros."""
        self.puntos_suavizados = None
        self.z_suavizados = {}
        self.frames_perdidos = 0
        for f in self.filtros_puntos.values():
            f.reset()
        for f in self.filtros_z.values():
            f.reset()
        self._ultimo_timestamp_ms = 0
        self._ultima_deteccion = None
        self._velocidad = {}
        self._cuadros_desde_deteccion = 0

    def reiniciar_medidas(self):
        """Olvida las medidas del cuerpo (por ejemplo, cuando entra otra persona)."""
        self.medidas.reiniciar()

    def cerrar(self):
        """Libera los recursos del detector."""
        if self.detector:
            self.detector.close()

    def procesar_frame(self, frame_bgr, timestamp_ms=None):
        """
        Detecta la pose corporal en el fotograma en modo VIDEO continuo.
        Retorna (landmarks_actuales, info_anatomica).
        """
        alto, ancho, _ = frame_bgr.shape

        # Garantizar timestamps estrictamente crecientes requeridos por detect_for_video
        if timestamp_ms is None:
            ahora_ms = int(time.time() * 1000)
            if ahora_ms <= self._ultimo_timestamp_ms:
                timestamp_ms = self._ultimo_timestamp_ms + 33
            else:
                timestamp_ms = ahora_ms
        else:
            if timestamp_ms <= self._ultimo_timestamp_ms:
                timestamp_ms = self._ultimo_timestamp_ms + 1
        self._ultimo_timestamp_ms = timestamp_ms

        # Saltear cuadros: si la última detección fue buena, en los cuadros intermedios
        # se predice la pose en lugar de volver a correr MediaPipe.
        if (self._ultima_deteccion is not None and self.frames_perdidos == 0
                and self._cuadros_desde_deteccion < self.cada_n_cuadros - 1):
            self._cuadros_desde_deteccion += 1
            return self._predecir_cuadro(ancho, alto, timestamp_ms)
        self._cuadros_desde_deteccion = 0

        # Optimización de rendimiento para notebooks: MediaPipe trabaja sobre una imagen
        # chica (el modelo igual la reduce a 256 px); los puntos vuelven en proporciones.
        if ancho > self.ancho_mediapipe:
            escala = self.ancho_mediapipe / float(ancho)
            ancho_proc = self.ancho_mediapipe
            alto_proc = int(round(alto * escala))
        else:
            ancho_proc, alto_proc = ancho, alto
        # MediaPipe necesita anchos y altos múltiplos de 4 (si no, falla al leer la silueta)
        ancho_proc = max(4, (ancho_proc // 4) * 4)
        alto_proc = max(4, (alto_proc // 4) * 4)
        if (ancho_proc, alto_proc) != (ancho, alto):
            frame_proc = cv2.resize(frame_bgr, (ancho_proc, alto_proc), interpolation=cv2.INTER_LINEAR)
        else:
            frame_proc = frame_bgr

        frame_rgb = cv2.cvtColor(frame_proc, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
        
        resultado = self.detector.detect_for_video(mp_image, timestamp_ms)
        
        if not resultado.pose_landmarks or len(resultado.pose_landmarks) == 0:
            self.frames_perdidos += 1
            if self.frames_perdidos > self.max_frames_hold:
                self.puntos_suavizados = None
                self.medidas.reiniciar()  # probablemente se fue la persona
                for f in self.filtros_puntos.values():
                    f.reset()
                for f in self.filtros_z.values():
                    f.reset()
            return None, None

        self.frames_perdidos = 0
        lms = resultado.pose_landmarks[0]
        num_lms = len(lms)
        
        # Extraer puntos clave principales (en píxeles de la imagen original)
        p_raw = {
            "nose": np.array([lms[0].x * ancho, lms[0].y * alto], dtype=np.float32),
            "ear_left": np.array([lms[7].x * ancho, lms[7].y * alto], dtype=np.float32) if num_lms > 7 else np.array([lms[0].x * ancho - 50, lms[0].y * alto], dtype=np.float32),
            "ear_right": np.array([lms[8].x * ancho, lms[8].y * alto], dtype=np.float32) if num_lms > 8 else np.array([lms[0].x * ancho + 50, lms[0].y * alto], dtype=np.float32),
            "mouth_left": np.array([lms[9].x * ancho, lms[9].y * alto], dtype=np.float32) if num_lms > 9 else np.array([lms[0].x * ancho - 20, lms[0].y * alto + 30], dtype=np.float32),
            "mouth_right": np.array([lms[10].x * ancho, lms[10].y * alto], dtype=np.float32) if num_lms > 10 else np.array([lms[0].x * ancho + 20, lms[0].y * alto + 30], dtype=np.float32),
            "sh_left": np.array([lms[11].x * ancho, lms[11].y * alto], dtype=np.float32),
            "sh_right": np.array([lms[12].x * ancho, lms[12].y * alto], dtype=np.float32),
            "elb_left": np.array([lms[13].x * ancho, lms[13].y * alto], dtype=np.float32),
            "elb_right": np.array([lms[14].x * ancho, lms[14].y * alto], dtype=np.float32),
            "wri_left": np.array([lms[15].x * ancho, lms[15].y * alto], dtype=np.float32),
            "wri_right": np.array([lms[16].x * ancho, lms[16].y * alto], dtype=np.float32),
            "hip_left": np.array([lms[23].x * ancho, lms[23].y * alto], dtype=np.float32),
            "hip_right": np.array([lms[24].x * ancho, lms[24].y * alto], dtype=np.float32),
        }

        # Profundidad Z relativa de articulaciones
        z_raw = {
            "sh_left": lms[11].z,
            "sh_right": lms[12].z,
            "elb_left": lms[13].z,
            "elb_right": lms[14].z,
            "wri_left": lms[15].z,
            "wri_right": lms[16].z,
            "hip_left": lms[23].z,
            "hip_right": lms[24].z,
        }

        # Visibilidades
        vis = {
            "sh_left": lms[11].visibility,
            "sh_right": lms[12].visibility,
            "elb_left": lms[13].visibility,
            "elb_right": lms[14].visibility,
            "wri_left": lms[15].visibility,
            "wri_right": lms[16].visibility,
            "hip_left": lms[23].visibility,
            "hip_right": lms[24].visibility,
            "nose": lms[0].visibility,
            "ear_left": lms[7].visibility if num_lms > 7 else 0.0,
            "ear_right": lms[8].visibility if num_lms > 8 else 0.0,
        }

        # Silueta de la persona -> medidas reales de pecho, cintura y cadera
        mascara = None
        if getattr(resultado, "segmentation_masks", None):
            mascara_raw = np.squeeze(resultado.segmentation_masks[0].numpy_view())
            if mascara_raw.shape[:2] != (alto, ancho):
                mascara = cv2.resize(mascara_raw, (ancho, alto), interpolation=cv2.INTER_LINEAR)
            else:
                mascara = mascara_raw

        # Velocidad de cada punto entre esta detección y la anterior (para predecir
        # los cuadros salteados). Si pasó mucho tiempo, no se confía en ella.
        t_sec = float(timestamp_ms) / 1000.0
        anterior = self._ultima_deteccion
        dt_det = t_sec - anterior["t"] if anterior is not None else 0.0
        if anterior is not None and 1e-3 < dt_det < 0.25:
            self._velocidad = {k: (v - anterior["p_raw"][k]) / dt_det for k, v in p_raw.items()}
        else:
            self._velocidad = {}
        self._ultima_deteccion = {"t": t_sec, "p_raw": p_raw, "z_raw": z_raw, "vis": vis,
                                  "mascara": mascara, "lms": lms}

        info_anatomica = self._actualizar_con_puntos(p_raw, z_raw, vis, ancho, alto, t_sec)
        info_anatomica["orientacion"] = self.actualizar_orientacion(info_anatomica["orientacion_cuadro"])
        self.ultima_mascara = mascara
        self.agregar_medidas(info_anatomica, mascara)
        return lms, info_anatomica

    # Hasta cuánto tiempo hacia adelante se extrapola el movimiento (segundos)
    MAX_PREDICCION_S = 0.10

    def _predecir_cuadro(self, ancho, alto, timestamp_ms):
        """
        Cuadro salteado: no corre MediaPipe. Avanza cada punto con su velocidad desde
        la última detección y corre la silueta anterior lo mismo que se movió el torso.
        Cuesta ~1 ms en lugar de ~80 ms.
        """
        det = self._ultima_deteccion
        t_sec = float(timestamp_ms) / 1000.0
        dt = min(max(0.0, t_sec - det["t"]), self.MAX_PREDICCION_S)
        p_pred = {k: v + self._velocidad.get(k, 0.0) * dt for k, v in det["p_raw"].items()}

        mascara = det["mascara"]
        if mascara is not None and self._velocidad:
            torso = ("sh_left", "sh_right", "hip_left", "hip_right")
            dx, dy = np.mean([p_pred[k] - det["p_raw"][k] for k in torso], axis=0)
            if abs(dx) >= 0.5 or abs(dy) >= 0.5:
                traslacion = np.float32([[1, 0, dx], [0, 1, dy]])
                mascara = cv2.warpAffine(mascara, traslacion, (ancho, alto), flags=cv2.INTER_NEAREST,
                                         borderMode=cv2.BORDER_CONSTANT, borderValue=0)

        info_anatomica = self._actualizar_con_puntos(p_pred, det["z_raw"], det["vis"], ancho, alto, t_sec)
        info_anatomica["orientacion"] = self.orientacion  # la vista sólo cambia con detecciones reales
        self.ultima_mascara = mascara
        self.agregar_medidas(info_anatomica, mascara, medir=False)
        return det["lms"], info_anatomica

    def _actualizar_con_puntos(self, p_raw, z_raw, vis, ancho, alto, t_sec):
        """Suaviza los puntos con One Euro y calcula la geometría del cuerpo."""
        # Aplicar Filtro One Euro adaptativo (sin lag en movimientos, suave en reposo)
        self.puntos_suavizados = {}
        for k, v in p_raw.items():
            if k not in self.filtros_puntos:
                self.filtros_puntos[k] = OneEuroFilter(t0=t_sec, x0=v, min_cutoff=1.0, beta=0.04, d_cutoff=1.0)
                self.puntos_suavizados[k] = v.copy()
            else:
                self.puntos_suavizados[k] = self.filtros_puntos[k].filter(v, t_sec)

        self.z_suavizados = {}
        for k, v in z_raw.items():
            if k not in self.filtros_z:
                self.filtros_z[k] = OneEuroFilter(t0=t_sec, x0=float(v), min_cutoff=1.0, beta=0.04, d_cutoff=1.0)
                self.z_suavizados[k] = float(v)
            else:
                self.z_suavizados[k] = float(self.filtros_z[k].filter(v, t_sec))

        return self._calcular_geometria_corporal(
            self.puntos_suavizados, self.z_suavizados, vis, ancho, alto
        )

    def agregar_medidas(self, info_anatomica, mascara, medir=True):
        """
        Mide la silueta, suaviza las medidas con OneEuroFilter y las agrega a info_anatomica.
        Con medir=False (cuadros salteados) reutiliza las últimas medidas: el cuerpo no
        cambia de forma en 30 ms y así se ahorra el recorrido de la silueta.
        """
        t_sec = float(self._ultimo_timestamp_ms) / 1000.0
        if mascara is not None and medir:
            medidas = self.medidas.actualizar(medir_silueta(mascara, info_anatomica), timestamp_s=t_sec)
        else:
            medidas = dict(self.medidas.valores)
        info_anatomica["medidas"] = medidas
        info_anatomica["figura"] = estimar_figura(medidas)

        # Cuello medido en la silueta: un poco arriba de la base del cuello
        if mascara is not None and medir:
            cuello = self._medir_cuello(mascara, info_anatomica)
            self._cuello_medido = cuello is not None
            if cuello is not None:
                anterior = getattr(self, "_cuello_suave", None)
                self._cuello_suave = cuello if anterior is None else anterior * 0.8 + cuello * 0.2
        if mascara is not None and getattr(self, "_cuello_medido", False):
            info_anatomica["medio_cuello"] = self._cuello_suave
        info_anatomica["mascara"] = mascara
        return info_anatomica

    # Umbrales de orientación (relación ancho de hombros / largo del torso)
    RELACION_PERFIL = 0.40   # por debajo: la persona está de perfil (más de ~60°)
    RELACION_GIRADA = 0.60   # por debajo: girada de forma notable
    GIRO_GIRADA = 0.15

    @classmethod
    def estimar_orientacion(cls, pts, vis, dist_sh, dist_torso, caderas_visibles, giro):
        """
        Estima hacia dónde mira la persona en ESTE cuadro:
          "frente"  -> de frente a la cámara (como un espejo)
          "girada"  -> girada, pero todavía se puede vestir
          "perfil"  -> de costado (los hombros casi se superponen)
          "espalda" -> de espaldas a la cámara

        Pistas que usa:
        - En la imagen espejada, de frente, el hombro IZQUIERDO real (landmark 11)
          aparece a la DERECHA de la pantalla. De espaldas, el orden se invierte.
        - De espaldas no se ve la cara (nariz y orejas con baja visibilidad).
        - De perfil, el ancho de hombros es muy chico comparado con el torso.
        """
        relacion = dist_sh / max(1.0, dist_torso) if caderas_visibles else 1.0
        if caderas_visibles and relacion < cls.RELACION_PERFIL:
            return "perfil"

        orden_invertido = float(pts["sh_left"][0]) < float(pts["sh_right"][0])
        nariz = float(vis.get("nose", 1.0))
        orejas = max(float(vis.get("ear_left", 1.0)), float(vis.get("ear_right", 1.0)))
        if (orden_invertido and nariz < 0.6) or (nariz < 0.15 and orejas < 0.25):
            return "espalda"

        if abs(giro) > cls.GIRO_GIRADA or (caderas_visibles and relacion < cls.RELACION_GIRADA):
            return "girada"
        return "frente"

    def actualizar_orientacion(self, orientacion_cuadro):
        """Aplica la histéresis: evita que la vista 'parpadee' entre estados."""
        if orientacion_cuadro == self.orientacion:
            self._cuadros_candidata = 0
            return self.orientacion
        if orientacion_cuadro == self._orientacion_candidata:
            self._cuadros_candidata += 1
        else:
            self._orientacion_candidata = orientacion_cuadro
            self._cuadros_candidata = 1
        if self._cuadros_candidata >= self.cuadros_para_cambiar:
            self.orientacion = orientacion_cuadro
            self._cuadros_candidata = 0
        return self.orientacion

    @staticmethod
    def _medir_cuello(mascara, info):
        """Medio ancho del cuello en la silueta (píxeles) o None."""
        d_sh = float(info["dist_sh"])
        centro = info["p_neck_base"] + info["u_up"] * (d_sh * 0.16)
        alto, ancho = mascara.shape[:2]
        lados = []
        for signo in (-1.0, 1.0):
            direccion = info["u_sh"] * signo
            dist = None
            for t in np.arange(0.0, d_sh * 0.40, 1.5):
                x, y = (centro + direccion * t).astype(int)
                if not (0 <= x < ancho and 0 <= y < alto) or mascara[y, x] < 0.5:
                    dist = t
                    break
            if dist is None:
                return None
            lados.append(dist)
        medio = 0.5 * (lados[0] + lados[1])
        if not (d_sh * 0.10 <= medio <= d_sh * 0.32):
            return None  # el cuello se fundió con hombros o pelo: medida no confiable
        return float(medio)

    def _calcular_geometria_corporal(self, pts, z_vals, vis, ancho, alto):
        """
        Calcula vectores, orientación, dimensiones y ordenamiento de pantalla
        (el hombro a menor X es pantalla-izquierda, mayor X es pantalla-derecha).
        """
        p11, p12 = pts["sh_left"], pts["sh_right"]
        p13, p14 = pts["elb_left"], pts["elb_right"]
        p15, p16 = pts["wri_left"], pts["wri_right"]
        p23, p24 = pts["hip_left"], pts["hip_right"]

        # En vista espejo (flipped):
        # El hombro a la izquierda de la pantalla es el que tiene menor X
        if p12[0] <= p11[0]:
            p_sh_l, p_sh_r = p12, p11
            p_elb_l, p_elb_r = p14, p13
            p_wri_l, p_wri_r = p16, p15
            p_hip_l, p_hip_r = p24, p23
            z_wri_l, z_wri_r = z_vals["wri_right"], z_vals["wri_left"]
            z_sh_l, z_sh_r = z_vals["sh_right"], z_vals["sh_left"]
            vis_elb_l, vis_elb_r = vis["elb_right"], vis["elb_left"]
        else:
            p_sh_l, p_sh_r = p11, p12
            p_elb_l, p_elb_r = p13, p14
            p_wri_l, p_wri_r = p15, p16
            p_hip_l, p_hip_r = p23, p24
            z_wri_l, z_wri_r = z_vals["wri_left"], z_vals["wri_right"]
            z_sh_l, z_sh_r = z_vals["sh_left"], z_vals["sh_right"]
            vis_elb_l, vis_elb_r = vis["elb_left"], vis["elb_right"]

        # Vector de hombros (apunta hacia la derecha: X+)
        v_sh = p_sh_r - p_sh_l
        dist_sh = float(np.linalg.norm(v_sh))
        if dist_sh < 15.0:
            dist_sh = 15.0
        u_sh = v_sh / dist_sh

        # Vector perpendicular hacia la cabeza (Y- en pantalla)
        u_up = np.array([u_sh[1], -u_sh[0]], dtype=np.float32)
        if u_up[1] > 0:
            u_up = -u_up
        u_down = -u_up

        # Inclinación en grados
        inclinacion_deg = math.degrees(math.atan2(v_sh[1], v_sh[0]))

        # Puntos medios de hombros y caderas
        p_neck_base = (p_sh_l + p_sh_r) * 0.5
        p_hip_mid = (p_hip_l + p_hip_r) * 0.5
        v_torso = p_hip_mid - p_neck_base
        dist_torso = float(np.linalg.norm(v_torso))

        # Salvaguarda si las caderas no son visibles o están muy cerca
        caderas_visibles = True
        if dist_torso < 25.0 or v_torso[1] <= 0 or vis["hip_left"] < 0.25 or vis["hip_right"] < 0.25:
            caderas_visibles = False
            dist_torso = dist_sh * 1.35
            u_torso = u_down
            p_hip_mid = p_neck_base + u_torso * dist_torso
            p_hip_l = p_sh_l + u_torso * dist_torso
            p_hip_r = p_sh_r + u_torso * dist_torso
        else:
            u_torso = v_torso / dist_torso

        # Vectores de brazos/mangas orientados hacia los codos
        # Manga izquierda (pantalla)
        v_arm_l = p_elb_l - p_sh_l
        d_arm_l = float(np.linalg.norm(v_arm_l))
        if d_arm_l > 15.0 and vis_elb_l > 0.25:
            u_arm_l = v_arm_l / d_arm_l
        else:
            u_arm_l = (-0.35 * u_sh + 0.94 * u_down).astype(np.float32)

        # Manga derecha (pantalla)
        v_arm_r = p_elb_r - p_sh_r
        d_arm_r = float(np.linalg.norm(v_arm_r))
        if d_arm_r > 15.0 and vis_elb_r > 0.25:
            u_arm_r = v_arm_r / d_arm_r
        else:
            u_arm_r = (0.35 * u_sh + 0.94 * u_down).astype(np.float32)

        # Vectores perpendiculares para el ancho de las mangas
        u_cuff_l = np.array([u_arm_l[1], -u_arm_l[0]], dtype=np.float32)
        if np.dot(u_cuff_l, u_sh) < 0:
            u_cuff_l = -u_cuff_l

        u_cuff_r = np.array([u_arm_r[1], -u_arm_r[0]], dtype=np.float32)
        if np.dot(u_cuff_r, u_sh) > 0:
            u_cuff_r = -u_cuff_r

        # Brazos cruzados / manos al frente (Z menor que hombros)
        brazos_al_frente = (z_wri_l < z_sh_l - 0.12) or (z_wri_r < z_sh_r - 0.12)

        # --- Línea de caderas (puede inclinarse distinto que los hombros)
        v_hip = p_hip_r - p_hip_l
        d_hip = float(np.linalg.norm(v_hip))
        if caderas_visibles and d_hip > dist_sh * 0.25:
            u_hip = (v_hip / d_hip).astype(np.float32)
            if float(u_hip @ u_sh) < 0:
                u_hip = -u_hip
        else:
            u_hip = u_sh.copy()

        # --- Giro del torso (yaw) con la profundidad Z de hombros y caderas.
        # En MediaPipe, Z más chico = más cerca de la cámara.
        # giro > 0: el lado DERECHO de la pantalla se aleja; giro < 0: se aleja el izquierdo.
        z_hip_l, z_hip_r = (z_vals["hip_right"], z_vals["hip_left"]) if p12[0] <= p11[0] else (z_vals["hip_left"], z_vals["hip_right"])
        dz = (z_sh_r - z_sh_l)
        if caderas_visibles:
            dz = 0.65 * dz + 0.35 * (z_hip_r - z_hip_l)
        giro = float(np.clip(dz * 2.2, -0.7, 0.7))

        # --- Brazos levantados: cuánto sube el codo por encima del hombro (0 a 1)
        def elevacion(p_sh, p_elb):
            return float(np.clip(((p_elb - p_sh) @ u_up) / (dist_sh * 0.45) + 0.15, 0.0, 1.0))
        brazo_arriba_l = elevacion(p_sh_l, p_elb_l)
        brazo_arriba_r = elevacion(p_sh_r, p_elb_r)

        # --- Cuello: ancho estimado con las orejas (si están), para que el escote lo abrace
        if "ear_left" in pts and "ear_right" in pts:
            d_orejas = float(np.linalg.norm(pts["ear_left"] - pts["ear_right"]))
            medio_cuello = float(np.clip(d_orejas * 0.36, dist_sh * 0.13, dist_sh * 0.30))
        else:
            medio_cuello = dist_sh * 0.20
        if "mouth_left" in pts and "mouth_right" in pts:
            p_boca = (pts["mouth_left"] + pts["mouth_right"]) * 0.5
        else:
            p_boca = pts["nose"] + (p_neck_base - pts["nose"]) * 0.25

        orientacion_cuadro = self.estimar_orientacion(
            pts, vis, dist_sh, dist_torso, caderas_visibles, giro)

        return {
            "orientacion_cuadro": orientacion_cuadro,
            "orientacion": orientacion_cuadro,
            "p_sh_l": p_sh_l,
            "p_sh_r": p_sh_r,
            "p_elb_l": p_elb_l,
            "p_elb_r": p_elb_r,
            "p_wri_l": p_wri_l,
            "p_wri_r": p_wri_r,
            "p_hip_l": p_hip_l,
            "p_hip_r": p_hip_r,
            "p_neck_base": p_neck_base,
            "p_hip_mid": p_hip_mid,
            "dist_sh": dist_sh,
            "dist_torso": dist_torso,
            "inclinacion_deg": inclinacion_deg,
            "u_sh": u_sh,
            "u_up": u_up,
            "u_down": u_down,
            "u_torso": u_torso,
            "u_arm_l": u_arm_l,
            "u_arm_r": u_arm_r,
            "u_cuff_l": u_cuff_l,
            "u_cuff_r": u_cuff_r,
            "brazos_al_frente": brazos_al_frente,
            "caderas_visibles": caderas_visibles,
            "u_hip": u_hip,
            "giro": giro,
            "brazo_arriba_l": brazo_arriba_l,
            "brazo_arriba_r": brazo_arriba_r,
            "medio_cuello": medio_cuello,
            "p_boca": p_boca,
            "nose": pts["nose"],
        }

    def calcular_puntos_destino_malla(self, info, tiene_mangas=True, factor_escala=1.0,
                                      holgura_talle=1.05, calce="regular"):
        """
        Calcula los 23 puntos destino de la prenda en el cuadro de la cámara.

        - Si hay medidas de la silueta (pecho, cintura, cadera, brazo), los costados
          de la prenda se apoyan sobre el borde REAL del cuerpo, más la holgura del
          talle elegido. Así se adapta a cuerpos con distintas figuras.
        - Si no hay medidas (por ejemplo, la máscara todavía no está lista), se usan
          proporciones a partir del ancho de hombros, como antes.

        factor_escala: ajuste manual con las teclas + / -.
        holgura_talle: 1.00 (S) ... 1.18 (XL), ver catalogo.HOLGURA_TALLES.
        calce: "entallado", "regular" u "holgado".
        """
        p_sh_l = info["p_sh_l"]
        p_sh_r = info["p_sh_r"]
        p_neck_base = info["p_neck_base"]
        d_sh_real = info["dist_sh"]
        d_torso_real = info["dist_torso"]
        u_sh = info["u_sh"]
        u_up = info["u_up"]
        u_torso = info["u_torso"]
        u_arm_l = info["u_arm_l"]
        u_arm_r = info["u_arm_r"]
        u_cuff_l = info["u_cuff_l"]
        u_cuff_r = info["u_cuff_r"]

        # Holgura total = talle x ajuste manual. Los talles más grandes también son
        # un poco más largos (no sólo más anchos).
        holgura = float(holgura_talle) * float(factor_escala)
        largo_talle = 1.0 + (float(holgura_talle) - 1.05) * 0.6
        d_sh = d_sh_real * factor_escala
        d_torso = d_torso_real * factor_escala * largo_talle

        # Dirección lateral perpendicular al torso (para los costados de la prenda)
        u_lat = np.array([-u_torso[1], u_torso[0]], dtype=np.float32)
        if float(u_lat @ u_sh) < 0:
            u_lat = -u_lat

        # Ancho y holguras anatómicas (valores por defecto, sin silueta)
        # El escote abraza el cuello medido (orejas o silueta), con una pequeña holgura
        ancho_cuello = float(np.clip(info.get("medio_cuello", d_sh_real * 0.20) * 1.10,
                                     d_sh_real * 0.15, d_sh_real * 0.32))
        altura_cuello = d_sh_real * 0.20
        largo_manga = d_sh * 0.52
        ancho_manga = d_sh * 0.26 * holgura / 1.05
        salida_manga = d_sh * 0.08
        medio = {  # medios anchos (izquierda, derecha) en píxeles
            "pecho": (d_sh * 0.56, d_sh * 0.56),
            "cintura": (d_sh * 0.44 * holgura / 1.05, d_sh * 0.44 * holgura / 1.05),
            "ruedo": (d_sh * 0.449 * holgura / 1.05, d_sh * 0.449 * holgura / 1.05),
        }
        medio["bajo_busto"] = tuple(0.5 * (a + b) for a, b in zip(medio["pecho"], medio["cintura"]))
        medio["cadera_alta"] = tuple(0.5 * (a + b) for a, b in zip(medio["cintura"], medio["ruedo"]))
        hombro_extra = d_sh * 0.10

        medidas = info.get("medidas") or {}
        if medidas.get("cintura_l") is not None or medidas.get("pecho_l") is not None:
            medio = self._medios_anchos_desde_silueta(medidas, holgura, calce, d_sh_real)
            hombro_extra = d_sh_real * (0.10 + (holgura - 1.05) * 0.5)
        if medidas.get("brazo"):
            radio = medidas["brazo"] * 0.5
            # La manga rodea el brazo con holgura: hacia afuera y hacia adentro
            salida_manga = max(d_sh_real * 0.08, radio * 1.05 * holgura)
            ancho_manga = max(d_sh_real * 0.17 * holgura, radio * 1.30 * holgura)

        # Giro del torso: el centro de la prenda (botones, logo) se corre hacia el lado
        # que se aleja; sin silueta, además se achica ese lado.
        giro = float(info.get("giro", 0.0))
        corrimiento = u_lat * (giro * d_sh_real * 0.12)
        if not medidas:
            factor_l = 1.0 + 0.30 * giro   # giro > 0: se aleja el lado derecho
            factor_r = 1.0 - 0.30 * giro
            medio = {k: (v[0] * factor_l, v[1] * factor_r) for k, v in medio.items()}

        # Brazos levantados: la axila de ese lado sube y el ruedo se levanta un poco
        sube_l = float(info.get("brazo_arriba_l", 0.0))
        sube_r = float(info.get("brazo_arriba_r", 0.0))
        sube_ruedo = max(sube_l, sube_r) * d_torso * 0.05

        # Hacia abajo, los costados pasan de seguir los hombros a seguir la línea de caderas
        u_hip = info.get("u_hip", u_lat)
        def lateral(mezcla):
            v = u_lat * (1.0 - mezcla) + u_hip * mezcla
            return v / max(1e-6, float(np.linalg.norm(v)))

        def nivel(fraccion):
            return p_neck_base + u_torso * (d_torso * fraccion)

        dst_pts = {
            # 1. Cuello y Escote (alineado a la base del cuello de la persona)
            "collar_top_mid": p_neck_base + u_up * (altura_cuello * 1.10),
            "collar_top_l": p_neck_base - u_sh * ancho_cuello + u_up * (altura_cuello * 0.90),
            "collar_top_r": p_neck_base + u_sh * ancho_cuello + u_up * (altura_cuello * 0.90),
            "collar_tip_l": p_neck_base - u_sh * (ancho_cuello * 0.65) - u_up * (altura_cuello * 0.25),
            "collar_tip_r": p_neck_base + u_sh * (ancho_cuello * 0.65) - u_up * (altura_cuello * 0.25),
            "neck_v": p_neck_base + u_torso * (d_torso_real * 0.18) + corrimiento * 0.5,

            # 2. Hombros (un poco más afuera de la articulación, según el talle)
            # (el punto de MediaPipe es la articulación; la parte de arriba del hombro
            #  está más alta, y el recorte a la silueta quita lo que sobre)
            "shoulder_l": p_sh_l - u_sh * hombro_extra + u_up * (d_sh_real * 0.09),
            "shoulder_r": p_sh_r + u_sh * hombro_extra + u_up * (d_sh_real * 0.09),

            # 3. Mangas (orientadas dinámicamente con los brazos y con el grosor medido)
            "sleeve_top_l": p_sh_l - u_sh * (hombro_extra * 2.0) + u_arm_l * (largo_manga * 0.45),
            "sleeve_top_r": p_sh_r + u_sh * (hombro_extra * 2.0) + u_arm_r * (largo_manga * 0.45),
            "sleeve_cuff_out_l": p_sh_l + u_arm_l * largo_manga - u_cuff_l * salida_manga,
            "sleeve_cuff_out_r": p_sh_r + u_arm_r * largo_manga - u_cuff_r * salida_manga,
            "sleeve_cuff_in_l": p_sh_l + u_arm_l * (largo_manga * 0.95) + u_cuff_l * ancho_manga,
            "sleeve_cuff_in_r": p_sh_r + u_arm_r * (largo_manga * 0.95) + u_cuff_r * ancho_manga,
            # Bíceps: punto intermedio de la manga para que acompañe el brazo sin quebrarse
            "bicep_out_l": p_sh_l + u_arm_l * (largo_manga * 0.62) - u_cuff_l * (salida_manga * 1.05),
            "bicep_out_r": p_sh_r + u_arm_r * (largo_manga * 0.62) - u_cuff_r * (salida_manga * 1.05),
            "bicep_in_l": p_sh_l + u_arm_l * (largo_manga * 0.60) + u_cuff_l * (ancho_manga * 1.05),
            "bicep_in_r": p_sh_r + u_arm_r * (largo_manga * 0.60) + u_cuff_r * (ancho_manga * 1.05),

            # 4. Axilas: sobre el costado del pecho medido
            "armpit_l": nivel(0.33) - u_lat * medio["pecho"][0] + u_up * (sube_l * d_torso * 0.10),
            "armpit_r": nivel(0.33) + u_lat * medio["pecho"][1] + u_up * (sube_r * d_torso * 0.10),

            # 5. Pecho y Centro
            "chest_mid": nivel(0.36) + corrimiento,
            "torso_mid": nivel(0.68) + corrimiento * 0.8,

            # 5b. Bajo busto: punto intermedio del costado entre axila y cintura
            "underbust_l": nivel(0.50) - lateral(0.2) * medio["bajo_busto"][0] + u_up * (sube_l * d_torso * 0.04),
            "underbust_r": nivel(0.50) + lateral(0.2) * medio["bajo_busto"][1] + u_up * (sube_r * d_torso * 0.04),

            # 6. Cintura (sigue la cintura según el calce de la prenda)
            "waist_l": nivel(0.68) - lateral(0.5) * medio["cintura"][0],
            "waist_r": nivel(0.68) + lateral(0.5) * medio["cintura"][1],

            # 6b. Cadera alta: punto intermedio del costado entre cintura y ruedo
            "high_hip_l": nivel(0.86) - lateral(0.8) * medio["cadera_alta"][0] - u_torso * (sube_ruedo * 0.6),
            "high_hip_r": nivel(0.86) + lateral(0.8) * medio["cadera_alta"][1] - u_torso * (sube_ruedo * 0.6),

            # 7. Ruedo inferior (nunca más angosto que la cadera)
            "hem_l": nivel(1.05) - lateral(1.0) * medio["ruedo"][0] - u_torso * sube_ruedo,
            "hem_mid": nivel(1.06) + corrimiento * 0.6 - u_torso * sube_ruedo,
            "hem_r": nivel(1.05) + lateral(1.0) * medio["ruedo"][1] - u_torso * sube_ruedo,
        }

        # Si no tiene mangas (ej. top halter o musculosa), plegar las mangas hacia los hombros
        if not tiene_mangas:
            dst_pts["sleeve_top_l"] = dst_pts["shoulder_l"]
            dst_pts["sleeve_top_r"] = dst_pts["shoulder_r"]
            dst_pts["sleeve_cuff_out_l"] = dst_pts["armpit_l"]
            dst_pts["sleeve_cuff_out_r"] = dst_pts["armpit_r"]
            dst_pts["sleeve_cuff_in_l"] = dst_pts["armpit_l"]
            dst_pts["sleeve_cuff_in_r"] = dst_pts["armpit_r"]
            dst_pts["bicep_out_l"] = dst_pts["armpit_l"]
            dst_pts["bicep_out_r"] = dst_pts["armpit_r"]
            dst_pts["bicep_in_l"] = dst_pts["armpit_l"]
            dst_pts["bicep_in_r"] = dst_pts["armpit_r"]

        return dst_pts

    @staticmethod
    def _medios_anchos_desde_silueta(medidas, holgura, calce, d_sh):
        """
        Convierte las medidas del cuerpo en los medios anchos de la prenda
        (pecho, cintura y ruedo, a cada lado), según el talle y el calce.
        """
        def lado(nivel, lado_):
            valor = medidas.get(f"{nivel}_{lado_}")
            if valor is None:
                otro = medidas.get(f"{nivel}_{'r' if lado_ == 'l' else 'l'}")
                return otro
            return valor

        resultado = {"pecho": [0.0, 0.0], "bajo_busto": [0.0, 0.0], "cintura": [0.0, 0.0],
                     "cadera_alta": [0.0, 0.0], "ruedo": [0.0, 0.0]}
        for i, s in enumerate(("l", "r")):
            pecho = lado("pecho", s) or d_sh * 0.44
            cintura = lado("cintura", s) or pecho * 0.92
            cadera = lado("cadera", s)

            # Cómo cae la tela en la cintura según el calce
            if calce == "holgado":
                cintura_prenda = max(cintura, pecho, (cadera or 0.0) * 0.98)
                holgura_pecho = holgura * 1.04
            elif calce == "regular":
                promedio = 0.5 * (pecho + (cadera if cadera is not None else pecho)) * 0.93
                cintura_prenda = max(cintura, promedio)
                holgura_pecho = holgura
            else:  # entallado
                cintura_prenda = cintura
                holgura_pecho = holgura

            # El ruedo cae sobre la cadera: nunca más angosto que ella ni que la cintura
            base_ruedo = max(cintura_prenda, cadera if cadera is not None else cintura_prenda * 1.04)

            resultado["pecho"][i] = pecho * holgura_pecho
            resultado["cintura"][i] = cintura_prenda * holgura
            resultado["ruedo"][i] = base_ruedo * holgura * 1.03

            # Puntos intermedios: siguen el cuerpo medido, pero respetando el calce
            # (una prenda holgada no se mete en la curva del bajo busto ni de la cadera alta)
            bajo_busto = lado("bajo_busto", s) or 0.5 * (pecho + cintura)
            cadera_alta = lado("cadera_alta", s) or 0.5 * (cintura + (cadera or cintura))
            if calce == "entallado":
                bajo_busto_prenda = bajo_busto
                cadera_alta_prenda = max(cadera_alta, cintura_prenda)
            else:
                bajo_busto_prenda = max(bajo_busto, 0.5 * (pecho * holgura_pecho / holgura + cintura_prenda))
                cadera_alta_prenda = max(cadera_alta, 0.5 * (cintura_prenda + base_ruedo))
            resultado["bajo_busto"][i] = bajo_busto_prenda * holgura
            resultado["cadera_alta"][i] = min(cadera_alta_prenda * holgura, resultado["ruedo"][i])
        return {k: tuple(v) for k, v in resultado.items()}
