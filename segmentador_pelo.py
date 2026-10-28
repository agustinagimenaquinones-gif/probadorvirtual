# ==========================================================
# PROYECTO: PROBADOR VIRTUAL INTELIGENTE
# MÓDULO: PELO POR DELANTE DE LA PRENDA (MediaPipe Image Segmenter)
# ==========================================================
# El pelo largo cae sobre los hombros y el pecho, POR DELANTE de la ropa. Sin este
# módulo la prenda virtual lo tapa. El modelo "hair_segmenter" de MediaPipe marca
# qué píxeles son pelo; la prenda se borra ahí y el pelo queda adelante.
#
# El modelo tarda ~60 ms por cuadro en una notebook, así que corre en su propio hilo
# sobre la zona de la cabeza y los hombros, y entre una detección y la siguiente la
# máscara se corre junto con el cuello (el pelo se mueve con la cabeza). Si el pelo no
# baja de los hombros (pelo corto o atado) se revisa sólo una vez por segundo: así no
# le quita velocidad al probador a quien no lo necesita.
# La misma máscara ayuda a medir el cuello: el pelo rubio tiene un color parecido a
# la piel y por color solo se confundiría con el cuello.

import os
import threading
import time

import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision


class SegmentadorPelo:
    def __init__(self, model_path="hair_segmenter.tflite", cada_s=0.10, cada_s_sin_pelo=1.0):
        self.cada_s = cada_s          # con pelo sobre los hombros: una detección cada 'cada_s' segundos
        self.cada_s_sin_pelo = cada_s_sin_pelo
        self.pelo_sobre_hombros = False
        self.disponible = False
        self._segmentador = None
        self._resultado = None        # (x0, y0, máscara uint8 0-255, cuello al detectar)
        self._trabajo = None
        self._ocupado = False
        self._ultimo_pedido = 0.0
        self._cerrando = False
        self._candado = threading.Lock()
        self._hay_trabajo = threading.Event()
        self._hilo = None
        if not os.path.exists(model_path):
            print(f"[AVISO] No está el modelo de pelo ({model_path}): el pelo no se pone delante de la prenda.")
            return
        try:
            opciones = vision.ImageSegmenterOptions(
                base_options=python.BaseOptions(model_asset_path=model_path),
                running_mode=vision.RunningMode.IMAGE,
                output_category_mask=False, output_confidence_masks=True)
            self._segmentador = vision.ImageSegmenter.create_from_options(opciones)
        except Exception as error:
            print(f"[AVISO] No se pudo cargar el modelo de pelo: {error}")
            return
        self.disponible = True
        self._hilo = threading.Thread(target=self._trabajar, daemon=True)
        self._hilo.start()

    @staticmethod
    def zona_cabeza(info, ancho, alto):
        """Rectángulo de la cabeza, el cuello, los hombros y el pecho (donde cae el pelo)."""
        d_sh = float(info["dist_sh"])
        cuello = np.asarray(info["p_neck_base"], np.float32)
        x0 = int(max(0, min(info["p_sh_l"][0], info["p_sh_r"][0]) - d_sh * 0.35))
        x1 = int(min(ancho, max(info["p_sh_l"][0], info["p_sh_r"][0]) + d_sh * 0.35))
        y0 = int(max(0, cuello[1] - d_sh * 1.1))
        y1 = int(min(alto, cuello[1] + float(info["dist_torso"]) * 0.65))
        return x0, y0, x1, y1

    def pedir(self, frame_bgr, info):
        """Manda a segmentar este cuadro si el hilo está libre (no espera el resultado)."""
        if not self.disponible or info is None:
            return
        ahora = time.time()
        espera = self.cada_s if self.pelo_sobre_hombros else self.cada_s_sin_pelo
        if self._ocupado or ahora - self._ultimo_pedido < espera:
            return
        alto, ancho = frame_bgr.shape[:2]
        x0, y0, x1, y1 = self.zona_cabeza(info, ancho, alto)
        if x1 - x0 < 16 or y1 - y0 < 16:
            return
        with self._candado:
            self._trabajo = (frame_bgr[y0:y1, x0:x1].copy(), x0, y0,
                             np.asarray(info["p_neck_base"], np.float32).copy(), float(info["dist_sh"]))
            self._ocupado = True
        self._ultimo_pedido = ahora
        self._hay_trabajo.set()

    def _trabajar(self):
        while not self._cerrando:
            self._hay_trabajo.wait()
            self._hay_trabajo.clear()
            if self._cerrando:
                break
            with self._candado:
                trabajo, self._trabajo = self._trabajo, None
            if trabajo is None:
                continue
            recorte, x0, y0, cuello, d_sh = trabajo
            try:
                imagen = mp.Image(image_format=mp.ImageFormat.SRGB,
                                  data=np.ascontiguousarray(cv2.cvtColor(recorte, cv2.COLOR_BGR2RGB)))
                salida = self._segmentador.segment(imagen)
                pelo = np.squeeze(salida.confidence_masks[-1].numpy_view())
                if pelo.shape[:2] != recorte.shape[:2]:
                    pelo = cv2.resize(pelo, (recorte.shape[1], recorte.shape[0]))
                pelo = np.clip(pelo * 255.0, 0, 255).astype(np.uint8)
                # ¿Baja el pelo de la línea de los hombros? (ahí tapa la prenda)
                fila = int(max(0, cuello[1] - y0))
                self.pelo_sobre_hombros = int(np.count_nonzero(pelo[fila:] > 128)) > (d_sh * 0.05) ** 2
                with self._candado:
                    self._resultado = (x0, y0, pelo, cuello)
            except Exception as error:
                print(f"[AVISO] Falló la detección de pelo: {error}")
            finally:
                self._ocupado = False

    def mascara(self, info):
        """
        (x0, y0, máscara) del pelo, corrida con el cuello desde que se detectó, o None.
        La máscara es uint8: 255 = seguro pelo.
        """
        with self._candado:
            resultado = self._resultado
        if resultado is None or info is None:
            return None
        x0, y0, pelo, cuello = resultado
        dx, dy = np.asarray(info["p_neck_base"], np.float32) - cuello
        if abs(dx) > float(info["dist_sh"]) * 0.5 or abs(dy) > float(info["dist_sh"]) * 0.5:
            return None  # la persona se movió mucho: la máscara vieja ya no sirve
        return int(round(x0 + dx)), int(round(y0 + dy)), pelo

    def cerrar(self):
        self._cerrando = True
        self._hay_trabajo.set()
        if self._hilo is not None:
            self._hilo.join(timeout=3.0)
            if self._hilo.is_alive():
                return  # sigue dentro de MediaPipe: se libera al terminar el programa
        if self._segmentador is not None:
            self._segmentador.close()


def recortar_a(pelo, x0, y0, ancho, alto):
    """Pasa la máscara del pelo a un rectángulo (x0, y0, ancho, alto) del cuadro (0 fuera)."""
    px, py, m = pelo
    salida = np.zeros((alto, ancho), np.uint8)
    ax0, ay0 = max(x0, px), max(y0, py)
    ax1, ay1 = min(x0 + ancho, px + m.shape[1]), min(y0 + alto, py + m.shape[0])
    if ax1 > ax0 and ay1 > ay0:
        salida[ay0 - y0:ay1 - y0, ax0 - x0:ax1 - x0] = m[ay0 - py:ay1 - py, ax0 - px:ax1 - px]
    return salida
