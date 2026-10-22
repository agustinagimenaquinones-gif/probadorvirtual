# ==========================================================
# PROYECTO: PROBADOR VIRTUAL INTELIGENTE
# MÓDULO: MEDICIÓN DE LA SILUETA Y ESTIMACIÓN DE LA FIGURA
# ==========================================================
# MediaPipe entrega, además de los 33 puntos, una "máscara de segmentación":
# una imagen donde cada píxel dice si pertenece a la persona (1) o al fondo (0).
#
# Con esa máscara medimos el ANCHO REAL del cuerpo a tres alturas:
#   - pecho   (debajo de las axilas)
#   - cintura (la parte más angosta del torso)
#   - cadera  (a la altura de las articulaciones de la cadera)
# y el grosor del brazo. Así la prenda se adapta a cada figura y no sólo
# al ancho de hombros.

import math
import numpy as np

# -------------------------------------------------------------------------
# FILTRO ADAPTATIVO ONE EURO (1€ FILTER)
# -------------------------------------------------------------------------
class OneEuroFilter:
    """
    Filtro adaptativo One Euro (Casiez et al., CHI 2012).
    A bajas velocidades reduce la frecuencia de corte para eliminar el temblor / jitter.
    A altas velocidades aumenta la frecuencia de corte para eliminar el retraso (lag).
    Soporta valores escalares y arreglos NumPy (puntos 2D, vectores Z).
    """
    def __init__(self, t0=0.0, x0=None, min_cutoff=1.0, beta=0.04, d_cutoff=1.0):
        self.min_cutoff = float(min_cutoff)
        self.beta = float(beta)
        self.d_cutoff = float(d_cutoff)
        self.x_prev = None if x0 is None else np.array(x0, dtype=np.float32)
        self.dx_prev = np.zeros_like(self.x_prev) if self.x_prev is not None else 0.0
        self.t_prev = float(t0)

    def reset(self):
        self.x_prev = None
        self.dx_prev = 0.0
        self.t_prev = 0.0

    def _alpha(self, dt, cutoff):
        tau = 1.0 / (2.0 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def filter(self, x, t=None):
        es_arreglo = isinstance(x, (np.ndarray, list, tuple))
        x_val = np.array(x, dtype=np.float32) if es_arreglo else float(x)
        if self.x_prev is None:
            self.x_prev = x_val.copy() if es_arreglo else x_val
            self.dx_prev = np.zeros_like(x_val) if es_arreglo else 0.0
            self.t_prev = float(t) if t is not None else 0.0
            return x

        if t is None:
            dt = 1.0 / 30.0
        else:
            dt = max(1e-4, float(t - self.t_prev))
            self.t_prev = float(t)

        # 1. Filtro de la derivada (velocidad de cambio)
        dx = (x_val - self.x_prev) / dt
        alpha_d = self._alpha(dt, self.d_cutoff)
        dx_hat = alpha_d * dx + (1.0 - alpha_d) * self.dx_prev
        self.dx_prev = dx_hat

        # 2. Frecuencia de corte adaptativa en función de la velocidad
        vel = float(np.linalg.norm(dx_hat)) if es_arreglo else abs(float(dx_hat))
        cutoff = max(0.1, self.min_cutoff + self.beta * vel)
        alpha = self._alpha(dt, cutoff)

        # 3. Filtrado de la posición
        x_hat = alpha * x_val + (1.0 - alpha) * self.x_prev
        self.x_prev = x_hat
        if not es_arreglo:
            return float(x_hat)
        return x_hat

# Altura de cada medición, como fracción del largo del torso
# (0 = base del cuello, 1 = línea de caderas).
# Añadimos axila, bajo busto y cadera alta para seguir las curvas anatómicas reales.
NIVELES_MEDICION = {
    "axila": 0.20,
    "pecho": 0.30,
    "bajo_busto": 0.46,
    "cintura": 0.62,
    "cadera_alta": 0.82,
    "cadera": 1.00,
}

# Rango razonable de cada MEDIO ancho, en relación con el ancho entre hombros.
# Si la máscara da algo fuera de este rango (ruido, ropa muy suelta, objeto
# detrás), se recorta para no deformar la prenda de forma absurda.
LIMITES_MEDIO_ANCHO = {
    "axila": (0.28, 0.75),
    "pecho": (0.28, 0.72),
    "bajo_busto": (0.24, 0.74),
    "cintura": (0.22, 0.80),
    "cadera_alta": (0.24, 0.90),
    "cadera": (0.26, 0.95),
}


def _distancia_a_segmento(puntos, a, b):
    """Distancia de cada punto (N, 2) al segmento a-b."""
    ab = b - a
    largo2 = float(ab @ ab)
    if largo2 < 1e-6:
        return np.linalg.norm(puntos - a, axis=1)
    t = np.clip(((puntos - a) @ ab) / largo2, 0.0, 1.0)
    proyeccion = a + t[:, None] * ab
    return np.linalg.norm(puntos - proyeccion, axis=1)


def _escanear_borde(mascara, origen, direccion, largo_max, brazos=(), radio_brazo=0.0, paso=1.5):
    """
    Camina desde 'origen' en 'direccion' hasta salir de la silueta o tocar un brazo.
    Devuelve la distancia recorrida (en píxeles) o None si no se pudo medir.

    Detenerse al tocar el brazo es importante: con los brazos al costado del cuerpo
    la máscara une brazo y torso, y sin este control mediríamos "torso + brazo".
    """
    alto, ancho = mascara.shape[:2]
    ts = np.arange(0.0, largo_max, paso, dtype=np.float32)
    puntos = origen[None, :] + ts[:, None] * direccion[None, :]
    xs = np.round(puntos[:, 0]).astype(np.int32)
    ys = np.round(puntos[:, 1]).astype(np.int32)

    dentro_imagen = (xs >= 0) & (xs < ancho) & (ys >= 0) & (ys < alto)
    en_cuerpo = np.zeros(len(ts), dtype=bool)
    en_cuerpo[dentro_imagen] = mascara[ys[dentro_imagen], xs[dentro_imagen]] > 0.5

    toca_brazo = np.zeros(len(ts), dtype=bool)
    for a, b in brazos:
        toca_brazo |= _distancia_a_segmento(puntos, a, b) < radio_brazo

    valido = en_cuerpo & ~toca_brazo
    if len(valido) < 3 or not valido[0]:
        return None  # el centro del torso no está dentro de la silueta

    # Primer lugar donde hay dos muestras seguidas fuera (ignora un píxel suelto de ruido)
    fuera = ~valido
    dos_fuera = fuera[:-1] & fuera[1:]
    indices = np.where(dos_fuera)[0]
    if len(indices) == 0:
        return None  # no encontramos el borde: medida poco confiable
    return float(ts[indices[0]])


def _direccion_lateral(info):
    """Vector perpendicular al eje del torso que apunta hacia la derecha de la pantalla."""
    u_torso = info["u_torso"]
    lateral = np.array([-u_torso[1], u_torso[0]], dtype=np.float32)
    if float(lateral @ info["u_sh"]) < 0:
        lateral = -lateral
    return lateral / max(1e-6, float(np.linalg.norm(lateral)))


def medir_silueta(mascara, info):
    """
    Mide el cuerpo usando la máscara de segmentación y los puntos del torso.
    Devuelve un diccionario con medios anchos (izquierda y derecha de pantalla)
    en píxeles para pecho, cintura y cadera, y el grosor del brazo.
    Las medidas que no se pueden obtener quedan en None.
    """
    medidas = {}
    if mascara is None or info is None:
        return medidas

    d_sh = float(info["dist_sh"])
    d_torso = float(info["dist_torso"])
    p_neck = info["p_neck_base"]
    u_torso = info["u_torso"]
    lateral = _direccion_lateral(info)

    brazos = [
        (info["p_sh_l"], info["p_elb_l"]), (info["p_elb_l"], info["p_wri_l"]),
        (info["p_sh_r"], info["p_elb_r"]), (info["p_elb_r"], info["p_wri_r"]),
    ]
    radio_brazo = d_sh * 0.09

    for nivel, fraccion in NIVELES_MEDICION.items():
        if nivel == "cadera" and not info.get("caderas_visibles", True):
            medidas[f"{nivel}_l"] = medidas[f"{nivel}_r"] = None
            continue
        centro = p_neck + u_torso * (d_torso * fraccion)
        minimo, maximo = LIMITES_MEDIO_ANCHO[nivel]
        for lado, direccion in (("l", -lateral), ("r", lateral)):
            dist = _escanear_borde(mascara, centro, direccion, d_sh * 1.3, brazos, radio_brazo)
            if dist is not None:
                dist = float(np.clip(dist, minimo * d_sh, maximo * d_sh))
            medidas[f"{nivel}_{lado}"] = dist
        medidas[f"{nivel}_centro"] = centro

    # Grosor del brazo: se mide hacia AFUERA del cuerpo a mitad del brazo superior
    grosores = []
    for hombro, codo, signo in ((info["p_sh_l"], info["p_elb_l"], -1.0),
                                (info["p_sh_r"], info["p_elb_r"], 1.0)):
        eje = codo - hombro
        largo = float(np.linalg.norm(eje))
        if largo < d_sh * 0.25:
            continue
        eje = eje / largo
        perpendicular = np.array([-eje[1], eje[0]], dtype=np.float32)
        if float(perpendicular @ lateral) * signo < 0:
            perpendicular = -perpendicular  # que apunte hacia afuera
        punto = hombro + eje * (largo * 0.45)
        radio = _escanear_borde(mascara, punto, perpendicular, d_sh * 0.40)
        if radio is not None:
            grosores.append(radio * 2.0)
    medidas["brazo"] = float(np.clip(np.mean(grosores), d_sh * 0.14, d_sh * 0.46)) if grosores else None

    return medidas


def ancho_total(medidas, nivel):
    """Ancho total a un nivel (izquierda + derecha), o None."""
    izq, der = medidas.get(f"{nivel}_l"), medidas.get(f"{nivel}_r")
    if izq is None and der is None:
        return None
    if izq is None:
        izq = der
    if der is None:
        der = izq
    return izq + der


def estimar_figura(medidas):
    """
    Estima el tipo de figura a partir de las proporciones pecho / cintura / cadera.
    Es una estimación visual de frente (no una medición en centímetros).
    """
    pecho = ancho_total(medidas, "pecho")
    cintura = ancho_total(medidas, "cintura")
    cadera = ancho_total(medidas, "cadera")
    if pecho is None or cintura is None or cadera is None:
        return "Analizando figura..."

    if cintura >= 0.97 * max(pecho, cadera):
        return "Ovalada (cintura amplia)"
    if cadera > pecho * 1.08:
        return "Triangulo / Pera (cadera mas ancha)"
    if pecho > cadera * 1.08:
        return "Triangulo invertido (pecho mas ancho)"
    if cintura < 0.82 * min(pecho, cadera):
        return "Reloj de arena (cintura marcada)"
    return "Rectangulo (medidas parejas)"


class MedidasSuavizadas:
    """
    Suavizado adaptativo de las medidas mediante filtro One Euro:
    elimina el temblor / ruido cuando la persona está quieta y responde
    instantáneamente cuando se mueve, evitando desfases o 'respiración' de la prenda.
    Si en un cuadro una medida falla, se conserva la anterior.
    """

    def __init__(self, alpha=0.20):
        self.alpha = alpha
        self.filtros = {}
        self.valores = {}

    def reiniciar(self):
        self.filtros = {}
        self.valores = {}

    def actualizar(self, medidas_nuevas, timestamp_s=None):
        for clave, valor in medidas_nuevas.items():
            if valor is None:
                continue
            if clave not in self.filtros:
                self.filtros[clave] = OneEuroFilter(
                    x0=valor,
                    min_cutoff=0.8,
                    beta=0.04,
                    d_cutoff=1.0
                )
                self.valores[clave] = np.array(valor, dtype=np.float32) if isinstance(valor, np.ndarray) else float(valor)
            else:
                filtrado = self.filtros[clave].filter(valor, timestamp_s)
                self.valores[clave] = filtrado

        # Las claves que nunca se midieron quedan en None para que el resto del código lo sepa
        for clave in medidas_nuevas:
            self.valores.setdefault(clave, None)
        return dict(self.valores)
