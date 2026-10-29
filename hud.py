# ==========================================================
# PROYECTO: PROBADOR VIRTUAL INTELIGENTE - BOUTIQUE FEMENINA
# MÓDULO: HUD (textos y medidas dibujados sobre la cámara)
# ==========================================================

import cv2
import numpy as np

from catalogo import obtener_medidas_talle
from body_measure import ancho_total


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


# Botón para volver a la galería (abajo a la derecha, en la barra de controles)
TEXTO_BOTON_GALERIA = "<  Volver a la galeria"
ANCHO_BOTON_GALERIA = 230
ALTO_BOTON_GALERIA = 34


def rectangulo_boton_galeria(ancho, alto):
    """(x0, y0, x1, y1) del botón 'Volver a la galería' en una imagen de ese tamaño."""
    x1, y1 = ancho - 14, alto - 6
    return x1 - ANCHO_BOTON_GALERIA, y1 - ALTO_BOTON_GALERIA, x1, y1


def punto_en_boton_galeria(x, y, ancho, alto):
    x0, y0, x1, y1 = rectangulo_boton_galeria(ancho, alto)
    return x0 <= x <= x1 and y0 <= y <= y1


# Botón para comprar la prenda que se está probando (a la izquierda del de la galería)
TEXTO_BOTON_COMPRAR = "Comprar  [B]"
ANCHO_BOTON_COMPRAR = 150


def rectangulo_boton_comprar(ancho, alto):
    """(x0, y0, x1, y1) del botón 'Comprar' en una imagen de ese tamaño."""
    x0_galeria, y0, _, y1 = rectangulo_boton_galeria(ancho, alto)
    x1 = x0_galeria - 10
    return x1 - ANCHO_BOTON_COMPRAR, y0, x1, y1


def punto_en_boton_comprar(x, y, ancho, alto):
    x0, y0, x1, y1 = rectangulo_boton_comprar(ancho, alto)
    return x0 <= x <= x1 and y0 <= y <= y1


def dibujar_boton_comprar(frame, resaltado=False):
    """Botón dorado (como 'Confirmar compra' en la galería)."""
    alto, ancho = frame.shape[:2]
    x0, y0, x1, y1 = rectangulo_boton_comprar(ancho, alto)
    color = (63, 133, 168) if resaltado else (90, 160, 201)  # COLOR_GOLD(_HOVER) en BGR
    cv2.rectangle(frame, (x0, y0), (x1, y1), color, -1, cv2.LINE_AA)
    cv2.rectangle(frame, (x0, y0), (x1, y1), (255, 255, 255), 1, cv2.LINE_AA)
    (w, h), _ = cv2.getTextSize(TEXTO_BOTON_COMPRAR, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
    cv2.putText(frame, TEXTO_BOTON_COMPRAR, (x0 + (ANCHO_BOTON_COMPRAR - w) // 2, y0 + (y1 - y0 + h) // 2),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)


def dibujar_boton_galeria(frame, resaltado=False):
    """Botón rosa con el texto centrado; más intenso cuando el mouse está encima."""
    alto, ancho = frame.shape[:2]
    x0, y0, x1, y1 = rectangulo_boton_galeria(ancho, alto)
    color = (109, 117, 197) if resaltado else (128, 136, 217)  # COLOR_ROSE(_HOVER) en BGR
    cv2.rectangle(frame, (x0, y0), (x1, y1), color, -1, cv2.LINE_AA)
    cv2.rectangle(frame, (x0, y0), (x1, y1), (255, 255, 255), 1, cv2.LINE_AA)
    (w, h), _ = cv2.getTextSize(TEXTO_BOTON_GALERIA, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
    cv2.putText(frame, TEXTO_BOTON_GALERIA, (x0 + (ANCHO_BOTON_GALERIA - w) // 2, y0 + (ALTO_BOTON_GALERIA + h) // 2),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)


def dibujar_diagnostico(frame, info_anatomica, deteccion):
    """
    Modo diagnóstico (tecla I): los puntos que entrega MediaPipe (círculo vacío, con su
    confianza) y los que usa el probador después de corregirlos (círculo lleno), más el
    eje del torso. Sirve para ver por qué una prenda queda torcida o corrida.
    """
    if deteccion:
        for clave in ("nose", "sh_left", "sh_right", "elb_left", "elb_right", "hip_left", "hip_right"):
            p = deteccion["p_raw"].get(clave)
            if p is None:
                continue
            v = float(deteccion["vis"].get(clave, 0.0))
            color = (80, 220, 80) if v >= 0.5 else (60, 60, 230)
            x, y = int(p[0]), int(p[1])
            cv2.circle(frame, (x, y), 7, color, 2, cv2.LINE_AA)
            cv2.putText(frame, f"{clave} {v:.2f}", (x + 9, y - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.38, color, 1, cv2.LINE_AA)
    if info_anatomica:
        for clave in ("p_sh_l", "p_sh_r", "p_hip_l", "p_hip_r", "p_neck_base"):
            p = info_anatomica.get(clave)
            if p is not None:
                cv2.circle(frame, (int(p[0]), int(p[1])), 4, (255, 200, 60), -1, cv2.LINE_AA)
        cuello = info_anatomica["p_neck_base"]
        cadera = cuello + info_anatomica["u_torso"] * float(info_anatomica["dist_torso"])
        cv2.line(frame, tuple(np.int32(cuello)), tuple(np.int32(cadera)), (255, 200, 60), 2, cv2.LINE_AA)
        cv2.line(frame, tuple(np.int32(info_anatomica["p_sh_l"])), tuple(np.int32(info_anatomica["p_sh_r"])),
                 (255, 200, 60), 2, cv2.LINE_AA)


NOMBRES_ORIENTACION = {"frente": "De frente", "girada": "Girada", "perfil": "De perfil", "espalda": "De espaldas"}


def dibujar_hud_probador(frame, prenda_info, factor_escala, mensaje_notif="", modo_malla=True,
                         talle="M", figura="", fps=None, recorte=True, orientacion=None,
                         boton_resaltado=False, color="", aviso_encuadre="", comprar_resaltado=False):
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
    precio_formateado = f"${int(round(float(prenda_info['precio']))):,}".replace(',', '.')
    texto_prenda = f"{prenda_info['nombre']}" + (f" ({color})" if color else "") + f"   |   {precio_formateado}"
    cv2.putText(frame, texto_prenda, (25, 52), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (210, 180, 120), 1, cv2.LINE_AA)

    # Talle elegido, sus medidas y figura estimada
    meds_t = obtener_medidas_talle(prenda_info, talle)
    calce_txt = prenda_info.get('calce', 'regular').capitalize()
    texto_talle = f"Talle: {talle} (Pecho: {meds_t['pecho']}cm · Cintura: {meds_t['cintura']}cm)   |   Calce: {calce_txt}"
    if figura:
        texto_talle += f"   |   Figura: {figura}"
    cv2.putText(frame, texto_talle, (ancho - 740, 52), cv2.FONT_HERSHEY_SIMPLEX, 0.46, (200, 235, 200), 1, cv2.LINE_AA)

    # Controles inferiores limpios y claros
    controles = "[G] Galeria | [C] Foto | [1..9 / N] Prenda | [T] Talle | [K] Color | [V] Medidas | [I] Diagnostico | [R] Recorte | [M] Modo | [+/-] Calce | [Q] Cerrar"
    cv2.putText(frame, controles, (25, alto - 18), cv2.FONT_HERSHEY_SIMPLEX, 0.46, (220, 220, 220), 1, cv2.LINE_AA)
    dibujar_boton_comprar(frame, comprar_resaltado)
    dibujar_boton_galeria(frame, boton_resaltado)

    # Guía de encuadre: cómo pararse para que la prenda se ajuste bien
    if aviso_encuadre:
        (w_txt, h_txt), _ = cv2.getTextSize(aviso_encuadre, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
        x0 = (ancho - w_txt) // 2 - 18
        y0 = 82
        zona = frame[y0:y0 + h_txt + 26, max(0, x0):min(ancho, x0 + w_txt + 36)]
        zona[:] = (zona.astype(np.float32) * 0.35 + np.array([40, 38, 36], np.float32) * 0.65).astype(np.uint8)
        cv2.putText(frame, aviso_encuadre, (x0 + 18, y0 + h_txt + 12), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                    (90, 210, 255), 2, cv2.LINE_AA)

    # Notificación temporal en el centro (por ejemplo al sacar una foto o cambiar prenda/talle)
    if mensaje_notif:
        cv2.putText(frame, mensaje_notif, (ancho // 2 - 250, alto - 65), cv2.FONT_HERSHEY_DUPLEX, 0.72, (80, 255, 140), 2, cv2.LINE_AA)
