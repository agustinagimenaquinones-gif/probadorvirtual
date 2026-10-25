# ==========================================================
# PROYECTO: PROBADOR VIRTUAL INTELIGENTE
# MÓDULO: INERCIA DE LA TELA (EL RUEDO Y LAS MANGAS SE BALANCEAN)
# ==========================================================
# Una prenda real no es rígida: cuando la persona se mueve, la parte de abajo de la
# tela tarda un instante en seguirla y cuando frena se pasa un poco y vuelve.
#
# Cada punto "suelto" de la malla (ruedo, cadera, puños) cuelga de su posición en el
# cuerpo con un resorte amortiguado: aceleración = rigidez x distancia - freno x
# velocidad. Los puntos que sostienen la prenda (cuello, hombros, axilas, pecho)
# no tienen inercia: siguen al cuerpo exactamente, así la prenda nunca se atrasa.

import math
import numpy as np

# Cuánto se suelta cada punto (0 = sigue al cuerpo exacto, 1 = máxima inercia)
SOLTURA_PUNTOS = {
    "hem_l": 1.0, "hem_mid": 1.0, "hem_r": 1.0,
    "high_hip_l": 0.6, "high_hip_r": 0.6, "torso_mid": 0.35,
    "waist_l": 0.3, "waist_r": 0.3,
    "sleeve_cuff_out_l": 0.55, "sleeve_cuff_in_l": 0.55,
    "sleeve_cuff_out_r": 0.55, "sleeve_cuff_in_r": 0.55,
    "bicep_out_l": 0.25, "bicep_in_l": 0.25, "bicep_out_r": 0.25, "bicep_in_r": 0.25,
}
# Las prendas sueltas se balancean más que las ajustadas
SOLTURA_CALCE = {"holgado": 1.0, "regular": 0.7, "entallado": 0.4}

FRECUENCIA_HZ = 3.2      # qué tan rápido vuelve la tela (más bajo = más pesada)
AMORTIGUACION = 0.42     # < 1: se pasa un poco y vuelve; 1 = sin rebote
DESVIO_MAXIMO = 0.10     # como mucho se separa esta fracción del largo del torso


class InerciaTela:
    """Guarda la posición y velocidad de los puntos sueltos entre cuadros."""

    def __init__(self, frecuencia=FRECUENCIA_HZ, amortiguacion=AMORTIGUACION):
        self.omega = 2.0 * math.pi * frecuencia
        self.zeta = amortiguacion
        self.reiniciar()

    def reiniciar(self):
        self.pos = {}
        self.vel = {}
        self.t = None

    def aplicar(self, dst_pts, t_seg, calce="regular", largo_torso=200.0):
        """
        Devuelve una copia de dst_pts con la inercia aplicada a los puntos sueltos.
        t_seg: tiempo del cuadro en segundos (para que el movimiento no dependa de los FPS).
        """
        if self.t is None or t_seg <= self.t or t_seg - self.t > 0.25:
            # Primer cuadro o pausa larga: arrancar quieta en la posición del cuerpo
            self.pos = {k: np.asarray(v, np.float32).copy() for k, v in dst_pts.items() if k in SOLTURA_PUNTOS}
            self.vel = {k: np.zeros(2, np.float32) for k in self.pos}
            self.t = t_seg
            return dict(dst_pts)
        dt = t_seg - self.t
        self.t = t_seg
        soltura_calce = SOLTURA_CALCE.get(calce, 0.7)
        maximo = DESVIO_MAXIMO * float(largo_torso)
        resultado = dict(dst_pts)
        # Integración en pasos chicos (estable aunque baje la cantidad de cuadros por segundo)
        pasos = max(1, int(math.ceil(dt / 0.012)))
        h = dt / pasos
        for k, soltura in SOLTURA_PUNTOS.items():
            if k not in dst_pts:
                continue
            objetivo = np.asarray(dst_pts[k], np.float32)
            if k not in self.pos:
                self.pos[k], self.vel[k] = objetivo.copy(), np.zeros(2, np.float32)
            p, v = self.pos[k], self.vel[k]
            for _ in range(pasos):
                a = self.omega ** 2 * (objetivo - p) - 2.0 * self.zeta * self.omega * v
                v = v + a * h
                p = p + v * h
            desvio = p - objetivo
            largo = float(np.linalg.norm(desvio))
            if largo > maximo:  # la tela no puede quedar demasiado lejos del cuerpo
                p = objetivo + desvio * (maximo / largo)
                v = v * 0.5
            self.pos[k], self.vel[k] = p, v
            peso = soltura * soltura_calce
            resultado[k] = (objetivo + (p - objetivo) * peso).astype(np.float32)
        return resultado
